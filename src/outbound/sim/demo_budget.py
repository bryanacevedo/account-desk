"""The demo's weekly proposal limits (BL-172, decision 119), set after the simulated history so they change nothing in it.

Every SDR gets a limit. The busiest SDR of the week is held at what they have used, and a few accounts of theirs that came in on
a fresh signal wait for next Monday: the same signal feed, scoring and matching the desk always runs, so the waiting rows are the
ones the code writes, not rows put in by hand. A planted routine, like the call-note plants (docs/WORLD.md)."""
from __future__ import annotations

from .. import budget, db, gate, plays, scoring
from ..db import J

DEFAULT_CAP = 14
PLANTED = 4


def seed(cur) -> dict:
    manager = db.val(cur, "select id from users where role = 'manager' and active order by id limit 1")
    sdrs = [r["id"] for r in db.all(cur, "select id from users where role = 'sdr' and active order by id")]
    if manager is None or not sdrs:
        return {"limits": 0, "waiting": 0}
    for sid in sdrs:
        budget.set_cap(cur, sid, DEFAULT_CAP, "Starting limit: about what an SDR approved in a busy week of this sample", by=manager)
    used = {sid: budget.usage(cur, sid)["used"] for sid in sdrs}
    busiest = max(sdrs, key=lambda s: (used[s], -s))
    held_at = max(1, used[busiest])
    budget.set_cap(cur, busiest, held_at, "Out two days this week, so held at what is already proposed to them", by=manager)
    play = db.one(cur, "select * from plays where status = 'live' order by urgent, id limit 1")
    source = db.val(cur, "select key from signal_sources where enabled order by key limit 1")
    if play is None or source is None:
        return {"limits": len(sdrs), "waiting": 0}
    sig_type = play["trigger"]["any_of"][0]
    from ..signals import ingest
    made = 0
    for row in db.all(cur, """select a.id, a.name from accounts a join account_scores s on s.account_id = a.id
                              where a.owner_id = %s and s.priority > 0 and a.fit_tier in ('A', 'B')
                              order by s.priority desc, a.id limit 60""", busiest):
        if made >= PLANTED:
            break
        if gate.account_reasons(cur, row["id"]):
            continue
        ingest(cur, source, [{"type": sig_type, "account_id": row["id"], "external_id": f"demo-budget-{row['id']}",
                              "observed_at": db.val(cur, "select app_now()"), "strength": 0.85,
                              "evidence": {"summary": f"{row['name']} shows a fresh buying signal this week",
                                           "url": f"https://signals.example/{row['id']}"}}])
        scoring.rescore(cur, row["id"])
        plays.match(cur, row["id"])
        if db.val(cur, "select exists (select 1 from proposal_waits where account_id = %s)", row["id"]):
            made += 1
    return {"limits": len(sdrs), "held": busiest, "waiting": made}


__all__ = ["seed", "J"]
