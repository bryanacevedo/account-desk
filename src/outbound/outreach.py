"""From an accepted account to approved first emails: research, the brief, the buying committee, verified
contacts, drafts that pass the copy checks, approval by autonomy stage, and the account calendar."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import timedelta

import psycopg

from . import (
    adapters,
    audit,
    copy_gate,
    db,
    gate,
    jobs,
    llm,
    plays,
    signals,
    sim_llm,  # noqa: F401  registers the stand-in model tasks
    spend,
    standing,
    telemetry,
    timeutil,
)
from .config import CONFIG
from .db import J

log = logging.getLogger("outbound.outreach")
SENIORITY_RANK = {"c_suite": 4, "vp": 3, "director": 2, "manager": 1, "ic": 0}
# Where a first email carries a privacy notice: the EU and EEA (GDPR art. 14), the UK, Switzerland and Brazil (LGPD).
# Every EU member state is listed, so a new country is covered before anyone remembers to add it.
NOTICE_COUNTRIES = {"GB", "DE", "FR", "NL", "ES", "IE", "IT", "BE", "SE", "DK", "PL", "AT", "PT", "FI", "LU", "GR", "CZ",
                    "SK", "SI", "HR", "HU", "RO", "BG", "EE", "LV", "LT", "CY", "MT", "NO", "IS", "LI", "CH", "BR"}
# Where a person's details came from, in the notice's words. Anything not listed reads as public business sources.
DATA_SOURCES = {"people_search": "a business contact database", "import": "our own business records",
                "crm": "our own business records", "referral": "a colleague's suggestion",
                "people_moves": "public news of your new role", "news_feed": "public company news",
                "events": "an event you registered for", "product": "your sign-up to our product"}
OUR_NAMES = [CONFIG.sender_company]
# Signals the desk acts on but never mentions to the buyer: they came from tracking, not from anything the
# company published. Citing them reads as surveillance.
PRIVATE_SIGNALS = ("pricing_visit", "site_visit", "intent_topic", "product_signup", "social_engaged", "event_attended",
                   "competitor_review")


# ---------------------------------------------------------------- research

def _research_facts(cur, account: dict) -> None:
    cached = db.one(cur, "select fetched_at from research_cache where domain = %s and kind = 'pages' "
                         "and fetched_at > app_now() - interval '30 days'", account["primary_domain"])
    if cached:
        return
    with spend.free_call(cur, "research", "pages") as info:
        pages = adapters.get().research.pages(cur, account)
        info["pages"] = len(pages)
    for pg in pages:
        exists = db.val(cur, "select exists (select 1 from facts where account_id = %s and kind = %s and text = %s)",
                        account["id"], "page:" + pg.kind, pg.text)
        if not exists:
            db.run(cur, """insert into facts (account_id, kind, text, source, source_url, observed_at)
                           values (%s,%s,%s,'research',%s,app_now())""", account["id"], "page:" + pg.kind, pg.text,
                   signals.http_url(pg.url))
    db.run(cur, """insert into research_cache (domain, kind, content, fetched_at) values (%s, 'pages', %s, app_now())
                   on conflict (domain, kind) do update set content = excluded.content, fetched_at = excluded.fetched_at""",
           account["primary_domain"], J([pg.__dict__ for pg in pages]))


def account_facts(cur, account_id: int, limit: int = 14, *, citable_only: bool = True) -> list[dict]:
    private = [f"signal:{k}" for k in PRIVATE_SIGNALS] if citable_only else []
    return db.all(cur, """
        (select id, kind, text, source_url, observed_at, person_id from facts
          where account_id = %s and kind like 'signal:%%' and observed_at > app_now() - interval '90 days'
            and kind <> all(%s)
          order by observed_at desc, id desc limit 8)
        union all
        (select id, kind, text, source_url, observed_at, person_id from facts
          where account_id = %s and kind not like 'signal:%%' order by observed_at desc, id desc limit 8)""",
        account_id, private, account_id)[:limit]


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


def _fits(person: dict, persona: dict) -> bool:
    """A person fits a persona by title; a vendor's department alone is not enough (a finance analyst is not the CFO),
    but it rules out a title that matched by accident (a "data" title in sales)."""
    if not _title_matches(person.get("title"), persona["title_patterns"]):
        return False
    depts, want = set(person.get("departments") or []), set(persona.get("departments") or [])
    return not depts or not want or bool(depts & want) or depts == {"other"}


def _enrollable(cur, person_id: int, ap_id: int, channel: str = "email") -> list[gate.Reason]:
    """Person-level reasons that matter at selection, for the play's first channel. Email problems are fixed by
    finding and verifying; a play with no email never refuses someone over their email."""
    skip = {"no_email", "verify_due", "no_basis"}
    return [r for r in gate.person_reasons(cur, person_id, channel, account_play_id=ap_id) if r.code not in skip]


def _first_channel(play: dict) -> str:
    chans = [st["channel"] for st in play["sequence"]]
    if "email" in chans:
        return "email"
    return "call" if chans and chans[0] == "call" else "linkedin"


@jobs.handler("replace_person")
def replace_person(cur, payload: dict) -> None:
    """The person for a role left or was the wrong one: find the next person for that role and enroll them, or tell
    the SDR why nobody could be found."""
    ap = db.one(cur, "select * from account_plays where id = %s", payload["account_play_id"])
    if ap is None or ap["state"] not in ("approving", "active", "engaged"):
        return
    play = dict(db.one(cur, "select * from plays where id = %s", ap["play_id"]))
    account = db.one(cur, "select * from accounts where id = %s", ap["account_id"])
    tried = frozenset(r["person_id"] for r in db.all(cur, "select person_id from enrollments where account_play_id = %s", ap["id"]))
    play.update(personas=[payload["persona_key"]], max_people=1)
    found = build_committee(cur, ap, play, account, exclude=tried)
    label = db.val(cur, "select label from personas where key = %s", payload["persona_key"]).lower()
    if not found:
        why = db.val(cur, "select reason from committee_gaps where account_play_id = %s and persona_key = %s",
                     ap["id"], payload["persona_key"])
        db.run(cur, """insert into tasks (account_play_id, kind, title, due_at, owner_id, note)
                       values (%s,'research',%s,app_now(),%s,%s)""", ap["id"], f"Find another {label} at this account",
               ap["owner_id"], why or "The desk found nobody else for this role")
        return
    p = found[0]
    eid = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, mailbox_id, next_at)
                         values (%s,%s,%s,'pending',%s,app_now()) returning id""",
                 ap["id"], p["id"], p["persona_key"], pick_mailbox(cur, ap["owner_id"], ap["id"]))
    first_email = next((i for i, st in enumerate(play["sequence"]) if st["channel"] == "email" and st["by"] == "desk"), None)
    if first_email is None:
        activate(cur, eid)
    else:
        draft_step(cur, eid, first_email)
    audit.log(cur, "desk", "person_replaced", "account_play", ap["id"], {"person_id": p["id"], "persona": p["persona_key"]})


