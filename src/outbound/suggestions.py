"""Plays suggested from call learnings (docs/PLAY-SUGGESTIONS.md, DECISIONS 47).

Code decides when a pattern is clear; the model only drafts the play once it is. A theme T (a reason to buy or a
competitor) is a pattern in segment S (the signal type that started the account's play) when, over the accounts with
learnings from call notes in the last 90 days:

  1. T is heard at 5 or more accounts in S;
  2. the notes saying it there were written by 2 or more different SDRs;
  3. T is more common in S than among the other accounts: a one-sided Fisher exact test on the 2x2 table (in S or
     not, against T heard or not) passes at 0.05 divided by the number of (theme, segment) pairs looked at in the same
     check (Bonferroni). A pair is looked at when its theme was heard at one account or more in that segment;
  4. no play of any status was made from T;
  5. no suggestion for T is open or was dismissed; one set aside as "not now" comes back only when T is heard at 1.5
     times as many accounts in S as when it was set aside, and the rule passes again.

An open suggestion lapses when a check no longer finds its pattern. A person decides everything else: GTM turns a
suggestion into a draft play; a manager or GTM sets it aside or dismisses its theme for good."""
from __future__ import annotations

import logging
import math

from . import alerts, audit, copy_gate, db, jobs, llm, stats, themes
from .db import J
from .outreach import PRIVATE_SIGNALS

log = logging.getLogger("outbound.suggestions")

# The thresholds, in one place. Shown read-only on Settings.
RULE = {"min_accounts": 5, "min_sdrs": 2, "window_days": 90, "alpha": 0.05, "regrow": 1.5}
PLAY_KINDS = ("reason_to_buy", "competitor")


# ---------------------------------------------------------------- the rule

def _window(cur) -> list[dict]:
    """Every learning from a call note in the window, with its account, its SDR and its segment."""
    return db.all(cur, """
        select l.id, l.theme_id, t.kind as theme_kind, l.signal_type, m.account_id,
               case when u.role = 'sdr' then cn.written_by end as sdr
        from learnings l join call_notes cn on cn.id = l.call_note_id join meetings m on m.id = cn.meeting_id
        left join learning_themes t on t.id = l.theme_id left join users u on u.id = cn.written_by
        where cn.created_at > app_now() - make_interval(days => %s) order by l.id""", RULE["window_days"])


def evaluate(rows: list[dict], *, rule: dict | None = None) -> dict[tuple[int, str], dict]:
    """Every (theme, segment) pair looked at, with its counts, its p and whether it passes rules 1 to 3.
    Pure: the rows are what `_window` returns, so tests can hand it a table."""
    rule = rule or RULE
    accounts = {r["account_id"] for r in rows}
    segment: dict[str, set[int]] = {}
    heard: dict[int, set[int]] = {}
    for r in rows:
        if r["signal_type"]:
            segment.setdefault(r["signal_type"], set()).add(r["account_id"])
        if r["theme_id"] is not None and r["theme_kind"] in PLAY_KINDS:
            heard.setdefault(r["theme_id"], set()).add(r["account_id"])
    pairs: dict[tuple[int, str], dict] = {}
    total = len(accounts)
    for t, at in heard.items():
        for s, inside in segment.items():
            k = len(at & inside)
            if k == 0:
                continue
            n_in, m = len(inside), len(at)
            sdrs = {r["sdr"] for r in rows if r["theme_id"] == t and r["account_id"] in inside and r["sdr"] is not None}
            pairs[(t, s)] = {"theme_id": t, "segment": s, "accounts": k, "segment_accounts": n_in,
                             "elsewhere": m - k, "elsewhere_accounts": total - n_in, "total_accounts": total,
                             "sdrs": len(sdrs), "p": stats.fisher_greater(k, n_in, m, total)}
    tested = len(pairs)
    alpha = rule["alpha"] / tested if tested else rule["alpha"]
    for e in pairs.values():
        rate_in = e["accounts"] / e["segment_accounts"]
        rate_out = e["elsewhere"] / e["elsewhere_accounts"] if e["elsewhere_accounts"] else 0.0
        e.update(pairs_tested=tested, alpha=alpha, rate=rate_in, rate_elsewhere=rate_out,
                 window_days=rule["window_days"],
                 passes=(e["accounts"] >= rule["min_accounts"] and e["sdrs"] >= rule["min_sdrs"]
                         and rate_in > rate_out and e["p"] < alpha))
    return pairs


