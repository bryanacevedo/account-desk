"""Plays: match an account to a play, draw the comparison group, propose to the owner, and move the account play
through its states (docs/SPEC.md 22.1 and 22.19). Every close writes the cooldown as a hold."""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from . import audit, db, gate, jobs, timeutil
from .db import J

log = logging.getLogger("outbound.plays")

OPEN = ("proposed", "accepted", "researching", "approving", "active", "engaged", "meeting")
CLOSED = ("converted", "lost", "stopped", "skipped", "expired", "held_out")

ALLOWED = {
    "proposed": {"accepted", "skipped", "expired", "stopped"},
    "accepted": {"researching", "stopped"},
    "researching": {"approving", "active", "stopped", "lost"},
    "approving": {"active", "stopped", "lost", "engaged"},
    "active": {"engaged", "meeting", "stopped", "lost", "converted"},
    "engaged": {"meeting", "stopped", "lost", "converted"},
    "meeting": {"engaged", "converted", "stopped", "lost"},
}

# Cooldown in days before the account can be proposed again, by close reason (22.19).
COOLDOWN = {"research_failed": 7, "nothing_approved": 30, "no_meeting": 60, "no_opportunity": 90,
            "sequence_finished": 90, "skipped": 30, "expired": 14, "not_interested": 180, "held_out": 90,
            "no_reachable_people": 60, "manual": 30, "play_paused": 14}


class BadTransition(Exception):
    pass


def holdout_draw(play_key: str, account_id: int, pct: int) -> bool:
    """Deterministic: the same play and account always land in the same group."""
    h = int(hashlib.sha256(f"{play_key}:{account_id}".encode()).hexdigest()[:8], 16)
    return (h % 100) < pct


def _trigger_signal(cur, play: dict, account_id: int) -> dict | None:
    trig = play["trigger"]
    return db.one(cur, """
        select s.id, s.type_key, s.observed_at, s.strength, s.evidence, s.person_id, t.label, t.because, t.weight
        from signals s join signal_types t on t.key = s.type_key
        where s.account_id = %s and s.status = 'matched' and s.type_key = any(%s)
          and s.strength >= %s and s.observed_at > app_now() - (%s || ' days')::interval
          and s.observed_at <= app_now()
        order by t.weight * s.strength desc, s.observed_at desc limit 1""",
        account_id, trig["any_of"], trig.get("min_strength", 0), trig.get("within_days", 30))


def match(cur, account_id: int) -> int | None:
    """Propose the best live play for this account, if any matches and the account gate allows it."""
    if gate.account_reasons(cur, account_id):
        return None
    score = db.one(cur, "select priority, fit, inputs from account_scores where account_id = %s", account_id)
    acc = db.one(cur, "select fit_tier, owner_id from accounts where id = %s", account_id)
    if not score or acc["fit_tier"] not in ("A", "B"):
        return None
    best = None
    for play in db.all(cur, "select * from plays where status = 'live' order by urgent desc, id"):
        trig = play["trigger"]
        if acc["fit_tier"] not in trig.get("fit_tiers", ["A", "B"]) or score["priority"] < trig.get("min_priority", 0):
            continue
        sig = _trigger_signal(cur, play, account_id)
        if sig is None:
            continue
        if play["key"] == "champion_moved":
            # The champion has to be confirmed at this company before we write to them as one.
            if not sig["person_id"] or not db.val(cur, "select account_id = %s from people where id = %s",
                                                  account_id, sig["person_id"]):
                continue
        rank = (play["urgent"], float(sig["weight"]) * float(sig["strength"]))
        if best is None or rank > best[0]:
            best = (rank, play, sig)
    if best is None:
        return None
    _, play, sig = best
    return propose(cur, account_id, play, sig, score)


def _pick_owner(cur, account_owner: int | None) -> int:
    if account_owner:
        return account_owner
    return db.val(cur, """select u.id from users u where u.role = 'sdr' and u.active
                          order by (select count(*) from account_plays ap where ap.owner_id = u.id
                                    and ap.state in ('proposed','accepted','researching','approving','active','engaged'))
                          , u.id limit 1""")


