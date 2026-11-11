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
    # A deal credited to this meeting is re-attributed when the meeting turns out not to have happened.
    if status in ("cancelled", "no_show"):
        for o in db.all(cur, "select id from opportunities where attribution_meeting_id = %s", meeting_id):
            attribute(cur, o["id"])
    if status in ("cancelled", "no_show") and m["account_play_id"]:
        ap = db.one(cur, "select * from account_plays where id = %s", m["account_play_id"])
        if ap["state"] == "meeting":
            plays.set_state(cur, ap["id"], "engaged")
            db.run(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                           values (%s,%s,'call','Rebook the meeting',app_now(),%s)""", ap["id"], m["person_id"], ap["owner_id"])
    audit.log(cur, "person" if user_id else "desk", f"meeting_{status}", "meeting", meeting_id, {}, actor_id=user_id)


# ---------------------------------------------------------------- deals, read from the CRM

def attribute(cur, opp_id: int) -> str:
    """Who gets credit for a deal, recomputed whenever the deal or a meeting it rests on changes.

    Sourced: a meeting from a treated play, not an inbound request, booked after the play's first outreach to the
    account and within the 90 days before the deal, and not a no-show or cancelled.
    Influenced: otherwise, a treated play that actually reached the account in the 90 days before the deal.
    A play that was offered but never contacted anyone gets no credit."""
    o = db.one(cur, "select * from opportunities where id = %s for update", opp_id)
    m = db.one(cur, """
        select m.id as meeting_id, m.account_play_id, ap.play_id from meetings m join account_plays ap on ap.id = m.account_play_id
        where m.account_id = %s and ap.arm = 'treated' and m.source <> 'inbound' and m.status in ('held', 'booked')
          and m.booked_at <= %s and m.booked_at > %s - interval '90 days'
          and exists (select 1 from touches t where t.account_play_id = ap.id and t.direction = 'out' and t.at < m.booked_at)
        order by m.booked_at desc limit 1""", o["account_id"], o["created_at"], o["created_at"])
    inf = None if m else db.one(cur, """
        select ap.id as account_play_id, ap.play_id from account_plays ap
        where ap.account_id = %s and ap.arm = 'treated'
          and exists (select 1 from touches t where t.account_play_id = ap.id and t.direction = 'out'
                      and t.at <= %s and t.at > %s - interval '90 days')
        order by ap.proposed_at desc limit 1""", o["account_id"], o["created_at"], o["created_at"])
    att = "sourced" if m else "influenced" if inf else "none"
    src = m or inf or {}
    db.run(cur, """update opportunities set attribution = %s, source_play_id = %s, account_play_id = %s,
                   attribution_meeting_id = %s, attributed_at = app_now() where id = %s""",
           att, src.get("play_id"), src.get("account_play_id"), src.get("meeting_id"), opp_id)
    if att != o["attribution"]:
        audit.log(cur, "desk", "attributed", "opportunity", opp_id, {"from": o["attribution"], "to": att})
    return att


def upsert_deal(cur, d, *, account_id: int | None = None) -> int | None:
    """One deal from the CRM: create or update it, set the account's lifecycle, attribute it, and close the play it
    converted. Returns the opportunity id, or None when the account is not one we know (counted by the caller)."""
    from . import signals
    if account_id is None:
        account_id, _ = signals.resolve_account(cur, d.account_domain, None)
    if account_id is None:
        account_id = db.val(cur, "select id from accounts where primary_domain = %s", (d.account_domain or "").lower())
    if account_id is None:
        return None
    existing = db.one(cur, "select * from opportunities where crm_id = %s for update", d.crm_id)
    oid = db.val(cur, """
        insert into opportunities (account_id, crm_id, name, amount_cents, stage, created_at, updated_at, closed_at, won,
                                   loss_reason, contact_email)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (crm_id) do update set name = excluded.name, amount_cents = excluded.amount_cents, stage = excluded.stage,
          updated_at = excluded.updated_at, closed_at = excluded.closed_at, won = excluded.won,
          loss_reason = excluded.loss_reason, contact_email = excluded.contact_email
        returning id""", account_id, d.crm_id, d.name, d.amount_cents, d.stage, d.created_at, d.updated_at, d.closed_at,
                 d.won, d.loss_reason, (d.contact_email or "").lower() or None)
    att = attribute(cur, oid)
    _lifecycle(cur, account_id)
    if existing is None and att != "none":
        ap_id = db.val(cur, "select account_play_id from opportunities where id = %s", oid)
        if db.val(cur, "select state from account_plays where id = %s", ap_id) in ("meeting", "engaged", "active"):
            plays.set_state(cur, ap_id, "converted")
    if d.won and d.contact_email:
        # The person who bought becomes a champion: if they move company, that is a signal worth acting on.
        db.run(cur, "update people set is_champion = true where email = %s", d.contact_email.lower())
    return oid


def _lifecycle(cur, account_id: int) -> None:
    """A won deal makes a customer; an open deal an open opportunity; a lost expansion leaves a customer a customer."""
    # A customer stays a customer: the CRM or an import said so, and a lost expansion deal does not change it.
    # Only an account the desk itself moved to open_opp falls back to prospect when its last open deal closes lost.
    db.run(cur, """update accounts a set lifecycle = case
                     when exists (select 1 from opportunities x where x.account_id = a.id and x.won) then 'customer'
                     when a.lifecycle = 'customer' then 'customer'
                     when exists (select 1 from opportunities x where x.account_id = a.id and x.closed_at is null) then 'open_opp'
                     else 'prospect' end
                   where a.id = %s and a.lifecycle in ('open_opp', 'prospect', 'customer')""", account_id)


def opportunity_created(cur, *, account_id: int, crm_id: str, name: str, amount_cents: int, stage: str,
                        created_at: datetime) -> int:
    """A deal created now, for callers that are not the CRM read (tests, a webhook)."""
    from .adapters import CrmDeal
    domain = db.val(cur, "select primary_domain from accounts where id = %s", account_id)
    return upsert_deal(cur, CrmDeal(crm_id, domain, name, amount_cents, stage, created_at, created_at), account_id=account_id)


def opportunity_closed(cur, crm_id: str, won: bool, closed_at: datetime, loss_reason: str | None = None) -> None:
    o = db.one(cur, "select account_id from opportunities where crm_id = %s", crm_id)
    if o is None:
        return
    db.run(cur, """update opportunities set won = %s, closed_at = %s, stage = %s, loss_reason = %s, updated_at = %s
                   where crm_id = %s""", won, closed_at, "Closed Won" if won else "Closed Lost", loss_reason, closed_at, crm_id)
    _lifecycle(cur, o["account_id"])


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


def apply_owner(cur, account_id: int, owner_email: str) -> str:
    """The CRM says who owns the account. The account, its open play and that play's open work move to them;
    sequences already under way finish from the original sender, so a thread never changes voice halfway.
    Returns what happened: moved, unchanged, or not_on_desk."""
    email = owner_email.strip().lower()
    a = db.one(cur, "select id, name, owner_id from accounts where id = %s for update", account_id)
    db.run(cur, "update accounts set crm_owner_email = %s where id = %s", email, account_id)
    new = db.one(cur, "select id, name, role from users where email = %s and active", email)
    if new is None or new["role"] != "sdr":
        alerts.raise_alert(cur, kind="owner_not_on_desk", severity="info", channel="#outbound-ops",
                           title=f"{a['name']} now belongs to {email} in the CRM",
                           body="They are not an SDR on the desk, so the account and its play stay where they are.",
                           object_kind="account", object_id=account_id, dedup_key=f"owner:{account_id}:{email}")
        return "not_on_desk"
    if a["owner_id"] == new["id"]:
        return "unchanged"
    old = a["owner_id"]
    db.run(cur, "update accounts set owner_id = %s where id = %s", new["id"], account_id)
    for ap in db.all(cur, """select id, owner_id from account_plays where account_id = %s and state in
                             ('proposed','accepted','researching','approving','active','engaged','meeting')""", account_id):
        db.run(cur, "update account_plays set owner_id = %s where id = %s", new["id"], ap["id"])
        db.run(cur, "update tasks set owner_id = %s where account_play_id = %s and status = 'open'", new["id"], ap["id"])
        db.run(cur, "update meetings set owner_id = %s where account_play_id = %s and status = 'booked'", new["id"], ap["id"])
    db.run(cur, """update tasks t set owner_id = %s from replies r where t.reply_id = r.id and r.account_id = %s
                   and t.status = 'open'""", new["id"], account_id)
    for uid in {old, new["id"]} - {None}:
        alerts.raise_alert(cur, kind="owner_changed", severity="info", channel="#outbound-ops", target_user=uid,
                           title=f"{a['name']} moved to {new['name']} in the CRM",
                           body="Its open play and tasks moved too. Emails already under way finish from the original sender.",
                           object_kind="account", object_id=account_id, dedup_key=f"owner:{account_id}:{email}:{uid}")
    audit.log(cur, "desk", "owner_changed", "account", account_id, {"from": old, "to": new["id"], "via": "crm"})
    return "moved"


@jobs.handler("crm_sync")
def crm_sync(cur, payload: dict) -> None:
    """Read every deal the CRM changed since the last read, oldest first, and keep a cursor so a failed read
    resumes where it stopped. Deals on accounts we do not know are counted, not dropped silently."""
    from . import signals
    since = db.val(cur, "select value #>> '{}' from settings where key = 'crm_cursor'")
    crm = adapters.get().crm
    unknown = 0
    while True:
        batch = crm.deals_changed(cur, since, 200)
        for d in batch:
            if upsert_deal(cur, d) is None:
                unknown += 1
            # The cursor is (time, id): deals that share a timestamp across a batch edge are still all read.
            since = (d.updated_at.isoformat() if hasattr(d.updated_at, "isoformat") else str(d.updated_at)) + "|" + d.crm_id
        if len(batch) < 200:
            break
    if since:
        db.run(cur, """insert into settings (key, value) values ('crm_cursor', %s)
                       on conflict (key) do update set value = excluded.value""", J(since))
    db.run(cur, """insert into settings (key, value) values ('crm_unknown_accounts', %s)
                   on conflict (key) do update set value = excluded.value""", J(unknown))
    # Owners, with their own cursor.
    from . import signals as _s
    owner_since = db.val(cur, "select value #>> '{}' from settings where key = 'crm_owner_cursor'")
    while True:
        batch = crm.owners_changed(cur, owner_since, 200)
        for o in batch:
            aid, _ = _s.resolve_account(cur, o.account_domain, None)
            if aid:
                apply_owner(cur, aid, o.owner_email)
            owner_since = (o.updated_at.isoformat() if hasattr(o.updated_at, "isoformat") else str(o.updated_at)) + "|" + o.change_id
        if len(batch) < 200:
            break
    if owner_since:
        db.run(cur, """insert into settings (key, value) values ('crm_owner_cursor', %s)
                       on conflict (key) do update set value = excluded.value""", J(owner_since))
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
