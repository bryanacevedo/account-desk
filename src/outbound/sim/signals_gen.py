"""Simulated signal sources. Each type has a base daily rate and a link to the company's hidden need, so some
signals predict meetings well and some are mostly noise, as in real life.

Signals agree with the world they come from: a new finance leader is announced on the day they start, naming the person
who took the seat; only a company on a billing tool we replace reviews it or drops it, and it names that tool; and the
people who change jobs are champions and people we have been in touch with, the ones a job-change feed is set to watch.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .. import db

# type: (source, base rate per account-day, extra rate per unit of need, person-level). A new finance leader is not
# drawn here: it comes from the world's planned seat changes (sim_seat_changes), announced on the day.
RATES = {
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
# Every rate above is multiplied by this. It sets how much the world says per account and day, so a list of 3,000
# accounts gives six SDRs a week's work they can do, not a pile (README "At production size").
SCALE = 0.5
# A review or a removal comes only from a company on that tool, so their rate there is higher than the all-account
# rate above, which keeps their share of the world's signals close to what it was before they had to agree.
COMPETITOR_BOOST = {"competitor_review": 2.5, "tech_removed": 2.0}
# Who reviews a tool: users of Chargewise, who in first calls say they are also looking at Meterline.
REVIEWED = ("Chargewise",)
REPLACED = ("Chargewise", "Meterline")
# Job changes a day, and the share of them that are past champions. The rest are people we have been in touch with.
MOVES_A_DAY = 0.35
CHAMPION_SHARE = 0.4

OUTSIDE_A = "Alder Basalt Cobalt Delta Ember Fjord Garnet Halcyon Iris Jasper Kelp Lattice Morrow Nimbus Onyx Prism".split()
OUTSIDE_B = "Freight Foods Studio Robotics Media Clinics Logistics Retail Energy Travel Insurance Labs".split()
ROLES = ["Revenue Accountant", "Billing Specialist", "Finance Systems Analyst", "Billing Operations Manager",
         "Senior Revenue Accountant", "Accounts Receivable Lead"]
TOPICS = ["usage-based billing", "revenue recognition automation", "ASC 606 for usage pricing", "metered billing"]
PRICING = ["moved its API product to pay-as-you-go pricing", "announced credit-based pricing for its platform",
           "launched usage tiers alongside seat plans"]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def article(word: str) -> str:
    """'a' or 'an' by sound: an Accounts Receivable Lead, an $18M round, a $25M round."""
    w = word.lstrip("$")
    if w[:1].isdigit():
        return "an" if w.startswith(("8", "11", "18")) else "a"
    return "an" if w[:1].lower() in "aeio" else "a"


def day_month(at: datetime) -> str:
    return f"{at.day} {at:%B}"


def evidence(rng: random.Random, kind: str, acct: dict, at: datetime, person: dict | None) -> dict:
    name, slug, dom = acct["name"], _slug(acct["name"]), acct["primary_domain"]
    n = rng.randint(1000, 9999)
    if kind == "new_exec":
        who, title = person["full_name"], person["title"]
        return {"summary": f"Appointed {who} as {title} on {day_month(at)}.",
                "url": f"https://news.example.net/{slug}-names-{_slug(title)}-{n}",
                "quote": f"{name} today announced the appointment of {who} as {title}."}
    if kind == "hiring_function":
        role = rng.choice(ROLES)
        return {"summary": f"Posted a job for {article(role)} {role}.", "url": f"https://jobs.example.net/{slug}/{_slug(role)}-{n}",
                "quote": f"You will own monthly invoicing and revenue reconciliation as the {role}."}
    if kind == "funding":
        amt = rng.choice([12, 18, 25, 30, 40, 55, 70])
        rnd = rng.choice(["Series A", "Series B", "Series C"])
        return {"summary": f"Raised {article(str(amt))} ${amt}M {rnd} on {day_month(at)}.", "url": f"https://news.example.net/{slug}-raises-{amt}m-{n}",
                "quote": f"{name} raised ${amt} million in {rnd} funding."}
    if kind == "pricing_visit":
        v = rng.randint(2, 6)
        return {"summary": f"{v} visits to the pricing page from the company's network in seven days.",
                "url": f"https://lumenledger.example/pricing?ref=visits-{n}", "quote": f"{v} sessions on /pricing"}
    if kind == "site_visit":
        v = rng.randint(2, 9)
        return {"summary": f"{v} visits to product pages in seven days.", "url": f"https://lumenledger.example/product?ref=visits-{n}",
                "quote": f"{v} sessions on product pages"}
    if kind == "intent_topic":
        t = rng.choice(TOPICS)
        return {"summary": f"Research on {t} above their usual level.", "url": f"https://intent.example.net/{dom}/{n}",
                "quote": f"Topic surge: {t}"}
    if kind == "competitor_review":
        c = acct["billing"]
        return {"summary": f"Left a review of {c} that mentions invoice errors.", "url": f"https://reviews.example.net/{_slug(c)}/review-{n}",
                "quote": f"{c} works until usage pricing, then the invoices need fixing by hand."}
    if kind == "tech_added":
        t = rng.choice(["Snowflake", "NetSuite", "Databricks"])
        return {"summary": f"Started using {t}.", "url": f"https://stack.example.net/{dom}/{_slug(t)}", "quote": f"Detected: {t}"}
    if kind == "tech_removed":
        c = acct["billing"]
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


def _eligible(kind: str, acct: dict) -> bool:
    if kind == "competitor_review":
        return acct["billing"] in REVIEWED and not acct["billing_dropped"]
    if kind == "tech_removed":
        return acct["billing"] in REPLACED and not acct["billing_dropped"]
    return True


def day_signals(cur, rng: random.Random, day_start: datetime) -> dict[str, list[dict]]:
    """Raw signals per source for one simulated day."""
    out: dict[str, list[dict]] = {}
    accts = db.all(cur, """select a.id, a.name, a.primary_domain, sa.need::float as need, sa.billing, sa.billing_dropped
                           from accounts a join sim_accounts sa on sa.account_id = a.id
                           where a.lifecycle <> 'competitor' order by a.id""")
    for acct in accts:
        for kind, (source, base, link, person_level) in RATES.items():
            if not _eligible(kind, acct):
                continue
            rate = 1.5 * SCALE * COMPETITOR_BOOST.get(kind, 1.0) * (base + link * acct["need"])
            if rng.random() >= rate:
                continue
            at = day_start + timedelta(minutes=rng.randint(0, 24 * 60 - 1))
            person = None
            if person_level:
                pool = db.all(cur, "select full_name, email, linkedin_url from people where account_id = %s order by id",
                              acct["id"])
                person = rng.choice(pool) if pool else None
            raw = {"type": kind, "external_id": f"{source}-{kind}-{acct['id']}-{rng.randint(10**8, 10**9)}",
                   "observed_at": at, "domain": rng.choice([acct["primary_domain"], "www." + acct["primary_domain"]]),
                   "strength": round(min(1.0, rng.uniform(0.4, 0.9) + 0.15 * acct["need"]), 2),
                   "evidence": evidence(rng, kind, acct, at, person)}
            if person_level and person:
                raw["person"] = {"linkedin_url": person["linkedin_url"], "email": person["email"]}
            if rng.random() < 0.04:  # some sources only know the company name, sometimes with a suffix
                raw.pop("domain")
                raw["company"] = acct["name"] + rng.choice(["", " Inc.", " Ltd"])
            if kind == "tech_removed":  # a tool is dropped once; nobody reviews a tool they no longer use
                db.run(cur, "update sim_accounts set billing_dropped = true where account_id = %s", acct["id"])
                acct["billing_dropped"] = True
            out.setdefault(source, []).append(raw)
    # A new finance leader: announced by the news on the day they start, naming them and the seat.
    for c in db.all(cur, """select c.at, a.id, a.name, a.primary_domain, h.full_name, h.title, h.linkedin_url
                            from sim_seat_changes c join accounts a on a.id = c.account_id
                            join sim_hidden_people h on h.id = c.hidden_person_id
                            where c.announced and c.at >= %s and c.at < %s order by c.id""",
                    day_start, day_start + timedelta(days=1)):
        who = {"full_name": c["full_name"], "title": c["title"], "linkedin_url": c["linkedin_url"]}
        out.setdefault("news_feed", []).append({
            "type": "new_exec", "external_id": f"news_feed-new_exec-{c['id']}-{c['at']:%Y%m%d}", "observed_at": c["at"],
            "domain": c["primary_domain"], "strength": round(rng.uniform(0.75, 0.95), 2),
            "evidence": evidence(rng, "new_exec", c, c["at"], who), "person": who})
    # Noise every real feed has: companies outside the account list, from several sources.
    for _ in range(rng.randint(0, 3)):
        name = f"{rng.choice(OUTSIDE_A)} {rng.choice(OUTSIDE_B)}"
        dom = name.lower().replace(" ", "") + rng.choice([".com", ".io", ".co"])
        kind, source = rng.choice([("intent_topic", "intent_feed"), ("site_visit", "web_visits"),
                                   ("hiring_function", "jobs_feed"), ("funding", "funding_feed")])
        at = day_start + timedelta(hours=rng.randint(0, 23))
        fake = {"name": name, "primary_domain": dom}
        out.setdefault(source, []).append({
            "type": kind, "external_id": f"{source}-outside-{rng.randint(10**8, 10**9)}", "observed_at": at,
            "domain": dom, "strength": 0.5, "evidence": evidence(rng, kind, fake, at, None)})
    # Job changes: a job-change feed watches the people it is given, the past champions and the people we have been in
    # touch with, so those are the ones it reports moving. Most are reported by two sources a few days apart.
    if rng.random() < MOVES_A_DAY:
        # Picks use the sim's seeded generator, never SQL random(), so the same seeds replay the same world.
        if rng.random() < CHAMPION_SHARE:
            movers = db.all(cur, """select p.id, p.full_name, p.linkedin_url, p.email, p.is_champion, p.account_id
                                   from people p where p.status = 'active' and p.is_champion and p.linkedin_url is not null
                                   order by p.id""")
        else:
            movers = db.all(cur, """select p.id, p.full_name, p.linkedin_url, p.email, p.is_champion, p.account_id
                                   from people p where p.status = 'active' and p.linkedin_url is not null and exists (
                                     select 1 from touches t where t.person_id = p.id and t.direction = 'out')
                                   order by p.id""")
        mover = rng.choice(movers) if movers else None
        targets = db.all(cur, """select a.id, a.primary_domain, a.name from accounts a join sim_accounts sa on sa.account_id = a.id
                                where a.lifecycle = 'prospect' and a.id <> %s order by a.id""",
                         mover["account_id"] if mover else 0)
        target = rng.choice(targets) if targets else None
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
