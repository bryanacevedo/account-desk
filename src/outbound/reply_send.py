"""Answering a reply from the desk (bl_121, decision 90; SPEC 23.4).

A reply is a person writing back, not a step in a sequence, so its send has its own table (`reply_sends`), its own
reason set and its own database guard (migration 0038). The reasons here are not `gate.person_reasons`: its cooldown
and consent rules exist to stop cold outreach and would refuse every answer to someone who wrote to us. What stays is
what protects the person and the sender: a reply that asks us to stop, a bounce or an automatic message is never
answered; suppression, erasure, a person who left, the kill switch and the daily caps hold as they do for any email.
A blocked country does not stop a reply: they wrote to us first (Bryan, 2026-11-15, decision 92; Risk: legal, counsel
to confirm). A first email keeps the rule.

The send is an outbox row and a job, never one transaction: the row is committed first, the job asks the database
guard to let it go, and only then is the provider called.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import adapters, audit, db, jobs, outreach, replies
from .config import CONFIG

log = logging.getLogger("outbound.reply_send")

# Labels that are never answered, and what the desk did instead (shown where the editor would be).
NO_SEND = {
    "unsubscribe": "They asked to stop. The desk added them to the do-not-contact list and will not write to them.",
    "bounce": "The address did not work. The desk marked it and stopped the sequence.",
    "out_of_office": "An automatic out-of-office message. The desk paused the sequence until they are back.",
    "auto_reply": "An automatic reply. Nothing needs an answer.",
}
MAX_REFINES = 10


@dataclass
class Refusal:
    code: str
    message: str


def refusal(cur, r: dict) -> Refusal | None:
    """Why this reply may not be answered from the desk, or None. Asked when the page loads, again on Send, and again
    by the job, so a reply that is labelled late as an unsubscribe is refused at the last step."""
    label = r["label"] or "other"
    if label in NO_SEND:
        return Refusal("label", NO_SEND[label])
    if replies.OPT_OUT.search(r["cleaned"] or "") or (r["needs_review"] and replies.OPT_OUT.search(r["review_reason"] or "")):
        return Refusal("asked_to_stop", "They may have asked us to stop. Read it and label it; nothing is sent meanwhile.")
    if r["needs_review"]:
        return Refusal("needs_review", "The desk is not sure what this reply means. Label it first.")
    if not r["person_id"]:
        return Refusal("no_person", "This reply is not tied to a person we emailed.")
    if r["same_person"] is False:
        return Refusal("someone_else", "It was written by someone other than the person we emailed. Answer from your own mail.")
    p = db.one(cur, "select * from people where id = %s", r["person_id"])
    if p is None or not p["email"]:
        return Refusal("no_address", "There is no address on file for them.")
    if p["status"] != "active":
        return Refusal("person_status", "They have left the company or cannot be reached.")
    if p["email_status"] == "invalid":
        return Refusal("address_invalid", "The address bounced. Nothing is sent to it.")
    later = db.all(cur, """select label, needs_review, cleaned from replies where person_id = %s and received_at > %s and id <> %s""",
                   r["person_id"], r["received_at"], r["id"])
    for x in later:  # stop first, read after: a newer message from them that is unread or asks to stop holds this one
        if x["label"] is None or x["needs_review"] or x["label"] == "unsubscribe" or replies.OPT_OUT.search(x["cleaned"] or ""):
            return Refusal("newer_reply", "They wrote again after this. Read the newer message first.")
    if db.val(cur, "select value from settings where key = 'kill_switch'"):
        return Refusal("kill_switch", "Sending is stopped for everyone.")
    if db.val(cur, """select exists (select 1 from suppressions s where (s.expires_at is null or s.expires_at > app_now())
                      and ((s.kind = 'email' and s.value in (%s, %s)) or (s.kind = 'person' and s.value = %s)
                        or (s.kind = 'account' and s.value = %s)
                        or (s.kind = 'domain' and s.value = split_part(%s, '@', 2))))""",
              p["email"], r["from_addr"], str(p["id"]), str(r["account_id"] or 0), p["email"]):
        return Refusal("suppressed", "They are on the do-not-contact list.")
    return None


def owner_of(cur, r: dict) -> int | None:
    """The SDR whose account it is: the latest play's owner, else the account's."""
    if not r["account_id"]:
        return None
    return db.val(cur, """select coalesce((select ap.owner_id from account_plays ap where ap.account_id = %s
                          order by ap.proposed_at desc limit 1), (select owner_id from accounts where id = %s))""",
                  r["account_id"], r["account_id"])


def mailbox_for(cur, r: dict, user: dict) -> dict | None:
    """The mailbox the thread used when it is healthy, else another of the same SDR's, else None."""
    owner = owner_of(cur, r) or user["id"]
    used = db.val(cur, "select mailbox_id from messages where id = %s", r["message_id"]) if r["message_id"] else None
    ids = ([used] if used else []) + [x["id"] for x in db.all(cur, "select id from mailboxes where user_id = %s order by id", owner)]
    for mid in dict.fromkeys(ids):
        m = db.one(cur, "select * from mailboxes where id = %s", mid)
        if m and not outreach.mailbox_sendable(cur, m):
            return m
    return None


