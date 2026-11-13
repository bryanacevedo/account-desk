"""Meetings, opportunities, CRM write-back through the outbox, and Slack delivery of alerts."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

# suggestions and themes are unused here; importing them registers their jobs wherever learn_from can queue one.
from . import adapters, alerts, audit, db, integration, jobs, plays, scoring, suggestions, themes  # noqa: F401
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


MEETING_OUTCOMES = ("held", "no_show", "cancelled")


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
    if status in MEETING_OUTCOMES:
        # The CRM learns how the meeting this desk booked turned out. The row waits for the booking to reach the CRM first.
        db.run(cur, "insert into crm_outbox (kind, payload, idempotency_key) values ('meeting_outcome', %s, %s) on conflict do nothing",
               J({"meeting_id": meeting_id, "person_id": m["person_id"], "status": status}), f"meeting_outcome:{meeting_id}:{status}")
    audit.log(cur, "person" if user_id else "desk", f"meeting_{status}", "meeting", meeting_id, {}, actor_id=user_id)


# ---------------------------------------------------------------- deals, read from the CRM

def attribute(cur, opp_id: int) -> str:
    """Who gets credit for a deal, recomputed whenever the deal or a meeting it rests on changes.

    Sourced: a meeting from a treated play, not an inbound request, booked after the play's first outreach to the
    account and within the 90 days before the deal, and not a no-show or cancelled.
    Influenced: otherwise, a treated play that actually reached the account in the 90 days before the deal.
    A play that was offered but never contacted anyone gets no credit."""
    o = db.one(cur, "select * from opportunities where id = %s for update", opp_id)
    # A deal belongs to the meeting held with its own contact. When that contact met us in the 90 days before the deal,
    # only their meeting can source it (an inbound one cannot), so a colleague's earlier meeting is never credited with
    # a deal that came from someone else's conversation (found 2026-11-11).
    contact_met = bool(o["contact_email"]) and db.val(cur, """
        select exists (select 1 from meetings m join people p on p.id = m.person_id where m.account_id = %s
                       and lower(p.email) = lower(%s) and m.status in ('held', 'booked')
                       and m.booked_at <= %s and m.booked_at > %s - interval '90 days')""",
        o["account_id"], o["contact_email"], o["created_at"], o["created_at"])
    m = db.one(cur, """
        select m.id as meeting_id, m.account_play_id, ap.play_id from meetings m join account_plays ap on ap.id = m.account_play_id
        left join people p on p.id = m.person_id
        where m.account_id = %s and ap.arm = 'treated' and m.source <> 'inbound' and m.status in ('held', 'booked')
          and m.booked_at <= %s and m.booked_at > %s - interval '90 days'
          and exists (select 1 from touches t where t.account_play_id = ap.id and t.direction = 'out' and t.at < m.booked_at)
          and (not %s or lower(p.email) = lower(%s))
        order by m.booked_at desc limit 1""",
        o["account_id"], o["created_at"], o["created_at"], contact_met, o["contact_email"] or "")
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


# Kinds added after the three-method CRM contract. A CRM that does not know them is not an error: the row is finished
# with a note, so a stub or a Salesforce-shaped adapter that only has today's kinds runs the whole flow.
OPTIONAL_KINDS = ("contact", "meeting_outcome")


def _push(cur, crm, item: dict) -> str:
    kind = item["kind"]
    if kind in OPTIONAL_KINDS:
        if kind not in getattr(crm, "accepts_kinds", {kind}):
            return "skipped:unsupported"
        try:
            return crm.push(cur, kind, item["payload"], item["idempotency_key"])
        except ValueError:
            return "skipped:unsupported"
    return crm.push(cur, kind, item["payload"], item["idempotency_key"])


@jobs.handler("crm_push")
def crm_push(cur, payload: dict) -> None:
    for item in db.all(cur, """select * from crm_outbox where status = 'pending' and next_at <= app_now()
                               order by id limit 100 for update skip locked"""):
        try:
            with cur.connection.transaction():
                ref = _push(cur, adapters.get().crm, item)
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


def desk_user(cur, email: str) -> dict | None:
    """The active user with this address, or whose old address it was (the roster renames people; the CRM may still
    use the old one)."""
    e = (email or "").strip().lower()
    return db.one(cur, """select id, name, role from users where active and (email = %s
                          or id = (select user_id from user_aliases where alias = %s))""", e, e)


def apply_owner(cur, account_id: int, owner_email: str) -> str:
    """The CRM says who owns the account. The account, its open play and that play's open work move to them;
    sequences already under way finish from the original sender, so a thread never changes voice halfway.
    Returns what happened: moved, unchanged, or not_on_desk."""
    email = owner_email.strip().lower()
    a = db.one(cur, "select id, name, owner_id from accounts where id = %s for update", account_id)
    db.run(cur, "update accounts set crm_owner_email = %s where id = %s", email, account_id)
    new = desk_user(cur, email)
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


def hold_deal(cur, d) -> None:
    """Keep a deal whose account the desk does not know, newest version wins, to be read again later."""
    from dataclasses import asdict
    raw = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in asdict(d).items()}
    db.run(cur, """insert into crm_held_deals (crm_id, account_domain, deal) values (%s, %s, %s)
                   on conflict (crm_id) do update set deal = excluded.deal, account_domain = excluded.account_domain""",
           d.crm_id, (d.account_domain or "").lower(), J(raw))


@jobs.handler("crm_retry_held")
def retry_held_deals(cur, payload: dict | None = None) -> int:
    """Read held deals again; those whose account now exists become opportunities and are attributed."""
    from .adapters import CrmDeal
    done = 0
    for h in db.all(cur, "select * from crm_held_deals order by first_seen, crm_id limit 500"):
        raw = dict(h["deal"])
        for k in ("created_at", "updated_at", "closed_at"):
            if raw.get(k):
                raw[k] = datetime.fromisoformat(raw[k])
        if upsert_deal(cur, CrmDeal(**raw)) is not None:
            db.run(cur, "delete from crm_held_deals where crm_id = %s", h["crm_id"])
            done += 1
        else:
            db.run(cur, "update crm_held_deals set last_tried = app_now() where crm_id = %s", h["crm_id"])
    return done


@jobs.handler("crm_sync")
def crm_sync(cur, payload: dict) -> None:
    """Read every deal the CRM changed since the last read, oldest first, keeping a cursor. A deal on an account the
    desk does not know is held and read again later, never passed over."""
    from . import signals
    since = db.val(cur, "select value #>> '{}' from settings where key = 'crm_cursor'")
    crm = adapters.get().crm
    unknown = 0
    while True:
        batch = crm.deals_changed(cur, since, 200)
        for d in batch:
            if upsert_deal(cur, d) is None:
                hold_deal(cur, d)
                unknown += 1
            else:
                db.run(cur, "delete from crm_held_deals where crm_id = %s", d.crm_id)
            # The cursor is (time, id): deals that share a timestamp across a batch edge are still all read.
            since = (d.updated_at.isoformat() if hasattr(d.updated_at, "isoformat") else str(d.updated_at)) + "|" + d.crm_id
        if len(batch) < 200:
            break
    if since:
        db.run(cur, """insert into settings (key, value) values ('crm_cursor', %s)
                       on conflict (key) do update set value = excluded.value""", J(since))
    retry_held_deals(cur)
    db.run(cur, """insert into settings (key, value) values ('crm_unknown_accounts', %s)
                   on conflict (key) do update set value = excluded.value""",
           J(db.val(cur, "select count(*) from crm_held_deals")))
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
    sync_accounts(cur, crm)
    sync_campaign_members(cur, crm)
    signals.first_party_from_crm(cur)


# ---------------------------------------------------------------- the account book, read from a CRM that keeps one

# Market Desk's tiers (A, B, C, X, or "Not judged") use this desk's own letters, so a tier read from the CRM is stored as
# it is and "Not judged" or none is no tier at all (shared-world DESIGN.md 5 and 7 step 2). With a tier present, the
# account's fit tier follows it; with none, the desk's own fit decides, as it does alone.
TIERS = ("A", "B", "C", "X")


def _set_setting(cur, key: str, value) -> None:
    db.run(cur, """insert into settings (key, value) values (%s, %s)
                   on conflict (key) do update set value = excluded.value""", key, J(value))


def _stamp(row) -> str:
    return (row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else str(row.updated_at)) + "|" + row.change_id


def sync_accounts(cur, crm) -> int:
    """Accounts whose SDR owner is a desk SDR become, or update, this desk's accounts, with the CRM's tier and segment.
    A failed read stops here: the book the desk has stays as it is and nothing is removed. Returns accounts touched."""
    read = getattr(crm, "accounts_changed", None)
    if read is None:
        return 0
    since = db.val(cur, "select value #>> '{}' from settings where key = 'crm_account_cursor'")
    touched = 0
    failure = None
    while True:
        try:
            with cur.connection.transaction():     # one batch at a time: a failure keeps the batches already read
                batch = read(cur, since, 200)
                for a in batch:
                    touched += 1 if apply_account(cur, a) else 0
        except Exception as exc:
            failure = exc
            break
        if batch:
            since = _stamp(batch[-1])
        if len(batch) < 200:
            break
    if since:
        _set_setting(cur, "crm_account_cursor", since)
    if failure is None:
        _set_setting(cur, "crm_account_read_error", None)
        _set_setting(cur, "crm_account_read_at", db.val(cur, "select app_now()::text"))
    else:
        log.warning("accounts read stopped: %s", failure)
        _set_setting(cur, "crm_account_read_error", str(failure)[:300])
    return touched


def apply_account(cur, a) -> bool:
    """One account from the CRM. Not ours (its SDR is not a desk SDR) changes nothing. Returns whether it was applied."""
    owner = desk_user(cur, a.sdr_owner_email) if a.sdr_owner_email else None
    if owner is None or owner["role"] != "sdr":
        return False
    from . import signals
    domain = signals.normalize_domain(a.domain)
    aid = None
    if a.crm_id:
        aid = db.val(cur, "select id from accounts where crm_id = %s", a.crm_id)
    if aid is None and a.world_id:
        aid = db.val(cur, "select id from accounts where world_id = %s", a.world_id)
    if aid is None and domain:
        aid, _ = signals.resolve_account(cur, domain, None)
    tier = a.tier if a.tier in TIERS else None
    if aid is None:
        if not domain:
            return False
        aid = db.val(cur, """insert into accounts (name, name_key, primary_domain, source, world_id, crm_id, owner_id, crm_owner_email,
                                                   fit_tier)
                             values (%s,%s,%s,'crm',%s,%s,%s,%s,%s) returning id""",
                     a.name or domain, signals.normalize_name(a.name), domain, a.world_id, a.crm_id, owner["id"],
                     (a.sdr_owner_email or "").lower(), tier)
        db.run(cur, "insert into account_domains (domain, account_id) values (%s, %s) on conflict do nothing", domain, aid)
        audit.log(cur, "desk", "account_from_crm", "account", aid, {"domain": domain, "tier": tier})
    else:
        # An id this desk already gave another account is left alone rather than moved.
        db.run(cur, """update accounts set
                         world_id = coalesce(world_id, case when not exists (select 1 from accounts o where o.world_id = %s) then %s end),
                         crm_id = coalesce(crm_id, case when not exists (select 1 from accounts o where o.crm_id = %s) then %s end)
                       where id = %s""", a.world_id, a.world_id, a.crm_id, a.crm_id, aid)
        if db.val(cur, "select owner_id is distinct from %s from accounts where id = %s", owner["id"], aid):
            apply_owner(cur, aid, a.sdr_owner_email)
    db.run(cur, """update accounts set crm_tier = %s, crm_segment = %s, crm_fit_score = %s, crm_icp_version = %s, crm_read_at = app_now(),
                   fit_tier = coalesce(%s, fit_tier) where id = %s""", tier, a.segment, a.fit, a.icp_version, tier, aid)
    jobs.enqueue(cur, "rescore", {"account_id": aid, "reason": "crm_book"}, dedupe_key=f"rescore:{aid}")
    return True


def _fit_with_crm_tier(own):
    """The desk's fit, except that a tier read from the CRM wins when there is one. Wrapped around scoring.fit so that
    scoring.py needs no change; an account the desk excludes for being a customer stays excluded."""
    def fit(rules: dict, account: dict) -> dict:
        f = own(rules, account)
        tier = account.get("crm_tier")
        if tier not in TIERS or account.get("lifecycle") in ("customer", "open_opp", "competitor"):
            return f
        score = account.get("crm_fit_score")
        return {**f, "tier": tier, "score": f["score"] if score is None else int(score),
                "excluded": f["excluded"] if tier == "X" else None, "source": "crm"}
    fit.__wrapped_by_crm__ = True
    return fit


if not getattr(scoring.fit, "__wrapped_by_crm__", False):
    scoring.fit = _fit_with_crm_tier(scoring.fit)


# ---------------------------------------------------------------- event members, read from a CRM that keeps campaigns

# A member of an event or webinar campaign becomes a signal. Attended or met is the stronger one; registered, and no
# show, is "registered, did not attend" and is its own type with a lighter weight (DESIGN.md 2b, option A).
MEMBER_SIGNALS = {"registered": ("event_registered", 0.5), "no_show": ("event_registered", 0.3),
                  "attended": ("event_campaign_member", 0.8), "met": ("event_campaign_member", 0.95)}
MEMBER_VERBS = {"registered": "registered for", "no_show": "registered for but missed", "attended": "attended", "met": "met us at"}


def sync_campaign_members(cur, crm) -> int:
    """Only when Events Desk is present (INTEGRATED_WITH) and the CRM can list campaign members. Returns signals made."""
    read = getattr(crm, "campaign_members_changed", None)
    if read is None or not integration.has("events_desk"):
        return 0
    plays.ensure_event_play(cur)
    since = db.val(cur, "select value #>> '{}' from settings where key = 'crm_member_cursor'")
    made = 0
    failure = None
    while True:
        try:
            with cur.connection.transaction():
                batch = read(cur, since, 200)
                made += ingest_members(cur, batch)
        except Exception as exc:
            failure = exc
            break
        if batch:
            since = _stamp(batch[-1])
        if len(batch) < 200:
            break
    if since:
        _set_setting(cur, "crm_member_cursor", since)
    if failure is not None:
        log.warning("campaign members read stopped: %s", failure)
    _set_setting(cur, "crm_member_read_error", str(failure)[:300] if failure is not None else None)
    return made


def ingest_members(cur, members) -> int:
    """Turn members of event campaigns into signals, once each (the external id carries campaign, contact and status).
    A person the desk holds, or an account it works, is needed; nobody is created here."""
    from . import signals
    raws = []
    for m in members:
        if m.campaign_type not in ("event", "webinar") or m.status not in MEMBER_SIGNALS:
            continue
        person = None
        if m.contact_email:
            person = db.one(cur, "select id, account_id, email, linkedin_url from people where email = %s", m.contact_email.lower())
        if person is None and m.contact_crm_id:
            person = db.one(cur, "select id, account_id, email, linkedin_url from people where crm_id = %s", m.contact_crm_id)
        account_id = person["account_id"] if person else None
        if account_id is None and m.account_domain:
            account_id, _ = signals.resolve_account(cur, m.account_domain, None)
        if account_id is None:
            continue
        kind, strength = MEMBER_SIGNALS[m.status]
        who = m.contact_crm_id or m.contact_email or "unknown"
        raws.append({"type": kind, "external_id": f"member:{m.campaign_ref}:{who}:{m.status}", "observed_at": m.updated_at,
                     "account_id": account_id, "strength": strength,
                     "evidence": {"summary": f"Someone at the company {MEMBER_VERBS[m.status]} {m.event_name or m.campaign_name}.",
                                  "quote": f"{m.campaign_name}: {m.status}"},
                     **({"person": {"email": person["email"], "linkedin_url": person["linkedin_url"]}} if person else {})})
    return signals.ingest(cur, "crm", raws)["matched"] if raws else 0


# ---------------------------------------------------------------- the first touch: may this person be contacted

# Which of the CRM's flags bar which channel. A bounce bars email only; a do-not-call bars calls only.
BARS = {"email": {"do_not_contact", "do_not_email", "unsubscribed", "bounced", "left_company"},
        "call": {"do_not_contact", "do_not_call", "left_company"},
        "linkedin": {"do_not_contact", "left_company"}}
WAITS_BEFORE_ALERT = 3


def enqueue_contact(cur, person_id: int) -> None:
    """Write the person to the CRM before their first activity, once per person (the outbox is read oldest first)."""
    db.run(cur, "insert into crm_outbox (kind, payload, idempotency_key) values ('contact', %s, %s) on conflict do nothing",
           J({"person_id": person_id}), f"contact:{person_id}")


def _barred(answer: dict, channel: str) -> str | None:
    """Why the CRM's answer bars this channel, or None."""
    if answer.get("erased"):
        return "erased"
    if answer.get("suppressed"):
        return "On the CRM's do-not-contact list"
    flags = [f for f in answer.get("flags") or [] if f.get("kind") in BARS.get(channel, ())]
    if flags:
        return "Do not contact: " + flags[0].get("reason", flags[0]["kind"])
    if channel == "email" and not answer.get("can_email", True):
        return "The CRM says this person cannot be emailed"
    return None