@jobs.handler("enroll_referral")
def enroll_referral(cur, payload: dict) -> None:
    """Someone replied 'talk to my colleague'. The colleague becomes a person at the account, the referral becomes a
    fact a draft may cite, and if the play is still open they are found, verified and enrolled like anyone else.
    When that cannot happen, the SDR gets a task that says why."""
    r = db.one(cur, "select * from replies where id = %s", payload["reply_id"])
    ref = (r["extracted"] or {}).get("referral") or {}
    name = (ref.get("name") or "").strip()
    if not r["account_id"] or not name:
        return
    account = db.one(cur, "select * from accounts where id = %s", r["account_id"])
    referrer = db.val(cur, "select full_name from people where id = %s", r["person_id"]) or "A colleague"
    email = (ref.get("email") or "").strip().lower() or None
    # An address in a reply is untrusted: it is used only when it is at this account's own domain.
    if email and not db.val(cur, "select exists (select 1 from account_domains where account_id = %s and domain = %s)",
                            account["id"], email.split("@")[-1]):
        email = None
    from .privacy import erased
    if erased(cur, email=email, linkedin_url=None):
        return
    pid = db.val(cur, "select id from people where email = %s", email) if email else None
    pid = pid or db.val(cur, "select id from people where account_id = %s and lower(full_name) = lower(%s)", account["id"], name)
    if pid is None:
        first, _, last = name.partition(" ")
        pid = db.val(cur, """insert into people (account_id, full_name, first_name, last_name, title, email, source)
                             values (%s,%s,%s,%s,%s,%s,'referral') returning id""",
                     account["id"], name, first, last or None, ref.get("title"), email)
    db.run(cur, """insert into facts (account_id, person_id, kind, text, source, observed_at)
                   values (%s,%s,'referral',%s,'reply',%s)""",
           account["id"], pid, f"{referrer} suggested speaking with {name}.", r["received_at"])
    ap = db.one(cur, """select * from account_plays where account_id = %s and state in ('approving','active','engaged')
                        order by proposed_at desc limit 1""", account["id"])

    def task(why: str) -> None:
        db.run(cur, """insert into tasks (account_play_id, person_id, reply_id, kind, title, due_at, owner_id, note)
                       values (%s,%s,%s,'referral',%s,app_now(),%s,%s)""", ap["id"] if ap else None, pid, r["id"],
               f"Referred to {name}", ap["owner_id"] if ap else account["owner_id"], why)

    if ap is None:
        return task("No open play at this account, so nobody was enrolled.")
    play = db.one(cur, "select * from plays where id = %s", ap["play_id"])
    # A reply gives a name, not where the person works from, and an email's region rule needs a country.
    if _first_channel(play) == "email":
        from .enrichment import locate_person
        try:
            locate_person(cur, pid)
        except (spend.OverBudget, adapters.VendorMissing):
            pass
    reasons = _enrollable(cur, pid, ap["id"], _first_channel(play))
    if reasons:
        return task(reasons[0].message)
    person = db.one(cur, "select * from people where id = %s", pid)
    if _first_channel(play) == "email":
        status = _ensure_email(cur, person, account)
        if status != "valid":
            # _ensure_email says catch_all for an unconfirmed address (found when a referral's job died on it).
            return task({"missing": "No email address found for them", "risky": "Their email could not be confirmed",
                         "catch_all": "Their company accepts every address, so theirs could not be confirmed",
                         "invalid": "Their email address does not work"}.get(status, "Their email could not be confirmed"))
    persona = _persona_for(cur, person["title"]) or db.val(
        cur, "select persona_key from enrollments where person_id = %s order by created_at desc limit 1", r["person_id"]) or "cfo"
    db.run(cur, "update people set persona_key = coalesce(persona_key, %s) where id = %s", persona, pid)
    eid = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, mailbox_id, next_at, via_referral)
                         values (%s,%s,%s,'pending',%s,app_now(),true) returning id""",
                 ap["id"], pid, persona, pick_mailbox(cur, ap["owner_id"], ap["id"]))
    first_email = next((i for i, st in enumerate(play["sequence"]) if st["channel"] == "email" and st["by"] == "desk"), None)
    if first_email is None:
        activate(cur, eid)
    else:
        draft_step(cur, eid, first_email)
    audit.log(cur, "desk", "referral_enrolled", "person", pid, {"reply_id": r["id"], "enrollment_id": eid})


def _ensure_email(cur, person: dict, account: dict) -> str:
    """Find and verify. Returns valid | catch_all | invalid | missing.

    An address on file is verified; if it fails, the finders are asked for a better one. With no address, the finders
    run as a waterfall: the first is asked; if it has nothing, an address someone else holds, an address erased on
    request, or one that fails verification, the next is asked. Each finder charges only for an address it returns, and
    every answer is kept, so a job that runs again never pays twice."""
    from .enrichment import bought
    from .privacy import erased
    ad = adapters.get()
    if person["email"]:
        status = _verify(cur, ad, person, account, person["email"])
        if status != "invalid":
            return status
        db.run(cur, "update people set email = null, email_status = 'unknown' where id = %s", person["id"])
    status = "missing"
    for step in ad.finders or [ad.finder]:
        provider = getattr(step, "provider", "email_finder")

        def buy(step=step, provider=provider):
            with spend.paid_call(cur, f"email_finder:{provider}", "find", vendor="email_finder", qty=1,
                                 purpose=f"find email ({provider})", account_id=account["id"]) as info:
                email = step.find(cur, person, account["primary_domain"])
                info["found"] = bool(email)
                info["charged_qty"] = 1 if email else 0
            return email

        email = bought(cur, f"email_finder:{provider}", str(person["id"]), buy)
        if not email:
            continue
        email = email.lower()
        if db.val(cur, "select id from people where email = %s and id <> %s", email, person["id"]) or erased(cur, email=email, linkedin_url=None):
            continue
        db.run(cur, "update people set email = %s, email_found_by = %s, email_found_at = app_now() where id = %s",
               email, provider, person["id"])
        status = _verify(cur, ad, person, account, email)
        if status != "invalid":
            return status
        db.run(cur, "update people set email = null, email_status = 'unknown' where id = %s", person["id"])
    return status


def _verify(cur, ad, person: dict, account: dict, email: str) -> str:
    """Verify, then for a catch-all server ask the resolver. A verdict is kept for the verify window, whatever it
    was, so an unconfirmed address is not paid for again every few hours."""
    from .enrichment import bought, source
    max_age = int(setting(cur, "verify_max_age_days", 45))
    fresh = db.one(cur, """select email_status from people where id = %s and email = %s
                           and email_status in ('valid', 'catch_all') and email_verified_at > app_now() - (%s || ' days')::interval""",
                   person["id"], email, str(max_age))
    if fresh:
        return fresh["email_status"]

    def check():
        with spend.paid_call(cur, "email_verifier", "verify", vendor="email_verifier", qty=1, purpose="verify email",
                             account_id=account["id"]) as info:
            v = ad.verifier.verify(cur, email)
            info["status"] = v
        return v

    status = bought(cur, "email_verifier", email, check, keep_days=max_age)
    status = "catch_all" if status == "risky" else status
    by, confidence = ad.verifier.name, None
    if status == "catch_all" and ad.resolver is not None:
        def resolve():
            with spend.paid_call(cur, "email_resolver", "resolve", vendor="email_resolver", qty=1,
                                 purpose="resolve a catch-all address", account_id=account["id"]) as info:
                v = ad.resolver.resolve(cur, email)
                info["status"] = v[0]
            return list(v)

        status, confidence = bought(cur, "email_resolver", email, resolve, keep_days=max_age)
        by = ad.resolver.name
    db.run(cur, """update people set email_status = %s, email_verified_at = app_now(), email_verified_by = %s,
                   email_confidence = coalesce(%s, email_confidence) where id = %s""", status, by, confidence, person["id"])
    source(cur, "person", person["id"], "email_status", status, by, confidence)
    return status


def check_claims(cur, out: dict, facts: dict[int, str], company: str, account_id: int | None = None) -> list[dict]:
    """The second check: every sentence about the buyer is read against the facts. Returns copy-gate style failures,
    empty when every sentence holds. The copy checks catch what code can see (citations, numbers, names); this catches
    the implication code cannot ('your team rebuilds invoices by hand')."""
    from . import llm
    sentences = [s["text"] for s in out["sentences"]]
    got = llm.run(cur, "check_claims", {"company": company, "facts": [{"id": k, "text": v} for k, v in facts.items()],
                                        "sentences": sentences}, account_id=account_id)
    return [{"code": "unsupported_about_them",
             "message": f"Sentence {c['index'] + 1} says something about them the facts do not: {c['why']}"}
            for c in got["sentences"] if not c["supported"] and 0 <= c["index"] < len(sentences)]


def _record_basis(cur, person: dict, play: dict) -> str | None:
    rule = db.val(cur, "select rule from region_rules where country = %s", person["country"])
    # Legitimate interest rests on a current assessment: one past its review date records no new basis.
    if rule == "basis_required" and play.get("lia_ref") and play.get("lia_review_due") is not None \
            and not db.val(cur, "select %s::date < app_now()::date", play["lia_review_due"]):
        db.run(cur, """insert into contact_basis (person_id, basis, recorded_by) values (%s, %s, null)
                       on conflict (person_id) do nothing""", person["id"], f"legitimate_interest:{play['lia_ref']}")
    return rule


def build_committee(cur, ap: dict, play: dict, account: dict, *, exclude: frozenset[int] = frozenset()) -> list[dict]:
    ad = adapters.get()
    personas = {p["key"]: p for p in db.all(cur, "select * from personas")}
    chosen: list[dict] = []
    gaps: dict[str, str] = {}
    trigger_person = db.val(cur, "select person_id from signals where id = %s", ap["trigger_signal_id"])
    used: set[int] = set(exclude)
    # The account's own cap wins: a play may ask for five, but only tier A accounts take more than three at once
    # (the enrollment trigger refuses the rest).
    wide = int(setting(cur, "account_max_active_wide", 5)) if account.get("fit_tier") == "A" else int(setting(cur, "account_max_active", 3))
    limit = min(play["max_people"], wide if play["max_people"] > 3 else play["max_people"])
    for key in play["personas"]:
        if len(chosen) >= limit:
            break
        persona = personas[key]
        candidates = db.all(cur, """select * from people where account_id = %s and status = 'active'
                                    order by (id = %s) desc, id""", account["id"], trigger_person or 0)
        candidates = [c for c in candidates if c["id"] not in used and (
            _fits(c, persona) or (c["id"] == trigger_person and key in ("controller", "cfo")))]
        if not candidates:
            from .adapters import Candidate
            from .enrichment import apply_person, bought, linkedin_key

            def search(persona=persona):
                with spend.paid_call(cur, "people_search", "search", vendor="people_search", qty=1, purpose="find people",
                                     account_id=account["id"]) as info:
                    hits = ad.people.search(cur, account, persona["title_patterns"], 3)
                    info["found"] = len(hits)
                return hits

            found = [Candidate(**c) for c in bought(cur, "people_search", f"{account['id']}:{key}", search)]
            from .privacy import linkedin_hash, linkedin_hmac
            for c in found:
                existing = db.val(cur, "select id from people where linkedin_key = %s", linkedin_key(c.linkedin_url))
                if existing:
                    continue
                if c.linkedin_url and db.val(cur, "select exists (select 1 from suppressions where "
                                                  "(kind = 'linkedin_hash' and value = %s) or (kind = 'linkedin_hmac' and value = %s))",
                                             linkedin_hash(c.linkedin_url), linkedin_hmac(c.linkedin_url)):
                    continue  # erased on request: never added again
                if c.match_confidence == "low":
                    continue  # the vendor is not sure this is the right person
                pid = db.val(cur, """insert into people (account_id, full_name, first_name, last_name, title, seniority,
                                                         linkedin_url, linkedin_key, country, timezone, source, photo_url,
                                                         source_origin)
                                     values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'people_search',%s,%s) returning id""",
                             account["id"], c.full_name, c.first_name, c.last_name, c.title, c.seniority, c.linkedin_url,
                             linkedin_key(c.linkedin_url), c.country, c.timezone, c.photo_url,
                             getattr(ad.people, "name", None) or "people_search")
                ad.people.saved(cur, c, pid)
                apply_person(cur, pid, {k: getattr(c, k) for k in ("departments", "role_started_at", "city", "headline",
                                                                    "match_confidence", "timezone", "title")}, "people_search")
            candidates = [c for c in db.all(cur, "select * from people where account_id = %s and status = 'active' "
                                                 "and source = 'people_search' order by id", account["id"])
                          if c["id"] not in used and _fits(c, persona)]
        candidates.sort(key=lambda c: (c["id"] != trigger_person, -SENIORITY_RANK.get(c["seniority"] or "", 0)))
        picked = None
        last_reason = "Nobody with this role found"
        for c in candidates:
            if not c["country"] and any(st["channel"] == "email" for st in play["sequence"]):
                # Known only by name and seat (an announcement, a referral): the region rule needs their country.
                from .enrichment import locate_person
                try:
                    locate_person(cur, c["id"])
                except (spend.OverBudget, adapters.VendorMissing):
                    pass
                c = db.one(cur, "select * from people where id = %s", c["id"])
            reasons = _enrollable(cur, c["id"], ap["id"], _first_channel(play))
            if reasons:
                last_reason = reasons[0].message
                continue
            # Ask only for what the sequence uses: an email for emails, a profile for LinkedIn, a number for calls.
            channels = {st["channel"] for st in play["sequence"]}
            if "email" in channels:
                rule = _record_basis(cur, c, play)
                if rule == "consent_required":
                    last_reason = f"Email in {gate.country_name(c['country'])} needs consent first; the SDR can call or connect instead"
                    continue
                status = _ensure_email(cur, c, account)
                if status != "valid":
                    last_reason = {"missing": "No email address found by any finder",
                                   "catch_all": "Their company accepts every address, so theirs could not be confirmed",
                                   "invalid": "Email address does not work"}[status]
                    continue
            elif channels & {"linkedin_connect", "linkedin_message"} and not c["linkedin_url"]:
                last_reason = "No LinkedIn profile found"
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
    """Today's cap for a mailbox. The rule lives in the database (mailbox_cap), where the send trigger enforces it."""
    return int(db.val(cur, "select mailbox_cap(%s)", mailbox["id"]))


