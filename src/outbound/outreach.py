"""From an accepted account to approved first emails: research, the brief, the buying committee, verified
contacts, drafts that pass the copy checks, approval by autonomy stage, and the account calendar."""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import timedelta

from . import adapters, audit, copy_gate, db, gate, jobs, llm, plays, spend, timeutil
from . import sim_llm  # noqa: F401  registers the stand-in model tasks
from .config import CONFIG
from .db import J

log = logging.getLogger("outbound.outreach")
SENIORITY_RANK = {"c_suite": 4, "vp": 3, "director": 2, "manager": 1, "ic": 0}
EU_UK = {"GB", "DE", "FR", "NL", "ES", "IE", "IT", "BE", "SE", "DK", "PL", "AT", "PT", "FI"}
OUR_NAMES = [CONFIG.sender_company]


# ---------------------------------------------------------------- research

def _research_facts(cur, account: dict) -> None:
    cached = db.one(cur, "select fetched_at from research_cache where domain = %s and kind = 'pages' "
                         "and fetched_at > app_now() - interval '30 days'", account["primary_domain"])
    if cached:
        return
    with spend.paid_call(cur, "research", "pages", vendor="research", qty=0, purpose="research",
                         account_id=account["id"]) as info:
        pages = adapters.get().research.pages(cur, account)
        info["pages"] = len(pages)
    for pg in pages:
        exists = db.val(cur, "select exists (select 1 from facts where account_id = %s and kind = %s and text = %s)",
                        account["id"], "page:" + pg.kind, pg.text)
        if not exists:
            db.run(cur, """insert into facts (account_id, kind, text, source, source_url, observed_at)
                           values (%s,%s,%s,'research',%s,app_now())""", account["id"], "page:" + pg.kind, pg.text, pg.url)
    db.run(cur, """insert into research_cache (domain, kind, content, fetched_at) values (%s, 'pages', %s, app_now())
                   on conflict (domain, kind) do update set content = excluded.content, fetched_at = excluded.fetched_at""",
           account["primary_domain"], J([pg.__dict__ for pg in pages]))


def account_facts(cur, account_id: int, limit: int = 14) -> list[dict]:
    return db.all(cur, """
        (select id, kind, text, source_url, observed_at from facts
          where account_id = %s and kind like 'signal:%%' and observed_at > app_now() - interval '90 days'
          order by observed_at desc limit 8)
        union all
        (select id, kind, text, source_url, observed_at from facts
          where account_id = %s and kind not like 'signal:%%' order by observed_at desc limit 8)""",
        account_id, account_id)[:limit]


def write_brief(cur, ap: dict, account: dict) -> dict:
    facts = account_facts(cur, account["id"])
    payload = {"company": account["name"], "facts": [{"id": f["id"], "kind": f["kind"], "text": f["text"]} for f in facts],
               "why_now": ap["why_now"].get("summary")}
    out = llm.run(cur, "brief", payload, account_id=account["id"])
    valid_ids = {f["id"] for f in facts}
    kept = [x for x in out["findings"] if x["fact_ids"] and all(i in valid_ids for i in x["fact_ids"])]
    brief = {"findings": kept, "angle": out["angle"], "dropped": len(out["findings"]) - len(kept),
             "facts": {str(f["id"]): {"text": f["text"], "url": f["source_url"], "kind": f["kind"]} for f in facts}}
    db.run(cur, "update account_plays set brief = %s where id = %s", J(brief), ap["id"])
    return brief


# ---------------------------------------------------------------- committee

def _title_matches(title: str | None, patterns: list[str]) -> bool:
    t = (title or "").lower()
    return any(p in t for p in patterns)


def _persona_for(cur, title: str | None) -> str | None:
    for p in db.all(cur, "select key, title_patterns from personas"):
        if _title_matches(title, p["title_patterns"]):
            return p["key"]
    return None


def _enrollable(cur, person_id: int, ap_id: int) -> list[gate.Reason]:
    """Person-level reasons that matter at selection. Email problems are fixed by finding and verifying."""
    skip = {"no_email", "verify_due", "no_basis"}
    return [r for r in gate.person_reasons(cur, person_id, "email", account_play_id=ap_id) if r.code not in skip]


