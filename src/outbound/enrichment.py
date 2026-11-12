"""Enrichment: turning an account or a person into data the desk can trust, and keeping it true.

Four rules hold here.
1. A paid answer is bought once. Each vendor answer is kept in `enrichment_results` on its own connection, like the
   ledger, so a job that rolls back and runs again reads it instead of paying again.
2. Every enriched field says where it came from: `field_sources` holds the vendor, the time and the confidence.
3. Enrichment fills what is blank and refreshes what has gone stale; it never overwrites what a person typed or the
   CRM holds with a vendor's guess, except fields that only a vendor provides.
4. A change between two reads is a signal: a finance team growing, a finance role opening, a tool arriving or going,
   a new round, someone new in a finance seat.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from datetime import date, datetime
from typing import Any, Callable

from . import adapters, db, jobs, spend
from .db import J

log = logging.getLogger("outbound.enrichment")

# How long a paid answer stays good before it is bought again (days).
KEEP = {"people_search": 30, "email_finder": 90, "email_verifier": 45, "email_resolver": 45, "phone_finder": 180,
        "company": 25, "person": 90}
COMPANY_EVERY_DAYS = 30   # read each working account's company data monthly, so two reads show what changed
PERSON_EVERY_DAYS = 90    # contact data decays around a quarter a year: people in open plays are re-read quarterly


def _plain(v: Any) -> Any:
    if dataclasses.is_dataclass(v):
        return {k: _plain(x) for k, x in dataclasses.asdict(v).items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def bought(cur, kind: str, key: str, buy: Callable[[], Any], *, keep_days: int | None = None) -> Any:
    """Return a kept answer younger than keep_days, or buy it (inside the caller's paid_call) and keep it.

    The answer is stored as plain JSON; callers rebuild what they need from it."""
    days = keep_days if keep_days is not None else KEEP.get(kind.split(":")[0], 30)
    with db.pool().connection() as own, own.cursor() as c:
        row = db.one(c, "select result from enrichment_results where kind = %s and key = %s and at > now() - (%s || ' days')::interval",
                     kind, key, str(days))
    if row is not None:
        return row["result"].get("v")
    value = _plain(buy())
    with db.pool().connection() as own:
        with own.transaction(), own.cursor() as c:
            db.run(c, """insert into enrichment_results (kind, key, result, at) values (%s, %s, %s, now())
                         on conflict (kind, key) do update set result = excluded.result, at = excluded.at""",
                   kind, key, J({"v": value}))
    return value


def source(cur, kind: str, object_id: int, field: str, value: Any, vendor: str, confidence: float | None = None) -> None:
    db.run(cur, """insert into field_sources (object_kind, object_id, field, value, vendor, confidence)
                   values (%s,%s,%s,%s,%s,%s)""", kind, object_id, field,
           None if value is None else (value if isinstance(value, str) else json.dumps(_plain(value))), vendor, confidence)


def linkedin_key(url: str | None) -> str | None:
    if not url:
        return None
    return url.strip().lower().split("://")[-1].removeprefix("www.").rstrip("/") or None


CONFIDENCE = {"high": 0.9, "medium": 0.7, "low": 0.4}


# ---------------------------------------------------------------- people

def apply_person(cur, person_id: int, c: dict, vendor: str, *, refresh: bool = False) -> None:
    """Write what a people-data vendor said about someone: departments, when the role started, city, headline, how
    sure the match is, and the time zone if none was known. On a refresh a changed title is taken too."""
    p = db.one(cur, "select * from people where id = %s", person_id)
    if p is None:
        return
    conf = CONFIDENCE.get(c.get("match_confidence") or "", None)
    if c.get("match_confidence") == "low":
        source(cur, "person", person_id, "match", "low", vendor, conf)
        return  # a low-confidence match is not trusted with anyone's data
    started = c.get("role_started_at")
    updates = {
        "departments": c.get("departments") or p["departments"],
        "role_started_at": started or p["role_started_at"],
        "city": c.get("city") or p["city"],
        "headline": c.get("headline") or p["headline"],
        "match_confidence": c.get("match_confidence") or p["match_confidence"],
        "timezone": p["timezone"] or c.get("timezone"),
        "country": p["country"] or c.get("country"),
        "enriched_at": db.val(cur, "select app_now()"),
        # Provenance: who first told the desk about this person, kept once known.
        "source_origin": p["source_origin"] or vendor,
    }
    if refresh and c.get("title") and c["title"] != p["title"]:
        updates["title"] = c["title"]
        source(cur, "person", person_id, "title", c["title"], vendor, conf)
    db.run(cur, "update people set " + ", ".join(f"{k} = %s" for k in updates) + " where id = %s",
           *updates.values(), person_id)
    for f in ("departments", "role_started_at", "city", "country"):
        if c.get(f) and c.get(f) != p[f]:
            source(cur, "person", person_id, f, c.get(f), vendor, conf)
    _new_in_seat(cur, person_id)


LEADER_TITLES = ("cfo", "chief financial", "vp finance", "vice president of finance", "head of finance", "finance director")


def in_leader_seat(cur, title: str | None) -> bool:
    """Whether a title is the finance leader's seat (CFO, VP Finance, Head of Finance): the seat the new finance
    leader play is about. A controller or an accountant who started recently is not a new finance leader."""
    patterns = set(LEADER_TITLES) | set(db.val(cur, "select title_patterns from personas where key = 'cfo'") or [])
    t = (title or "").lower()
    return any(x in t for x in patterns)


def _new_in_seat(cur, person_id: int) -> None:
    """Someone took the finance leader's seat in the last 90 days: the strongest single reason to talk to an account."""
    p = db.one(cur, """select p.*, a.primary_domain, a.name as company from people p join accounts a on a.id = p.account_id
                       where p.id = %s and p.role_started_at > (app_now() - interval '90 days')::date""", person_id)
    if p is None or p["status"] != "active" or not in_leader_seat(cur, p["title"]):
        return
    from . import signals
    started = datetime.combine(p["role_started_at"], datetime.min.time(), tzinfo=db.val(cur, "select app_now()").tzinfo)
    signals.ingest(cur, "enrichment", [{
        "type": "new_exec", "external_id": f"seat:{person_id}:{p['role_started_at']}", "domain": p["primary_domain"],
        "account_id": p["account_id"], "person": {"full_name": p["full_name"], "linkedin_url": p["linkedin_url"]},
        "observed_at": started, "strength": 0.8,  # when they started, so a seat taken 80 days ago reads as 80 days old
        # A whole clause with its own subject, so a draft can say "Saw that {company} appointed ..." as written.
        "evidence": {"summary": f"{p['company']} appointed {p['full_name']} as {p['title'] or 'finance leader'} on "
                                f"{p['role_started_at']:%d %b %Y}.",
                     "quote": "From people data: role start date"}}])


def locate_person(cur, person_id: int) -> None:
    """Ask the people-data vendor about someone the desk knows only by name (a referral): where they work from, their
    time zone and what their role is. Paid once, like any other match; nothing is guessed when it finds nobody."""
    p = db.one(cur, "select * from people where id = %s", person_id)
    ad = adapters.get()
    if p is None or p["country"] or ad.people is None:
        return

    def buy():
        with spend.paid_call(cur, "people_search", "match", vendor="people_search", qty=1, purpose="locate person",
                             account_id=p["account_id"]) as info:
            c = ad.people.enrich(cur, p)
            info["found"] = bool(c and c.country)
            info["charged_qty"] = 1 if c and c.country else 0
        return c

    c = bought(cur, "person", f"{person_id}:locate", buy)
    if c:
        apply_person(cur, person_id, c, "people_search")


# ---------------------------------------------------------------- companies

def enrich_company(cur, account: dict, *, force: bool = False) -> bool:
    """Read the company's data, fill what is blank, keep a snapshot, and raise signals for what changed since the
    last read. Returns whether anything was read."""
    ad = adapters.get()
    if ad.company is None:
        return False
    if not force and account.get("enriched_at") and db.val(
            cur, "select %s > app_now() - (%s || ' days')::interval", account["enriched_at"], str(COMPANY_EVERY_DAYS)):
        return False
    key = f"{account['id']}:{db.val(cur, "select to_char(app_now(), 'YYYY-MM')")}"

    def buy():
        with spend.paid_call(cur, "company_data", "enrich", vendor="company_data", qty=1, purpose="company data",
                             account_id=account["id"]) as info:
            data = ad.company.enrich(cur, account)
            info["found"] = data is not None
            info["charged_qty"] = 1 if data is not None else 0
        return data

    d = bought(cur, "company", key, buy)
    if not d:
        db.run(cur, "update accounts set enriched_at = app_now(), enriched_by = %s where id = %s", ad.company.name, account["id"])
        return True
    vendor = ad.company.name
    conf = d.get("confidence")
    fill = {"industry": d.get("industry"), "employees": d.get("employees"), "revenue_band": d.get("revenue_band"),
            "founded_year": d.get("founded_year")}
    sets, vals = [], []
    for f, v in fill.items():
        if v is not None and account.get(f) in (None, ""):
            sets.append(f"{f} = %s")
            vals.append(v)
            source(cur, "account", account["id"], f, v, vendor, conf)
    # Vendor-only fields are always the vendor's latest word.
    tech = sorted(set(account.get("tech") or []) | set(d.get("technologies") or []))
    sets += ["tech = %s", "keywords = %s", "total_funding_cents = %s", "latest_funding_round = %s", "latest_funding_at = %s",
             "enriched_at = app_now()", "enriched_by = %s"]
    vals += [tech, d.get("keywords") or [], d.get("total_funding_cents"), d.get("latest_funding_round"),
             d.get("latest_funding_at"), vendor]
    if d.get("parent_domain") and not account.get("parent_id"):
        parent = db.val(cur, "select id from accounts where primary_domain = %s", d["parent_domain"])
        if parent and parent != account["id"]:
            sets.append("parent_id = %s")
            vals.append(parent)
            source(cur, "account", account["id"], "parent", d["parent_domain"], vendor, conf)
    db.run(cur, f"update accounts set {', '.join(sets)} where id = %s", *vals, account["id"])
    prev = db.one(cur, "select data, at from account_snapshots where account_id = %s order by at desc limit 1", account["id"])
    db.run(cur, "insert into account_snapshots (account_id, vendor, data) values (%s,%s,%s)", account["id"], vendor, J(d))
    if prev:
        _changes(cur, account, prev["data"], d, since=prev["at"])
    from . import scoring
    scoring.rescore(cur, account["id"])  # fit is judged on what is known, and now more is known
    return True


def _changes(cur, account: dict, before: dict, after: dict, *, since) -> None:
    """Signals from what changed between two reads of the same company. A change is dated to the earlier read, the
    latest it can have started, so it is never presented as fresher than it is; a round is dated to its close."""
    from . import signals
    now = db.val(cur, "select app_now()")
    raws = []
    b_fin = (before.get("headcount") or {}).get("finance") or 0
    a_fin = (after.get("headcount") or {}).get("finance") or 0
    if b_fin and a_fin >= b_fin * 1.15 and a_fin - b_fin >= 2:
        raws.append({"type": "hiring_function", "external_id": f"growth:{account['id']}:{now:%Y-%m}",
                     "summary": f"The finance team grew from {b_fin} to {a_fin} people since the last read.", "strength": 0.7})
    seen = {r["title"] for r in before.get("open_roles") or []}
    new_roles = [r for r in after.get("open_roles") or [] if r["title"] not in seen]
    if len(new_roles) >= 1 and len(after.get("open_roles") or []) >= 2:
        raws.append({"type": "hiring_function", "external_id": f"roles:{account['id']}:{now:%Y-%m}",
                     "summary": f"Hiring for {len(after['open_roles'])} finance roles, including a {new_roles[0]['title']}.",
                     "strength": 0.65})
    # A tool we connect to arriving means the stack is being rebuilt; a billing tool we compete with arriving is not
    # good news, and only one of those leaving is a reason to call ("Dropped a tool we replace").
    competing = set(db.val(cur, "select value from settings where key = 'competing_tools'") or [])
    added = sorted(set(after.get("technologies") or []) - set(before.get("technologies") or []) - competing)
    removed = sorted((set(before.get("technologies") or []) - set(after.get("technologies") or [])) & competing)
    if added:
        raws.append({"type": "tech_added", "external_id": f"tech+:{account['id']}:{','.join(added)}",
                     "summary": f"Started using {', '.join(added)}.", "strength": 0.6})
    if removed:
        raws.append({"type": "tech_removed", "external_id": f"tech-:{account['id']}:{','.join(removed)}",
                     "summary": f"Stopped using {', '.join(removed)}.", "strength": 0.6})
    if after.get("latest_funding_at") and after.get("latest_funding_at") != before.get("latest_funding_at"):
        closed = datetime.fromisoformat(str(after["latest_funding_at"])).replace(tzinfo=now.tzinfo)
        raws.append({"type": "funding", "external_id": f"round:{account['id']}:{after['latest_funding_at']}",
                     "summary": f"Raised a {after.get('latest_funding_round') or 'round'}.", "strength": 0.7, "at": closed})
    if raws:
        signals.ingest(cur, "enrichment", [{"type": r["type"], "external_id": r["external_id"], "domain": account["primary_domain"],
                                            "account_id": account["id"],
                                            "observed_at": min(r.get("at") or since, now), "strength": r["strength"],
                                            "evidence": {"summary": r["summary"], "quote": f"From company data read {now:%d %b %Y}"}} for r in raws])


# ---------------------------------------------------------------- keeping data true

@jobs.handler("enrichment_refresh")
def refresh(cur, payload: dict) -> None:
    """Daily. Re-read company data for working accounts monthly, people in open plays quarterly, and re-verify the
    addresses of people about to be emailed. Bounded per run so a large desk spreads the cost."""
    for a in db.all(cur, """select a.* from accounts a where a.lifecycle = 'prospect' and (a.fit_tier in ('A', 'B') or exists (
                              select 1 from account_plays ap where ap.account_id = a.id
                              and ap.state in ('accepted','researching','approving','active','engaged','meeting')))
                            and (a.enriched_at is null or a.enriched_at < app_now() - (%s || ' days')::interval)
                            order by a.enriched_at nulls first limit 40""", str(COMPANY_EVERY_DAYS)):
        try:
            enrich_company(cur, a)
        except spend.OverBudget:
            break
    ad = adapters.get()
    for p in db.all(cur, """select distinct p.* from people p join enrollments e on e.person_id = p.id
                            where e.state in ('pending','active','paused') and p.status = 'active'
                            and (p.enriched_at is null or p.enriched_at < app_now() - (%s || ' days')::interval)
                            order by p.enriched_at nulls first limit 60""", str(PERSON_EVERY_DAYS)):
        def buy(p=p):
            with spend.paid_call(cur, "people_search", "match", vendor="people_search", qty=1, purpose="refresh person",
                                 account_id=p["account_id"]) as info:
                c = ad.people.enrich(cur, p)
                info["found"] = bool(c)
                info["charged_qty"] = 1 if c else 0
            return c
        try:
            c = bought(cur, "person", f"{p['id']}:{db.val(cur, "select to_char(app_now(), 'YYYY-Q')")}", buy)
        except spend.OverBudget:
            break
        if c:
            apply_person(cur, p["id"], c, "people_search", refresh=True)
    from . import outreach
    for p in db.all(cur, """select distinct p.* from people p join enrollments e on e.person_id = p.id
                            where e.state in ('pending','active') and p.email is not null and p.email_status = 'valid'
                            and p.email_verified_at < app_now() - (%s || ' days')::interval limit 60""",
                    str(int(outreach.setting(cur, "verify_max_age_days", 45)))):
        jobs.enqueue(cur, "reverify", {"person_id": p["id"]}, dedupe_key=f"reverify:{p['id']}")


def ensure_company(cur, account_id: int) -> None:
    """Called when an account is researched: company data is read first, if it has not been this month."""
    a = db.one(cur, "select * from accounts where id = %s", account_id)
    if a:
        try:
            enrich_company(cur, a)
        except (spend.OverBudget, adapters.VendorMissing):
            log.info("company data skipped for account %s", account_id)