def setting(cur, key: str, default):
    v = db.val(cur, "select value from settings where key = %s", key)
    return default if v is None else v


def placement(cur, mailbox_id: int) -> tuple[float | None, bool]:
    """The worst inbox rate across providers in the mailbox's latest seed test, and whether that test is too old
    (or missing) to go on."""
    rows = db.all(cur, """select distinct on (provider) provider, inbox::float / seeds as rate, at from placement_tests
                          where mailbox_id = %s order by provider, at desc""", mailbox_id)
    if not rows:
        return None, True
    max_age = int(setting(cur, "placement_max_age_days", 10))
    stale = db.val(cur, "select min(x) < app_now() - (%s || ' days')::interval from unnest(%s::timestamptz[]) x",
                   max_age, [r["at"] for r in rows])
    return min(r["rate"] for r in rows), bool(stale)


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
    return db.val(cur, """select (select count(*) from messages where mailbox_id = %s and status in ('sent', 'sending', 'send_unknown')
                                  and sent_at >= date_trunc('day', app_now()))
                                + (select count(*) from reply_sends where mailbox_id = %s and status in ('sent', 'sending', 'send_unknown')
                                  and sent_at >= date_trunc('day', app_now()))""", mailbox_id, mailbox_id)


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
    token = unsubscribe_token(person["id"])
    url = f"{CONFIG.public_url}/u/{person['id']}-{token[:12]}"
    privacy = CONFIG.privacy_url if (person.get("country") or "").upper() in NOTICE_COUNTRIES else None
    return copy_gate.footer(company=CONFIG.sender_company, address=CONFIG.sender_address, unsubscribe_url=url,
                            privacy_url=privacy, data_source=DATA_SOURCES.get(person.get("source") or ""))