def compose(cur, r: dict, person: dict, sender: dict, text: str) -> tuple[str, str]:
    """The subject and the whole email: what the person wrote, the signature and the footer the desk always adds."""
    text = text.split("\n\n--\n")[0].strip()
    subject = r["subject"] or r.get("our_subject") or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}".strip()
    footer = outreach.footer_for(person, f"reply:{r['id']}")
    signature = sender["name"] + (f"\n{CONFIG.sender_company}" if CONFIG.sender_company else "")
    return subject[:200], f"{text}\n\n{signature}\n\n{footer}"


def queue(cur, r: dict, user: dict, text: str) -> dict:
    """Checks, then queues the send. Raises ValueError with a message for the page, never partly writes."""
    from .copy_gate import check_suggestion
    why = refusal(cur, r)
    if why:
        raise ValueError(why.message)
    found = check_suggestion(text, r["cleaned"])
    if found:
        raise ValueError(found[0]["message"])
    if not text.strip():
        raise ValueError("There is nothing to send.")
    mailbox = mailbox_for(cur, r, user)
    if mailbox is None:
        raise LookupError("No healthy mailbox")
    person = db.one(cur, "select * from people where id = %s", r["person_id"])
    sender = db.one(cur, "select name from users where id = %s", mailbox["user_id"])
    subject, body = compose(cur, r, person, sender, text)
    if db.val(cur, "select exists (select 1 from reply_sends where reply_id = %s and status in ('queued', 'sending') and body <> %s)",
              r["id"], body):
        raise ValueError("A different answer to this reply is already on its way.")
    thread = db.val(cur, "select thread_key from messages where id = %s", r["message_id"]) if r["message_id"] else None
    row = db.one(cur, """insert into reply_sends (reply_id, user_id, person_id, mailbox_id, subject, body, thread_key, in_reply_to)
                         values (%s,%s,%s,%s,%s,%s,%s,%s)
                         on conflict (reply_id, body_hash) do update set
                           status = case when reply_sends.status in ('failed', 'cancelled') then 'queued' else reply_sends.status end,
                           error = case when reply_sends.status in ('failed', 'cancelled') then null else reply_sends.error end,
                           mailbox_id = excluded.mailbox_id, user_id = excluded.user_id returning *""",
                 r["id"], user["id"], person["id"], mailbox["id"], subject, body, thread, r["provider_id"])
    if row["status"] == "queued":
        jobs.enqueue(cur, "send_reply", {"reply_send_id": row["id"]}, dedupe_key=f"reply_send:{row['id']}", max_attempts=1)
        audit.log(cur, "person", "reply_send_queued", "reply", r["id"], {"reply_send_id": row["id"]}, actor_id=user["id"])
    return row


