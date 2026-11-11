"""Replies. Stop first, in the same transaction the reply is stored. Then clean, label (rules, then the model),
check the model's side facts in code, and act (docs/SPEC.md sections 12, 22.2 and 22.19)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from . import alerts, audit, db, jobs, llm, outreach, plays, sending, signals, timeutil
from .db import J

log = logging.getLogger("outbound.replies")
HOT = {"interested", "meeting_request", "question"}
NO_PERSON_NEEDED = {"out_of_office", "auto_reply"}

QUOTE_HEADERS = [
    re.compile(r"^On .{3,120}wrote:\s*$", re.M),
    re.compile(r"^El .{3,120}escribió:\s*$", re.M),
    re.compile(r"^Am .{3,120}schrieb .{0,80}:\s*$", re.M),
    re.compile(r"^Le .{3,120}a écrit\s*:\s*$", re.M),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.M | re.I),
    re.compile(r"^From: .+$\n^(Sent|Date): .+$", re.M),
]
SIGNATURE = [re.compile(r"^--\s*$", re.M), re.compile(r"^Sent from my (iPhone|iPad|Android|mobile)", re.M | re.I),
             re.compile(r"^(Best|Thanks|Regards|Cheers|Kind regards|Best regards|Saludos|Grüße|Cordialement),?\s*$",
                        re.M | re.I)]
LEGAL = re.compile(r"(this (e-?mail|message) and any attachments? (is|are) confidential|if you (have )?received this "
                   r"(e-?mail|message) in error)", re.I)
OPT_OUT = re.compile(r"\b(unsubscribe|remove me|stop emailing|take me off|opt[ -]?out|do not (contact|email) me|"
                     r"keine weiteren e-?mails|abmelden|no me envíen|darme de baja|ne plus me contacter|"
                     r"désinscri|não quero receber|remover meu e-?mail)\b", re.I)
OOO = re.compile(r"\b(out of (the )?office|on (annual )?leave|automatic reply|auto-?reply|abwesenheit\w*|"
                 r"fuera de la oficina|absent du bureau|ausente)\b", re.I)
BOUNCE_FROM = re.compile(r"^(mailer-daemon|postmaster)@", re.I)
LEFT = re.compile(r"\b(no longer (with|at)|has left the company|left the company|is no longer employed)\b", re.I)
# Only a company the person actually named: "I'm now at Kestrel Health." Nothing is guessed.
NEW_CO = re.compile(r"\b(?:now at|now with|joined|moved to)\s+([A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*){0,3})")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], start=1)}


def clean(raw: str) -> str:
    """The words the person typed: no quoted history, no signature, no legal footer. Never empty."""
    text = raw.replace("\r\n", "\n")
    cut = len(text)
    for rx in QUOTE_HEADERS:
        m = rx.search(text)
        if m:
            cut = min(cut, m.start())
    lines = text[:cut].split("\n")
    lines = [ln for ln in lines if not ln.lstrip().startswith(">")]
    text = "\n".join(lines)
    for rx in SIGNATURE:
        m = rx.search(text)
        if m and m.start() > 0:
            text = text[:m.start()]
    m = LEGAL.search(text)
    if m:
        text = text[:m.start()]
    text = text.strip()
    return text or raw.strip()[:500]


def detect_language(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(bitte|nicht|ich|und|termin|grüße)\b", t):
        return "de"
    if re.search(r"\b(por favor|gracias|hola|semana|correos)\b", t):
        return "es"
    if re.search(r"\b(merci|bonjour|ne plus|semaine)\b", t):
        return "fr"
    if re.search(r"\b(obrigad|não|semana que vem)\b", t):
        return "pt"
    return "en"


def rules_label(from_addr: str, subject: str | None, cleaned: str) -> tuple[str, float] | None:
    if BOUNCE_FROM.search(from_addr) or (subject or "").lower().startswith(("undeliverable", "delivery status notification",
                                                                             "mail delivery failed")):
        return "bounce", 1.0
    if OOO.search(cleaned) or (subject or "").lower().startswith(("automatic reply", "out of office", "autoreply")):
        return "out_of_office", 0.97
    if OPT_OUT.search(cleaned) and len(cleaned.split()) <= 25:
        return "unsubscribe", 0.96
    if LEFT.search(cleaned):
        return "left_company", 0.9
    return None


def parse_return(text: str | None, received: datetime) -> datetime | None:
    if not text:
        return None
    t = text.lower()
    if re.match(r"\d{4}-\d{2}-\d{2}", t):
        try:
            d = datetime.fromisoformat(t[:10])
            return received.replace(year=d.year, month=d.month, day=d.day, hour=9, minute=0)
        except ValueError:
            return None
    for name, num in MONTHS.items():
        if name in t:
            day = re.search(r"(\d{1,2})\s+" + name, t)
            year = received.year + (1 if num < received.month else 0)
            try:
                return received.replace(year=year, month=num, day=int(day.group(1)) if day else 1, hour=9, minute=0)
            except ValueError:
                return None
    return None


def match(cur, from_addr: str, thread_key: str | None) -> dict:
    """By thread, then sender email, then sender domain. Never drops an unmatched reply."""
    if thread_key:
        m = db.one(cur, """select m.id as message_id, e.person_id, ap.account_id from messages m
                           join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
                           where m.thread_key = %s or m.provider_id = %s order by m.sent_at desc nulls last limit 1""",
                   thread_key, thread_key)
        if m:
            return m
    addr = from_addr.strip().lower()
    p = db.one(cur, "select id, account_id from people where email = %s", addr)
    if p:
        last = db.val(cur, """select m.id from messages m join enrollments e on e.id = m.enrollment_id
                              where e.person_id = %s and m.status = 'sent' order by m.sent_at desc limit 1""", p["id"])
        return {"message_id": last, "person_id": p["id"], "account_id": p["account_id"]}
    aid, _ = signals.resolve_account(cur, addr, None)
    return {"message_id": None, "person_id": None, "account_id": aid}


def ingest(cur, *, from_addr: str, subject: str | None, raw: str, received_at: datetime, thread_key: str | None = None,
           channel: str = "email", provider_id: str | None = None, person_id: int | None = None) -> int | None:
    """Store, stop first, then queue classification. Returns the reply id (None for a duplicate). A LinkedIn message
    comes with the person already known."""
    if person_id is not None:
        p = db.one(cur, "select id, account_id from people where id = %s", person_id)
        found = {"message_id": db.val(cur, """select m.id from messages m join enrollments e on e.id = m.enrollment_id
                                             where e.person_id = %s and m.status = 'sent' and m.channel = %s
                                             order by m.sent_at desc limit 1""", person_id, channel),
                 "person_id": p["id"], "account_id": p["account_id"]}
    else:
        found = match(cur, from_addr, thread_key)
    cleaned = clean(raw)
    row = db.one(cur, """insert into replies (message_id, person_id, account_id, channel, received_at, from_addr, subject,
                                              raw, cleaned, language, provider_id)
                         values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (provider_id) do nothing returning id""",
                 found["message_id"], found["person_id"], found["account_id"], channel, received_at, from_addr.lower(),
                 subject, raw, cleaned, detect_language(cleaned), provider_id)
    if row is None:
        return None
    rid = row["id"]
    if found["person_id"] or found["account_id"]:
        stop_first(cur, found["person_id"], found["account_id"], rid)
    if found["person_id"]:
        db.run(cur, """insert into touches (account_id, person_id, channel, direction, kind, at, source, dedup_key,
                                            account_play_id)
                       values (%s,%s,%s,'in','reply',%s,'desk',%s,
                               (select e.account_play_id from enrollments e where e.person_id = %s
                                order by e.created_at desc limit 1))""",
               found["account_id"], found["person_id"], "linkedin" if channel == "linkedin" else "email", received_at,
               f"reply:{rid}", found["person_id"])
    jobs.enqueue(cur, "classify_reply", {"reply_id": rid}, dedupe_key=f"classify:{rid}")
    return rid


def stop_first(cur, person_id: int | None, account_id: int | None, reply_id: int) -> None:
    if person_id:
        db.run(cur, """update enrollments set state = 'paused', pause_reason = 'reply_received'
                       where person_id = %s and state = 'active'""", person_id)
    if account_id:
        # A pause keeps each person's planned time, so a resume never brings a colleague's first email forward.
        db.run(cur, """update enrollments e set state = 'paused', pause_reason = 'account_reply'
                       from account_plays ap where ap.id = e.account_play_id and ap.account_id = %s
                       and e.state = 'active' and e.person_id is distinct from %s""", account_id, person_id)
    db.run(cur, """update messages set status = 'approved' where status = 'scheduled' and enrollment_id in
                   (select id from enrollments where state = 'paused' and person_id in
                    (select p.id from people p where p.account_id = %s or p.id = %s))""", account_id or 0, person_id or 0)


@jobs.handler("classify_reply")
def classify_job(cur, payload: dict) -> None:
    r = db.one(cur, "select * from replies where id = %s for update", payload["reply_id"])
    if r["label"] is not None:
        return
    ruled = rules_label(r["from_addr"], r["subject"], r["cleaned"])
    extracted: dict = {}
    same_person = True
    if ruled:
        label, conf = ruled
        by = "rules"
        if label == "left_company":
            m = NEW_CO.search(r["cleaned"])
            if m:
                extracted["new_company"] = m.group(1).strip()
        if label == "out_of_office":
            extracted["return_date"] = None
            m = re.search(r"(?:until|return(?:ing)? on|bis|hasta|jusqu'au)\s+(\d{1,2}\s+\w+|\w+\s+\d{1,2})", r["cleaned"], re.I)
            if m:
                extracted["return_text"] = m.group(1)
    else:
        out = llm.run(cur, "classify", {"cleaned": r["cleaned"], "subject": r["subject"], "language_hint": r["language"]},
                      account_id=r["account_id"])
        label, conf, by = out["label"], out["confidence"], "model"
        same_person = out["same_person"]
        extracted = {k: out[k] for k in ("return_date", "new_company") if out.get(k)}
        if out.get("referral"):
            ref = dict(out["referral"])
            # The model may name who; an address counts only if it is really in the reply.
            if ref.get("email") and ref["email"].lower() not in r["raw"].lower():
                ref["email"] = None
                extracted["referral_email_dropped"] = True
            extracted["referral"] = ref
        if out["instructs_system"]:
            db.run(cur, "update replies set needs_review = true, review_reason = 'The text tries to instruct the system' "
                        "where id = %s", r["id"])
    needs_review = conf < 0.7 or (not same_person and label not in NO_PERSON_NEEDED | {"bounce"})
    db.run(cur, """update replies set label = %s, confidence = %s, classified_by = %s, extracted = %s, same_person = %s,
                   hot = %s, needs_review = needs_review or %s,
                   review_reason = coalesce(review_reason, case when %s then %s end) where id = %s""",
           label, conf, by, J(extracted), same_person, label in HOT, needs_review, needs_review,
           "Low confidence" if conf < 0.7 else "Written by someone else", r["id"])
    r = db.one(cur, "select * from replies where id = %s", r["id"])
    if r["needs_review"]:
        _review_task(cur, r)
        return
    act(cur, r)


def _owner_of(cur, r: dict) -> int | None:
    return db.val(cur, """select coalesce(ap.owner_id, a.owner_id) from accounts a left join account_plays ap
                          on ap.account_id = a.id and ap.state in ('proposed','accepted','researching','approving','active',
                          'engaged','meeting') where a.id = %s limit 1""", r["account_id"]) if r["account_id"] else None


def _review_task(cur, r: dict) -> None:
    owner = _owner_of(cur, r) or db.val(cur, "select id from users where role = 'gtm' limit 1")
    db.run(cur, """insert into tasks (person_id, reply_id, kind, title, due_at, owner_id)
                   values (%s,%s,'review_reply',%s,app_now(),%s)""", r["person_id"], r["id"],
           "Read and label a reply the desk was unsure about", owner)


def _open_play(cur, account_id: int | None) -> dict | None:
    if not account_id:
        return None
    return db.one(cur, """select * from account_plays where account_id = %s and state in
                          ('proposed','accepted','researching','approving','active','engaged','meeting')""", account_id)


def _resume_others(cur, account_id: int, except_person: int | None) -> None:
    for e in db.all(cur, """select e.id from enrollments e join account_plays ap on ap.id = e.account_play_id
                            where ap.account_id = %s and e.state = 'paused' and e.pause_reason = 'account_reply'
                            and e.person_id is distinct from %s""", account_id, except_person):
        resume(cur, e["id"])


def resume(cur, enrollment_id: int, at: datetime | None = None) -> None:
    now = db.val(cur, "select app_now()")
    planned = db.val(cur, "select next_at from enrollments where id = %s", enrollment_id)
    at = max(at or now, now, planned or now)
    db.run(cur, "update enrollments set state = 'active', pause_reason = null, pause_until = null, next_at = %s "
                "where id = %s and state = 'paused'", at, enrollment_id)
    m = db.one(cur, """select m.id from messages m join enrollments e on e.id = m.enrollment_id
                       where m.enrollment_id = %s and m.step_index = e.step_index and m.status = 'approved'""", enrollment_id)
    if m:
        outreach.schedule_message(cur, m["id"])


def _stop_person(cur, person_id: int, reason: str) -> None:
    for e in db.all(cur, "select id from enrollments where person_id = %s and state in ('pending','active','paused')",
                    person_id):
        outreach.stop_enrollment(cur, e["id"], reason, close_play=False)


def _sla(cur, r: dict, owner: int) -> datetime:
    u = db.one(cur, "select timezone from users where id = %s", owner)
    hours = float(db.val(cur, "select value from settings where key = 'sla_business_hours'") or 4)
    return timeutil.add_business_hours(r["received_at"], hours, timezone=u["timezone"])


def act(cur, r: dict) -> None:
    label, pid, aid = r["label"], r["person_id"], r["account_id"]
    ap = _open_play(cur, aid)
    owner = _owner_of(cur, r)
    timeutil.load_holidays(cur)
    if r["message_id"]:
        if label == "bounce":
            sending.record_delivery_event(cur, r["message_id"], "bounced_hard", {"reply_id": r["id"]})
    if label in NO_PERSON_NEEDED:
        db.run(cur, "update replies set handled_at = app_now(), outcome = 'auto' where id = %s", r["id"])
        back = parse_return(r["extracted"].get("return_date") or r["extracted"].get("return_text"), r["received_at"])
        if back is None:
            back = timeutil.add_business_days(r["received_at"], 5)
        else:
            back = timeutil.add_business_days(back, 1)
        if pid:
            for e in db.all(cur, "select id from enrollments where person_id = %s and state = 'paused' "
                                 "and pause_reason = 'reply_received'", pid):
                db.run(cur, "update enrollments set pause_until = %s, pause_reason = 'out_of_office' where id = %s", back, e["id"])
                jobs.enqueue(cur, "resume", {"enrollment_id": e["id"]}, run_at=back, dedupe_key=f"resume:{e['id']}")
        if aid:
            _resume_others(cur, aid, pid)
        return
    if label == "bounce":
        if pid:
            db.run(cur, "update people set email_status = 'invalid' where id = %s", pid)
            _stop_person(cur, pid, "bounced")
            _next_for_persona(cur, pid, ap)
        db.run(cur, "update replies set handled_at = app_now(), outcome = 'bounced' where id = %s", r["id"])
        if aid:
            _resume_others(cur, aid, pid)
        return
    if label == "unsubscribe":
        email = db.val(cur, "select email from people where id = %s", pid) if pid else r["from_addr"]
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email', %s, 'Asked to stop', 'reply')",
               (email or r["from_addr"]).lower())
        if pid:
            _stop_person(cur, pid, "unsubscribed")
        db.run(cur, """insert into crm_outbox (kind, payload, idempotency_key) values ('opt_out', %s, %s)
                       on conflict do nothing""", J({"email": email, "person_id": pid}), f"optout:{r['id']}")
        db.run(cur, "update replies set handled_at = app_now(), outcome = 'suppressed' where id = %s", r["id"])
        if aid:
            _resume_others(cur, aid, pid)
        return
    if label in HOT:
        if pid:
            _stop_person(cur, pid, "replied_positive")
        if ap and ap["state"] in ("active", "approving"):
            plays.set_state(cur, ap["id"], "engaged")
        owner = owner or db.val(cur, "select id from users where role = 'manager' limit 1")
        due = _sla(cur, r, owner)
        db.run(cur, "update replies set sla_due_at = %s where id = %s", due, r["id"])
        suggestion = llm.run(cur, "suggest_reply", {"label": label, "cleaned": r["cleaned"],
                                                    "first_name": db.val(cur, "select first_name from people where id = %s", pid)
                                                    if pid else None}, account_id=aid)
        db.run(cur, "update replies set extracted = extracted || %s where id = %s", J({"suggested": suggestion["body"]}), r["id"])
        db.run(cur, """insert into tasks (account_play_id, person_id, reply_id, kind, title, due_at, owner_id)
                       values (%s,%s,%s,'reply',%s,%s,%s)""", ap["id"] if ap else None, pid, r["id"],
               "Answer a reply", due, owner)
        acct = db.one(cur, "select name, primary_domain from accounts where id = %s", aid) if aid else None
        if acct:
            chan = "#acct-" + acct["primary_domain"].split(".")[0][:60]
            alerts.raise_alert(cur, kind="hot_reply", severity="urgent", channel=chan, target_user=owner,
                               object_kind="reply", object_id=r["id"], title=f"{acct['name']} replied",
                               body=r["cleaned"][:400], dedup_key=f"hot:{r['id']}")
        db.run(cur, """insert into crm_outbox (kind, payload, idempotency_key) values ('task', %s, %s) on conflict do nothing""",
               J({"type": "hot_reply", "reply_id": r["id"], "person_id": pid, "owner": owner}), f"task:reply:{r['id']}")
        jobs.enqueue(cur, "resume_after_positive", {"account_id": aid, "person_id": pid},
                     run_at=timeutil.add_business_days(r["received_at"], 3), dedupe_key=f"rap:{r['id']}")
        return
    # Before the desk has written to anyone, a reply is recorded and shown to the owner; no play state changes (22.19).
    if ap and ap["state"] in ("proposed", "accepted", "researching"):
        if label in ("not_now", "not_interested") and aid:
            alerts.raise_alert(cur, kind="early_reply", severity="info", channel="#outbound-ops", target_user=ap["owner_id"],
                               object_kind="reply", object_id=r["id"], title="A reply arrived before any outreach",
                               body=r["cleaned"][:300], dedup_key=f"early:{r['id']}")
        db.run(cur, "update replies set handled_at = app_now(), outcome = 'noted_before_outreach' where id = %s", r["id"])
        return
    # Everything else stops the person; the account's others resume unless the play ends.
    if pid:
        _stop_person(cur, pid, label)
    if label == "not_now":
        until = parse_return(r["extracted"].get("return_date"), r["received_at"]) or (r["received_at"] + timedelta(days=90))
        if ap:
            plays.set_state(cur, ap["id"], "stopped", reason="not_now", cooldown_key="manual")
        db.run(cur, "insert into holds (account_id, reason, until, set_by) values (%s, 'Asked us to come back later', %s, 'reply')",
               aid, until)
    elif label == "not_interested":
        if ap:
            plays.set_state(cur, ap["id"], "lost", reason="not_interested")
    elif label == "referral":
        ref = r["extracted"].get("referral") or {}
        if ref.get("name") and aid:
            jobs.enqueue(cur, "enroll_referral", {"reply_id": r["id"]}, dedupe_key=f"referral:{r['id']}")
        else:
            db.run(cur, """insert into tasks (account_play_id, person_id, reply_id, kind, title, due_at, owner_id, note)
                           values (%s,%s,%s,'referral',%s,app_now(),%s,%s)""", ap["id"] if ap else None, pid, r["id"],
                   "Referred to a colleague", owner, "The reply did not name them clearly.")
        if aid:
            _resume_others(cur, aid, pid)
    elif label == "left_company":
        if pid:
            db.run(cur, "update people set status = 'left' where id = %s", pid)
            _next_for_persona(cur, pid, ap)
            _moved_signal(cur, r, pid)
        if aid:
            _resume_others(cur, aid, pid)
    elif label == "wrong_person":
        if pid:
            _next_for_persona(cur, pid, ap)
        if aid:
            _resume_others(cur, aid, pid)
    else:
        _review_task(cur, r)
        return
    db.run(cur, "update replies set handled_at = app_now(), outcome = %s where id = %s", label, r["id"])
    audit.log(cur, "desk", "reply_acted", "reply", r["id"], {"label": label})


def _moved_signal(cur, r: dict, person_id: int) -> None:
    """'I have left; I am at X now' is a job change told by the person themselves: a signal at X. Unknown companies
    land in Signals, Not matched, for a person to resolve."""
    new_company = (r["extracted"] or {}).get("new_company")
    if not new_company:
        return
    from . import signals
    p = db.one(cur, "select full_name, email, linkedin_url, is_champion from people where id = %s", person_id)
    signals.ingest(cur, "replies", [{
        "type": "champion_moved" if p["is_champion"] else "job_change", "external_id": f"reply-{r['id']}",
        "observed_at": r["received_at"], "company": new_company, "strength": 0.8,
        "person": {"email": p["email"], "linkedin_url": p["linkedin_url"]},
        "evidence": {"summary": f"{p['full_name']} joined {new_company}.", "quote": r["cleaned"][:300]}}])


def _next_for_persona(cur, person_id: int, ap: dict | None) -> None:
    """Propose the next person for the same role at this account, if the play is still open."""
    if not ap or ap["state"] not in ("active", "approving", "engaged"):
        return
    persona = db.val(cur, "select persona_key from enrollments where person_id = %s and account_play_id = %s",
                     person_id, ap["id"])
    if persona:
        jobs.enqueue(cur, "replace_person", {"account_play_id": ap["id"], "persona_key": persona},
                     dedupe_key=f"replace:{ap['id']}:{persona}")


@jobs.handler("resume")
def resume_job(cur, payload: dict) -> None:
    e = db.one(cur, "select * from enrollments where id = %s", payload["enrollment_id"])
    if e and e["state"] == "paused" and e["pause_reason"] == "out_of_office":
        resume(cur, e["id"])


@jobs.handler("resume_after_positive")
def resume_after_positive(cur, payload: dict) -> None:
    if payload.get("account_id"):
        _resume_others(cur, payload["account_id"], payload.get("person_id"))


def handle(cur, reply_id: int, *, user_id: int, outcome: str, label: str | None = None) -> None:
    """A person answered the reply, or labelled one the desk was unsure about."""
    r = db.one(cur, "select * from replies where id = %s for update", reply_id)
    if label and (label != r["label"] or r["needs_review"]):
        db.run(cur, "update replies set label = %s, classified_by = 'person', needs_review = false, hot = %s, "
                    "handled_at = null where id = %s", label, label in HOT, reply_id)
        r = db.one(cur, "select * from replies where id = %s", reply_id)
        db.run(cur, "update tasks set status = 'done', done_at = app_now() where reply_id = %s and kind = 'review_reply'",
               reply_id)
        act(cur, r)
    db.run(cur, "update replies set handled_by = %s, handled_at = coalesce(handled_at, app_now()), outcome = %s "
                "where id = %s", user_id, outcome, reply_id)
    db.run(cur, "update tasks set status = 'done', done_at = app_now() where reply_id = %s and kind = 'reply' "
                "and status = 'open'", reply_id)
    audit.log(cur, "person", "reply_handled", "reply", reply_id, {"outcome": outcome}, actor_id=user_id)


@jobs.handler("sla_check")
def sla_check(cur, payload: dict) -> None:
    for r in db.all(cur, """select r.*, a.name from replies r join accounts a on a.id = r.account_id
                            where r.hot and r.handled_at is null and r.escalated_at is null and r.sla_due_at < app_now()"""):
        manager = db.val(cur, "select id from users where role = 'manager' limit 1")
        alerts.raise_alert(cur, kind="sla_missed", severity="urgent", channel="#outbound-ops", target_user=manager,
                           object_kind="reply", object_id=r["id"], title=f"Reply from {r['name']} still unanswered",
                           body="Past the response time.", dedup_key=f"sla:{r['id']}")
        db.run(cur, "update replies set escalated_at = app_now() where id = %s", r["id"])