_unsub_secret: str | None = None


def _unsubscribe_secret() -> str:
    """Opt-out links must keep working for as long as an email can sit in an inbox, across every process and
    restart. The signing secret is made once and kept in the database, never derived from a per-process value."""
    global _unsub_secret
    if _unsub_secret is None:
        import secrets
        with db.tx() as cur:
            db.run(cur, "insert into settings (key, value) values ('unsubscribe_secret', %s) on conflict (key) do nothing",
                   J(secrets.token_hex(32)))
            _unsub_secret = db.val(cur, "select value from settings where key = 'unsubscribe_secret'")
    return _unsub_secret


def unsubscribe_token(person_id: int) -> str:
    return hmac.new(_unsubscribe_secret().encode(), f"unsub:{person_id}".encode(), hashlib.sha256).hexdigest()[:24]


def desk_steps(play: dict) -> list[int]:
    return [i for i, s in enumerate(play["sequence"]) if s["by"] == "desk"]


def limits_for(job: str, linkedin: bool, max_chars: int | None) -> dict:
    """The limits the copy checks hold a draft to, given to the model up front so the first attempt can meet them."""
    lo, hi = copy_gate.LIMITS.get(job, (10, 120))
    out = {"body_words": [lo, hi]}
    if linkedin:
        if max_chars:
            out["max_characters"] = max_chars
    else:
        out["subject_words"] = [1, 6]
    return out


def linkedin_text(sentences: list[dict]) -> str:
    """The greeting on its own line, as in email: lowering the next word could break a name it starts with."""
    if not sentences:
        return ""
    head, rest = sentences[0]["text"], " ".join(x["text"] for x in sentences[1:])
    return f"{head}\n{rest}" if rest else head


def seat_news_not_theirs(cur, fact: dict, person: dict) -> bool:
    """Whether a new-finance-leader fact must not go to this person: they sit in the finance leader's seat and are not
    the one it names, or it names nobody and they started in the seat more than 30 days before the news."""
    if fact["kind"] != "signal:new_exec":
        return False
    from .enrichment import in_leader_seat
    if not in_leader_seat(cur, person.get("title")):
        return False
    if fact.get("person_id") is not None:
        return fact["person_id"] != person["id"]
    started = person.get("role_started_at")
    return started is None or started < fact["observed_at"].date() - timedelta(days=30)


# Given to the draft model inside the `event` input, so the drafting prompt (and its recordings) stay as they are for every play.
EVENT_NOTE = ("This email is a note before the event: say you will be at the event (with its city and dates when given), citing "
              "the signal fact that names it, and never that they are on a list. In a first email say a reply will find a time "
              "there and write no link. Only when step.job is follow_up and booking_url is not null, add one sentence that gives "
              "booking_url exactly as written as the way to book a time; otherwise write no link.")


