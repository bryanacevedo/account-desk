"""Signals: ingest from any source, resolve to an account, keep the evidence, and queue a rescore.

A source adapter returns raw dicts:
    {"type", "external_id", "observed_at", "domain" | "company", "strength", "evidence": {"summary", "url"|"quote"},
     "person": {"linkedin_url", "email", "name", "title", "from_domain"}  # person-level types only
    }
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Iterable

from . import audit, db, jobs
from .db import J

log = logging.getLogger("outbound.signals")

PUBLIC_EMAIL_DOMAINS = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com",
                        "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com", "gmx.de", "web.de"}
_SCHEME = re.compile(r"^[a-z]+://")


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    d = value.strip().lower()
    if "@" in d:
        d = d.split("@", 1)[1]
    d = _SCHEME.sub("", d).split("/", 1)[0].split(":", 1)[0].strip(".")
    if d.startswith("www."):
        d = d[4:]
    if not d or "." not in d or d in PUBLIC_EMAIL_DOMAINS:
        return None
    return d


def normalize_name(value: str | None) -> str:
    v = (value or "").lower()
    v = re.sub(r"[^a-z0-9 ]", " ", v)
    v = re.sub(r"\b(inc|ltd|llc|gmbh|sa|bv|plc|limited|corp|corporation|co)\b", " ", v)
    return " ".join(v.split())


def resolve_account(cur, domain: str | None, company: str | None) -> tuple[int | None, str | None]:
    d = normalize_domain(domain)
    if d:
        aid = db.val(cur, "select account_id from account_domains where domain = %s", d)
        if aid:
            return aid, None
        # A subdomain of a known domain (billing.acme.com) resolves to acme.com.
        parts = d.split(".")
        for i in range(1, len(parts) - 1):
            aid = db.val(cur, "select account_id from account_domains where domain = %s", ".".join(parts[i:]))
            if aid:
                return aid, None
    name = normalize_name(company)
    if name:
        hits = [r["id"] for r in db.all(cur, "select id from accounts where name_key = %s", name)]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, "company name matches more than one account"
    if domain and not d:
        return None, "domain is a public email provider or invalid"
    return None, "no account with this domain or name"


def resolve_person(cur, person: dict | None) -> int | None:
    if not person:
        return None
    if person.get("email"):
        pid = db.val(cur, "select id from people where email = %s", person["email"].strip().lower())
        if pid:
            return pid
    if person.get("linkedin_url"):
        return db.val(cur, "select id from people where linkedin_url = %s", person["linkedin_url"].strip())
    return None


def ingest(cur, source_key: str, raws: Iterable[dict]) -> dict:
    """Ingest one batch from one source. Records the run, so a silent source shows up on Health."""
    run_id = db.val(cur, "insert into source_runs (source_key) values (%s) returning id", source_key)
    counts = {"fetched": 0, "matched": 0, "unmatched": 0, "duplicates": 0}
    types = {r["key"]: r for r in db.all(cur, "select * from signal_types where enabled")}
    touched: set[int] = set()
    for raw in raws:
        counts["fetched"] += 1
        t = types.get(raw.get("type"))
        if t is None:
            counts["unmatched"] += 1
            continue
        # A source that already knows the account (enrichment) names it; feeds are matched by domain or name.
        account_id, reason = ((raw["account_id"], None) if raw.get("account_id")
                              else resolve_account(cur, raw.get("domain"), raw.get("company")))
        person_id = resolve_person(cur, raw.get("person")) if t["level"] == "person" else None
        status = "matched" if account_id else "unmatched"
        ev = raw["evidence"]
        row = db.one(cur, """
            insert into signals (type_key, source, external_id, account_id, person_id, raw_domain, raw_company,
                                 observed_at, strength, evidence, status, status_reason)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (source, external_id) do nothing returning id""",
            t["key"], source_key, str(raw["external_id"]), account_id, person_id, normalize_domain(raw.get("domain")),
            raw.get("company"), raw["observed_at"], max(0.0, min(1.0, float(raw.get("strength", 0.6)))), J(ev),
            status, reason)
        if row is None:
            counts["duplicates"] += 1
            continue
        if account_id is None:
            counts["unmatched"] += 1
            continue
        counts["matched"] += 1
        touched.add(account_id)
        if t["key"] == "new_exec" and raw.get("person"):
            # An announcement names a person and a seat: the desk's record of who sits there is brought in line with
            # it, so the play writes to the new leader and never congratulates someone who has been there for years.
            person_id = seat_from_announcement(cur, account_id, raw["person"], raw["observed_at"], source_key)
            if person_id:
                db.run(cur, "update signals set person_id = %s where id = %s", person_id, row["id"])
        db.run(cur, """insert into facts (account_id, person_id, kind, text, source, source_url, observed_at)
                       values (%s,%s,%s,%s,%s,%s,%s)""",
               account_id, person_id, "signal:" + t["key"], ev["summary"], source_key, ev.get("url"), raw["observed_at"])
        if t["key"] in ("job_change", "champion_moved") and raw.get("person"):
            _consider_move(cur, row["id"], account_id, raw["person"], source_key)
    db.run(cur, """update source_runs set finished_at = app_now(), fetched = %s, matched = %s, unmatched = %s,
                   duplicates = %s where id = %s""", counts["fetched"], counts["matched"], counts["unmatched"],
           counts["duplicates"], run_id)
    for aid in touched:
        jobs.enqueue(cur, "rescore", {"account_id": aid, "reason": "signal"}, dedupe_key=f"rescore:{aid}")
    return counts


SENIORITY = [("chief", "c_suite"), ("cfo", "c_suite"), ("vice president", "vp"), ("vp", "vp"), ("head of", "director"),
             ("director", "director"), ("manager", "manager")]


def seat_from_announcement(cur, account_id: int, person: dict, observed_at, source_key: str) -> int | None:
    """Match the person a new-leader announcement names to someone on record at the account, or add them, with the
    announced title and the appointment date as their role start. A nameless announcement changes nobody."""
    from .enrichment import linkedin_key, source
    started = parse_observed(observed_at).date()
    title = (person.get("title") or "").strip() or None
    name = (person.get("full_name") or person.get("name") or "").strip()
    pid = resolve_person(cur, person)
    if pid and db.val(cur, "select account_id from people where id = %s", pid) != account_id:
        pid = None
    if pid is None and name:
        pid = db.val(cur, "select id from people where account_id = %s and lower(full_name) = lower(%s) and status = 'active' "
                          "order by id limit 1", account_id, name)
    if pid is None:
        if not name or not title:
            return None
        first, _, last = name.partition(" ")
        low = title.lower()
        seniority = next((v for k, v in SENIORITY if k in low), None)
        url = (person.get("linkedin_url") or "").strip() or None
        if url and db.val(cur, "select exists (select 1 from people where linkedin_key = %s)", linkedin_key(url)):
            url = None  # someone else on record has this profile; the name and seat are still worth keeping
        pid = db.val(cur, """insert into people (account_id, full_name, first_name, last_name, title, seniority, linkedin_url,
                                                 linkedin_key, role_started_at, source, source_origin)
                             values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                     account_id, name, first, last or None, title, seniority, url, linkedin_key(url), started, source_key,
                     source_key)
        source(cur, "person", pid, "role_started_at", started.isoformat(), source_key)
    else:
        p = db.one(cur, "select title, role_started_at from people where id = %s", pid)
        if title and title != p["title"]:
            db.run(cur, "update people set title = %s where id = %s", title, pid)
            source(cur, "person", pid, "title", title, source_key)
        if p["role_started_at"] is None or p["role_started_at"] < started:
            db.run(cur, "update people set role_started_at = %s where id = %s", started, pid)
            source(cur, "person", pid, "role_started_at", started.isoformat(), source_key)
    _replaced_in_seat(cur, account_id, pid, title, started)
    return pid