def propose(cur, account_id: int, play: dict, sig: dict, score: dict) -> int:
    contribs = score["inputs"]["signals"] if score.get("inputs") else []
    labels = {r["key"]: r["label"] for r in db.all(cur, "select key, label from signal_types")}
    top = []
    for c in sorted(contribs, key=lambda s: -(s["weight"] * s["strength"] * 0.5 ** (s["age_days"] / s["half_life"])))[:3]:
        top.append({"signal_id": c["id"], "label": labels.get(c["type"], c["type"])})
    why = {"signal_id": sig["id"], "type": sig["type_key"], "label": sig["label"], "because": sig["because"],
           "summary": sig["evidence"].get("summary"), "url": sig["evidence"].get("url"),
           "quote": sig["evidence"].get("quote"), "observed_at": sig["observed_at"].isoformat(),
           "priority": score["priority"], "top": top}
    owner = _pick_owner(cur, db.val(cur, "select owner_id from accounts where id = %s", account_id))
    held = holdout_draw(play["key"], account_id, play["holdout_pct"])
    if held:
        ap = db.val(cur, """insert into account_plays (account_id, play_id, trigger_signal_id, arm, state, why_now, owner_id,
                                                       closed_at, close_reason)
                            values (%s,%s,%s,'holdout','held_out',%s,%s,app_now(),'comparison group') returning id""",
                    account_id, play["id"], sig["id"], J(why), owner)
        _hold(cur, account_id, "held_out", COOLDOWN["held_out"])
        audit.log(cur, "desk", "held_out", "account_play", ap, {"play": play["key"]})
        return ap
    ap = db.val(cur, """insert into account_plays (account_id, play_id, trigger_signal_id, arm, state, why_now, owner_id)
                        values (%s,%s,%s,'treated','proposed',%s,%s) returning id""",
                account_id, play["id"], sig["id"], J(why), owner)
    audit.log(cur, "desk", "proposed", "account_play", ap, {"play": play["key"], "owner": owner})
    return ap


def _hold(cur, account_id: int, reason: str, days: int) -> None:
    if days <= 0:
        return
    db.run(cur, "insert into holds (account_id, reason, until, set_by) values (%s, %s, app_now() + (%s || ' days')::interval, 'desk')",
           account_id, reason.replace("_", " "), days)


def set_state(cur, ap_id: int, to: str, *, reason: str | None = None, actor: str = "desk",
              actor_id: int | None = None, cooldown_key: str | None = None) -> dict:
    ap = db.one(cur, "select * from account_plays where id = %s for update", ap_id)
    if ap["state"] == to:
        return ap
    if to not in ALLOWED.get(ap["state"], set()):
        raise BadTransition(f"account play {ap_id}: {ap['state']} -> {to}")
    closing = to in CLOSED
    db.run(cur, """update account_plays set state = %s, close_reason = coalesce(%s, close_reason),
                   closed_at = case when %s then app_now() else closed_at end,
                   decided_at = case when %s in ('accepted', 'skipped') then app_now() else decided_at end,
                   decided_by = case when %s in ('accepted', 'skipped') then %s else decided_by end
                   where id = %s""", to, reason if closing else None, closing, to, to, actor_id, ap_id)
    if closing:
        db.run(cur, """update enrollments set state = 'stopped', stop_reason = %s, next_at = null
                       where account_play_id = %s and state in ('pending', 'active', 'paused')""",
               "play_" + (reason or to), ap_id)
        db.run(cur, """update messages set status = 'cancelled' where enrollment_id in
                       (select id from enrollments where account_play_id = %s)
                       and status in ('draft', 'failed_gate', 'awaiting_approval', 'approved', 'scheduled')""", ap_id)
        db.run(cur, """update tasks set status = 'skipped', note = coalesce(note, 'Play closed')
                       where account_play_id = %s and status = 'open'""", ap_id)
        key = cooldown_key or reason or to
        _hold(cur, ap["account_id"], key, COOLDOWN.get(key, 30 if to != "converted" else 0))
    audit.log(cur, actor, f"play_{to}", "account_play", ap_id, {"from": ap["state"], "reason": reason}, actor_id=actor_id)
    return ap