def _blocked(cur, theme_id: int, segment: str, accounts: int) -> str | None:
    """Rules 4 and 5: why a passing pattern still may not open a suggestion, or None. A theme set aside comes back
    only through the segment it was set aside in, once it is heard there at 1.5 times as many accounts."""
    if db.val(cur, "select exists (select 1 from plays where suggested_from = %s)", theme_id):
        return "a play was made from it"
    if db.val(cur, "select exists (select 1 from play_suggestions where theme_id = %s and status in ('open', 'dismissed'))",
              theme_id):
        return "open or dismissed"
    last = db.one(cur, """select segment_signal_type, accounts_at_decision from play_suggestions
                          where theme_id = %s and status = 'not_now' order by decided_at desc limit 1""", theme_id)
    if last and (segment != last["segment_signal_type"]
                 or accounts < math.ceil(RULE["regrow"] * (last["accounts_at_decision"] or 0))):
        return "set aside, and not yet heard at 1.5 times as many accounts as when it was set aside"
    return None


@jobs.handler("check_patterns")
def check_patterns(cur, payload: dict) -> None:
    """Refresh and lapse in this job's transaction; each new suggestion is drafted by its own job, so no row is held
    while the model writes."""
    for tid, seg in check(cur):
        jobs.enqueue(cur, "open_suggestion", {"theme_id": tid, "segment": seg}, dedupe_key=f"open_suggestion:{tid}")


@jobs.handler("open_suggestion")
def open_suggestion_job(cur, payload: dict) -> None:
    open_suggestion(cur, payload["theme_id"], payload["segment"])


def check(cur) -> list[tuple[int, str]]:
    """Lapse open suggestions whose pattern went away and refresh the numbers of the rest. Returns the patterns that may
    open a new suggestion, as (theme, segment). Short: no model call happens here."""
    db.run(cur, "select pg_advisory_xact_lock(7342047)")  # one check at a time
    pairs = evaluate(_window(cur))
    for s in db.all(cur, "select id, theme_id, segment_signal_type from play_suggestions where status = 'open' order by id for update"):
        e = pairs.get((s["theme_id"], s["segment_signal_type"]))
        if e and e["passes"]:
            db.run(cur, "update play_suggestions set evidence = %s where id = %s", J(_evidence(e)), s["id"])
            continue
        db.run(cur, "update play_suggestions set status = 'lapsed', decided_at = app_now() where id = %s", s["id"])
        audit.log(cur, "desk", "suggestion_lapsed", "play_suggestion", s["id"],
                  {"theme_id": s["theme_id"], "segment": s["segment_signal_type"], **(_evidence(e) if e else {})})
    out: dict[int, str] = {}
    for e in sorted((e for e in pairs.values() if e["passes"]), key=lambda e: e["p"]):
        if e["theme_id"] not in out and not _blocked(cur, e["theme_id"], e["segment"], e["accounts"]):
            out[e["theme_id"]] = e["segment"]
    return list(out.items())


def open_suggestion(cur, theme_id: int, segment: str) -> int | None:
    """Draft and open one suggestion. The model writes while nothing is locked; the rule and rules 4 and 5 are checked
    again just before the insert, under a lock per theme, and a second open one for the theme is refused by the database."""
    e = pair_now(cur, theme_id, segment)
    if not e or not e["passes"] or _blocked(cur, theme_id, segment, e["accounts"]):
        return None
    draft = draft_for(cur, theme_id, segment)
    if draft is None:
        return None
    db.run(cur, "select pg_advisory_xact_lock(hashtext('open_suggestion:' || %s))", theme_id)
    e = pair_now(cur, theme_id, segment)
    if not e or not e["passes"] or _blocked(cur, theme_id, segment, e["accounts"]):
        return None
    sid = db.val(cur, """insert into play_suggestions (theme_id, segment_signal_type, evidence, draft) values (%s, %s, %s, %s)
                         on conflict (theme_id) where status = 'open' do nothing returning id""",
                 theme_id, segment, J(_evidence(e)), J(draft))
    if sid:
        audit.log(cur, "desk", "suggestion_opened", "play_suggestion", sid, {"theme_id": theme_id, "segment": segment,
                                                                            **_evidence(e)})
    return sid