def event_context(cur, ap: dict, play: dict, step: dict) -> dict | None:
    """The event a note before an event is about, from what Events Desk said when the person was targeted (stored in the
    signal's evidence): {name, city, starts_on, ends_on, booking_url}. Only the day-7 follow-up of `event_pre_event` carries
    the booking link, and only the one Events Desk gave; every other step has booking_url None, and the first email says a
    reply will find a time. None for every other play (alone, nothing about events reaches a draft)."""
    if play["key"] != "event_pre_event":
        return None
    sig = db.val(cur, "select evidence from signals where id = %s and type_key = 'event_targeted'", ap["trigger_signal_id"]) or {}
    ev = {**(sig.get("event") or {})}
    ev["name"] = ev.get("name") or sig.get("campaign_name")          # Events Desk did not answer: the CRM's campaign name
    if not ev["name"]:
        return None
    link = ev.get("booking_url") if step["job"] == "follow_up" and step["channel"] == "email" else None
    return {"instructions": EVENT_NOTE, "name": ev.get("name"), "city": ev.get("city"), "starts_on": ev.get("starts_on"), "ends_on": ev.get("ends_on"),
            "booking_url": signals.http_url(link) if link else None}


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
    # A referral is about one person: only their draft may cite it.
    others_refs = {r["id"] for r in db.all(cur, "select id from facts where account_id = %s and kind = 'referral' "
                                               "and person_id is distinct from %s", account["id"], person["id"])}
    facts = [f for f in facts if f["id"] not in others_refs]
    # News of a new finance leader is not written to someone else in that seat, nor to someone who has sat in it for
    # longer than the news is old: it would congratulate the wrong person (found 2026-11-11).
    not_theirs = {f["id"] for f in facts if seat_news_not_theirs(cur, f, person)}
    facts = [f for f in facts if f["id"] not in not_theirs]
    fact_map = {f["id"]: f["text"] for f in facts}
    prev = db.one(cur, "select subject, body from messages where enrollment_id = %s and step_index < %s and channel = 'email' "
                       "order by step_index desc limit 1", enrollment_id, step_index)
    others = [r["body"] for r in db.all(cur, """select m.body from messages m join enrollments en on en.id = m.enrollment_id
                                               where en.account_play_id = %s and en.id <> %s and m.status not in
                                               ('rejected', 'cancelled')""", ap["id"], enrollment_id)]
    earlier = (prev["body"] or "").split("\n\n--\n")[0] if prev and prev["body"] and not step["channel"].startswith("linkedin") else None
    linkedin = step["channel"].startswith("linkedin")
    max_chars = None
    if step["channel"] == "linkedin_connect":
        from .sdr_steps import note_limit
        max_chars = note_limit(cur)
    event = event_context(cur, ap, play, step)
    allowed_links = None
    if play["key"] in ("event_pre_event", "event_follow_up") and not linkedin:
        allowed_links = {event["booking_url"]} if event and event.get("booking_url") else set()
    attempts = []
    failures: list[dict] = []
    out = None
    verdict = None
    for attempt in (1, 2):
        payload = {"company": account["name"], "our_company": CONFIG.sender_company, "sender": owner["name"], "angle": persona["angle"],
                   "play_angle": play["angle"],
                   "brief": [x for x in (ap["brief"] or {}).get("findings", []) if not set(x.get("fact_ids") or []) & not_theirs],
                   "person": {"id": person["id"], "first_name": copy_gate.clean_first_name(person["first_name"], person["full_name"]),
                              "title": person["title"]},
                   "step": {"index": step_index, "job": step["job"]}, "persona_key": e["persona_key"],
                   "facts": [{"id": f["id"], "kind": f["kind"], "text": f["text"]} for f in facts],
                   "previous_subject": prev["subject"] if prev else None,
                   "previous_body": earlier, "attempt": attempt,
                   "failures": [x["message"] for x in failures], "limits": limits_for(step["job"], linkedin, max_chars)}
        if linkedin:
            payload["max_chars"] = max_chars
        if event is not None:
            payload["event"] = event
        out = llm.run(cur, "draft_linkedin" if linkedin else "draft", payload, account_id=account["id"])
        private_ids = {r["id"] for r in db.all(cur, "select id from facts where account_id = %s and kind = any(%s)",
                                              account["id"], [f"signal:{k}" for k in PRIVATE_SIGNALS])}
        verdict = copy_gate.check(out, job=step["job"], person=person, account=account, facts=fact_map,
                                  our_names=OUR_NAMES + [owner["name"]], other_bodies=others, private_ids=private_ids,
                                  channel="linkedin" if linkedin else "email", max_chars=max_chars, earlier=earlier,
                                  allowed_links=allowed_links)
        if verdict.passed:
            unsupported = check_claims(cur, out, fact_map, account["name"], account["id"])
            if unsupported:
                verdict = copy_gate.Verdict(passed=False, failures=unsupported, words=verdict.words)
        attempts.append({"attempt": attempt, "passed": verdict.passed, "failures": verdict.failures})
        if verdict.passed:
            break
        failures = verdict.failures
    citations = sorted({i for s in out["sentences"] for i in (s.get("fact_ids") or [])})
    status = "awaiting_approval" if verdict.passed else "failed_gate"
    if linkedin:
        # Sent by the SDR from their own account: no subject, no sign-off, no footer. The SDR approves it by
        # sending it (sdr_steps.complete), so it never waits in the approvals queue.
        msg = db.one(cur, """
            insert into messages (enrollment_id, step_index, channel, subject, body, citations, status, gate, attempts,
                                  template_key, body_hash)
            values (%s,%s,'linkedin',null,%s,%s,%s,%s,%s,%s,'')
            on conflict (enrollment_id, step_index) do update set body = excluded.body, citations = excluded.citations,
              status = excluded.status, gate = excluded.gate, attempts = excluded.attempts
            returning *""",
            enrollment_id, step_index, linkedin_text(out["sentences"]),
            J({"ids": citations, "sentences": out["sentences"]}), status, J(verdict.as_dict()), J(attempts),
            f"{play['key']}:v{play['version']}:{step_index}")
        return msg
    body = copy_gate.assemble(out, sender_name=owner["name"], company=CONFIG.sender_company,
                              footer=footer_for(person, f"{enrollment_id}:{step_index}"))
    msg = db.one(cur, """
        insert into messages (enrollment_id, step_index, channel, subject, body, citations, status, gate, attempts,
                              template_key, mailbox_id, body_hash)
        values (%s,%s,'email',%s,%s,%s,%s,%s,%s,%s,%s,'')
        on conflict (enrollment_id, step_index) do update set subject = excluded.subject, body = excluded.body,
          citations = excluded.citations, status = excluded.status, gate = excluded.gate, attempts = excluded.attempts,
          edited = false, original_subject = null, original_body = null
        returning *""",
        enrollment_id, step_index, out["subject"], body, J({"ids": citations, "sentences": out["sentences"]}), status,
        J(verdict.as_dict()), J(attempts), f"{play['key']}:v{play['version']}:{step_index}", e["mailbox_id"])
    if status == "awaiting_approval":
        maybe_auto_approve(cur, msg["id"])
    return db.one(cur, "select * from messages where id = %s", msg["id"])


# ---------------------------------------------------------------- approval

def _sample(message_id: int) -> bool:
    return int(hashlib.sha256(f"sample:{message_id}".encode()).hexdigest()[:4], 16) % 5 == 0


def autonomous_enabled(cur) -> bool:
    """Whether a manager has the fourth stage turned on. No row (an older desk) means on, as before BL-126."""
    return setting(cur, "autonomous_stage", True) is not False


def maybe_auto_approve(cur, message_id: int) -> bool:
    m = db.one(cur, """select m.*, pl.autonomy, pl.id as play_id, a.fit_tier from messages m join enrollments e on e.id = m.enrollment_id
                       join account_plays ap on ap.id = e.account_play_id join plays pl on pl.id = ap.play_id
                       join accounts a on a.id = ap.account_id where m.id = %s""", message_id)
    if m["status"] != "awaiting_approval":
        return False
    mode = None
    standing_id = None
    if m["autonomy"] == "supervised":
        # BL-171: only under a standing approval a manager signed, and only for what it covers; the rest waits for a person.
        pol = standing.in_force(cur, m["play_id"])
        ctx = standing.message_context(cur, message_id) if pol else None
        if pol and standing.covered(cur, pol, ctx) is None:
            standing_id = pol["id"]
            if _sample(message_id):
                db.run(cur, "update messages set standing_approval_id = %s where id = %s", standing_id, message_id)   # a sampled draft: a person decides
            else:
                mode = "auto_supervised"
    elif m["autonomy"] == "autonomous" and m["fit_tier"] == "B" and autonomous_enabled(cur):
        mode = "auto_autonomous"
    if mode is None:
        return False
    from . import replies
    if replies.unread_reply(cur, db.val(cur, "select person_id from enrollments where id = %s", m["enrollment_id"])):
        return False                # decision 108 holds for the automatic path too: a person reads their reply first
    _approve(cur, m, user_id=None, mode=mode)
    if standing_id is not None:
        db.run(cur, "update messages set standing_approval_id = %s where id = %s", standing_id, message_id)
    return True


def approve(cur, message_id: int, *, user_id: int, subject: str | None = None, body: str | None = None) -> dict:
    m = db.one(cur, "select * from messages where id = %s for update", message_id)
    if m["channel"] != "email":
        raise ValueError("A LinkedIn note is approved by sending it from its task.")
    if m["status"] not in ("awaiting_approval", "failed_gate"):
        raise ValueError(f"Message is {m['status']}, not waiting for approval")
    if m["status"] == "failed_gate" and body is None:
        raise ValueError("This draft failed the checks. Rewrite it before approving.")
    e = db.one(cur, "select person_id, account_play_id, id from enrollments where id = %s", m["enrollment_id"])
    from . import replies
    if replies.unread_reply(cur, e["person_id"]):
        raise ValueError(replies.READ_FIRST + ".")          # decision 108
    blocking = [r for r in gate.person_reasons(cur, e["person_id"], "email", account_play_id=e["account_play_id"],
                                               enrollment_id=e["id"]) if r.permanent]
    if blocking:
        raise ValueError(f"This person cannot be emailed: {blocking[0].message}")
    edited = False
    if (subject is not None and subject != m["subject"]) or (body is not None and body != m["body"]):
        edited = True
        # Checked on the text as it would be, before anything is written: a caller that does not roll back (the
        # simulation) must not be left with a failing body marked as edited.
        problems = _edit_checks({**m, "subject": m["subject"] if subject is None else subject,
                                 "body": m["body"] if body is None else body}, cur)
        if problems:
            raise ValueError("; ".join(problems))
        db.run(cur, "update messages set original_subject = case when original_body is null then subject else original_subject end, "
                    "original_body = coalesce(original_body, body), "
                    "subject = coalesce(%s, subject), body = coalesce(%s, body), edited = true where id = %s",
               subject, body, message_id)
        m = db.one(cur, "select * from messages where id = %s", message_id)
    _approve(cur, m, user_id=user_id, mode="person")
    audit.log(cur, "person", "approved", "message", message_id, {"edited": edited}, actor_id=user_id)
    return db.one(cur, "select * from messages where id = %s", message_id)


