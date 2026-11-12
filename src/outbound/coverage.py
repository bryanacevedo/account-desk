"""Scenario coverage: how many times a built desk shows each thing the app can show.

Every count is read from what the desk recorded while it ran (its own tables and audit log), never from the simulator's
hidden truth, so a scenario counts only when the desk itself handled it. A scenario at zero means the demo cannot show
it; the fix is to make the simulation produce it honestly (README, "What is real and what is simulated"), never to
insert it by hand.

    python -m outbound coverage      prints the table for the database in DATABASE_URL
"""
from __future__ import annotations

from . import db

PLAY_STATES = ["proposed", "accepted", "researching", "approving", "active", "engaged", "meeting", "converted", "lost",
               "stopped", "skipped", "expired", "held_out"]
REPLY_LABELS = ["interested", "meeting_request", "question", "not_now", "not_interested", "referral", "left_company",
                "out_of_office", "unsubscribe", "wrong_person", "bounce", "auto_reply", "other"]
OPT_OUT_LANGUAGES = ["en", "de", "es", "fr", "pt"]
AUTONOMY = ["research", "draft", "supervised", "autonomous"]
REGION_OUTCOMES = {
    "allowed: cold email sent": """select count(*) from messages m join enrollments e on e.id = m.enrollment_id
        join people p on p.id = e.person_id join region_rules r on r.country = p.country
        where m.status = 'sent' and m.channel = 'email' and r.rule = 'allowed'""",
    "basis required: legitimate interest recorded": "select count(*) from contact_basis where basis like 'legitimate_interest:%%'",
    "consent required: not cold-emailed": """select count(*) from committee_gaps where reason like '%%needs consent%%'""",
    "blocked: not emailed in this country": "select count(*) from committee_gaps where reason = 'Not emailed in this country'",
    "no rule: needs a region rule first": "select count(*) from committee_gaps where reason like '%%needs a region rule first%%'",
}
SUGGESTION_STATUSES = ["open", "drafted", "not_now", "dismissed", "lapsed"]
GAP_KINDS = {
    "nobody with the role": "Nobody with this role found",
    "no email found": "No email address found",
    "catch-all address": "accepts every address",
    "address does not work": "Email address does not work",
    "needs consent": "needs consent",
    "needs a region rule": "needs a region rule first",
    "already in another sequence": "Already in another sequence",
}
TASK_KINDS = ["call", "linkedin_connect", "linkedin_message", "research", "reply", "referral", "review_reply"]
LEARNING_KINDS = ["objection", "competitor", "reason_to_buy", "reason_not", "quote"]


def _n(cur, sql: str, *args) -> int:
    return int(db.val(cur, sql, *args) or 0)


