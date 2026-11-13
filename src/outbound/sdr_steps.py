"""Steps an SDR does by hand: LinkedIn connect notes and messages, and calls.

The desk drafts the LinkedIn words through the same copy checks as email and keeps them as a message on the linkedin
channel. The SDR sends them from their own account and says what happened. Marking one sent goes through the database's
send guard, so a holdout account, a stopped play, a suppressed person or a text changed after approval is refused
exactly as an email would be. Every outcome is a touch, so cooldowns, measurement and the slow-first-touch check see
LinkedIn and calls, not only email.

What happens next follows docs/SPEC.md 22.19: an accepted connection is a touch and pauses nothing; a LinkedIn message
from the person is a reply; a call where they spoke means the SDR is in conversation, so the desk's own steps for that
person stop.
"""
from __future__ import annotations

import re

import psycopg

from . import audit, copy_gate, db, gate, replies
from .db import J

LINKEDIN_OUTCOMES = {
    "linkedin_connect": {"sent": "Connection request sent", "already_connected": "Already connected",
                         "no_profile": "Could not find the profile"},
    "linkedin_message": {"sent": "Message sent", "not_connected": "Not connected yet"},
}
CALL_OUTCOMES = {"connected": "Spoke with them", "voicemail": "Left a voicemail", "no_answer": "No answer",
                 "wrong_number": "Wrong number"}


def note_limit(cur) -> int:
    v = db.val(cur, "select value from settings where key = 'linkedin_note_max_chars'")
    return int(v) if v is not None else 200