def edit_words(body: str) -> int:
    """Words in what the person writes: the greeting and the signature block are not counted, as in the copy check."""
    paras = [p for p in body.split("\n\n--\n")[0].split("\n\n") if p.strip()]
    if len(paras) >= 3:
        paras = paras[1:-1]
    elif len(paras) == 2:
        paras = paras[1:]
    return copy_gate.words(" ".join(paras))


def step_limits(cur, m: dict) -> tuple[int, int]:
    job = db.val(cur, """select p.sequence -> %s ->> 'job' from enrollments e join account_plays ap on ap.id = e.account_play_id
                         join plays p on p.id = ap.play_id where e.id = %s""", m["step_index"], m["enrollment_id"])
    return copy_gate.LIMITS.get(job, (10, 120))


def check_edit(cur, message_id: int, subject: str | None, body: str) -> dict:
    """A dry run of what `approve` checks on an edit. Writes nothing."""
    m = db.one(cur, "select * from messages where id = %s", message_id)
    m = {**m, "body": body, "subject": m["subject"] if subject is None else subject}
    lo, hi = step_limits(cur, m)
    return {"problems": _edit_checks(m, cur), "words": edit_words(body), "limit": [lo, hi]}


def _edit_checks(m: dict, cur=None) -> list[str]:
    """A person's edit is checked as text: the footer stays, no dashes, merge fields, banned or spam phrases,
    no link in a first email, and every number and name must be in the account's citable facts."""
    out = []
    text = m["body"].split("\n\n--\n")[0]
    if cur is not None:
        lo, hi = step_limits(cur, m)
        n = edit_words(m["body"])
        if not lo <= n <= hi:
            out.append(f"{n} words; this step needs {lo} to {hi}")
    low = (m["subject"] or "").lower() + " " + text.lower()
    out += [f"Uses \"{b}\"" for b in copy_gate.BANNED if b in low]
    out += [f"Spam-filter word \"{w}\"" for w in copy_gate.SPAM_HARD if re.search(r"\b" + re.escape(w) + r"\b", low)]
    if m["step_index"] == 0 and copy_gate.URL.search(text):
        out.append("First emails carry no links")
    if cur is not None:
        e = db.one(cur, "select ap.account_id from enrollments e join account_plays ap on ap.id = e.account_play_id "
                        "where e.id = %s", m["enrollment_id"])
        facts = " ".join(f["text"] for f in account_facts(cur, e["account_id"], 30))
        for num in copy_gate.NUMBER.findall(text):
            core = num.strip("$%.,")
            if core and core.replace(",", "") not in facts.replace(",", "") and not re.search(re.escape(num) + r"[- ]?(min|minutes|hour)", text):
                out.append(f"The number {num} is not in any fact we hold about them")
    if "To stop hearing from us" not in m["body"] and "won't write again" not in m["body"]:
        out.append("The opt-out line at the bottom has to stay")
    if any(d in m["body"] for d in copy_gate.DASHES):
        out.append("Long dashes are not allowed")
    if copy_gate.MERGE.search(m["body"]):
        out.append("A merge field is not filled in")
    return out


def _approve(cur, m: dict, *, user_id: int | None, mode: str) -> None:
    # The traceparent of the approving request is kept on the message (NULL when tracing is off or nobody's request
    # approved it), so the send's CRM check, hours later in a worker, is linked to the approval (decision 107).
    db.run(cur, """update messages set status = 'approved', approved_hash = body_hash, approved_by = %s,
                   approval_mode = %s, approved_at = app_now(), trace_parent = %s where id = %s""",
           user_id, mode, telemetry.current_traceparent(), m["id"])
    e = db.one(cur, "select * from enrollments where id = %s", m["enrollment_id"])
    if e["state"] == "pending":
        activate(cur, e["id"])
    else:
        schedule_message(cur, m["id"])


BATCH_MAX = 25


class BatchRefused(ValueError):
    """The whole request is refused before any draft is approved; `status` is the HTTP answer for it."""
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def approve_batch(cur, message_ids: list[int], *, user_id: int, role: str) -> dict:
    """BL-170 (decision 120). A person approves several drafts of one play and step at once. Each draft is its own approval:
    `approve` runs on it unchanged with no edit, in its own savepoint, so every refusal that applies to one draft still
    applies, and one refusal never stops the others. Only a draft that passed the checks qualifies; a draft that failed them
    needs its rewrite first. Nothing here runs without a person's request, and `maybe_auto_approve` is not involved."""
    ids = list(dict.fromkeys(message_ids))
    if not ids:
        raise BatchRefused("Tick at least one draft.")
    if len(ids) > BATCH_MAX:
        raise BatchRefused(f"Approve at most {BATCH_MAX} drafts at once; tick fewer.")
    rows = db.all(cur, """select m.id, m.template_key, m.status, m.channel, ap.owner_id, ap.account_id
                          from messages m join enrollments e on e.id = m.enrollment_id
                          join account_plays ap on ap.id = e.account_play_id where m.id = any(%s)""", ids)
    if len(rows) != len(ids):
        raise BatchRefused("One of those drafts no longer exists.", 404)
    if any(r["channel"] != "email" for r in rows):
        raise BatchRefused("Only emails are approved here; a LinkedIn note is approved by sending it.")
    if role == "sdr" and any(r["owner_id"] != user_id for r in rows):
        raise BatchRefused("One of those drafts belongs to another SDR's account.", 403)
    if len({r["template_key"] for r in rows}) != 1:
        raise BatchRefused("A group is one play and one email; tick drafts from a single group.")
    key = rows[0]["template_key"]
    batch = db.val(cur, "insert into approval_batches (template_key, approved_by, requested, approved) values (%s,%s,%s,0) returning id",
                   key, user_id, len(ids))
    approved: list[int] = []
    skipped: list[dict] = []
    # Accounts in id order: two people approving overlapping groups lock accounts in the same order and cannot deadlock.
    for r in sorted(rows, key=lambda r: (r["account_id"], r["id"])):
        if r["status"] != "awaiting_approval":
            skipped.append({"id": r["id"], "reason": "It needs a rewrite before it can be approved."
                            if r["status"] == "failed_gate" else f"It is {r['status']}, not waiting for approval."})
            continue
        try:
            with cur.connection.transaction():
                approve(cur, r["id"], user_id=user_id)
                db.run(cur, "update messages set approval_batch_id = %s where id = %s", batch, r["id"])
                audit.log(cur, "person", "approved_in_batch", "message", r["id"], {"batch": batch}, actor_id=user_id)
            approved.append(r["id"])
        except (ValueError, psycopg.Error) as exc:     # a lock timeout or deadlock on one draft skips that draft only
            skipped.append({"id": r["id"], "reason": str(exc).split("\n")[0]})
    db.run(cur, "update approval_batches set approved = %s, skipped = %s where id = %s", len(approved), J(skipped), batch)
    audit.log(cur, "person", "batch_approved", "approval_batch", batch,
              {"template_key": key, "requested": len(ids), "approved": len(approved), "skipped": len(skipped)}, actor_id=user_id)
    return {"batch": batch, "approved": approved, "skipped": skipped}


