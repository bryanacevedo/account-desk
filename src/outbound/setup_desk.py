"""Standing up a real desk, without the demo: one file for the team and its sending setup, then CSV imports for
accounts and people. Everything here is validated before anything is written, and imports report each row they
refuse instead of stopping or skipping silently.

    python -m outbound init desk.json
    python -m outbound import accounts accounts.csv
    python -m outbound import people people.csv
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import audit, db, jobs
from .db import J
from .seed import catalog as C
from .signals import normalize_domain, normalize_name

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class User(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=EMAIL)
    role: Literal["sdr", "manager", "gtm"]
    timezone: str = "America/New_York"
    slack_id: str | None = None


class Mailbox(BaseModel):
    address: str = Field(pattern=EMAIL)
    owner_email: str = Field(pattern=EMAIL)
    provider: Literal["google", "microsoft"]
    warmup_started: date


class SendingDomain(BaseModel):
    domain: str
    registered: date
    mailboxes: list[Mailbox] = Field(max_length=3)  # at most three mailboxes a domain (decision in SPEC 22.5)

    @field_validator("domain")
    @classmethod
    def _domain(cls, v: str) -> str:
        d = normalize_domain(v)
        if not d:
            raise ValueError("not a domain")
        return d


class DeskConfig(BaseModel):
    users: list[User] = Field(min_length=1)
    sending_domains: list[SendingDomain] = []
    lia_ref: str = Field(min_length=3, max_length=60, description="Your legitimate-interest assessment's reference")
    lia_review_due: date | None = Field(None, description="When the assessment is next reviewed. Without it, a play "
                                                          "that relies on legitimate interest cannot launch.")
    region_rules: dict[str, Literal["allowed", "basis_required", "consent_required", "blocked"]] | None = None
    budgets: dict[str, int] | None = None
    sources: list[str] | None = Field(None, description="Signal sources you have; the rest start disabled")
    starter_plays: bool = True

    @field_validator("users")
    @classmethod
    def _roles(cls, v: list[User]) -> list[User]:
        roles = {u.role for u in v}
        if "manager" not in roles:
            raise ValueError("a desk needs at least one manager, who launches plays")
        return v


def init(cur, cfg: DeskConfig) -> dict:
    """Create the desk on an empty database. Refuses to run on a desk that already has users."""
    if db.val(cur, "select count(*) from users"):
        raise ValueError("This desk already has users. init only runs once, on an empty database.")
    for k, v in C.SETTINGS.items():
        db.run(cur, "insert into settings (key, value) values (%s, %s) on conflict (key) do nothing", k, J(v))
    db.run(cur, "insert into settings (key, value) values ('lia_ref', %s) on conflict (key) do update set value = excluded.value",
           J(cfg.lia_ref))
    if cfg.lia_review_due:
        db.run(cur, "insert into settings (key, value) values ('lia_review_due', %s) on conflict (key) do update "
                    "set value = excluded.value", J(cfg.lia_review_due.isoformat()))
    ids: dict[str, int] = {}
    for u in cfg.users:
        ids[u.email.lower()] = db.val(cur, """insert into users (name, email, role, timezone, slack_id)
                                              values (%s,%s,%s,%s,%s) returning id""",
                                      u.name, u.email.lower(), u.role, u.timezone, u.slack_id)
    gtm = next((i for u, i in zip(cfg.users, ids.values()) if u.role == "gtm"), next(iter(ids.values())))
    for key, label, patterns, seniority, role, angle in C.PERSONAS:
        db.run(cur, "insert into personas (key, label, title_patterns, seniority, committee_role, angle) "
                    "values (%s,%s,%s,%s,%s,%s) on conflict do nothing", key, label, patterns, seniority, role, angle)
    for key, label, because, level, weight, hl in C.SIGNAL_TYPES:
        db.run(cur, "insert into signal_types (key, label, because, level, weight, half_life_days) "
                    "values (%s,%s,%s,%s,%s,%s) on conflict do nothing", key, label, because, level, weight, hl)
    for key, label, adapter, cadence, paid, provider in C.SIGNAL_SOURCES:
        enabled = cfg.sources is None or key in cfg.sources or key in ("webhook", "replies")
        db.run(cur, """insert into signal_sources (key, label, adapter, cadence_minutes, paid, provider, enabled)
                       values (%s,%s,%s,%s,%s,%s,%s) on conflict (key) do update set enabled = excluded.enabled""",
               key, label, adapter, cadence, paid, provider, enabled)
    db.run(cur, "insert into icp_versions (rules, note, published_by, published_at) values (%s, %s, %s, app_now())",
           J(C.ICP), "Starting ICP: edit it in Settings", gtm)
    for country, rule in (cfg.region_rules or dict(C.REGION_RULES)).items():
        call_rule, register = C.CALL_RULES.get(country, ("blocked", None))
        db.run(cur, "insert into region_rules (country, rule, call_rule, dnc_register) values (%s,%s,%s,%s) "
                    "on conflict do nothing", country, rule, call_rule, register)
    for vendor, cap in (cfg.budgets or dict(C.BUDGETS)).items():
        db.run(cur, "insert into budgets (vendor, monthly_cap_cents) values (%s,%s) on conflict do nothing", vendor, cap)
    for d in cfg.sending_domains:
        # Authentication is unknown until the DNS check reads it: nothing sends from a domain before then.
        db.run(cur, """insert into sending_domains (domain, spf, dkim, dmarc, dmarc_policy, dmarc_aligned, registered_at)
                       values (%s, false, false, false, null, false, %s)""", d.domain, d.registered)
        for mb in d.mailboxes:
            owner = ids.get(mb.owner_email.lower())
            if owner is None:
                raise ValueError(f"{mb.address}: owner {mb.owner_email} is not one of the users")
            db.run(cur, """insert into mailboxes (address, domain, provider, display_name, user_id, warmup_started, ramp_start)
                           values (%s,%s,%s,(select name from users where id = %s),%s,%s,%s)""",
                   mb.address.lower(), d.domain, mb.provider, owner, owner, mb.warmup_started,
                   mb.warmup_started + timedelta(days=14))
    plays = 0
    if cfg.starter_plays:
        for (key, name, hyp, trig, personas, maxp, seq, angle, _autonomy, urgent, latency) in C.PLAYS:
            # Drafts, written by GTM, in the most careful autonomy stage: a manager reads and launches each one.
            db.run(cur, """insert into plays (key, name, hypothesis, trigger, personas, max_people, sequence, angle, autonomy,
                                              status, holdout_pct, owner_id, created_by, urgent, latency_hours, lia_ref,
                                              lia_review_due)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,'draft','draft',20,%s,%s,%s,%s,%s,%s)""",
                   key, name, hyp, J(trig), personas, maxp, J(seq), angle, gtm, gtm, urgent, latency, cfg.lia_ref,
                   cfg.lia_review_due)
            plays += 1
    for country, day, name in C.HOLIDAYS:
        db.run(cur, "insert into holidays (country, day, name) values (%s,%s,%s) on conflict do nothing",
               country, date.fromisoformat(day), name)
    audit.log(cur, "person", "desk_initialised", "desk", None, {"users": len(ids), "plays": plays})
    return {"users": len(ids), "mailboxes": sum(len(d.mailboxes) for d in cfg.sending_domains), "draft_plays": plays}


# ---------------------------------------------------------------- imports

LIFECYCLES = {"prospect", "customer", "open_opp", "churned", "competitor", "partner"}
NORTH_AMERICA = {"US", "CA", "MX"}
EUROPE = {"GB", "IE", "DE", "FR", "NL", "BE", "LU", "ES", "PT", "IT", "AT", "CH", "SE", "NO", "DK", "FI", "IS", "PL", "CZ",
          "SK", "HU", "RO", "BG", "GR", "HR", "SI", "EE", "LV", "LT", "CY", "MT"}


def region_of(country: str | None) -> str | None:
    """The region the ICP speaks in, from a two-letter country code. Unknown countries stay unknown."""
    c = (country or "").upper()
    return "North America" if c in NORTH_AMERICA else "Europe" if c in EUROPE else None


def _rows(text: str) -> list[dict]:
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]


def import_accounts(cur, text: str) -> dict:
    """Columns: name, domain (required); industry, employees, country, revenue_band, tech (separated by ';'),
    lifecycle, owner_email, crm_id, parent_domain, subscriber_type (corporate for a limited company, individual for a
    sole trader or partnership; UK email needs it). Region comes from the country. A domain already on the desk is
    updated, never duplicated; a blank cell keeps what the desk has."""
    done, refused, parents = 0, [], []
    for i, r in enumerate(_rows(text), start=2):
        domain = normalize_domain(r.get("domain"))
        if not r.get("name") or not domain:
            refused.append({"row": i, "why": "needs a name and a company domain (not a free email provider)"})
            continue
        lifecycle = (r.get("lifecycle") or "").lower() or None  # blank keeps what the desk has
        if lifecycle is not None and lifecycle not in LIFECYCLES:
            refused.append({"row": i, "why": f"lifecycle must be one of {', '.join(sorted(LIFECYCLES))}"})
            continue
        emp = r.get("employees") or None
        if emp is not None and not emp.isdigit():
            refused.append({"row": i, "why": "employees must be a whole number"})
            continue
        subscriber = (r.get("subscriber_type") or "").lower() or None
        if subscriber is not None and subscriber not in ("corporate", "individual", "unknown"):
            refused.append({"row": i, "why": "subscriber_type must be corporate, individual or unknown"})
            continue
        owner = db.val(cur, "select id from users where email = %s", r["owner_email"].lower()) if r.get("owner_email") else None
        aid = db.val(cur, """
            insert into accounts (name, name_key, primary_domain, industry, employees, hq_country, lifecycle, owner_id, crm_id, source,
                                  region, revenue_band, tech, subscriber_type)
            values (%s,%s,%s,%s,%s,%s,coalesce(%s, 'prospect'),%s,%s,'import',%s,%s,%s,coalesce(%s, 'unknown'))
            on conflict (primary_domain) do update set name = excluded.name, name_key = excluded.name_key,
              industry = coalesce(excluded.industry, accounts.industry), employees = coalesce(excluded.employees, accounts.employees),
              hq_country = coalesce(excluded.hq_country, accounts.hq_country),
              lifecycle = case when %s::text is null then accounts.lifecycle else excluded.lifecycle end,
              owner_id = coalesce(excluded.owner_id, accounts.owner_id), crm_id = coalesce(excluded.crm_id, accounts.crm_id),
              region = coalesce(excluded.region, accounts.region), revenue_band = coalesce(excluded.revenue_band, accounts.revenue_band),
              tech = case when cardinality(excluded.tech) > 0 then excluded.tech else accounts.tech end,
              subscriber_type = case when %s::text is null then accounts.subscriber_type else excluded.subscriber_type end
            returning id""", r["name"], normalize_name(r["name"]), domain, r.get("industry") or None,
                     int(emp) if emp else None, (r.get("country") or "").upper() or None, lifecycle, owner,
                     r.get("crm_id") or None, region_of(r.get("country")), r.get("revenue_band") or None,
                     [t.strip() for t in (r.get("tech") or "").split(";") if t.strip()], subscriber, lifecycle, subscriber)
        db.run(cur, "insert into account_domains (domain, account_id) values (%s,%s) on conflict do nothing", domain, aid)
        if r.get("parent_domain"):
            parents.append((aid, normalize_domain(r["parent_domain"])))
        jobs.enqueue(cur, "rescore", {"account_id": aid, "reason": "import"}, dedupe_key=f"rescore:{aid}")
        done += 1
    if done:
        jobs.enqueue(cur, "crm_retry_held", {}, dedupe_key="crm_retry_held")  # deals waiting for these accounts
    for aid, parent in parents:  # after every row, so a parent later in the file still links
        db.run(cur, "update accounts set parent_id = (select account_id from account_domains where domain = %s) where id = %s",
               parent, aid)
    return {"imported": done, "refused": refused}


def import_people(cur, text: str) -> dict:
    """Columns: full_name, company_domain (required); title, email, linkedin_url, phone, country, timezone, source
    (where the list came from, kept as the person's provenance).
    Emails are imported unverified: the desk verifies before any send."""
    done, refused = 0, []
    for i, r in enumerate(_rows(text), start=2):
        domain = normalize_domain(r.get("company_domain"))
        aid = db.val(cur, "select account_id from account_domains where domain = %s", domain) if domain else None
        if not r.get("full_name") or aid is None:
            refused.append({"row": i, "why": "needs full_name and the domain of an account already on the desk"})
            continue
        email = (r.get("email") or "").lower() or None
        if email and "@" not in email:
            refused.append({"row": i, "why": "email is not an address"})
            continue
        from .privacy import erased
        if erased(cur, email=email, linkedin_url=r.get("linkedin_url") or None):
            refused.append({"row": i, "why": "this person was erased on request and is never added again"})
            continue
        from .enrichment import linkedin_key
        existing = db.val(cur, "select id from people where email = %s", email) if email else None
        if existing is None and r.get("linkedin_url"):
            existing = db.val(cur, "select id from people where linkedin_key = %s", linkedin_key(r["linkedin_url"]))
        first, _, last = r["full_name"].partition(" ")
        if existing:
            was = db.val(cur, "select account_id from people where id = %s", existing)
            if was is not None and was != aid:
                from .signals import move_person
                move_person(cur, existing, aid, corroborated_by="import")
            db.run(cur, """update people set title = coalesce(%s, title), phone = coalesce(%s, phone),
                           email = coalesce(email, %s) where id = %s""",
                   r.get("title") or None, r.get("phone") or None, email, existing)
        else:
            db.run(cur, """insert into people (account_id, full_name, first_name, last_name, title, email, linkedin_url,
                                               linkedin_key, phone, country, timezone, source, source_origin)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'import',%s)""",
                   aid, r["full_name"], first, last or None, r.get("title") or None, email, r.get("linkedin_url") or None,
                   linkedin_key(r.get("linkedin_url")),
                   r.get("phone") or None, (r.get("country") or "").upper() or None, r.get("timezone") or None,
                   (r.get("source") or "").strip()[:200] or "CSV import")
        done += 1
    return {"imported": done, "refused": refused}
