"""Meetings, opportunities, CRM write-back through the outbox, and Slack delivery of alerts."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from . import adapters, alerts, audit, db, jobs, plays
from .db import J

log = logging.getLogger("outbound.pipeline")


def book_meeting(cur, *, account_id: int, person_id: int | None, starts_at: datetime, source: str,
                 owner_id: int | None = None, external_id: str | None = None) -> int:
    ap = db.one(cur, """select * from account_plays where account_id = %s and state in
                        ('active','engaged','meeting','approving') order by proposed_at desc limit 1""", account_id)
    mid = db.val(cur, """insert into meetings (account_play_id, account_id, person_id, owner_id, booked_at, starts_at,
                                               status, source, external_id)
                         values (%s,%s,%s,%s,app_now(),%s,'booked',%s,%s) on conflict (external_id) do nothing returning id""",
                 ap["id"] if ap else None, account_id, person_id, owner_id or (ap["owner_id"] if ap else None), starts_at,
                 source, external_id)
    if mid is None:
        return db.val(cur, "select id from meetings where external_id = %s", external_id)
    if ap and ap["state"] != "meeting":
        if ap["state"] == "approving":
            plays.set_state(cur, ap["id"], "active")
        if ap["state"] in ("active", "approving"):
            plays.set_state(cur, ap["id"], "engaged")
        plays.set_state(cur, ap["id"], "meeting")
        db.run(cur, """update enrollments set state = 'stopped', stop_reason = 'meeting_booked', next_at = null
                       where account_play_id = %s and state in ('pending','active','paused')""", ap["id"])
        db.run(cur, """update messages set status = 'cancelled' where status in ('draft','failed_gate','awaiting_approval',
                       'approved','scheduled') and enrollment_id in (select id from enrollments where account_play_id = %s)""",
               ap["id"])
    db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source, dedup_key)
                   values (%s,%s,%s,'meeting','in','meeting_booked',app_now(),%s,%s) on conflict do nothing""",
           account_id, person_id, ap["id"] if ap else None, source, f"meeting:{mid}")
    db.run(cur, "insert into crm_outbox (kind, payload, idempotency_key) values ('meeting', %s, %s) on conflict do nothing",
           J({"meeting_id": mid, "account_id": account_id, "person_id": person_id, "starts_at": starts_at.isoformat()}),
           f"meeting:{mid}")
    audit.log(cur, "desk", "meeting_booked", "meeting", mid, {"source": source})
    return mid