def _ensure_email(cur, person: dict, account: dict) -> str:
    """Find and verify. Returns valid | risky | invalid | missing."""
    ad = adapters.get()
    email = person["email"]
    if not email:
        with spend.paid_call(cur, "email_finder", "find", vendor="email_finder", qty=1, purpose="find email",
                             account_id=account["id"]) as info:
            email = ad.finder.find(cur, person, account["primary_domain"])
            info["found"] = bool(email)
        if not email:
            return "missing"
        clash = db.val(cur, "select id from people where email = %s and id <> %s", email.lower(), person["id"])
        if clash:
            return "missing"
        db.run(cur, "update people set email = %s where id = %s", email.lower(), person["id"])
    fresh = db.val(cur, """select email_status = 'valid' and email_verified_at > app_now() - interval '45 days'
                           from people where id = %s""", person["id"])
    if fresh:
        return "valid"
    with spend.paid_call(cur, "email_verifier", "verify", vendor="email_verifier", qty=1, purpose="verify email",
                         account_id=account["id"]) as info:
        status = ad.verifier.verify(cur, email)
        info["status"] = status
    db.run(cur, "update people set email_status = %s, email_verified_at = app_now(), email_verified_by = %s where id = %s",
           status, ad.verifier.name, person["id"])
    return status


def _record_basis(cur, person: dict, play: dict) -> str | None:
    rule = db.val(cur, "select rule from region_rules where country = %s", person["country"])
    if rule == "basis_required" and play.get("lia_ref"):
        db.run(cur, """insert into contact_basis (person_id, basis, recorded_by) values (%s, %s, null)
                       on conflict (person_id) do nothing""", person["id"], f"legitimate_interest:{play['lia_ref']}")
    return rule


def build_committee(cur, ap: dict, play: dict, account: dict) -> list[dict]:
    ad = adapters.get()
    personas = {p["key"]: p for p in db.all(cur, "select * from personas")}
    chosen: list[dict] = []
    gaps: dict[str, str] = {}
    trigger_person = db.val(cur, "select person_id from signals where id = %s", ap["trigger_signal_id"])
    used: set[int] = set()
    for key in play["personas"]:
        if len(chosen) >= play["max_people"]:
            break
        persona = personas[key]
        candidates = db.all(cur, """select * from people where account_id = %s and status = 'active'
                                    order by (id = %s) desc, id""", account["id"], trigger_person or 0)
        candidates = [c for c in candidates if c["id"] not in used and (
            _title_matches(c["title"], persona["title_patterns"]) or (c["id"] == trigger_person and key in ("controller", "cfo")))]
        if not candidates:
            with spend.paid_call(cur, "people_search", "search", vendor="people_search", qty=1, purpose="find people",
                                 account_id=account["id"]) as info:
                found = ad.people.search(cur, account, persona["title_patterns"], 3)
                info["found"] = len(found)
            for c in found:
                existing = db.val(cur, "select id from people where linkedin_url = %s", c.linkedin_url)
                if existing:
                    continue
                pid = db.val(cur, """insert into people (account_id, full_name, first_name, last_name, title, seniority,
                                                         linkedin_url, country, timezone, source)
                                     values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'people_search') returning id""",
                             account["id"], c.full_name, c.first_name, c.last_name, c.title, c.seniority, c.linkedin_url,
                             c.country, c.timezone)
                ad.people.saved(cur, c, pid)
            candidates = [c for c in db.all(cur, "select * from people where account_id = %s and status = 'active' "
                                                 "and source = 'people_search' order by id", account["id"])
                          if c["id"] not in used and _title_matches(c["title"], persona["title_patterns"])]
        candidates.sort(key=lambda c: (c["id"] != trigger_person, -SENIORITY_RANK.get(c["seniority"] or "", 0)))
        picked = None
        last_reason = "Nobody with this role found"
        for c in candidates:
            reasons = _enrollable(cur, c["id"], ap["id"])
            if reasons:
                last_reason = reasons[0].message
                continue
            rule = _record_basis(cur, c, play)
            if rule == "consent_required":
                last_reason = f"Email in {c['country']} needs consent first; the rep can call or connect instead"
                continue
            status = _ensure_email(cur, c, account)
            if status != "valid":
                last_reason = {"missing": "No email address found", "risky": "Email could not be confirmed",
                               "invalid": "Email address does not work"}[status]
                continue
            picked = c
            break
        if picked is None:
            gaps[key] = last_reason
            continue
        used.add(picked["id"])
        db.run(cur, "update people set persona_key = %s where id = %s", key, picked["id"])
        chosen.append({**picked, "persona_key": key})
    for key, reason in gaps.items():
        db.run(cur, """insert into committee_gaps (account_play_id, persona_key, reason) values (%s,%s,%s)
                       on conflict (account_play_id, persona_key) do update set reason = excluded.reason""",
               ap["id"], key, reason)
    return chosen