def crm_first_touch(cur, person_id: int, channel: str = "email") -> str:
    """Ask the CRM whether a person may be contacted, before the first email, call or LinkedIn step. Returns `ok`,
    `wait` (the CRM did not answer: nothing is sent on a guess, the caller tries again) or `stopped` (flagged or erased:
    the person is stopped, or erased here). Alone, or with a CRM that cannot answer, the desk's own suppression list
    decides and this returns `ok`. The database send guard still runs after it."""
    crm = adapters.get().crm
    ask = getattr(crm, "contactability", None)
    if ask is None or not getattr(crm, "configured", False):
        enqueue_contact(cur, person_id)
        return "ok"
    row = db.one(cur, "select * from crm_contact_checks where person_id = %s", person_id)
    answer = row["answer"] if row and row["state"] == "ok" else None
    if answer is None:
        p = db.one(cur, """select p.email, p.world_id, p.full_name, a.primary_domain from people p
                           left join accounts a on a.id = p.account_id where p.id = %s""", person_id)
        if p is None:
            return "stopped"
        item = {"ref": str(person_id), "email": p["email"], "world_id": p["world_id"], "full_name": p["full_name"],
                "domain": p["primary_domain"]}
        try:
            answer = ask(cur, [item])[0]
        except Exception as exc:
            waits = (row["waits"] if row else 0) + 1
            db.run(cur, """insert into crm_contact_checks (person_id, state, waits, last_error) values (%s, 'waiting', %s, %s)
                           on conflict (person_id) do update set state = 'waiting', waits = excluded.waits,
                           last_error = excluded.last_error""", person_id, waits, str(exc)[:300])
            if waits >= WAITS_BEFORE_ALERT:
                alerts.raise_alert(cur, kind="crm_check_waiting", severity="warn", channel="#outbound-ops",
                                   title="A first email is waiting for the CRM to answer",
                                   body=f"The CRM has not said whether {p['full_name']} may be contacted ({waits} tries). "
                                        "Nothing is sent until it does.", object_kind="person", object_id=person_id,
                                   dedup_key=f"crmwait:{person_id}")
            return "wait"
        db.run(cur, """insert into crm_contact_checks (person_id, state, checked_at, waits, last_error, answer)
                       values (%s, 'ok', app_now(), 0, null, %s)
                       on conflict (person_id) do update set state = 'ok', checked_at = app_now(), waits = 0,
                       last_error = null, answer = excluded.answer""", person_id, J(answer))
    why = _barred(answer, channel)
    if why is None:
        enqueue_contact(cur, person_id)
        return "ok"
    if why == "erased":
        from . import privacy
        privacy.erase(cur, person_id, actor_id=None)    # the checks row goes with the person
        return "stopped"
    _stop_for_crm(cur, person_id, channel, why)
    return "stopped"