@jobs.handler("send_reply")
def send_reply(cur, payload: dict) -> None:
    import psycopg
    rs = db.one(cur, "select * from reply_sends where id = %s for update", payload["reply_send_id"])
    if rs is None or rs["status"] != "queued":
        return
    r = db.one(cur, "select * from replies where id = %s", rs["reply_id"])
    why = refusal(cur, r)  # the label may have changed since the page loaded
    if why:
        db.run(cur, "update reply_sends set status = 'cancelled', error = %s where id = %s", why.message, rs["id"])
        return
    if CONFIG.mode == "live" and (not CONFIG.live_send or getattr(adapters.get().email, "name", "").startswith("missing:")):
        db.run(cur, "update reply_sends set status = 'failed', error = %s where id = %s",
               "Sending is not switched on" if not CONFIG.live_send else "No mail provider is configured", rs["id"])
        return
    try:
        with cur.connection.transaction():
            db.run(cur, "update reply_sends set status = 'sending', sent_at = app_now() where id = %s", rs["id"])
    except psycopg.errors.RaiseException as exc:
        db.run(cur, "update reply_sends set status = 'failed', error = %s where id = %s",
               str(exc).split("\n")[0][:200], rs["id"])
        return
    jobs.enqueue(cur, "send_reply_provider", {"reply_send_id": rs["id"]}, dedupe_key=f"reply_provider:{rs['id']}", max_attempts=1)