def sweep() -> dict:
    """A check, then each new suggestion in its own transaction. For the backfill and the demo."""
    with db.tx() as cur:
        todo = check(cur)
    opened = 0
    for tid, seg in todo:
        with db.tx() as cur:
            opened += open_suggestion(cur, tid, seg) is not None
    return {"candidates": len(todo), "opened": opened}


def _evidence(e: dict) -> dict:
    """What a suggestion keeps of its pattern: counts, rates, p and pairs tested. Never a quote or a name."""
    return {k: e[k] for k in ("accounts", "segment_accounts", "elsewhere", "elsewhere_accounts", "total_accounts", "sdrs",
                              "rate", "rate_elsewhere", "p", "alpha", "pairs_tested", "window_days")}


def pair_now(cur, theme_id: int, segment: str) -> dict | None:
    return evaluate(_window(cur)).get((theme_id, segment))


# ---------------------------------------------------------------- drafting the play

def catalog(cur, segment: str | None = None) -> dict:
    """What a play may be built from: signal types that can start a play (enabled, positive weight) and personas.
    Private signals (DECISIONS 7) are left out, except the pattern's own segment: a play they start can never say
    what was seen, so a suggestion does not add them on its own."""
    return without_private({"signal_types": db.all(cur, "select key, label from signal_types where enabled and weight > 0 order by key"),
                            "personas": db.all(cur, "select key, label from personas order by key")}, segment)


def without_private(cat: dict, segment: str | None) -> dict:
    return {**cat, "signal_types": [t for t in cat["signal_types"] if t["key"] not in PRIVATE_SIGNALS or t["key"] == segment]}


def check_draft(cur, d: dict, segment: str, cat: dict) -> list[str]:
    """Code's checks on a drafted play, as failures the model can act on. Empty when it can be offered."""
    fails = []
    types = {t["key"] for t in cat["signal_types"]}
    personas = {p["key"] for p in cat["personas"]}
    trig = (d.get("trigger") or {}).get("any_of") or []
    if bad := [t for t in trig if t not in types]:
        fails.append(f"Trigger signals not in the catalog: {', '.join(bad)}.")
    if segment not in trig:
        fails.append(f"The trigger must include {segment}.")
    if not 1 <= len(trig) <= 8:
        fails.append("Use one to eight trigger signals.")
    pk = d.get("personas") or []
    if bad := [p for p in pk if p not in personas]:
        fails.append(f"Personas not in the catalog: {', '.join(bad)}.")
    if not 1 <= len(pk) <= 4 or len(set(pk)) != len(pk):
        fails.append("Name one to four different personas.")
    for field, lo, hi in (("name", 3, 80), ("hypothesis", 10, 400), ("angle", 10, 400)):
        n = len((d.get(field) or "").strip())
        if not lo <= n <= hi:
            fails.append(f"The {field} is {n} characters; keep it between {lo} and {hi}.")
    text = " ".join(d.get(f) or "" for f in ("name", "hypothesis", "angle"))
    if any(x in text for x in copy_gate.DASHES):
        fails.append("No long dashes.")
    angle = (d.get("angle") or "").lower()
    if any(t in PRIVATE_SIGNALS for t in trig) and "without naming" not in angle:
        # The same rule the shipped plays keep (tests/test_play_catalog.py): a play a private signal starts says how
        # it opens without naming what was seen.
        fails.append("A trigger is a private signal (a visit, a sign-up, research, an event or social engagement), so the "
                     "angle must say how to open without naming what we saw, in those words: 'without naming'.")
    if banned := [b for b in copy_gate.BANNED if b in angle]:
        fails.append(f"The angle uses a banned phrase: {banned[0]}.")
    if cur is not None:
        for name in themes.names_in(cur, text, companies=True):
            fails.append(f"It names {name}; a play never names a customer, a person or a company.")
    return fails


def draft(cur, *, theme: dict, segment: dict, objections: list[str], cat: dict) -> tuple[dict | None, list[str]]:
    """Ask for a play built on the pattern only: never quotes or account names. One rewrite with the failures named."""
    payload: dict = {"theme": theme, "segment": segment, "objections": objections,
                     "catalog": {"signal_types": [{"key": t["key"], "label": t["label"]} for t in cat["signal_types"]],
                                 "personas": [{"key": p["key"], "label": p["label"]} for p in cat["personas"]]}}
    fails: list[str] = []
    for _ in (1, 2):
        out = llm.run(cur, "draft_play", payload)
        fails = check_draft(cur, out, segment["key"], cat)
        if not fails:
            return out, []
        payload = {**payload, "failures": fails}
    return None, fails