def _stop_for_crm(cur, person_id: int, channel: str, why: str) -> None:
    from . import outreach
    p = db.one(cur, "select email, phone from people where id = %s", person_id)
    # The desk's own list becomes a copy of the flag, so the gate refuses this person everywhere from now on.
    if channel == "email" and p["email"]:
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email', %s, %s, 'crm')", p["email"], why[:200])
    elif channel == "call" and p["phone"]:
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('phone', %s, %s, 'crm')", p["phone"], why[:200])
    db.run(cur, "update crm_contact_checks set state = 'stopped' where person_id = %s", person_id)
    for e in db.all(cur, "select id from enrollments where person_id = %s and state in ('pending','active','paused')", person_id):
        outreach.stop_enrollment(cur, e["id"], ("crm: " + why)[:120])
    audit.log(cur, "desk", "stopped_by_crm", "person", person_id, {"why": why, "channel": channel})


def record_call_notes(cur, meeting_id: int, text: str, user_id: int) -> int:
    """The person saving the notes wrote them; who later marks them worth learning from may be someone else."""
    return db.val(cur, "insert into call_notes (meeting_id, text, marked_by, written_by) values (%s,%s,%s,%s) returning id",
                  meeting_id, text, user_id, user_id)


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
    # Filing under themes is a model call per learning: a background job, never part of this request.
    if kept:
        jobs.enqueue(cur, "file_learnings", {"call_note_id": note_id})
    return kept