def make_task(cur, e: dict, step: dict, now) -> int | None:
    """When an SDR step's day comes: check the person may be contacted on that channel, draft the LinkedIn words,
    and give the SDR a task. Returns the task id, or None when the step is skipped (the reason goes to the audit)."""
    from . import outreach
    kind = step["channel"] if step["channel"] in ("linkedin_connect", "linkedin_message") else "call"
    channel = "call" if kind == "call" else "linkedin"
    reasons = [r for r in gate.person_reasons(cur, e["person_id"], channel, account_play_id=e["account_play_id"],
                                              enrollment_id=e["id"]) if r.permanent and r.code != "cooldown"]
    p = db.one(cur, "select full_name, phone, phone_status, linkedin_url, country, timezone from people where id = %s",
               e["person_id"])
    if channel == "call" and (not p["phone"] or p["phone_status"] == "invalid"):
        reasons.append(gate.Reason("no_phone", True, "No working phone number"))
    due, register = now, None
    if channel == "call" and not reasons:
        # Calls wait for calling hours in the person's own time, and the task names the register screened.
        due = gate.next_call_time(cur, p, now)
        if due is None:
            reasons.append(gate.Reason("no_call_hours", True, "No calling hours in their time zone in the next ten days"))
        register = db.val(cur, "select dnc_register from region_rules where country = %s", p["country"])
    if channel == "linkedin" and not p["linkedin_url"]:
        reasons.append(gate.Reason("no_linkedin", True, "No LinkedIn profile on record"))
    if not reasons:  # a configured CRM is asked before a person's first touch; it fails closed (shared-world DESIGN.md 7, step 4)
        from . import pipeline
        verdict = pipeline.crm_first_touch(cur, e["person_id"], channel)
        if verdict != "ok":
            reasons.append(gate.Reason("crm_check", True, "The CRM flags this person" if verdict == "stopped"
                                       else "The CRM did not answer, so nothing is sent on a guess"))
    if reasons:
        audit.log(cur, "desk", "step_skipped", "enrollment", e["id"], {"step": e["step_index"], "why": reasons[0].message})
        return None
    message_id = None
    if channel == "linkedin":
        message_id = outreach.draft_step(cur, e["id"], e["step_index"])["id"]
    title = {"linkedin_connect": f"Connect with {p['full_name']} on LinkedIn",
             "linkedin_message": f"Message {p['full_name']} on LinkedIn",
             "call": f"Call {p['full_name']}" + (f" ({p['phone']})" if p["phone"] else "")}[kind]
    return db.val(cur, """insert into tasks (account_play_id, person_id, message_id, kind, title, due_at, owner_id,
                                             dnc_register)
                          values (%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                  e["account_play_id"], e["person_id"], message_id, kind, title, due, e["owner_id"], register)


def linkedin_edit_problems(cur, m: dict, text: str) -> list[str]:
    """A person's edit to a LinkedIn note, checked as text the way an email edit is."""
    out = []
    low = text.lower()
    out += [f"Uses \"{b}\"" for b in copy_gate.BANNED if b in low]
    if copy_gate.URL.search(text):
        out.append("LinkedIn notes and messages carry no links")
    if any(d in text for d in copy_gate.DASHES):
        out.append("Long dashes are not allowed")
    if copy_gate.MERGE.search(text):
        out.append("A merge field is not filled in")
    task_kind = db.val(cur, "select kind from tasks where message_id = %s limit 1", m["id"])
    if task_kind == "linkedin_connect" and len(text) > note_limit(cur):
        out.append(f"{len(text)} characters; a connect note fits in {note_limit(cur)}")
    from . import outreach
    acct = db.val(cur, "select ap.account_id from enrollments e join account_plays ap on ap.id = e.account_play_id "
                       "where e.id = %s", m["enrollment_id"])
    facts = " ".join(f["text"] for f in outreach.account_facts(cur, acct, 30))
    for num in copy_gate.NUMBER.findall(text):
        core = num.strip("$%.,")
        if core and core not in facts.replace(",", "") and not re.search(re.escape(num) + r"[- ]?(min|minutes|hour)", text):
            out.append(f"The number {num} is not in any fact we hold about them")
    return out


def complete(cur, task_id: int, *, user: dict, outcome: str, text: str | None = None, note: str | None = None) -> dict:
    """The SDR says what happened with a LinkedIn or call task. Raises ValueError with a plain reason when the desk
    refuses (for LinkedIn, the send guard: they replied, the play stopped, they opted out)."""
    t = db.one(cur, "select * from tasks where id = %s for update", task_id)
    if t is None or t["status"] != "open":
        raise ValueError("No open task with that id.")
    if user["role"] == "sdr" and t["owner_id"] not in (None, user["id"]):
        raise ValueError("This task belongs to another SDR.")
    if t["kind"] in LINKEDIN_OUTCOMES:
        allowed = LINKEDIN_OUTCOMES[t["kind"]]
    elif t["kind"] == "call":
        allowed = CALL_OUTCOMES
    else:
        allowed = {"done": "Done"}
    if outcome not in allowed and outcome != "skipped":
        raise ValueError(f"Outcome must be one of: {', '.join(allowed)}, skipped.")
    p = db.one(cur, "select id, account_id from people where id = %s", t["person_id"]) if t["person_id"] else None
    touch_kind = None
    if t["kind"] in LINKEDIN_OUTCOMES and outcome == "sent":
        m = db.one(cur, "select * from messages where id = %s for update", t["message_id"])
        if m is None:
            raise ValueError("This task has no drafted note.")
        if text is not None and text.strip() != m["body"]:
            problems = linkedin_edit_problems(cur, m, text.strip())
            if problems:
                raise ValueError("; ".join(problems))
            db.run(cur, "update messages set body = %s, edited = true where id = %s", text.strip(), m["id"])
        elif m["status"] == "failed_gate":
            raise ValueError("This note failed the checks. Edit it before sending.")
        try:
            with cur.connection.transaction():
                db.run(cur, """update messages set status = 'approved', approved_hash = body_hash, approved_by = %s,
                               approval_mode = 'person', approved_at = app_now() where id = %s""", user["id"], m["id"])
                db.run(cur, "update messages set status = 'sent', sent_at = app_now() where id = %s", m["id"])
        except psycopg.errors.RaiseException as exc:
            reason = str(exc).split("\n")[0].replace("send refused: ", "")
            db.run(cur, "update tasks set status = 'skipped', done_at = app_now(), note = %s where id = %s",
                   f"Not sent: {reason}", task_id)
            raise ValueError(f"The desk refused this: {reason}. The task is closed.") from None
        touch_kind = t["kind"]
    elif t["kind"] == "research" and outcome == "done" and t["person_id"] and t["title"].startswith("Write to"):
        # A research-stage play: the SDR wrote this email themselves. It is outreach, so it is recorded as such.
        touch_kind = "sdr_email"
    elif t["kind"] == "call" and outcome != "skipped":
        # Someone who opted out, asked for no calls or was erased is not called, whatever the task list says.
        blocked = [r for r in gate.person_reasons(cur, t["person_id"], "call") if r.permanent and r.code in
                   ("suppressed", "person_left", "person_unreachable", "phone_dnc", "no_call_rule", "call_blocked")]
        if blocked:
            db.run(cur, "update tasks set status = 'skipped', done_at = app_now(), note = %s where id = %s",
                   f"Not called: {blocked[0].message}", task_id)
            raise ValueError(f"The desk refused this: {blocked[0].message}. The task is closed.")
        touch_kind = f"call_{outcome}"
        if outcome == "wrong_number":
            db.run(cur, "update people set phone_status = 'invalid' where id = %s", t["person_id"])
    if touch_kind and p:
        db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source,
                                            message_id, dedup_key)
                       values (%s,%s,%s,%s,'out',%s,app_now(),'sdr',%s,%s) on conflict do nothing""",
               p["account_id"], p["id"], t["account_play_id"],
               {"call": "call", "research": "email"}.get(t["kind"], "linkedin"), touch_kind,
               t["message_id"], f"task:{task_id}")
    if t["kind"] == "call" and outcome == "connected" and p:
        in_conversation(cur, p["id"], t["account_play_id"])
    label = allowed.get(outcome, "Skipped")
    # A task's own note (why a referral could not be enrolled) is kept; the outcome goes in only where there was none.
    db.run(cur, "update tasks set status = %s, done_at = app_now(), note = coalesce(%s, note, %s) where id = %s",
           "skipped" if outcome == "skipped" else "done", note, label, task_id)
    if t["kind"] in ("linkedin_connect", "linkedin_message", "call"):
        db.run(cur, "insert into crm_outbox (kind, payload, idempotency_key) values ('activity', %s, %s) on conflict do nothing",
               J({"task_id": task_id, "kind": t["kind"], "outcome": outcome, "person_id": t["person_id"]}), f"task:{task_id}")
    audit.log(cur, "person", "task_" + outcome, "task", task_id, {"kind": t["kind"]}, actor_id=user["id"])
    return {"ok": True, "outcome": label}


def in_conversation(cur, person_id: int, account_play_id: int | None) -> None:
    """The SDR is talking to them: the desk's own steps for this person stop (docs/SPEC.md 22.19,
    rep_in_conversation). The send guard also refuses any email already approved for them in this play."""
    db.run(cur, """update enrollments set state = 'stopped', stop_reason = 'rep_in_conversation', next_at = null
                   where person_id = %s and state in ('pending', 'active', 'paused')""", person_id)
    db.run(cur, """update messages set status = 'cancelled' where status in ('approved', 'scheduled', 'awaiting_approval',
                   'failed_gate', 'draft') and enrollment_id in (select id from enrollments where person_id = %s)""", person_id)
    # They are talking to us: the play is engaged, as after a positive reply, so a meeting booked later still
    # belongs to it and can be credited to it.
    if account_play_id:
        from . import plays
        state = db.val(cur, "select state from account_plays where id = %s", account_play_id)
        if state == "approving":
            plays.set_state(cur, account_play_id, "active")
            state = "active"
        if state == "active":
            plays.set_state(cur, account_play_id, "engaged")


def connection_accepted(cur, person_id: int, *, user_id: int | None, source: str = "sdr") -> None:
    """They accepted the connection request: a touch from them that pauses nothing (22.19)."""
    p = db.one(cur, "select id, account_id from people where id = %s", person_id)
    ap = db.val(cur, "select account_play_id from enrollments where person_id = %s order by created_at desc limit 1", person_id)
    db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source, dedup_key)
                   values (%s,%s,%s,'linkedin','in','linkedin_accepted',app_now(),%s,%s) on conflict do nothing""",
           p["account_id"], person_id, ap, source, f"li_accept:{person_id}:{ap}")
    audit.log(cur, "person" if user_id else "desk", "linkedin_accepted", "person", person_id, {}, actor_id=user_id)


def linkedin_reply(cur, person_id: int, *, text: str, received_at, provider_id: str) -> int | None:
    """A LinkedIn message from them, pasted by the SDR or sent by a LinkedIn tool's webhook: a reply like any other,
    so it stops their steps first and is labelled the same way."""
    return replies.ingest(cur, from_addr=f"linkedin:{person_id}", subject=None, raw=text, received_at=received_at,
                          channel="linkedin", provider_id=provider_id, person_id=person_id)