def take_back(cur, message_id: int, *, user_id: int, role: str) -> dict:
    """BL-170. A person takes their approval of an email back while it has not gone out: it returns to waiting for approval,
    the approval's hash, slot and mark are cleared, and when that approval had started the person's sequence (a first email)
    and nothing of it was sent, the sequence returns to waiting and the play to approving. Locks enrollment then message,
    the order the send uses, so a send that already claimed the message wins and this refuses."""
    eid = db.val(cur, "select enrollment_id from messages where id = %s", message_id)
    if eid is None:
        raise ValueError("No such email.")
    e = db.one(cur, "select * from enrollments where id = %s for update", eid)
    m = db.one(cur, "select * from messages where id = %s for update", message_id)
    if m["channel"] != "email":
        raise ValueError("Only an email approval can be taken back.")
    if m["status"] not in ("approved", "scheduled"):
        raise ValueError("This email is " + m["status"].replace("_", " ") + ", so its approval cannot be taken back."
                         if m["status"] != "awaiting_approval" else "This email is not approved.")
    if m["approval_mode"] != "person":
        raise ValueError("The desk approved this one under a standing approval; revoke that to stop the rest.")
    if role == "sdr" and m["approved_by"] != user_id:
        raise PermissionError("Only the person who approved it, or a manager, can take it back.")
    db.run(cur, """update messages set status = 'awaiting_approval', approved_hash = null, approved_by = null, approval_mode = null,
                   approved_at = null, scheduled_for = null, planned_for = null, trace_parent = null,
                   taken_back_at = app_now(), taken_back_by = %s where id = %s""", user_id, message_id)
    # An approval of the sequence's first step is what started the person's sequence; taking it back puts the sequence back to
    # waiting, with a fresh lapse clock (a pending sequence nobody approves lapses, `due_steps`). Only for step 0: a later
    # step just returns to waiting, and a sequence that opens with a call or LinkedIn step is left as it is.
    first = m["step_index"] == 0 and e["state"] == "active" and not db.val(
        cur, "select exists (select 1 from messages where enrollment_id = %s and status in ('sending', 'sent', 'send_unknown'))", e["id"])
    if first:
        db.run(cur, "update enrollments set state = 'pending', started_at = null, next_at = app_now() where id = %s", e["id"])
        ap = db.one(cur, "select id, state from account_plays where id = %s for update", e["account_play_id"])
        # Only a play that has not reached anyone goes back: no other enrollment is going, and nothing of the play was sent.
        if ap["state"] == "active" and not db.val(
                cur, """select exists (select 1 from enrollments x where x.account_play_id = %s and x.id <> %s
                        and (x.state in ('active', 'done', 'paused')
                             or exists (select 1 from messages y where y.enrollment_id = x.id and y.status in ('sending', 'sent', 'send_unknown'))))""",
                ap["id"], e["id"]):
            # plays.ALLOWED has no active -> approving: this is the one reverse move, written on purpose and audited.
            db.run(cur, "update account_plays set state = 'approving' where id = %s", ap["id"])
            audit.log(cur, "person", "play_approving", "account_play", ap["id"],
                      {"from": "active", "reason": "approval taken back"}, actor_id=user_id)
    audit.log(cur, "person", "approval_taken_back", "message", message_id,
              {"was": m["status"], "batch": m.get("approval_batch_id")}, actor_id=user_id)
    return db.one(cur, "select * from messages where id = %s", message_id)


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
    # Each colleague's first email goes two business days, in their own time, after the last colleague's first email
    # at this account: the one actually sent, or the one scheduled. A start date alone is not enough, because a first
    # email can wait days behind a send window, a holiday or a full mailbox (found 2026-11-11). The account row lock
    # keeps two approvals from picking the same day, and the send itself checks again (colleague_clear). It is a
    # no-key lock: a full one blocks the ledger rows that paid calls write about this account on their own connection,
    # and the transaction holding it then waits on itself (found when the 3,000-account build hung).
    db.one(cur, "select id from accounts where id = %s for no key update", ap["account_id"])
    start = first_email_start(cur, e, ap, person)
    db.run(cur, "update enrollments set state = 'active', started_at = %s, next_at = %s, step_index = 0 where id = %s",
           start, start, enrollment_id)
    if ap["state"] == "approving":
        plays.set_state(cur, ap["id"], "active")
    m = db.one(cur, "select id from messages where enrollment_id = %s and step_index = 0", enrollment_id)
    if m:
        schedule_message(cur, m["id"])  # when the first step is a task, the email waits for its own day


def first_email_start(cur, e: dict, ap: dict, person: dict):
    """When a person's sequence starts once their first email is approved: now, or two business days (in their own
    time) after the last colleague's first email at the account. `activate` and the approval sheet's slot share this."""
    stagger = int(db.val(cur, "select value from settings where key = 'stagger_days'") or 2)
    last = last_colleague_first_email(cur, ap["account_id"], e["id"])
    now = db.val(cur, "select app_now()")
    if last is None:
        return now
    return max(now, timeutil.add_business_days(last, stagger, country=person["country"], timezone=person["timezone"]))


def message_slot(cur, message_id: int) -> dict | None:
    """The moment `approve` would give this message, worked out the way `activate` and `schedule_message` do it (same
    start, same window, same jitter key), without writing anything. None while it waits for an earlier step."""
    m = db.one(cur, "select * from messages where id = %s", message_id)
    if m["channel"] != "email":
        return None
    e = db.one(cur, "select * from enrollments where id = %s", m["enrollment_id"])
    person = db.one(cur, "select first_name, full_name, timezone, country from people where id = %s", e["person_id"])
    now = db.val(cur, "select app_now()")
    if m["status"] == "scheduled":
        at = m["scheduled_for"]
    elif m["status"] not in ("awaiting_approval", "failed_gate", "approved"):
        return None
    else:
        if e["state"] == "pending" and m["step_index"] == 0:
            ap = db.one(cur, "select * from account_plays where id = %s", e["account_play_id"])
            planned = max(first_email_start(cur, e, ap, person), now)
        elif e["state"] == "active" and m["step_index"] == e["step_index"]:
            planned = max(e["next_at"] or now, now)
        else:
            return None
        at = timeutil.next_slot(planned, timezone=person["timezone"], country=person["country"], window=_window(cur),
                                jitter_key=f"m{message_id}")
    return {"at": at, "recipient_tz": person["timezone"],
            "recipient_first_name": copy_gate.clean_first_name(person["first_name"], person["full_name"])}


def last_colleague_first_email(cur, account_id: int, enrollment_id: int):
    """When the latest colleague at this account got (or is set to get) their first email: sent beats scheduled, and a
    colleague with neither counts from when their sequence started."""
    return db.val(cur, """
        select max(coalesce(
                 (select min(m.sent_at) from messages m where m.enrollment_id = e.id and m.channel = 'email'
                    and m.status in ('sent', 'sending', 'send_unknown')),
                 (select min(m.scheduled_for) from messages m where m.enrollment_id = e.id and m.channel = 'email'
                    and m.status = 'scheduled'),
                 e.started_at))
        from enrollments e join account_plays x on x.id = e.account_play_id
        where x.account_id = %s and e.started_at is not null and e.id <> %s""", account_id, enrollment_id)