def scenarios(cur) -> list[dict]:
    """Every scenario as {"group", "scenario", "count"}, in the order the table prints them."""
    out: list[dict] = []

    def add(group: str, scenario: str, count: int) -> None:
        out.append({"group": group, "scenario": scenario, "count": int(count)})

    reached = {r["state"]: r["n"] for r in db.all(cur, """
        select substr(action, 6) as state, count(distinct object_id) as n from audit_log
        where object_kind = 'account_play' and action like 'play\\_%%' group by 1""")}
    reached["proposed"] = _n(cur, "select count(*) from account_plays where arm = 'treated'")
    reached["held_out"] = _n(cur, "select count(*) from account_plays where arm = 'holdout'")
    for s in PLAY_STATES:
        add("Play states (accounts that reached it)", s, reached.get(s, 0))

    labels = {r["label"]: r["n"] for r in db.all(cur, "select label, count(*) as n from replies where label is not null group by 1")}
    for lb in REPLY_LABELS:
        add("Reply labels", lb, labels.get(lb, 0))
    langs = {r["language"]: r["n"] for r in db.all(cur, """select language, count(*) as n from replies
                                                           where label = 'unsubscribe' group by 1""")}
    for lang in OPT_OUT_LANGUAGES:
        add("Opt-outs by language", lang, langs.get(lang, 0))

    types = {r["type_key"]: r["n"] for r in db.all(cur, """select type_key, count(*) as n from signals
                                                          where status = 'matched' group by 1""")}
    for t in db.all(cur, "select key from signal_types order by key"):
        add("Signal types (matched)", t["key"], types.get(t["key"], 0))

    stages = {r["autonomy"] for r in db.all(cur, "select autonomy from plays")}
    changes = db.all(cur, "select from_stage, to_stage from play_stage_changes")
    for s in AUTONOMY:
        add("Autonomy stages (plays that were at it)", s,
            (1 if s in stages else 0) + sum(1 for c in changes if c["to_stage"] == s))
    add("Autonomy stages (plays that were at it)", "a promotion",
        sum(1 for c in changes if AUTONOMY.index(c["to_stage"]) > AUTONOMY.index(c["from_stage"])))
    add("Autonomy stages (plays that were at it)", "a demotion",
        sum(1 for c in changes if AUTONOMY.index(c["to_stage"]) < AUTONOMY.index(c["from_stage"])))

    for name, sql in REGION_OUTCOMES.items():
        add("Region rules", name, _n(cur, sql))

    add("Sending and data", "held-back accounts", reached["held_out"])
    add("Sending and data", "hard bounce", _n(cur, "select count(*) from deliveries where event = 'bounced_hard'"))
    add("Sending and data", "spam complaint", _n(cur, "select count(*) from deliveries where event = 'complaint'"))
    add("Sending and data", "mailbox paused", _n(cur, """select count(distinct object_id) from alerts where object_kind = 'mailbox'
                                                       and kind in ('complaint', 'mailbox_paused', 'placement_pause')"""))
    add("Sending and data", "catch-all address", _n(cur, "select count(*) from people where email_status = 'catch_all'")
        + _n(cur, "select count(*) from adapter_calls where adapter = 'email_resolver' and ok"))
    add("Sending and data", "do-not-call number", _n(cur, """select count(*) from audit_log where action = 'step_skipped'
                                                           and detail->>'why' like '%%do-not-call%%'"""))

    sug = {r["status"]: r["n"] for r in db.all(cur, "select status, count(*) as n from play_suggestions group by 1")}
    for s in SUGGESTION_STATUSES:
        add("Play suggestions", s, sug.get(s, 0))

    gaps = db.all(cur, "select reason from committee_gaps")
    for name, words in GAP_KINDS.items():
        add("Buying committee gaps", name, sum(1 for g in gaps if words in g["reason"]))

    tasks = {r["kind"]: r["n"] for r in db.all(cur, "select kind, count(*) as n from tasks group by 1")}
    for k in TASK_KINDS:
        add("Tasks", k, tasks.get(k, 0))

    add("Calls and learnings", "call notes", _n(cur, "select count(*) from call_notes"))
    kinds = {r["kind"]: r["n"] for r in db.all(cur, "select kind, count(*) as n from learnings group by 1")}
    for k in LEARNING_KINDS:
        add("Calls and learnings", f"learning: {k}", kinds.get(k, 0))

    add("Deals", "sourced", _n(cur, "select count(*) from opportunities where attribution = 'sourced'"))
    add("Deals", "influenced", _n(cur, "select count(*) from opportunities where attribution = 'influenced'"))
    add("Deals", "won", _n(cur, "select count(*) from opportunities where won"))
    add("Deals", "lost", _n(cur, "select count(*) from opportunities where won = false"))
    return out


def missing(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["count"] == 0]


def table(rows: list[dict]) -> str:
    lines, group = [], None
    width = max(len(r["scenario"]) for r in rows) + 2
    for r in rows:
        if r["group"] != group:
            group = r["group"]
            lines.append(f"\n{group}")
        lines.append(f"  {r['scenario']:<{width}}{r['count']:>7}" + ("   MISSING" if r["count"] == 0 else ""))
    gone = missing(rows)
    lines.append(f"\n{len(rows)} scenarios, {len(rows) - len(gone)} shown, {len(gone)} at zero.")
    return "\n".join(lines).lstrip("\n")


def main() -> int:
    with db.tx() as cur:
        rows = scenarios(cur)
    print(table(rows))
    return 1 if missing(rows) else 0