# ---------------------------------------------------------------- mailboxes and capacity

def mailbox_capacity(cur, mailbox: dict) -> int:
    weeks = max(0, int(db.val(cur, "select (app_now()::date - %s) / 7", mailbox["ramp_start"])))
    cap = min(int(db.val(cur, "select value from settings where key = 'mailbox_max_daily'") or 30), 5 + 5 * weeks)
    d = db.one(cur, "select * from sending_domains where domain = %s", mailbox["domain"])
    unknown_long = d["spam_rate"] is None and db.val(cur, "select coalesce(%s::timestamptz, '-infinity') < app_now() - interval '7 days'",
                                                     d["spam_rate_at"])
    if unknown_long or (d["spam_rate"] is not None and float(d["spam_rate"]) >= 0.001):
        cap = min(cap, 10)  # cannot gain capacity while complaints are unknown or high
    return cap


def mailbox_sendable(cur, mailbox: dict) -> str | None:
    """None when the mailbox may send today, else the reason it may not."""
    if mailbox["status"] != "active":
        return f"Paused: {mailbox['pause_reason']}"
    d = db.one(cur, "select *, (app_now()::date - registered_at) as age from sending_domains where domain = %s",
               mailbox["domain"])
    if not (d["spf"] and d["dkim"] and d["dmarc"] and d["dmarc_aligned"]):
        return "Domain authentication incomplete"
    if d["blocklisted"]:
        return "Domain is on a blocklist"
    if d["age"] < 30:
        return f"Domain is {d['age']} days old; 30 needed"
    if db.val(cur, "select app_now()::date - %s", mailbox["warmup_started"]) < 14:
        return "Warming up"
    if d["spam_rate"] is not None and float(d["spam_rate"]) >= 0.003:
        return "Domain spam rate at or above 0.3%"
    return None


def sent_today(cur, mailbox_id: int) -> int:
    return db.val(cur, """select count(*) from messages where mailbox_id = %s and status in ('sent', 'sending', 'send_unknown')
                          and sent_at >= date_trunc('day', app_now())""", mailbox_id)


def pick_mailbox(cur, owner_id: int, account_play_id: int) -> int | None:
    sticky = db.val(cur, """select mailbox_id from enrollments where account_play_id = %s and mailbox_id is not null
                            limit 1""", account_play_id)
    if sticky:
        return sticky
    best = None
    for m in db.all(cur, "select * from mailboxes where user_id = %s and status = 'active' order by id", owner_id):
        if mailbox_sendable(cur, m):
            continue
        load = db.val(cur, """select count(*) from enrollments where mailbox_id = %s and state in ('pending','active','paused')""",
                      m["id"])
        if best is None or load < best[0]:
            best = (load, m["id"])
    return best[1] if best else None


# ---------------------------------------------------------------- drafting

def footer_for(person: dict, message_id_hint: str) -> str:
    token = hashlib.sha256(f"unsub:{person['id']}:{CONFIG.webhook_secret}".encode()).hexdigest()[:20]
    url = f"{CONFIG.public_url}/u/{person['id']}/{token}"
    privacy = CONFIG.privacy_url if (person.get("country") or "") in EU_UK else None
    return copy_gate.footer(company=CONFIG.sender_company, address=CONFIG.sender_address, unsubscribe_url=url,
                            privacy_url=privacy)