def colleague_clear(cur, enrollment: dict, person: dict, at):
    """None when a first email may go now; otherwise the earliest time it may, two business days in the recipient's
    own time after a colleague's first email that was already sent."""
    stagger = int(db.val(cur, "select value from settings where key = 'stagger_days'") or 2)
    last = db.val(cur, """select max(m.sent_at) from messages m join enrollments e on e.id = m.enrollment_id
                          join account_plays x on x.id = e.account_play_id
                          where x.account_id = (select account_id from account_plays where id = %s) and e.id <> %s
                            and m.channel = 'email' and m.status in ('sent', 'sending', 'send_unknown')
                            and m.sent_at = (select min(m2.sent_at) from messages m2 where m2.enrollment_id = e.id
                                             and m2.channel = 'email' and m2.status in ('sent', 'sending', 'send_unknown'))""",
                  enrollment["account_play_id"], enrollment["id"])
    if last is None:
        return None
    earliest = timeutil.add_business_days(last, stagger, country=person["country"], timezone=person["timezone"])
    return None if at >= earliest else earliest


def _window(cur):
    return timeutil.windows(db.val(cur, "select value from settings where key = 'send_window'"))


def schedule_message(cur, message_id: int) -> None:
    m = db.one(cur, "select * from messages where id = %s", message_id)
    e = db.one(cur, "select * from enrollments where id = %s", m["enrollment_id"])
    if e["state"] != "active" or m["status"] != "approved" or m["step_index"] != e["step_index"]:
        return  # an email approved ahead of its step waits until the sequence reaches it
    p = db.one(cur, "select timezone, country from people where id = %s", e["person_id"])
    planned = max(e["next_at"] or db.val(cur, "select app_now()"), db.val(cur, "select app_now()"))
    slot = timeutil.next_slot(planned, timezone=p["timezone"], country=p["country"], window=_window(cur),
                              jitter_key=f"m{message_id}")
    db.run(cur, "update messages set status = 'scheduled', scheduled_for = %s, planned_for = coalesce(planned_for, %s) "
                "where id = %s", slot, planned, message_id)


def stop_enrollment(cur, enrollment_id: int, reason: str, *, close_play: bool = True) -> None:
    """Stop one person's sequence. When they were the last one in the play, the play closes now (close_play),
    except on the reply path, where the reply's outcome decides what the play becomes."""
    db.run(cur, """update enrollments set state = 'stopped', stop_reason = %s, next_at = null
                   where id = %s and state in ('pending', 'active', 'paused')""", reason, enrollment_id)
    db.run(cur, """update messages set status = 'cancelled' where enrollment_id = %s
                   and status in ('draft', 'failed_gate', 'awaiting_approval', 'approved', 'scheduled')""", enrollment_id)
    # Their open call and LinkedIn tasks in this play close too: a stopped person is not called tomorrow.
    db.run(cur, """update tasks set status = 'skipped', done_at = app_now(), note = 'Closed: their sequence stopped'
                   where status = 'open' and kind in ('call', 'linkedin_connect', 'linkedin_message')
                   and (person_id, account_play_id) = (select person_id, account_play_id from enrollments where id = %s)""",
           enrollment_id)
    if close_play:
        from . import plays
        plays.close_if_empty(cur, db.val(cur, "select account_play_id from enrollments where id = %s", enrollment_id))


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
    # A first email nobody approved in time lapses too, so its play can close.
    for e in db.all(cur, """select e.id, e.next_at, p.country from enrollments e join people p on p.id = e.person_id
                            where e.state = 'pending' and e.next_at is not null order by e.id for update of e skip locked"""):
        if timeutil.business_days_between(e["next_at"], now, e["country"]) > lapse:
            db.run(cur, "update messages set status = 'cancelled' where enrollment_id = %s and status in "
                        "('awaiting_approval', 'failed_gate', 'draft')", e["id"])
            db.run(cur, "update enrollments set state = 'done', stop_reason = 'approval_lapsed', next_at = null "
                        "where id = %s", e["id"])
    rows = db.all(cur, """select e.*, ap.owner_id, pl.sequence, p.country, p.full_name, p.phone from enrollments e
                          join account_plays ap on ap.id = e.account_play_id join plays pl on pl.id = ap.play_id
                          join people p on p.id = e.person_id
                          where e.state = 'active' and e.next_at <= app_now() order by e.next_at, e.id for update of e skip locked""")
    for e in rows:
        if e["step_index"] >= len(e["sequence"]):
            db.run(cur, "update enrollments set state = 'done', next_at = null where id = %s", e["id"])
            continue
        step = e["sequence"][e["step_index"]]
        if step["by"] == "sdr":
            from . import sdr_steps
            made = sdr_steps.make_task(cur, e, step, now)
            advance(cur, e["id"], skipped=made is None)
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
    from .enrichment import ensure_company
    ensure_company(cur, account["id"])  # company data first, if not read this month
    account = db.one(cur, "select * from accounts where id = %s", ap["account_id"])
    _research_facts(cur, account)  # out of budget raises, and the job waits a day (jobs.run_ready)
    write_brief(cur, ap, account)
    people = build_committee(cur, ap, play, account)
    if not people:
        plays.set_state(cur, ap["id"], "stopped", reason="no_reachable_people")
        return
    if any(s["channel"] == "call" for s in play["sequence"]):
        for p in people:
            if not p["phone"]:
                from .adapters import PhoneHit
                from .enrichment import bought, source

                def find_phone(p=p):
                    with spend.paid_call(cur, "phone_finder", "find", vendor="phone_finder", qty=1, purpose="find phone",
                                         account_id=account["id"]) as info:
                        hit = adapters.get().phone.find(cur, p)
                        info["found"] = bool(hit)
                        info["charged_qty"] = 1 if hit else 0
                    return PhoneHit(number=hit) if isinstance(hit, str) else hit

                try:
                    hit = bought(cur, "phone_finder", str(p["id"]), find_phone)
                except (spend.OverBudget, adapters.VendorMissing):
                    hit = None
                if hit:
                    db.run(cur, """update people set phone = %s, phone_status = 'valid', phone_verified_at = app_now(),
                                   phone_type = %s, phone_dnc = %s where id = %s""",
                           hit["number"], hit.get("type") or "unknown", bool(hit.get("dnc")), p["id"])
                    source(cur, "person", p["id"], "phone", hit.get("type"), "phone_finder")
    enrollments = []
    for p in people:
        mailbox = pick_mailbox(cur, ap["owner_id"], ap["id"])
        eid = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, mailbox_id, next_at)
                             values (%s,%s,%s,'pending',%s,app_now()) returning id""", ap["id"], p["id"], p["persona_key"],
                     mailbox)
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
    first_email = next((i for i, st in enumerate(play["sequence"]) if st["channel"] == "email" and st["by"] == "desk"), None)
    if first_email is None:
        # No desk emails: nothing to approve. Everyone starts on the account calendar and each step is an SDR task.
        plays.set_state(cur, ap["id"], "approving")
        for eid in enrollments:
            activate(cur, eid)
        plays.set_state(cur, ap["id"], "active")
        return
    plays.set_state(cur, ap["id"], "approving")
    for eid in enrollments:
        draft_step(cur, eid, first_email)


from . import enrichment  # noqa: E402,F401  registers the enrichment_refresh job wherever outreach is loaded
