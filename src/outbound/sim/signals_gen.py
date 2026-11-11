"""Simulated signal sources. Each type has a base daily rate and a link to the company's hidden need, so some
signals predict meetings well and some are mostly noise, as in real life."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .. import db

# type: (source, base rate per account-day, extra rate per unit of need, person-level)
RATES = {
    "new_exec": ("news_feed", 0.0006, 0.0035, False),
    "hiring_function": ("jobs_feed", 0.0018, 0.0090, False),
    "funding": ("funding_feed", 0.0014, 0.0016, False),
    "pricing_visit": ("web_visits", 0.0008, 0.0110, False),
    "site_visit": ("web_visits", 0.0060, 0.0080, False),
    "intent_topic": ("intent_feed", 0.0090, 0.0040, False),
    "competitor_review": ("reviews_feed", 0.0004, 0.0055, False),
    "tech_added": ("techstack_feed", 0.0018, 0.0026, False),
    "tech_removed": ("techstack_feed", 0.0003, 0.0028, False),
    "pricing_change": ("news_feed", 0.0004, 0.0050, False),
    "social_engaged": ("social_feed", 0.0035, 0.0035, True),
    "product_signup": ("product", 0.0003, 0.0040, False),
    "event_attended": ("events", 0.0008, 0.0018, True),
    "news_negative": ("news_feed", 0.0009, 0.0, False),
}

ROLES = ["Revenue Accountant", "Billing Specialist", "Finance Systems Analyst", "Billing Operations Manager",
         "Senior Revenue Accountant", "Accounts Receivable Lead"]
COMPETITORS = ["Chargewise", "Meterline"]
EXEC_TITLES = ["Chief Financial Officer", "VP Finance", "Corporate Controller"]
TOPICS = ["usage-based billing", "revenue recognition automation", "ASC 606 for usage pricing", "metered billing"]
PRICING = ["moved its API product to pay-as-you-go pricing", "announced credit-based pricing for its platform",
           "launched usage tiers alongside seat plans"]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def evidence(rng: random.Random, kind: str, acct: dict, at: datetime, person: dict | None) -> dict:
    name, slug, dom = acct["name"], _slug(acct["name"]), acct["primary_domain"]
    n = rng.randint(1000, 9999)
    if kind == "new_exec":
        title = rng.choice(EXEC_TITLES)
        return {"summary": f"Appointed a new {title} on {at:%d %B}.", "url": f"https://news.example.net/{slug}-names-{_slug(title)}-{n}",
                "quote": f"{name} today announced the appointment of a new {title}."}
    if kind == "hiring_function":
        role = rng.choice(ROLES)
        return {"summary": f"Posted a job for a {role}.", "url": f"https://jobs.example.net/{slug}/{_slug(role)}-{n}",
                "quote": f"You will own monthly invoicing and revenue reconciliation as the {role}."}
    if kind == "funding":
        amt = rng.choice([12, 18, 25, 30, 40, 55, 70])
        rnd = rng.choice(["Series A", "Series B", "Series C"])
        return {"summary": f"Raised a ${amt}M {rnd} on {at:%d %B}.", "url": f"https://news.example.net/{slug}-raises-{amt}m-{n}",
                "quote": f"{name} raised ${amt} million in {rnd} funding."}
    if kind == "pricing_visit":
        v = rng.randint(2, 6)
        return {"summary": f"{v} visits to the pricing page from the company's network this week.",
                "url": f"https://lumenledger.example/pricing?ref=visits-{n}", "quote": f"{v} sessions on /pricing"}
    if kind == "site_visit":
        v = rng.randint(2, 9)
        return {"summary": f"{v} visits to product pages this week.", "url": f"https://lumenledger.example/product?ref=visits-{n}",
                "quote": f"{v} sessions on product pages"}
    if kind == "intent_topic":
        t = rng.choice(TOPICS)
        return {"summary": f"Research on {t} above their usual level.", "url": f"https://intent.example.net/{dom}/{n}",
                "quote": f"Topic surge: {t}"}
    if kind == "competitor_review":
        c = rng.choice(COMPETITORS)
        return {"summary": f"Left a review of {c} that mentions invoice errors.", "url": f"https://reviews.example.net/{_slug(c)}/review-{n}",
                "quote": f"{c} works until usage pricing, then the invoices need fixing by hand."}
    if kind == "tech_added":
        t = rng.choice(["Snowflake", "NetSuite", "Databricks"])
        return {"summary": f"Started using {t}.", "url": f"https://stack.example.net/{dom}/{_slug(t)}", "quote": f"Detected: {t}"}
    if kind == "tech_removed":
        c = rng.choice(COMPETITORS)
        return {"summary": f"Stopped using {c}.", "url": f"https://stack.example.net/{dom}/{_slug(c)}-removed",
                "quote": f"No longer detected: {c}"}
    if kind == "pricing_change":
        p = rng.choice(PRICING)
        return {"summary": f"{name} {p}.", "url": f"https://{dom}/blog/new-pricing-{n}", "quote": f"Today {name} {p}."}
    if kind == "social_engaged":
        who = person["full_name"] if person else "Someone at the company"
        return {"summary": f"{who} commented on a post about usage-based billing.",
                "url": f"https://social.example.net/post/{n}", "quote": "Our month-end close is still half spreadsheets."}
    if kind == "product_signup":
        return {"summary": "Created a free workspace.", "url": f"https://app.lumenledger.example/admin/workspaces/{n}",
                "quote": f"New workspace for {dom}"}
    if kind == "event_attended":
        who = person["full_name"] if person else "Someone at the company"
        return {"summary": f"{who} attended the webinar on closing the books with usage pricing.",
                "url": f"https://lumenledger.example/events/webinar-{n}", "quote": "Attended 46 minutes"}
    if kind == "news_negative":
        return {"summary": "Announced a reduction in staff.", "url": f"https://news.example.net/{slug}-layoffs-{n}",
                "quote": f"{name} is reducing its workforce."}
    raise ValueError(kind)


def day_signals(cur, rng: random.Random, day_start: datetime) -> dict[str, list[dict]]:
    """Raw signals per source for one simulated day."""
    out: dict[str, list[dict]] = {}
    accts = db.all(cur, """select a.id, a.name, a.primary_domain, sa.need::float as need from accounts a
                           join sim_accounts sa on sa.account_id = a.id where a.lifecycle <> 'competitor'""")
    for acct in accts:
        for kind, (source, base, link, person_level) in RATES.items():
            if rng.random() >= base + link * acct["need"]:
                continue
            at = day_start + timedelta(minutes=rng.randint(0, 24 * 60 - 1))
            person = None
            if person_level:
                person = db.one(cur, "select full_name, email, linkedin_url from people where account_id = %s "
                                     "order by random() limit 1", acct["id"])
            raw = {"type": kind, "external_id": f"{source}-{kind}-{acct['id']}-{rng.randint(10**8, 10**9)}",
                   "observed_at": at, "domain": rng.choice([acct["primary_domain"], "www." + acct["primary_domain"]]),
                   "strength": round(min(1.0, rng.uniform(0.4, 0.9) + 0.15 * acct["need"]), 2),
                   "evidence": evidence(rng, kind, acct, at, person)}
            if person_level and person:
                raw["person"] = {"linkedin_url": person["linkedin_url"], "email": person["email"]}
            if rng.random() < 0.04:  # some sources only know the company name, sometimes with a suffix
                raw.pop("domain")
                raw["company"] = acct["name"] + rng.choice(["", " Inc.", " Ltd"])
            out.setdefault(source, []).append(raw)
    # Noise every real feed has: companies we do not know.
    for _ in range(rng.randint(0, 3)):
        out.setdefault("intent_feed", []).append({
            "type": "intent_topic", "external_id": f"intent-unknown-{rng.randint(10**8, 10**9)}",
            "observed_at": day_start + timedelta(hours=rng.randint(0, 23)),
            "domain": f"unknown{rng.randint(100, 999)}.com", "strength": 0.5,
            "evidence": {"summary": "Research on usage-based billing.", "url": "https://intent.example.net/unknown"}})
    # Job changes: a known person moves. Most are reported by two sources a few days apart.
    if rng.random() < 0.35:
        mover = db.one(cur, """select p.id, p.full_name, p.linkedin_url, p.email, p.is_champion, p.account_id
                               from people p join accounts a on a.id = p.account_id
                               where p.status = 'active' and p.title ~* '(cfo|finance|controller|accounting|revenue|billing)'
                               order by random() limit 1""")
        target = db.one(cur, """select a.id, a.primary_domain, a.name from accounts a join sim_accounts sa on sa.account_id = a.id
                                where a.lifecycle = 'prospect' and a.id <> %s order by random() limit 1""",
                        mover["account_id"] if mover else 0)
        if mover and target:
            kind = "champion_moved" if mover["is_champion"] else "job_change"
            ev = {"summary": f"{mover['full_name']} joined {target['name']}.", "url": f"https://social.example.net/in/{mover['id']}",
                  "quote": f"Started a new position at {target['name']}"}
            base = {"type": kind, "observed_at": day_start + timedelta(hours=rng.randint(8, 18)),
                    "domain": target["primary_domain"], "strength": 0.9, "evidence": ev,
                    "person": {"linkedin_url": mover["linkedin_url"], "email": mover["email"]}}
            out.setdefault("people_moves", []).append({**base, "external_id": f"moves-{mover['id']}-{target['id']}"})
            if rng.random() < 0.8:
                db.run(cur, "insert into sim_events (at, kind, payload) values (%s, 'second_move_source', %s)",
                       day_start + timedelta(days=rng.randint(1, 5)),
                       db.J({**{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in base.items()},
                             "external_id": f"social-move-{mover['id']}-{target['id']}"}))
    return out