def decide(cur, ap_id: int, *, accept: bool, user_id: int, reason: str | None = None) -> None:
    if accept:
        set_state(cur, ap_id, "accepted", actor="person", actor_id=user_id)
        jobs.enqueue(cur, "research", {"account_play_id": ap_id}, dedupe_key=f"research:{ap_id}")
    else:
        if not reason:
            raise ValueError("A skip needs a reason")
        set_state(cur, ap_id, "skipped", reason=reason, actor="person", actor_id=user_id, cooldown_key="skipped")


@jobs.handler("expire_proposals")
def expire_proposals(cur, payload: dict) -> None:
    ttl = int(db.val(cur, "select value from settings where key = 'proposal_ttl_days'") or 5)
    urgent_ttl = int(db.val(cur, "select value from settings where key = 'urgent_proposal_ttl_days'") or 1)
    timeutil.load_holidays(cur)
    now = db.val(cur, "select app_now()")
    for r in db.all(cur, """select ap.id, ap.proposed_at, p.urgent from account_plays ap join plays p on p.id = ap.play_id
                            where ap.state = 'proposed'"""):
        limit = urgent_ttl if r["urgent"] else ttl
        if timeutil.business_days_between(r["proposed_at"], now) > limit:
            set_state(cur, r["id"], "expired", reason="expired", cooldown_key="expired")


@jobs.handler("close_stale_plays")
def close_stale(cur, payload: dict) -> None:
    """The time-based exits of 22.19."""
    for r in db.all(cur, """select id from account_plays where state in ('accepted', 'researching')
                            and coalesce(decided_at, proposed_at) < app_now() - interval '4 days'"""):
        set_state(cur, r["id"], "stopped", reason="research_failed")
    for r in db.all(cur, """select ap.id from account_plays ap where ap.state = 'engaged' and not exists (
                              select 1 from replies r where r.account_id = ap.account_id and r.hot
                              and r.received_at > app_now() - interval '21 days')"""):
        set_state(cur, r["id"], "stopped", reason="no_meeting")
    for r in db.all(cur, """select ap.id from account_plays ap where ap.state = 'meeting' and not exists (
                              select 1 from meetings m where m.account_play_id = ap.id
                              and m.starts_at > app_now() - interval '120 days')"""):
        set_state(cur, r["id"], "stopped", reason="no_opportunity")
    for r in db.all(cur, """select ap.id from account_plays ap where ap.state = 'approving' and not exists (
                              select 1 from enrollments e where e.account_play_id = ap.id
                              and e.state in ('pending', 'active', 'paused'))"""):
        set_state(cur, r["id"], "stopped", reason="nothing_approved")
    for r in db.all(cur, """select ap.id from account_plays ap where ap.state = 'active' and not exists (
                              select 1 from enrollments e where e.account_play_id = ap.id
                              and e.state in ('pending', 'active', 'paused'))
                              and not exists (select 1 from tasks t where t.account_play_id = ap.id and t.status = 'open')"""):
        set_state(cur, r["id"], "stopped", reason="sequence_finished")
    # CRM turned the account into a customer or an open opportunity elsewhere.
    for r in db.all(cur, """select ap.id, a.lifecycle from account_plays ap join accounts a on a.id = ap.account_id
                            where ap.state in ('proposed','accepted','researching','approving','active','engaged')
                            and a.lifecycle in ('customer', 'open_opp')"""):
        set_state(cur, r["id"], "stopped",
                  reason="became_customer" if r["lifecycle"] == "customer" else "opportunity_elsewhere")


def cooldown_for(reason: str) -> timedelta:
    return timedelta(days=COOLDOWN.get(reason, 30))
