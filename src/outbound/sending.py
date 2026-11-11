"""Sending: the gate under a row lock, the send window, mailbox capacity, the watched batch, then the provider.

A message moves scheduled -> sending -> sent. The database trigger refuses 'sending' when any rule fails, so even
a bug here cannot send to a suppressed, held, holdout or changed message."""
from __future__ import annotations

import logging
from datetime import timedelta

import psycopg

from . import adapters, alerts, db, gate, jobs, outreach, timeutil
from .config import CONFIG
from .db import J

log = logging.getLogger("outbound.sending")
WATCH_SIZE = 20


def headers_for(message: dict, person: dict, play_key: str) -> dict:
    token = outreach.unsubscribe_token(person["id"])
    url = f"{CONFIG.public_url}/u/{person['id']}/{token}"
    return {
        "List-Unsubscribe": f"<{url}>, <mailto:unsubscribe@{CONFIG.public_url.split('//')[-1].split('/')[0]}?subject=unsubscribe-{person['id']}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        "Feedback-ID": f"{play_key}:{message['step_index']}:outbound:lumen",
        "X-Outbound-Message": str(message["id"]),
    }


@jobs.handler("send_due")
def send_due(cur, payload: dict) -> None:
    ids = [r["id"] for r in db.all(cur, """select id from messages where status = 'scheduled' and scheduled_for <= app_now()
                                           order by scheduled_for limit 200""")]
    for mid in ids:
        jobs.enqueue(cur, "send_one", {"message_id": mid}, dedupe_key=f"send:{mid}", max_attempts=3)


@jobs.handler("send_one")
def send_one(cur, payload: dict) -> None:
    timeutil.load_holidays(cur)
    m = db.one(cur, "select * from messages where id = %s for update skip locked", payload["message_id"])
    if m is None or m["status"] != "scheduled":
        return
    e = db.one(cur, "select * from enrollments where id = %s for update", m["enrollment_id"])
    ap = db.one(cur, "select ap.*, pl.key as play_key from account_plays ap join plays pl on pl.id = ap.play_id "
                     "where ap.id = %s", e["account_play_id"])
    person = db.one(cur, "select * from people where id = %s", e["person_id"])
    now = db.val(cur, "select app_now()")
    window = timeutil.windows(db.val(cur, "select value from settings where key = 'send_window'"))

    def later(at, why: str) -> None:
        db.run(cur, "update messages set scheduled_for = %s where id = %s", at, m["id"])
        db.run(cur, "update enrollments set next_at = %s where id = %s", at, e["id"])
        log.debug("message %s waits: %s", m["id"], why)

    if e["state"] != "active":
        return  # paused: the resume reschedules it
    reasons = gate.person_reasons(cur, person["id"], "email", account_play_id=ap["id"], enrollment_id=e["id"])
    permanent = [r for r in reasons if r.permanent]
    if permanent:
        outreach.stop_enrollment(cur, e["id"], "gate:" + permanent[0].code)
        return
    if reasons:
        if any(r.code == "verify_due" for r in reasons):
            jobs.enqueue(cur, "reverify", {"person_id": person["id"]}, dedupe_key=f"reverify:{person['id']}")
        later(now + timedelta(hours=4), reasons[0].message)
        return
    if not timeutil.in_window(now, timezone=person["timezone"], country=person["country"], window=window):
        later(timeutil.next_slot(now, timezone=person["timezone"], country=person["country"], window=window,
                                 jitter_key=f"m{m['id']}r"), "outside the send window")
        return
    watch = db.one(cur, "select * from play_step_watch where template_key = %s", m["template_key"])
    if watch and watch["paused"]:
        later(now + timedelta(hours=12), "play step paused")
        return
    mailbox = db.one(cur, "select * from mailboxes where id = %s", m["mailbox_id"] or e["mailbox_id"]) \
        if (m["mailbox_id"] or e["mailbox_id"]) else None
    if mailbox is None or outreach.mailbox_sendable(cur, mailbox):
        new_id = outreach.pick_mailbox(cur, ap["owner_id"], -1)
        mailbox = db.one(cur, "select * from mailboxes where id = %s", new_id) if new_id else None
        if mailbox is None:
            later(now + timedelta(hours=12), "no healthy mailbox")
            alerts.raise_alert(cur, kind="no_mailbox", severity="warn", channel="#outbound-ops",
                               title="A rep has no healthy mailbox", body="Sends are waiting for a mailbox.",
                               target_user=ap["owner_id"], dedup_key=f"no_mailbox:{ap['owner_id']}:{now:%Y-%m-%d}")
            return
        db.run(cur, "update enrollments set mailbox_id = %s where id = %s", mailbox["id"], e["id"])
    domain_cap = db.val(cur, "select daily_cap from sending_domains where domain = %s", mailbox["domain"])
    domain_today = db.val(cur, """select count(*) from messages m join mailboxes mb on mb.id = m.mailbox_id
                                  where mb.domain = %s and m.sent_at >= date_trunc('day', app_now())
                                  and m.status in ('sent','sending','send_unknown')""", mailbox["domain"])
    if outreach.sent_today(cur, mailbox["id"]) >= outreach.mailbox_capacity(cur, mailbox) or domain_today >= domain_cap:
        later(timeutil.next_slot(now + timedelta(days=1), timezone=person["timezone"], country=person["country"],
                                 window=window, jitter_key=f"m{m['id']}c"), "mailbox at its daily cap")
        return
    # The trigger is the last check. A refusal here means a rule changed between the gate and now.
    try:
        with cur.connection.transaction():
            db.run(cur, "update messages set status = 'sending', mailbox_id = %s, sent_at = app_now() where id = %s",
                   mailbox["id"], m["id"])
    except psycopg.errors.RaiseException as exc:
        outreach.stop_enrollment(cur, e["id"], "refused: " + str(exc).split("\n")[0][:120])
        return
    result = adapters.get().email.send(cur, {**m, "mailbox_id": mailbox["id"]}, mailbox, person,
                                       headers_for(m, person, ap["play_key"]))
    record_result(cur, m["id"], result.outcome, result.provider_id, result.error)


