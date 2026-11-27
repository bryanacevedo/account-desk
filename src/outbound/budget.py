"""The weekly proposal budget (BL-172, decision 119).

A manager can cap how many accounts the desk proposes to one SDR in a week. No cap (the default) changes nothing. With a cap,
a match never becomes a proposal at once: it waits in `proposal_waits`, and a release job proposes the waiting accounts for
the SDR highest priority first (urgent plays ahead), as many as the week has room for. What counts is proposals to the SDR
since Monday 00:00 in the SDR's own time zone; accounts in the comparison group never count; they wait with the rest and are drawn when released, because
no SDR sees them. Inside one week slots fill batch by batch: priority orders a batch and the weeks, not the whole week
looking back."""
from __future__ import annotations

import logging
from datetime import timedelta

from . import audit, db, jobs
from .db import J

log = logging.getLogger("outbound.budget")

# Batches: matches that arrive within this long of the first one are ranked together before any is proposed.
BATCH_DELAY = timedelta(minutes=15)
CAP_MIN, CAP_MAX = 1, 500

WEEK_START = "(date_trunc('week', app_now() at time zone u.timezone) at time zone u.timezone)"
USED = f"""(select count(*) from account_plays ap where ap.owner_id = u.id and ap.arm = 'treated'
            and ap.proposed_at >= {WEEK_START})"""


def usage(cur, user_id: int) -> dict | None:
    """One SDR's cap, how many proposals this week used, how many are left and how many accounts are waiting."""
    return db.one(cur, f"""
        select u.id as user_id, u.name, u.weekly_proposal_cap as cap, {USED}::int as used,
               case when u.weekly_proposal_cap is null then null else greatest(u.weekly_proposal_cap - {USED}, 0)::int end as left,
               {WEEK_START} as week_start, (date_trunc('week', app_now() at time zone u.timezone))::date as week_starts_on,
               (date_trunc('week', app_now() at time zone u.timezone))::date + 7 as resets_on,
               (select count(*) from proposal_waits w where w.owner_id = u.id)::int as waiting,
               (select count(*) from audit_log l where l.action = 'proposal_wait_dropped' and (l.detail->>'owner')::bigint = u.id
                  and l.at > app_now() - interval '7 days')::int as dropped_7d
        from users u where u.id = %s""", user_id)


def room(cur, user_id: int) -> int | None:
    """Proposals this SDR can still be given this week, or None when there is no cap."""
    u = usage(cur, user_id)
    return None if u is None or u["cap"] is None else u["left"]


def capped(cur, user_id: int) -> bool:
    return bool(db.val(cur, "select weekly_proposal_cap is not null from users where id = %s", user_id))


def queue(cur, account_id: int, owner_id: int, play: dict, sig: dict) -> None:
    """Hold a match for the owner's next release. One row per account: a newer match replaces the older one."""
    db.run(cur, """insert into proposal_waits (account_id, owner_id, play_id, trigger_signal_id) values (%s,%s,%s,%s)
                   on conflict (account_id) do update set owner_id = excluded.owner_id, play_id = excluded.play_id,
                     trigger_signal_id = excluded.trigger_signal_id""", account_id, owner_id, play["id"], sig["id"])
    enqueue_release(cur, owner_id)


def enqueue_release(cur, owner_id: int, *, delay: timedelta | None = BATCH_DELAY) -> None:
    """One release job per SDR waits for the batch; a second match while it is queued joins it."""
    jobs.enqueue(cur, "release_proposals", {"owner_id": owner_id}, delay=delay, dedupe_key=f"release_proposals:{owner_id}")


def drop(cur, account_id: int, reason: str) -> None:
    """A waiting account that no longer matches leaves the queue, and the audit log says why."""
    row = db.one(cur, "delete from proposal_waits where account_id = %s returning owner_id, play_id", account_id)
    if row:
        audit.log(cur, "desk", "proposal_wait_dropped", "account", account_id, {"reason": reason, "owner": row["owner_id"]})