def _seat(title: str | None) -> str | None:
    """The one seat a finance-leader title names: a company has one CFO, one VP Finance, one Head of Finance."""
    t = (title or "").lower()
    if re.search(r"\bcfo\b", t) or "chief financial" in t:
        return "cfo"
    if "vp finance" in t or "vice president of finance" in t:
        return "vp_finance"
    if "head of finance" in t:
        return "head_of_finance"
    return None


def _replaced_in_seat(cur, account_id: int, pid: int, title: str | None, started) -> None:
    """Whoever held the announced seat before the appointment is no longer in it: marked as left, their sequences
    stopped, so the account never shows two CFOs and nobody writes to the one who went."""
    seat = _seat(title)
    if seat is None:
        return
    from . import outreach
    for p in db.all(cur, """select id, title from people where account_id = %s and id <> %s and status = 'active'
                            and (role_started_at is null or role_started_at < %s)""", account_id, pid, started):
        if _seat(p["title"]) != seat:
            continue
        db.run(cur, "update people set status = 'left' where id = %s", p["id"])
        for e in db.all(cur, "select id from enrollments where person_id = %s and state in ('pending','active','paused')", p["id"]):
            outreach.stop_enrollment(cur, e["id"], "replaced_in_seat")
        audit.log(cur, "desk", "replaced_in_seat", "person", p["id"], {"by": pid, "seat": seat})