def unsubscribe_token(person_id: int) -> str:
    return hashlib.sha256(f"unsub:{person_id}:{CONFIG.webhook_secret}".encode()).hexdigest()[:20]


def desk_steps(play: dict) -> list[int]:
    return [i for i, s in enumerate(play["sequence"]) if s["by"] == "desk"]


def draft_step(cur, enrollment_id: int, step_index: int) -> dict:
    e = db.one(cur, "select * from enrollments where id = %s", enrollment_id)
    ap = db.one(cur, "select * from account_plays where id = %s", e["account_play_id"])
    play = db.one(cur, "select * from plays where id = %s", ap["play_id"])
    account = db.one(cur, "select * from accounts where id = %s", ap["account_id"])
    person = db.one(cur, "select * from people where id = %s", e["person_id"])
    persona = db.one(cur, "select * from personas where key = %s", e["persona_key"])
    step = play["sequence"][step_index]
    owner = db.one(cur, "select name from users where id = %s", ap["owner_id"])
    facts = account_facts(cur, account["id"])
    fact_map = {f["id"]: f["text"] for f in facts}
    prev = db.one(cur, "select subject from messages where enrollment_id = %s and step_index < %s and channel = 'email' "
                       "order by step_index desc limit 1", enrollment_id, step_index)
    others = [r["body"] for r in db.all(cur, """select m.body from messages m join enrollments en on en.id = m.enrollment_id
                                               where en.account_play_id = %s and en.id <> %s and m.status not in
                                               ('rejected', 'cancelled')""", ap["id"], enrollment_id)]
    attempts = []
    failures: list[dict] = []
    out = None
    verdict = None
    for attempt in (1, 2):
        payload = {"company": account["name"], "sender": owner["name"], "angle": persona["angle"],
                   "play_angle": play["angle"], "brief": (ap["brief"] or {}).get("findings", []),
                   "person": {"id": person["id"], "first_name": copy_gate.clean_first_name(person["first_name"], person["full_name"]),
                              "title": person["title"]},
                   "step": {"index": step_index, "job": step["job"]},
                   "facts": [{"id": f["id"], "kind": f["kind"], "text": f["text"]} for f in facts],
                   "previous_subject": prev["subject"] if prev else None, "attempt": attempt,
                   "failures": [x["message"] for x in failures]}
        out = llm.run(cur, "draft", payload, account_id=account["id"])
        verdict = copy_gate.check(out, job=step["job"], person=person, account=account, facts=fact_map,
                                  our_names=OUR_NAMES, other_bodies=others)
        attempts.append({"attempt": attempt, "passed": verdict.passed, "failures": verdict.failures})
        if verdict.passed:
            break
        failures = verdict.failures
    body = copy_gate.assemble(out, sender_name=owner["name"], footer=footer_for(person, f"{enrollment_id}:{step_index}"))
    citations = sorted({i for s in out["sentences"] for i in (s.get("fact_ids") or [])})
    status = "awaiting_approval" if verdict.passed else "failed_gate"
    msg = db.one(cur, """
        insert into messages (enrollment_id, step_index, channel, subject, body, citations, status, gate, attempts,
                              template_key, mailbox_id, body_hash)
        values (%s,%s,'email',%s,%s,%s,%s,%s,%s,%s,%s,'')
        on conflict (enrollment_id, step_index) do update set subject = excluded.subject, body = excluded.body,
          citations = excluded.citations, status = excluded.status, gate = excluded.gate, attempts = excluded.attempts
        returning *""",
        enrollment_id, step_index, out["subject"], body, J({"ids": citations, "sentences": out["sentences"]}), status,
        J(verdict.as_dict()), J(attempts), f"{play['key']}:{step_index}", e["mailbox_id"])
    if status == "awaiting_approval":
        maybe_auto_approve(cur, msg["id"])
    return db.one(cur, "select * from messages where id = %s", msg["id"])


# ---------------------------------------------------------------- approval

def _sample(message_id: int) -> bool:
    return int(hashlib.sha256(f"sample:{message_id}".encode()).hexdigest()[:4], 16) % 5 == 0