def set_meeting_status(cur, meeting_id: int, status: str, user_id: int | None = None) -> None:
    m = db.one(cur, "select * from meetings where id = %s for update", meeting_id)
    db.run(cur, "update meetings set status = %s where id = %s", status, meeting_id)
    if status in ("cancelled", "no_show") and m["account_play_id"]:
        ap = db.one(cur, "select * from account_plays where id = %s", m["account_play_id"])
        if ap["state"] == "meeting":
            plays.set_state(cur, ap["id"], "engaged")
            db.run(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                           values (%s,%s,'call','Rebook the meeting',app_now(),%s)""", ap["id"], m["person_id"], ap["owner_id"])
    audit.log(cur, "person" if user_id else "desk", f"meeting_{status}", "meeting", meeting_id, {}, actor_id=user_id)


def opportunity_created(cur, *, account_id: int, crm_id: str, name: str, amount_cents: int, stage: str,
                        created_at: datetime) -> int:
    """Attribution: sourced when created within 90 days after a meeting from an account play; else influenced when
    the account had an open play in the 90 days before; sourced wins."""
    # Sourced: a meeting from an account play, booked within the 90 days before the opportunity.
    sourced = db.one(cur, """select m.account_play_id, ap.play_id from meetings m join account_plays ap on ap.id = m.account_play_id
                             where m.account_id = %s and m.booked_at <= %s and m.booked_at > %s - interval '90 days'
                             and m.status in ('held', 'booked') order by m.booked_at desc limit 1""",
                     account_id, created_at, created_at)
    # Influenced: the account had a treated account play open at any time in the 90 days before.
    influenced = None if sourced else db.one(cur, """select id as account_play_id, play_id from account_plays
                     where account_id = %s and arm = 'treated' and proposed_at <= %s
                       and (closed_at is null or closed_at >= %s - interval '90 days')
                     order by proposed_at desc limit 1""", account_id, created_at, created_at)
    att = "sourced" if sourced else "influenced" if influenced else "none"
    src = sourced or influenced or {}
    oid = db.val(cur, """insert into opportunities (account_id, crm_id, name, amount_cents, stage, created_at, source_play_id,
                                                    account_play_id, attribution)
                         values (%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (crm_id) do update set stage = excluded.stage
                         returning id""", account_id, crm_id, name, amount_cents, stage, created_at,
                 src.get("play_id"), src.get("account_play_id"), att)
    db.run(cur, "update accounts set lifecycle = 'open_opp' where id = %s and lifecycle = 'prospect'", account_id)
    if src.get("account_play_id"):
        ap = db.one(cur, "select state from account_plays where id = %s", src["account_play_id"])
        if ap["state"] in ("meeting", "engaged", "active"):
            plays.set_state(cur, src["account_play_id"], "converted")
    return oid


def opportunity_closed(cur, crm_id: str, won: bool, closed_at: datetime) -> None:
    o = db.one(cur, "update opportunities set won = %s, closed_at = %s, stage = %s where crm_id = %s returning account_id",
               won, closed_at, "Closed Won" if won else "Closed Lost", crm_id)
    if o:
        # A lost expansion deal leaves a customer a customer; another open deal keeps the account an open opportunity.
        db.run(cur, """update accounts a set lifecycle = case
                         when exists (select 1 from opportunities x where x.account_id = a.id and x.won) then 'customer'
                         when exists (select 1 from opportunities x where x.account_id = a.id and x.closed_at is null)
                           then 'open_opp'
                         else 'prospect' end
                       where a.id = %s and a.lifecycle in ('open_opp', 'prospect', 'customer')""", o["account_id"])


@jobs.handler("crm_push")
def crm_push(cur, payload: dict) -> None:
    for item in db.all(cur, """select * from crm_outbox where status = 'pending' and next_at <= app_now()
                               order by id limit 100 for update skip locked"""):
        try:
            with cur.connection.transaction():
                ref = adapters.get().crm.push(cur, item["kind"], item["payload"], item["idempotency_key"])
                db.run(cur, "update crm_outbox set status = 'done', done_at = app_now(), last_error = null, "
                            "payload = payload || %s where id = %s", J({"crm_ref": ref}), item["id"])
        except Exception as exc:
            attempts = item["attempts"] + 1
            if attempts >= 5:
                db.run(cur, "update crm_outbox set status = 'dead', attempts = %s, last_error = %s where id = %s",
                       attempts, str(exc)[:500], item["id"])
                alerts.raise_alert(cur, kind="crm_dead", severity="warn", channel="#outbound-ops",
                                   title="A CRM write failed five times", body=str(exc)[:300], object_kind="crm_outbox",
                                   object_id=item["id"], dedup_key=f"crmdead:{item['id']}")
            else:
                db.run(cur, "update crm_outbox set attempts = %s, last_error = %s, next_at = app_now() + %s where id = %s",
                       attempts, str(exc)[:500], timedelta(minutes=5 * 2 ** attempts), item["id"])


@jobs.handler("deliver_alert")
def deliver_alert(cur, payload: dict) -> None:
    a = db.one(cur, "select a.*, u.slack_id from alerts a left join users u on u.id = a.target_user where a.id = %s",
               payload["alert_id"])
    if a is None or a["delivered_at"]:
        return
    chat = adapters.get().chat
    mention = f"<@{a['slack_id']}> " if a["slack_id"] else ""
    if a["channel"].startswith("#acct-"):
        chat.ensure_channel(a["channel"], [a["slack_id"]] if a["slack_id"] else [])
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{a['title']}*\n{mention}{a['body'][:2800]}"}}]
    ok = chat.post(a["channel"], f"{mention}{a['title']}", blocks)
    if ok:
        db.run(cur, "update alerts set delivered_at = app_now(), delivery_error = null where id = %s", a["id"])
    else:
        db.run(cur, "update alerts set delivery_error = 'Slack refused the post' where id = %s", a["id"])
        raise RuntimeError("alert not delivered")


@jobs.handler("crm_sync")
def crm_sync(cur, payload: dict) -> None:
    """In the demo the CRM is the database itself; live mode reads owners, lifecycle and opportunities here."""
    from . import signals
    signals.first_party_from_crm(cur)


def record_call_notes(cur, meeting_id: int, text: str, user_id: int) -> int:
    return db.val(cur, "insert into call_notes (meeting_id, text, marked_by) values (%s,%s,%s) returning id",
                  meeting_id, text, user_id)


def learn_from(cur, note_id: int, user_id: int) -> int:
    """A person marked the notes worth learning from. The model extracts; code keeps only quotes that are really there."""
    from . import llm
    n = db.one(cur, """select cn.*, m.account_play_id, ap.play_id, s.type_key from call_notes cn
                       join meetings m on m.id = cn.meeting_id left join account_plays ap on ap.id = m.account_play_id
                       left join signals s on s.id = ap.trigger_signal_id where cn.id = %s""", note_id)
    db.run(cur, "update call_notes set worth_learning = true, marked_by = %s where id = %s", user_id, note_id)
    out = llm.run(cur, "extract", {"notes": n["text"]})
    kept = 0
    for item in out["items"]:
        if item["quote"] and item["quote"] in n["text"]:
            db.run(cur, """insert into learnings (call_note_id, kind, text, quote, play_id, signal_type)
                           values (%s,%s,%s,%s,%s,%s)""", note_id, item["kind"], item["text"], item["quote"],
                   n["play_id"], n["type_key"])
            kept += 1
    return kept