def _consider_move(cur, signal_id: int, new_account_id: int, person: dict, source_key: str) -> None:
    """A job change moves the person only when a second source agrees, or their old address hard-bounced."""
    pid = resolve_person(cur, person)
    if pid is None:
        return
    p = db.one(cur, "select id, account_id, status from people where id = %s", pid)
    if p["account_id"] == new_account_id:
        return
    agreeing = db.val(cur, """select count(distinct source) from signals where person_id = %s and account_id = %s
                              and type_key in ('job_change', 'champion_moved')""", pid, new_account_id)
    bounced = db.val(cur, """select exists (select 1 from deliveries d join messages m on m.id = d.message_id
                              join enrollments e on e.id = m.enrollment_id where e.person_id = %s
                              and d.event = 'bounced_hard')""", pid)
    if agreeing >= 2 or bounced:
        move_person(cur, pid, new_account_id, corroborated_by="two sources" if agreeing >= 2 else "old address bounced")


def move_person(cur, person_id: int, new_account_id: int, *, corroborated_by: str) -> None:
    p = db.one(cur, "select account_id, email from people where id = %s for update", person_id)
    db.run(cur, "insert into person_moves (person_id, from_account_id, to_account_id, at, corroborated_by) "
                "values (%s,%s,%s,app_now(),%s)", person_id, p["account_id"], new_account_id, corroborated_by)
    # One row per human: the row moves. The old work address no longer reaches them.
    db.run(cur, """update people set account_id = %s, email = null, email_status = 'unknown', email_verified_at = null,
                   email_verified_by = null, email_found_by = null, email_confidence = null, status = 'active',
                   persona_key = null, title = null, seniority = null, departments = '{}', role_started_at = null,
                   phone = null, phone_status = 'unknown', phone_verified_at = null, phone_type = null, phone_dnc = false,
                   enriched_at = null where id = %s""",
           new_account_id, person_id)
    from . import outreach
    for e in db.all(cur, "select id from enrollments where person_id = %s and state in ('pending','active','paused')",
                    person_id):
        outreach.stop_enrollment(cur, e["id"], "person_moved")
    audit.log(cur, "desk", "person_moved", "person", person_id,
              {"from": p["account_id"], "to": new_account_id, "by": corroborated_by})


def first_party_from_crm(cur) -> int:
    """Closed-lost deals whose timing objection has passed become a signal. Champions come from won deals."""
    n = 0
    rows = db.all(cur, """
        select o.id, o.account_id, o.closed_at from opportunities o
        where o.won = false and o.closed_at < app_now() - interval '150 days' and o.loss_reason = 'timing'
          and not exists (select 1 from signals s where s.source = 'crm' and s.external_id = 'lost-' || o.id)""")
    for r in rows:
        db.run(cur, """insert into signals (type_key, source, external_id, account_id, observed_at, strength, evidence, status)
                       values ('closed_lost_revisit', 'crm', %s, %s, app_now(), 0.7, %s, 'matched')""",
               f"lost-{r['id']}", r["account_id"],
               J({"summary": "A deal lost on timing more than five months ago.", "quote": "Closed lost: timing"}))
        jobs.enqueue(cur, "rescore", {"account_id": r["account_id"]}, dedupe_key=f"rescore:{r['account_id']}")
        n += 1
    return n


def parse_observed(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)