def maybe_auto_approve(cur, message_id: int) -> bool:
    m = db.one(cur, """select m.*, pl.autonomy, a.fit_tier from messages m join enrollments e on e.id = m.enrollment_id
                       join account_plays ap on ap.id = e.account_play_id join plays pl on pl.id = ap.play_id
                       join accounts a on a.id = ap.account_id where m.id = %s""", message_id)
    if m["status"] != "awaiting_approval":
        return False
    mode = None
    if m["autonomy"] == "supervised" and m["step_index"] > 0 and not _sample(message_id):
        mode = "auto_supervised"
    elif m["autonomy"] == "autonomous" and m["fit_tier"] == "B":
        mode = "auto_autonomous"
    if mode is None:
        return False
    _approve(cur, m, user_id=None, mode=mode)
    return True


def approve(cur, message_id: int, *, user_id: int, subject: str | None = None, body: str | None = None) -> dict:
    m = db.one(cur, "select * from messages where id = %s for update", message_id)
    if m["status"] not in ("awaiting_approval", "failed_gate"):
        raise ValueError(f"Message is {m['status']}, not waiting for approval")
    edited = False
    if (subject is not None and subject != m["subject"]) or (body is not None and body != m["body"]):
        edited = True
        db.run(cur, "update messages set subject = coalesce(%s, subject), body = coalesce(%s, body), edited = true "
                    "where id = %s", subject, body, message_id)
        m = db.one(cur, "select * from messages where id = %s", message_id)
        problems = _edit_checks(m)
        if problems:
            raise ValueError("; ".join(problems))
    _approve(cur, m, user_id=user_id, mode="person")
    audit.log(cur, "person", "approved", "message", message_id, {"edited": edited}, actor_id=user_id)
    return db.one(cur, "select * from messages where id = %s", message_id)


def _edit_checks(m: dict) -> list[str]:
    """A person's edit still has to keep the footer, and stay clear of dashes and merge fields."""
    out = []
    if "won't write again" not in m["body"]:
        out.append("The opt-out line at the bottom has to stay")
    if any(d in m["body"] for d in copy_gate.DASHES):
        out.append("Long dashes are not allowed")
    if copy_gate.MERGE.search(m["body"]):
        out.append("A merge field is not filled in")
    return out


def _approve(cur, m: dict, *, user_id: int | None, mode: str) -> None:
    db.run(cur, """update messages set status = 'approved', approved_hash = body_hash, approved_by = %s,
                   approval_mode = %s, approved_at = app_now() where id = %s""", user_id, mode, m["id"])
    e = db.one(cur, "select * from enrollments where id = %s", m["enrollment_id"])
    if e["state"] == "pending":
        activate(cur, e["id"])
    else:
        schedule_message(cur, m["id"])


def reject(cur, message_id: int, *, user_id: int, reason: str, skip_person: bool = False) -> None:
    if not reason:
        raise ValueError("A rejection needs a reason")
    db.run(cur, "update messages set status = 'rejected', rejected_reason = %s where id = %s", reason, message_id)
    audit.log(cur, "person", "rejected", "message", message_id, {"reason": reason}, actor_id=user_id)
    m = db.one(cur, "select * from messages where id = %s", message_id)
    if skip_person or m["step_index"] == 0:
        stop_enrollment(cur, m["enrollment_id"], "rejected: " + reason)
    else:
        advance(cur, m["enrollment_id"], skipped=True)


# ---------------------------------------------------------------- calendar and sequence

def activate(cur, enrollment_id: int) -> None:
    """Step 1 was approved. Lay the person onto the account calendar, staggered behind colleagues."""
    e = db.one(cur, "select * from enrollments where id = %s", enrollment_id)
    ap = db.one(cur, "select * from account_plays where id = %s", e["account_play_id"])
    person = db.one(cur, "select * from people where id = %s", e["person_id"])
    stagger = int(db.val(cur, "select value from settings where key = 'stagger_days'") or 2)
    order = db.val(cur, """select count(*) from enrollments where account_play_id = %s and state in ('active','done','paused')
                           and started_at is not null""", ap["id"])
    now = db.val(cur, "select app_now()")
    start = timeutil.add_business_days(now, stagger * order, country=person["country"], timezone=person["timezone"]) \
        if order else now
    db.run(cur, "update enrollments set state = 'active', started_at = %s, next_at = %s, step_index = 0 where id = %s",
           start, start, enrollment_id)
    if ap["state"] == "approving":
        plays.set_state(cur, ap["id"], "active")
    m = db.one(cur, "select id from messages where enrollment_id = %s and step_index = 0", enrollment_id)
    if m:
        schedule_message(cur, m["id"])