def _objections(cur, theme_id: int, segment: str) -> list[dict]:
    """Objections and reasons not to buy heard at the accounts behind the pattern, by how many of them said each."""
    return db.all(cur, """
        with behind as (
          select distinct m.account_id from learnings l join call_notes cn on cn.id = l.call_note_id
          join meetings m on m.id = cn.meeting_id
          where l.theme_id = %s and cn.created_at > app_now() - make_interval(days => %s)
            and m.account_id in (select m2.account_id from learnings l2 join call_notes c2 on c2.id = l2.call_note_id
                                 join meetings m2 on m2.id = c2.meeting_id where l2.signal_type = %s
                                 and c2.created_at > app_now() - make_interval(days => %s)))
        select t.id, t.kind, t.label, count(distinct m.account_id) as accounts
        from learnings l join learning_themes t on t.id = l.theme_id join call_notes cn on cn.id = l.call_note_id
        join meetings m on m.id = cn.meeting_id
        where t.kind in ('objection', 'reason_not') and m.account_id in (select account_id from behind)
          and cn.created_at > app_now() - make_interval(days => %s)
        group by t.id, t.kind, t.label order by accounts desc, t.label limit 8""",
        theme_id, RULE["window_days"], segment, RULE["window_days"], RULE["window_days"])


def draft_for(cur, theme_id: int, segment: str) -> dict | None:
    t = db.one(cur, "select kind, label from learning_themes where id = %s", theme_id)
    s = db.one(cur, "select key, label, because from signal_types where key = %s", segment)
    out, fails = draft(cur, theme={"kind": t["kind"], "label": t["label"]}, segment=dict(s),
                       objections=[o["label"] for o in _objections(cur, theme_id, segment)], cat=catalog(cur, segment))
    if out is None:
        alerts.raise_alert(cur, kind="suggestion_dropped", severity="info", channel="#outbound-ops",
                           title="A play suggestion was dropped: its draft failed the checks twice",
                           body=" ".join(fails)[:400], object_kind="learning_theme", object_id=theme_id,
                           dedup_key=f"suggestion_dropped:{theme_id}:{db.val(cur, "select to_char(app_now(), 'YYYY-MM-DD')")}")
    return out


# ---------------------------------------------------------------- what people see and decide

def open_list(cur) -> list[dict]:
    """Open suggestions, each saying whether its theme was set aside before and came back (rule 5)."""
    return db.all(cur, """
        select ps.id, ps.theme_id, t.label as theme, t.kind, ps.segment_signal_type as segment, st.label as segment_label,
               ps.evidence, ps.draft, ps.created_at,
               (select max(x.decided_at) from play_suggestions x where x.theme_id = ps.theme_id and x.status = 'not_now')
                 as set_aside_at
        from play_suggestions ps join learning_themes t on t.id = ps.theme_id
        join signal_types st on st.key = ps.segment_signal_type
        where ps.status = 'open' order by (ps.evidence->>'p')::float, ps.id""")


def set_aside_list(cur) -> list[dict]:
    """Themes a person set aside or dismissed, or whose pattern lapsed, and that are not back: the latest such suggestion
    per theme, while the theme has no open suggestion and no play. A suggestion that became a play is the play's history
    now, never a suggestion, so it is not here (Bryan, 2026-11-12)."""
    return db.all(cur, """
        select * from (
          select distinct on (ps.theme_id) ps.id, ps.theme_id, t.label as theme, t.kind, ps.segment_signal_type as segment,
                 st.label as segment_label, ps.status, ps.reason, ps.decided_at, u.name as decided_by_name
          from play_suggestions ps join learning_themes t on t.id = ps.theme_id
          join signal_types st on st.key = ps.segment_signal_type left join users u on u.id = ps.decided_by
          where ps.status in ('not_now', 'dismissed', 'lapsed')
            and not exists (select 1 from play_suggestions x where x.theme_id = ps.theme_id and x.status in ('open', 'drafted'))
            and not exists (select 1 from plays p where p.suggested_from = ps.theme_id)
          order by ps.theme_id, ps.decided_at desc, ps.id desc) s
        order by decided_at desc, id desc""")