@jobs.handler("send_reply_provider")
def send_reply_provider(cur, payload: dict) -> None:
    rs = db.one(cur, "select * from reply_sends where id = %s for update", payload["reply_send_id"])
    if rs is None or rs["status"] != "sending":
        return
    person = db.one(cur, "select * from people where id = %s", rs["person_id"])
    mailbox = db.one(cur, "select * from mailboxes where id = %s", rs["mailbox_id"])
    token = outreach.unsubscribe_token(person["id"])
    headers = {"X-Outbound-Reply": str(rs["id"]),
               "List-Unsubscribe": f"<{CONFIG.public_url}/u/{person['id']}-{token[:12]}>",
               "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    if rs["in_reply_to"]:
        headers["In-Reply-To"] = rs["in_reply_to"]
    message = {"id": f"reply-{rs['id']}", "kind": "reply", "subject": rs["subject"], "body": rs["body"],
               "thread_key": rs["thread_key"], "step_index": 0}
    try:
        result = adapters.get().email.send(cur, message, mailbox, person, headers)
    except Exception as exc:  # we cannot know whether it left
        result = adapters.SendResult("unknown", None, f"{type(exc).__name__}: {exc}")
    if result.outcome == "sent":
        record_sent(cur, rs, result.provider_id)
    elif result.outcome == "unknown":
        db.run(cur, "update reply_sends set status = 'send_unknown', error = %s where id = %s", result.error, rs["id"])
    else:
        db.run(cur, "update reply_sends set status = 'failed', sent_at = null, error = %s where id = %s",
               (result.error or "The provider refused it")[:200], rs["id"])


def record_sent(cur, rs: dict, provider_id: str | None) -> None:
    """The answer left: mark it, write the touch and the CRM activity, mark the reply answered, audit it."""
    db.run(cur, "update reply_sends set status = 'sent', provider_id = %s where id = %s", provider_id, rs["id"])
    r = db.one(cur, "select * from replies where id = %s", rs["reply_id"])
    if r["account_id"]:
        db.run(cur, """insert into touches (account_id, person_id, channel, direction, kind, at, source, dedup_key)
                       values (%s,%s,'email','out','reply_sent',app_now(),'desk',%s) on conflict do nothing""",
               r["account_id"], rs["person_id"], f"reply_send:{rs['id']}")
    db.run(cur, """insert into crm_outbox (kind, payload, idempotency_key) values ('activity', %s, %s)
                   on conflict do nothing""",
           db.J({"type": "email_sent", "person_id": rs["person_id"], "reply_send_id": rs["id"], "subject": rs["subject"]}),
           f"activity:reply:{rs['id']}")
    replies.handle(cur, r["id"], user_id=rs["user_id"], outcome="answered")
    audit.log(cur, "person", "reply_sent", "reply", r["id"], {"reply_send_id": rs["id"]}, actor_id=rs["user_id"])


def sweep(cur) -> None:
    """Answers left in 'sending' for more than 15 minutes: a worker died mid-send. Ask the provider, never resend."""
    from . import alerts
    for rs in db.all(cur, """select * from reply_sends where status = 'sending'
                             and sent_at < app_now() - interval '15 minutes' order by id for update skip locked"""):
        try:
            found = adapters.get().email.lookup(cur, f"reply-{rs['id']}")
        except Exception as exc:  # the provider cannot say
            found = adapters.SendResult("unknown", None, f"{type(exc).__name__}: {exc}")
        if found.outcome == "sent":
            record_sent(cur, rs, found.provider_id)
        elif found.outcome == "failed":  # it never left: it may be sent again from the page
            db.run(cur, "update reply_sends set status = 'failed', sent_at = null, error = %s where id = %s",
                   "It did not leave after a crash. Send it again.", rs["id"])
        else:
            db.run(cur, "update reply_sends set status = 'send_unknown', error = %s where id = %s",
                   "The provider cannot say whether it went out.", rs["id"])
            alerts.raise_alert(cur, kind="send_unknown", severity="warn", channel="#outbound-ops",
                               title="An answer's outcome is unknown",
                               body="The provider cannot say whether the answer went out. Check the mailbox's sent folder.",
                               object_kind="reply_send", object_id=rs["id"], dedup_key=f"unknown:reply:{rs['id']}")


def refines_left(cur, reply_id: int) -> int:
    used = db.val(cur, "select coalesce((extracted ->> '_refines')::int, 0) from replies where id = %s", reply_id)
    return max(0, MAX_REFINES - int(used or 0))


def refine(cur, r: dict, instruction: str, current: str) -> dict:
    """One rewrite of the person's current text along their instruction, checked like the first suggestion. Text with
    its problems is returned rather than nothing, so the person sees why."""
    from .copy_gate import check_suggestion
    if refines_left(cur, r["id"]) <= 0:
        raise ValueError(f"That is {MAX_REFINES} rewrites for this reply. Edit it by hand from here.")
    if not CONFIG.public_demo:  # the demo is shared: one visitor must not use up everyone's rewrites
        db.run(cur, "update replies set extracted = jsonb_set(extracted, '{_refines}', to_jsonb(coalesce((extracted ->> '_refines')::int, 0) + 1)) "
                    "where id = %s", r["id"])
    first = r.get("first_name")
    failures: list[str] = []
    body, found = current, []
    from . import llm
    for attempt in (1, 2):
        out = llm.run(cur, "refine_reply", {"label": r["label"], "cleaned": r["cleaned"], "first_name": first,
                                            "instruction": instruction, "current": current,
                                            **({"attempt": attempt, "failures": failures} if failures else {})},
                      account_id=r["account_id"])
        body = out["body"]
        found = check_suggestion(body, r["cleaned"])
        if not found:
            break
        failures = [x["message"] for x in found]
    return {"body": body, "problems": [x["message"] for x in found], "refines_left": refines_left(cur, r["id"])}


def view(cur, r: dict, user: dict) -> dict:
    """What the sheet needs: whether a person may answer, why not, and what was already sent."""
    why = refusal(cur, r)
    mailbox = mailbox_for(cur, r, user) if why is None else None
    sends = db.all(cur, "select id, status, subject, body, error, sent_at, created_at from reply_sends where reply_id = %s order by id desc",
                   r["id"])
    return {"can_send": why is None, "no_send": {"code": why.code, "message": why.message} if why else None,
            "from_mailbox": mailbox["address"] if mailbox else None, "refines_left": refines_left(cur, r["id"]), "sends": sends}