def _window(cur):
    return timeutil.windows(db.val(cur, "select value from settings where key = 'send_window'"))


def schedule_message(cur, message_id: int) -> None:
    m = db.one(cur, "select * from messages where id = %s", message_id)
    e = db.one(cur, "select * from enrollments where id = %s", m["enrollment_id"])
    if e["state"] != "active" or m["status"] != "approved":
        return
    p = db.one(cur, "select timezone, country from people where id = %s", e["person_id"])
    planned = max(e["next_at"] or db.val(cur, "select app_now()"), db.val(cur, "select app_now()"))
    slot = timeutil.next_slot(planned, timezone=p["timezone"], country=p["country"], window=_window(cur),
                              jitter_key=f"m{message_id}")
    db.run(cur, "update messages set status = 'scheduled', scheduled_for = %s, planned_for = coalesce(planned_for, %s) "
                "where id = %s", slot, planned, message_id)


def stop_enrollment(cur, enrollment_id: int, reason: str) -> None:
    db.run(cur, """update enrollments set state = 'stopped', stop_reason = %s, next_at = null
                   where id = %s and state in ('pending', 'active', 'paused')""", reason, enrollment_id)
    db.run(cur, """update messages set status = 'cancelled' where enrollment_id = %s
                   and status in ('draft', 'failed_gate', 'awaiting_approval', 'approved', 'scheduled')""", enrollment_id)


def advance(cur, enrollment_id: int, *, skipped: bool = False) -> None:
    """Move to the next step after the current one was sent, done by the rep, or skipped."""
    e = db.one(cur, "select * from enrollments where id = %s for update", enrollment_id)
    ap = db.one(cur, "select * from account_plays where id = %s", e["account_play_id"])
    play = db.one(cur, "select * from plays where id = %s", ap["play_id"])
    p = db.one(cur, "select timezone, country from people where id = %s", e["person_id"])
    seq = play["sequence"]
    nxt = e["step_index"] + 1
    if nxt >= len(seq):
        db.run(cur, "update enrollments set state = 'done', next_at = null, step_index = %s where id = %s", nxt, enrollment_id)
        return
    gap = seq[nxt]["day"] - seq[e["step_index"]]["day"]
    now = db.val(cur, "select app_now()")
    at = timeutil.add_business_days(now, max(gap, 1), country=p["country"], timezone=p["timezone"])
    db.run(cur, "update enrollments set step_index = %s, next_at = %s where id = %s", nxt, at, enrollment_id)
    if seq[nxt]["by"] == "desk" and e["state"] == "active":
        jobs.enqueue(cur, "draft_step", {"enrollment_id": enrollment_id, "step_index": nxt},
                     dedupe_key=f"draft:{enrollment_id}:{nxt}")


@jobs.handler("draft_step")
def _draft_job(cur, payload: dict) -> None:
    e = db.one(cur, "select state from enrollments where id = %s", payload["enrollment_id"])
    if e and e["state"] in ("active", "paused"):
        draft_step(cur, payload["enrollment_id"], payload["step_index"])