def one(cur, suggestion_id: int) -> dict | None:
    s = db.one(cur, """
        select ps.*, t.label as theme, t.kind, st.label as segment_label, st.because as segment_because,
               u.name as decided_by_name
        from play_suggestions ps left join learning_themes t on t.id = ps.theme_id
        join signal_types st on st.key = ps.segment_signal_type left join users u on u.id = ps.decided_by
        where ps.id = %s""", suggestion_id)
    if s is None:
        return None
    if s["theme_id"] is None:
        s["quotes"], s["objections"] = [], []
        return s
    # The quotes are read live from the learnings, never copied into the suggestion, so an erasure removes them here too.
    # One quote per account (its latest), so the list counts accounts the way the pattern does.
    s["quotes"] = db.all(cur, """
        select * from (
        select distinct on (m.account_id) l.id, l.quote, l.text, cn.created_at, cn.meeting_id, m.account_id,
               a.name as company, a.primary_domain, u.name as sdr
        from learnings l join call_notes cn on cn.id = l.call_note_id join meetings m on m.id = cn.meeting_id
        join accounts a on a.id = m.account_id left join users u on u.id = cn.written_by
        where l.theme_id = %s and cn.created_at > app_now() - make_interval(days => %s)
          and m.account_id in (select m2.account_id from learnings l2 join call_notes c2 on c2.id = l2.call_note_id
                               join meetings m2 on m2.id = c2.meeting_id where l2.signal_type = %s
                               and c2.created_at > app_now() - make_interval(days => %s))
        order by m.account_id, cn.created_at desc) q order by created_at desc""",
        s["theme_id"], RULE["window_days"], s["segment_signal_type"], RULE["window_days"])
    s["objections"] = _objections(cur, s["theme_id"], s["segment_signal_type"])
    names = {r["key"]: r["label"] for r in db.all(cur, "select key, label from signal_types")}
    personas = {r["key"]: r["label"] for r in db.all(cur, "select key, label from personas")}
    s["draft_labels"] = {"signals": {k: names.get(k, k) for k in s["draft"]["trigger"]["any_of"]},
                         "personas": {k: personas.get(k, k) for k in s["draft"]["personas"]}}
    s["rule"] = RULE
    return s


def decide(cur, suggestion_id: int, *, decision: str, reason: str | None, user_id: int) -> None:
    """Not now (with a reason) or no (dismisses the theme for good). Raises LookupError or ValueError."""
    s = db.one(cur, "select * from play_suggestions where id = %s for update", suggestion_id)
    if s is None:
        raise LookupError("No such suggestion.")
    if s["status"] != "open":
        raise ValueError("This suggestion was already decided.")
    if decision == "not_now" and not (reason or "").strip():
        raise ValueError("Say why not now, so the next person knows.")
    e = pair_now(cur, s["theme_id"], s["segment_signal_type"])
    db.run(cur, """update play_suggestions set status = %s, reason = %s, decided_by = %s, decided_at = app_now(),
                   accounts_at_decision = %s where id = %s""", decision, (reason or "").strip() or None, user_id,
           e["accounts"] if e else s["evidence"].get("accounts", 0), suggestion_id)
    audit.log(cur, "person", f"suggestion_{decision}", "play_suggestion", suggestion_id,
              {"theme_id": s["theme_id"], "segment": s["segment_signal_type"], "reason": (reason or "").strip() or None},
              actor_id=user_id)


def drafted(cur, theme_id: int, play_id: int, user_id: int) -> int:
    """GTM saved a draft play from a suggestion: the open suggestion for its theme becomes drafted, with the play.
    Raises ValueError when there is none open, so a play never claims a suggestion that was decided otherwise."""
    s = db.one(cur, "select * from play_suggestions where theme_id = %s and status = 'open' for update", theme_id)
    if s is None:
        raise ValueError("That suggestion is no longer open.")
    e = pair_now(cur, theme_id, s["segment_signal_type"])
    db.run(cur, """update play_suggestions set status = 'drafted', play_id = %s, decided_by = %s, decided_at = app_now(),
                   accounts_at_decision = %s where id = %s""", play_id, user_id,
           e["accounts"] if e else s["evidence"].get("accounts", 0), s["id"])
    audit.log(cur, "person", "suggestion_drafted", "play_suggestion", s["id"],
              {"theme_id": theme_id, "segment": s["segment_signal_type"], "play_id": play_id}, actor_id=user_id)
    return s["id"]