@jobs.handler("release_proposals")
def release(cur, payload: dict) -> None:
    """Propose the waiting accounts of one SDR (every SDR with waits when none is named), highest priority first."""
    from . import plays
    owners = [payload["owner_id"]] if payload.get("owner_id") else [
        r["owner_id"] for r in db.all(cur, "select distinct owner_id from proposal_waits order by owner_id")]
    for owner in owners:
        db.run(cur, "select pg_advisory_xact_lock(7342172, %s)", owner)
        active = db.val(cur, "select active and role = 'sdr' from users where id = %s", owner)
        waits = db.all(cur, """
            select w.account_id, w.owner_id, coalesce(sc.priority, 0) as priority, p.urgent, w.since
            from proposal_waits w join plays p on p.id = w.play_id left join account_scores sc on sc.account_id = w.account_id
            where w.owner_id = %s order by p.urgent desc, coalesce(sc.priority, 0) desc, w.since, w.account_id""", owner)
        for w in waits:
            if active and plays._best(cur, w["account_id"]) is None:
                drop(cur, w["account_id"], "no longer matches any play")      # also reached while the week is full
                continue
            if active:
                left = room(cur, owner)
                if left is not None and left <= 0:
                    break
            # The account may have a new owner since it waited (the CRM moved it, the SDR left): it goes to them, through their cap.
            current = db.val(cur, "select a.owner_id from accounts a join users u on u.id = a.owner_id and u.active and u.role = 'sdr' "
                                  "where a.id = %s", w["account_id"])
            if current is not None and current != owner:
                db.run(cur, "delete from proposal_waits where account_id = %s", w["account_id"])
                plays.match(cur, w["account_id"])
                continue
            # The full matching gates run again: the account may be held, in another play, or past its signal's window.
            # A match that now belongs to someone else (the owner left) is queued again for them.
            db.run(cur, "delete from proposal_waits where account_id = %s", w["account_id"])
            made = plays.match(cur, w["account_id"], owner_id=owner if active else None, released=bool(active))
            if made is None and not db.val(cur, "select exists (select 1 from proposal_waits where account_id = %s)", w["account_id"]):
                audit.log(cur, "desk", "proposal_wait_dropped", "account", w["account_id"],
                          {"reason": "no longer matches any play", "owner": owner})
            elif made is not None and db.val(cur, "select state = 'proposed' from account_plays where id = %s", made):
                audit.log(cur, "desk", "proposal_released", "account_play", made,
                          {"owner": owner, "priority": w["priority"], "waited_since": w["since"].isoformat()})


def set_cap(cur, user_id: int, cap: int | None, reason: str, *, by: int) -> dict:
    """A manager (GTM) sets or clears one SDR's weekly cap. A raise releases what was waiting right away."""
    if cap is not None and not CAP_MIN <= cap <= CAP_MAX:
        raise ValueError(f"A weekly limit is {CAP_MIN} to {CAP_MAX}, or none")
    if len(reason.strip()) < 3:
        raise ValueError("Say why in a few words")
    db.run(cur, "select pg_advisory_xact_lock(7342172, %s)", user_id)    # the release job's lock first, then the row: never the other way
    u = db.one(cur, "select id, name, role, active, weekly_proposal_cap from users where id = %s for update", user_id)
    if u is None or u["role"] != "sdr" or not u["active"]:
        raise ValueError("Only an active SDR has a proposal limit")
    if u["weekly_proposal_cap"] == cap:
        return usage(cur, user_id)
    db.run(cur, "update users set weekly_proposal_cap = %s where id = %s", cap, user_id)
    db.run(cur, "insert into proposal_cap_changes (user_id, old_cap, new_cap, reason, changed_by) values (%s,%s,%s,%s,%s)",
           user_id, u["weekly_proposal_cap"], cap, reason.strip(), by)
    audit.log(cur, "person", "proposal_cap_set", "user", user_id,
              {"from": u["weekly_proposal_cap"], "to": cap, "reason": reason.strip()}, actor_id=by)
    if cap is None or (u["weekly_proposal_cap"] is not None and cap > u["weekly_proposal_cap"]):
        release(cur, {"owner_id": user_id})     # more room now: what was waiting is proposed in this same step
    return usage(cur, user_id)


def team(cur) -> list[dict]:
    """Every active SDR with the cap, this week's use and what is waiting (the Settings table, the manager's Today)."""
    rows = []
    for r in db.all(cur, "select id from users where role = 'sdr' and active order by id"):
        u = usage(cur, r["id"])
        u["top_waiting"] = db.all(cur, """
            select w.account_id, a.name, coalesce(sc.priority, 0) as priority, p.name as play, p.urgent
            from proposal_waits w join accounts a on a.id = w.account_id join plays p on p.id = w.play_id
            left join account_scores sc on sc.account_id = w.account_id where w.owner_id = %s
            order by p.urgent desc, coalesce(sc.priority, 0) desc, w.since limit 5""", r["id"])
        rows.append(u)
    return rows


def capacity_message(rows: list[dict]) -> str | None:
    """What a manager should do when SDRs are at their limit with accounts waiting. None when nobody is."""
    full = [u for u in rows if u["cap"] is not None and u["left"] == 0 and u["waiting"] > 0]
    if not full:
        return None
    n = sum(u["waiting"] for u in full)
    who = full[0]["name"] if len(full) == 1 else f"{len(full)} SDRs"
    verb = "is" if len(full) == 1 else "are"
    return (f"{who} {verb} at the weekly limit and {n} account{'s' if n != 1 else ''} {'is' if n == 1 else 'are'} waiting, highest priority "
            f"first. Add a person, or raise the limit.")


def changes(cur, limit: int = 20) -> list[dict]:
    return db.all(cur, """select c.id, c.at, c.old_cap, c.new_cap, c.reason, u.name as sdr, b.name as changed_by
                          from proposal_cap_changes c join users u on u.id = c.user_id join users b on b.id = c.changed_by
                          order by c.at desc, c.id desc limit %s""", limit)


__all__ = ["usage", "room", "capped", "queue", "release", "set_cap", "team", "capacity_message", "changes", "drop", "J"]