def record_result(cur, message_id: int, outcome: str, provider_id: str | None, error: str | None) -> None:
    m = db.one(cur, "select * from messages where id = %s", message_id)
    e = db.one(cur, "select * from enrollments where id = %s", m["enrollment_id"])
    ap = db.one(cur, "select * from account_plays where id = %s", e["account_play_id"])
    if outcome == "sent":
        db.run(cur, "update messages set status = 'sent', provider_id = %s, thread_key = coalesce(thread_key, %s) "
                    "where id = %s", provider_id, f"t{e['id']}", message_id)
        db.run(cur, "insert into deliveries (message_id, mailbox_id, event, at) values (%s,%s,'sent',app_now())",
               message_id, m["mailbox_id"])
        db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source,
                                            message_id, dedup_key)
                       values (%s,%s,%s,'email','out','email_sent',app_now(),'desk',%s,%s) on conflict do nothing""",
               ap["account_id"], e["person_id"], ap["id"], message_id, f"msg:{message_id}")
        db.run(cur, """insert into play_step_watch (template_key, sends) values (%s, 1)
                       on conflict (template_key) do update set sends = play_step_watch.sends + 1""", m["template_key"])
        db.run(cur, """insert into crm_outbox (kind, payload, idempotency_key) values ('activity', %s, %s)
                       on conflict do nothing""",
               J({"type": "email_sent", "person_id": e["person_id"], "message_id": message_id, "subject": m["subject"]}),
               f"activity:email:{message_id}")
        outreach.advance(cur, e["id"])
    elif outcome == "unknown":
        db.run(cur, "update messages set status = 'send_unknown' where id = %s", message_id)
        jobs.enqueue(cur, "reconcile_send", {"message_id": message_id}, delay=timedelta(minutes=30),
                     dedupe_key=f"reconcile:{message_id}")
    else:
        db.run(cur, "update messages set status = 'failed', sent_at = null where id = %s", message_id)
        outreach.stop_enrollment(cur, e["id"], f"send_failed: {(error or '')[:80]}")


@jobs.handler("reconcile_send")
def reconcile_send(cur, payload: dict) -> None:
    """Never retry an unknown send blindly. Ask the provider what happened."""
    m = db.one(cur, "select * from messages where id = %s for update", payload["message_id"])
    if m["status"] != "send_unknown":
        return
    r = adapters.get().email.lookup(cur, str(m["id"]))
    if r.outcome == "sent":
        record_result(cur, m["id"], "sent", r.provider_id, None)
    elif r.outcome == "failed":
        # It never left. Put it back in line; the gate runs again before the retry.
        db.run(cur, "update messages set status = 'scheduled', sent_at = null, scheduled_for = app_now() where id = %s",
               m["id"])
    else:
        alerts.raise_alert(cur, kind="send_unknown", severity="warn", channel="#outbound-ops",
                           title="A send's outcome is unknown", body="The provider cannot say whether it went out. "
                           "Check the mailbox's sent folder and mark it.", object_kind="message", object_id=m["id"],
                           dedup_key=f"unknown:{m['id']}")


@jobs.handler("reverify")
def reverify(cur, payload: dict) -> None:
    p = db.one(cur, "select * from people where id = %s", payload["person_id"])
    if p and p["email"] and p["account_id"]:
        account = db.one(cur, "select * from accounts where id = %s", p["account_id"])
        db.run(cur, "update people set email_verified_at = null, email_status = 'unknown' where id = %s", p["id"])
        p = db.one(cur, "select * from people where id = %s", p["id"])
        outreach._ensure_email(cur, p, account)


# ---------------------------------------------------------------- deliverability health

def record_delivery_event(cur, message_id: int, event: str, detail: dict | None = None) -> None:
    m = db.one(cur, "select m.*, e.person_id from messages m join enrollments e on e.id = m.enrollment_id where m.id = %s",
               message_id)
    source = db.val(cur, "select email_verified_by from people where id = %s", m["person_id"])
    db.run(cur, "insert into deliveries (message_id, mailbox_id, event, at, email_source, detail) "
                "values (%s,%s,%s,app_now(),%s,%s)", message_id, m["mailbox_id"], event, source, J(detail or {}))
    col = {"bounced_hard": "hard_bounces", "complaint": "complaints"}.get(event)
    if col:
        db.run(cur, f"update play_step_watch set {col} = {col} + 1 where template_key = %s", m["template_key"])
        w = db.one(cur, "select * from play_step_watch where template_key = %s", m["template_key"])
        if w and w["sends"] <= WATCH_SIZE and not w["paused"] and (w["hard_bounces"] >= 2 or w["complaints"] >= 1):
            db.run(cur, "update play_step_watch set paused = true, paused_reason = %s where template_key = %s",
                   f"{w['hard_bounces']} hard bounces, {w['complaints']} complaints in the first {w['sends']} sends",
                   m["template_key"])
            alerts.raise_alert(cur, kind="watch_paused", severity="urgent", channel="#outbound-ops",
                               title=f"Paused {m['template_key']} in its first batch",
                               body="Bounces or a complaint in the first sends. Check the data source before resuming.",
                               dedup_key=f"watch:{m['template_key']}")
    if event == "complaint":
        db.run(cur, "update mailboxes set status = 'paused', pause_reason = 'Spam complaint received' where id = %s "
                    "and status = 'active'", m["mailbox_id"])
        alerts.raise_alert(cur, kind="complaint", severity="urgent", channel="#outbound-ops",
                           title="A mailbox got a spam complaint and is paused", body="Feedback loop report.",
                           object_kind="mailbox", object_id=m["mailbox_id"], dedup_key=f"complaint:{message_id}")


@jobs.handler("mailbox_health")
def mailbox_health(cur, payload: dict) -> None:
    """Rolling 14-day hard-bounce rate per mailbox from 50 sends: warn at 1.5%, pause at 2%."""
    for r in db.all(cur, """select mb.id, mb.address, mb.status,
               count(*) filter (where d.event = 'sent') as sent,
               count(*) filter (where d.event = 'bounced_hard') as bounced
             from mailboxes mb left join deliveries d on d.mailbox_id = mb.id and d.at > app_now() - interval '14 days'
             group by mb.id"""):
        if r["sent"] < 50 or r["status"] != "active":
            continue
        rate = r["bounced"] / r["sent"]
        if rate >= 0.02:
            db.run(cur, "update mailboxes set status = 'paused', pause_reason = %s where id = %s",
                   f"Bounce rate {rate:.1%} over 14 days", r["id"])
            alerts.raise_alert(cur, kind="mailbox_paused", severity="urgent", channel="#outbound-ops",
                               title=f"{r['address']} paused", body=f"Hard bounces {r['bounced']} of {r['sent']} in 14 days.",
                               object_kind="mailbox", object_id=r["id"], dedup_key=f"mbpause:{r['id']}:{r['sent']}")
        elif rate >= 0.015:
            alerts.raise_alert(cur, kind="mailbox_warn", severity="warn", channel="#outbound-ops",
                               title=f"{r['address']} bounce rate {rate:.1%}", body="Watch the data source.",
                               object_kind="mailbox", object_id=r["id"],
                               dedup_key=f"mbwarn:{r['id']}:{db.val(cur, 'select app_now()::date')}")


@jobs.handler("telemetry")
def telemetry(cur, payload: dict) -> None:
    domains = [r["domain"] for r in db.all(cur, "select domain from sending_domains")]
    for t in adapters.get().telemetry.domains(cur, domains):
        if t.spam_rate is None:
            db.run(cur, "update sending_domains set postmaster_status = 'unknown', checked_at = app_now() where domain = %s",
                   t.domain)
            continue
        db.run(cur, """update sending_domains set spam_rate = %s, spam_rate_at = app_now(), postmaster_status = %s,
                       checked_at = app_now() where domain = %s""", t.spam_rate, t.status, t.domain)
        if t.spam_rate >= 0.003:
            db.run(cur, "update mailboxes set status = 'paused', pause_reason = 'Domain spam rate at or above 0.3%%' "
                        "where domain = %s and status = 'active'", t.domain)
            alerts.raise_alert(cur, kind="spam_rate", severity="urgent", channel="#outbound-ops",
                               title=f"{t.domain} spam rate {t.spam_rate:.2%}", body="Every mailbox on it is paused.",
                               dedup_key=f"spam:{t.domain}:{db.val(cur, 'select app_now()::date')}")