@jobs.handler("due_steps")
def due_steps(cur, payload: dict) -> None:
    """Rep steps become tasks when their day comes. Desk steps wait for approval and lapse after 5 business days."""
    timeutil.load_holidays(cur)
    lapse = int(db.val(cur, "select value from settings where key = 'approval_lapse_business_days'") or 5)
    now = db.val(cur, "select app_now()")
    rows = db.all(cur, """select e.*, ap.owner_id, pl.sequence, p.country, p.full_name, p.phone from enrollments e
                          join account_plays ap on ap.id = e.account_play_id join plays pl on pl.id = ap.play_id
                          join people p on p.id = e.person_id
                          where e.state = 'active' and e.next_at <= app_now() for update of e skip locked""")
    for e in rows:
        if e["step_index"] >= len(e["sequence"]):
            continue
        step = e["sequence"][e["step_index"]]
        if step["by"] == "rep":
            kind = {"linkedin_connect": "linkedin_connect", "linkedin_message": "linkedin_message", "call": "call"}[step["channel"]]
            title = {"linkedin_connect": f"Connect with {e['full_name']} on LinkedIn",
                     "linkedin_message": f"Message {e['full_name']} on LinkedIn",
                     "call": f"Call {e['full_name']}" + (f" ({e['phone']})" if e["phone"] else "")}[kind]
            db.run(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                           values (%s,%s,%s,%s,%s,%s)""", e["account_play_id"], e["person_id"], kind, title, now, e["owner_id"])
            advance(cur, e["id"])
            continue
        m = db.one(cur, "select * from messages where enrollment_id = %s and step_index = %s", e["id"], e["step_index"])
        if m is None:
            jobs.enqueue(cur, "draft_step", {"enrollment_id": e["id"], "step_index": e["step_index"]},
                         dedupe_key=f"draft:{e['id']}:{e['step_index']}")
        elif m["status"] == "approved":
            schedule_message(cur, m["id"])
        elif m["status"] in ("awaiting_approval", "failed_gate"):
            if timeutil.business_days_between(e["next_at"], now, e["country"]) > lapse:
                db.run(cur, "update messages set status = 'cancelled' where id = %s", m["id"])
                db.run(cur, "update enrollments set state = 'done', stop_reason = 'approval_lapsed', next_at = null "
                            "where id = %s", e["id"])
        elif m["status"] in ("rejected", "cancelled", "failed"):
            advance(cur, e["id"], skipped=True)


# ---------------------------------------------------------------- the research job

@jobs.handler("research")
def research_job(cur, payload: dict) -> None:
    ap = db.one(cur, "select * from account_plays where id = %s for update", payload["account_play_id"])
    if ap["state"] not in ("accepted", "researching"):
        return
    plays.set_state(cur, ap["id"], "researching")
    play = db.one(cur, "select * from plays where id = %s", ap["play_id"])
    account = db.one(cur, "select * from accounts where id = %s", ap["account_id"])
    try:
        _research_facts(cur, account)
    except spend.OverBudget:
        raise
    write_brief(cur, ap, account)
    people = build_committee(cur, ap, play, account)
    if not people:
        plays.set_state(cur, ap["id"], "stopped", reason="no_reachable_people")
        return
    if any(s["channel"] == "call" for s in play["sequence"]):
        for p in people:
            if not p["phone"]:
                try:
                    with spend.paid_call(cur, "phone_finder", "find", vendor="phone_finder", qty=1, purpose="find phone",
                                         account_id=account["id"]) as info:
                        phone = adapters.get().phone.find(cur, p)
                        info["found"] = bool(phone)
                except spend.OverBudget:
                    phone = None
                if phone:
                    db.run(cur, "update people set phone = %s, phone_status = 'valid', phone_verified_at = app_now() "
                                "where id = %s", phone, p["id"])
    enrollments = []
    for p in people:
        mailbox = pick_mailbox(cur, ap["owner_id"], ap["id"])
        eid = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, mailbox_id)
                             values (%s,%s,%s,'pending',%s) returning id""", ap["id"], p["id"], p["persona_key"], mailbox)
        enrollments.append(eid)
    if play["autonomy"] == "research":
        # The desk researched; the rep writes. Each person becomes a set of tasks.
        for eid in enrollments:
            e = db.one(cur, "select e.*, p.full_name from enrollments e join people p on p.id = e.person_id where e.id = %s", eid)
            db.run(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                           values (%s,%s,'research',%s,app_now(),%s)""", ap["id"], e["person_id"],
                   f"Write to {e['full_name']} using the brief", ap["owner_id"])
            db.run(cur, "update enrollments set state = 'done', stop_reason = 'rep_writes' where id = %s", eid)
        plays.set_state(cur, ap["id"], "approving")
        plays.set_state(cur, ap["id"], "active")
        return
    plays.set_state(cur, ap["id"], "approving")
    for eid in enrollments:
        draft_step(cur, eid, 0)
