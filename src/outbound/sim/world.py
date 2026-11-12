"""The simulated world: invented companies, their people, and the hidden truth about each.

Every company has a hidden `need` between 0 and 1. Signals are drawn more often at companies with more need,
with a different strength of link for each signal type, so the desk's results can show which signals are worth
their weight. Replies come from the same hidden need. The desk never reads `sim_*` tables.

The world holds together the way a real list does: a company's name and product fit its industry, its billing tool
is the one its stack, its docs and any competitor signal name, it has one finance leader, and a new finance leader
the news announces exists, holds that title and started that day, while the one they replaced has left.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from .. import db
from ..db import J
from ..gate import country_name
from ..signals import normalize_name
from . import names as N

INDUSTRIES = [("Software", 34), ("Fintech", 14), ("Data infrastructure", 10), ("Developer tools", 10),
              ("Marketplaces", 8), ("Healthcare", 7), ("Retail", 6), ("Manufacturing", 5), ("Media", 4),
              ("Government", 1), ("Education", 1)]
COUNTRIES = [("US", 46), ("GB", 12), ("DE", 8), ("CA", 7), ("FR", 6), ("NL", 6), ("ES", 4), ("IE", 3), ("BR", 3),
             ("AU", 3), ("SG", 2)]
# Tools in the stack besides billing. The billing tool is chosen first and joins the stack when it is a product, so the
# stack, the company's own docs and any competitor signal name the same tool.
TECH = ["Snowflake", "NetSuite", "Salesforce", "HubSpot", "BigQuery", "Sage Intacct", "QuickBooks", "Databricks", "dbt",
        "Legacy on-prem ERP"]
BILLING = [("Stripe Billing", 30), ("an in-house billing system", 20), ("Chargewise", 18), ("Meterline", 14),
           ("spreadsheets and Stripe invoices", 18)]
BILLING_TECH = {"Stripe Billing": "Stripe", "Chargewise": "Chargewise", "Meterline": "Meterline",
                "spreadsheets and Stripe invoices": "Stripe"}
# A company's name and what it builds fit its industry: no "Clinics" selling software, no clinic software in retail.
POST_BY = {"Software": "Apps Cloud Labs Logic Software Stack Systems Works Platforms Security Networks".split(),
           "Fintech": "Pay Payments Capital Money Finance".split(),
           "Data infrastructure": "Data Analytics Metrics Cloud Stack".split(),
           "Developer tools": "Labs Dev Stack Logic Code".split(),
           "Marketplaces": "Market Exchange Platforms Networks".split(),
           "Healthcare": "Health Care Clinics Medical".split(),
           "Retail": "Commerce Goods Retail Brands".split(),
           "Manufacturing": "Robotics Industries Manufacturing Works".split(),
           "Media": "Media Studios Publishing".split(),
           "Government": "Civic Systems".split(),
           "Education": "Learning Education".split()}
PRODUCTS_BY = {
    "Software": ["workflow automation for finance teams", "customer data platform", "contract lifecycle software",
                 "procurement software", "HR and payroll for hourly teams", "security posture management",
                 "cloud cost management", "AI document processing", "identity verification API"],
    "Fintech": ["payments infrastructure for marketplaces", "expense management for agencies", "embedded lending API",
                "treasury management software"],
    "Data infrastructure": ["observability for data pipelines", "streaming data platform", "a managed data warehouse"],
    "Developer tools": ["developer analytics", "API platform for logistics data", "feature flags for engineering teams"],
    "Marketplaces": ["a B2B marketplace for industrial parts", "a marketplace for freelance designers",
                     "booking software for studios"],
    "Healthcare": ["workflow automation for clinics", "patient scheduling software", "remote patient monitoring"],
    "Retail": ["e-commerce search", "point-of-sale software for shops", "a subscription box for pet food"],
    "Manufacturing": ["IoT device management", "fleet telematics software", "industrial sensors"],
    "Media": ["a streaming video service", "digital publishing tools", "podcast advertising software"],
    "Government": ["permitting software for cities"],
    "Education": ["online courses for finance professionals"],
}

# One seat per role, sized to the company: one finance leader, a controller and a finance team under them, revenue
# operations and data people where a company that size has them, and the rest of the company.
LEADER = {"small": [("Head of Finance", "director"), ("VP Finance", "vp")],
          "mid": [("VP Finance", "vp"), ("Vice President of Finance", "vp"), ("CFO", "c_suite")],
          "large": [("CFO", "c_suite"), ("Chief Financial Officer", "c_suite")]}
TITLES = {
    "controller": [("Corporate Controller", "director"), ("Controller", "director"), ("Head of Accounting", "director"),
                   ("Director of Accounting", "director")],
    "revops": [("VP Revenue Operations", "vp"), ("Head of Revenue Operations", "director"),
               ("Director of Billing Operations", "director"), ("Revenue Operations Manager", "manager"),
               ("Head of Billing", "director")],
    "data": [("Head of Data", "director"), ("Director of Finance Systems", "director"),
             ("Data Engineering Manager", "manager"), ("Business Systems Lead", "manager")],
    "finance_team": [("Senior Accountant", "ic"), ("Revenue Accountant", "ic"), ("Financial Analyst", "ic"),
                     ("FP&A Manager", "manager"), ("Billing Specialist", "ic"), ("Accounts Receivable Specialist", "ic"),
                     ("Staff Accountant", "ic")],
    None: [("Head of Marketing", "director"), ("Product Manager", "manager"), ("Software Engineer", "ic"),
           ("Account Executive", "ic"), ("Customer Success Manager", "manager"), ("Head of People", "director"),
           ("Office Manager", "ic"), ("CTO", "c_suite"), ("VP Sales", "vp"), ("Design Lead", "manager"),
           ("Engineering Manager", "manager"), ("Head of Product", "director")],
}
# How likely a company is to get a new finance leader in the next four months: about one in twenty, more where the
# need is real (a new leader is one of the signals most linked to need).
NEW_LEADER = (0.02, 0.08)
NEW_LEADER_WITHIN_DAYS = 120
NEWS_REPORTS_IT = 0.85


def _pick(rng: random.Random, weighted: list[tuple[str, int]]) -> str:
    return rng.choices([w[0] for w in weighted], weights=[w[1] for w in weighted])[0]


def _band(employees: int, rng: random.Random) -> str:
    rev = employees * rng.uniform(0.12, 0.35)  # $M
    for cap, label in [(5, "Under $5M"), (20, "$5M-$20M"), (100, "$20M-$100M"), (500, "$100M-$500M")]:
        if rev < cap:
            return label
    return "$500M+"


def _size(employees: int) -> str:
    return "small" if employees < 150 else "mid" if employees < 800 else "large"


def bench(rng: random.Random, employees: int) -> list[tuple[str | None, str, str]]:
    """The people at one company as (persona, title, seniority): about eight at a typical company."""
    out: list[tuple[str | None, str, str]] = []
    if rng.random() >= 0.08:  # some companies are missing a finance leader on record
        out.append(("cfo", *rng.choice(LEADER[_size(employees)])))
    out.append(("controller", *rng.choice(TITLES["controller"] + ([("Chief Accounting Officer", "c_suite")]
                                                                   if employees >= 800 else []))))
    if employees >= 400 and rng.random() < 0.5:
        out.append(("controller", "Assistant Controller", "manager"))
    team = 1 + min(3, employees // 300) + rng.randint(0, 1)
    out += [(None, *t) for t in rng.sample(TITLES["finance_team"], team)]
    if employees >= 600 and rng.random() < 0.5:
        out.append((None, "Director of FP&A", "director"))
    if rng.random() < 0.75:
        out.append(("revops", *rng.choice(TITLES["revops"])))
    if employees >= 500 and rng.random() < 0.4:
        out.append(("revops", "Sales Operations Manager", "manager"))
    if rng.random() < 0.6:
        out.append(("data", *rng.choice(TITLES["data"])))
    out += [(None, *t) for t in rng.sample(TITLES[None], rng.randint(1, 4))]
    return out


def tenure(rng: random.Random, start: datetime, leader: bool) -> date:
    """When someone started in their seat. About one finance leader in twenty took the seat in the three months before
    the world starts (people data finds them); the rest have sat there for months or years."""
    if leader:
        days = rng.randint(10, 89) if rng.random() < 0.045 else rng.randint(120, 2400)
    else:
        days = rng.choice([rng.randint(20, 119), rng.randint(120, 1400), rng.randint(200, 2400)])
    return (start - timedelta(days=days)).date()


class _People:
    """Invents people for one world: unique names per company, unique emails, a photo for most."""

    def __init__(self, rng: random.Random, seed: int) -> None:
        self.rng = rng
        self.used_people: set = set()
        self.used_emails: set[str] = set()
        self.portraits = N.Portraits(random.Random(seed + 1))

    def make(self, aid: int, domain: str, country: str, title: str, seniority: str) -> dict:
        rng = self.rng
        for _ in range(20):
            first, last = rng.choice(N.FIRST), rng.choice(N.LAST)
            if (first, last, aid) not in self.used_people:
                self.used_people.add((first, last, aid))
                break
        fmt = rng.choice(["{f}.{l}", "{f}", "{fi}{l}", "{f}{l}", "{f}.{l}"])
        local = fmt.format(f=first.lower(), l=last.lower(), fi=first[0].lower()).replace(" ", "").replace("-", "")
        email = f"{local}@{domain}"
        n = 2
        while email in self.used_emails:
            email = f"{local}{n}@{domain}"
            n += 1
        self.used_emails.add(email)
        prefix = "Dr. " if rng.random() < 0.03 else ""
        return {
            "first": first, "last": last, "full": f"{prefix}{first} {last}", "title": title, "seniority": seniority,
            "email": email, "truth": rng.choices(["valid", "invalid", "catch_all"], weights=[84, 9, 7])[0],
            "tz": rng.choice(N.US_TZ) if country == "US" else N.COUNTRY[country][1],
            "linkedin": f"https://www.linkedin.com/in/{first.lower()}-{last.lower()}-{aid}{rng.randint(10, 99)}".replace(" ", ""),
            "phone": f"+1 {rng.randint(201, 989)} {rng.randint(200, 999)} {rng.randint(1000, 9999)}" if rng.random() < 0.7 else None,
            "resp": round(rng.uniform(0.3, 1.0), 3), "photo": self.portraits.url(first)}


def _hide(cur, aid: int, country: str, p: dict, *, champion: bool, started: date, left_at=None) -> int:
    return db.val(cur, """insert into sim_hidden_people (account_id, full_name, first_name, last_name, title, seniority,
                             linkedin_url, country, timezone, true_email, email_truth, responsiveness, phone_truth,
                             is_champion, photo_url, role_started, left_at)
                          values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                  aid, p["full"], p["first"], p["last"], p["title"], p["seniority"], p["linkedin"], country, p["tz"],
                  p["email"], p["truth"], p["resp"], p["phone"], champion, p["photo"], started, left_at)


def build(cur, *, seed: int = 7, n_accounts: int = 260, start: datetime) -> dict:
    rng = random.Random(seed)
    reps = [r["id"] for r in db.all(cur, "select id from users where role = 'sdr' order by id")]
    rep_tz = {r["id"]: r["timezone"] for r in db.all(cur, "select id, timezone from users where role = 'sdr'")}
    eu_reps = [r for r in reps if rep_tz[r].startswith("Europe")] or reps[:1]
    other_reps = [r for r in reps if not rep_tz[r].startswith("Europe")] or reps
    used_names: set[str] = set()
    make = _People(rng, seed)
    accounts: list[int] = []
    people = 0
    for i in range(n_accounts):
        industry = _pick(rng, INDUSTRIES)
        post = POST_BY[industry]
        for attempt in range(400):
            if attempt < 20:
                name = f"{rng.choice(N.PRE)} {rng.choice(post)}"
            else:  # past the simple pairs, compound names give thousands more per industry
                name = f"{rng.choice(N.PRE)}{rng.choice(N.SUF)} {rng.choice(post)}"
            if name not in used_names:
                used_names.add(name)
                break
        else:
            raise RuntimeError("The name space is exhausted; add words to sim/names.py")
        slug = name.lower().replace(" ", "")
        domain = slug + rng.choice([".com", ".io", ".co", ".ai", ".com", ".io"])
        country = _pick(rng, COUNTRIES)
        region = N.COUNTRY[country][0]
        employees = int(min(9000, max(12, rng.lognormvariate(5.4, 0.95))))
        billing = _pick(rng, BILLING)
        tech = set(rng.sample(TECH, rng.randint(2, 4)))
        if billing in BILLING_TECH:
            tech.add(BILLING_TECH[billing])
        tech = sorted(tech)
        product = rng.choice(PRODUCTS_BY[industry])
        lifecycle = "prospect"
        roll = rng.random()
        if roll < 0.07:
            lifecycle = "customer"
        elif roll < 0.10:
            lifecycle = "open_opp"
        elif roll < 0.12:
            lifecycle = "churned"
        elif roll < 0.135:
            lifecycle = "competitor"
        # Owners by timezone family: European accounts to the European reps, the rest round robin.
        owner = eu_reps[i % len(eu_reps)] if region == "Europe" else other_reps[i % len(other_reps)]
        if rng.random() < 0.12:
            owner = None  # unowned accounts get round-robin at proposal time
        desc = f"{name} builds {product}."
        aid = db.val(cur, """
            insert into accounts (name_key, name, primary_domain, industry, employees, revenue_band, hq_country, region, tech,
                                  description, lifecycle, owner_id, crm_id, source, created_at)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'crm',%s) returning id""",
            normalize_name(name), name, domain, industry, employees, _band(employees, rng), country, region, tech, desc,
            lifecycle, owner, f"CRM-A{1000 + i}", start - timedelta(days=rng.randint(60, 900)))
        accounts.append(aid)
        db.run(cur, "insert into account_domains (domain, account_id) values (%s, %s)", domain, aid)
        if rng.random() < 0.15:
            alias = slug + "hq.com"
            db.run(cur, "insert into account_domains (domain, account_id) values (%s, %s) on conflict do nothing", alias, aid)
        # Hidden need: higher for software companies of the right size, plus noise.
        need = rng.betavariate(1.6, 3.2)
        if industry in ("Software", "Fintech", "Data infrastructure", "Developer tools", "Marketplaces"):
            need = min(1.0, need + 0.12)
        if 80 <= employees <= 2500:
            need = min(1.0, need + 0.08)
        pricing = rng.choice(["seat-based", "usage-based", "a mix of seats and usage", "moving to usage-based"])
        finance_team = max(2, employees // rng.randint(45, 90))
        where = country_name(country)
        pages = {
            "about": f"{name} builds {product}. Headquartered in {where}, about {employees} people.",
            "pricing": f"{name} prices its product as {pricing}.",
            "billing": f"Invoices are produced with {billing}.",
            "finance": f"The finance team has about {finance_team} people.",
            "careers": "Open roles include " + ", ".join(rng.sample(
                ["Billing Specialist", "Revenue Accountant", "Senior Software Engineer", "Account Executive",
                 "Data Analyst", "Product Designer", "Customer Success Manager", "Finance Systems Analyst"], 3)) + ".",
        }
        db.run(cur, "insert into sim_accounts (account_id, need, pages, billing) values (%s, %s, %s, %s)",
               aid, round(need, 3), J(pages), billing)
        # People. A planned change of finance leader: the leader on record leaves on that day, and the new one,
        # whom the CRM does not know yet, starts in the announced seat.
        change_at = None
        if rng.random() < NEW_LEADER[0] + NEW_LEADER[1] * need:
            change_at = start + timedelta(days=rng.randint(0, NEW_LEADER_WITHIN_DAYS - 1), hours=rng.randint(8, 17))
        for persona, title, seniority in bench(rng, employees):
            p = make.make(aid, domain, country, title, seniority)
            leader = persona == "cfo"
            started = tenure(rng, start, leader)
            left_at = change_at if leader else None
            known = rng.random() < 0.55  # already in the CRM, or only findable through people search
            champion = lifecycle == "customer" and persona in ("controller", "cfo", "revops") and rng.random() < 0.6
            people += 1
            if known:
                pid = db.val(cur, """
                    insert into people (account_id, full_name, first_name, last_name, title, seniority, email,
                                        email_status, linkedin_url, country, timezone, source, crm_id, created_at,
                                        is_champion, photo_url)
                    values (%s,%s,%s,%s,%s,%s,%s,'unknown',%s,%s,%s,'crm',%s,%s,%s,%s) returning id""",
                    aid, p["full"], p["first"], p["last"], title, seniority, p["email"], p["linkedin"], country, p["tz"],
                    f"CRM-C{aid}-{len(make.used_people)}", start - timedelta(days=rng.randint(10, 700)), champion, p["photo"])
                db.run(cur, """insert into sim_people (person_id, true_email, email_truth, responsiveness, phone_truth,
                                                       role_started, left_at) values (%s,%s,%s,%s,%s,%s,%s)""",
                       pid, p["email"], p["truth"], p["resp"], p["phone"], started, left_at)
            else:
                _hide(cur, aid, country, p, champion=champion, started=started, left_at=left_at)
        if change_at is not None:
            title, seniority = rng.choice(LEADER[_size(employees)])
            p = make.make(aid, domain, country, title, seniority)
            people += 1
            hid = _hide(cur, aid, country, p, champion=False, started=change_at.date())
            db.run(cur, "insert into sim_seat_changes (account_id, at, hidden_person_id, announced) values (%s,%s,%s,%s)",
                   aid, change_at, hid, rng.random() < NEWS_REPORTS_IT)
        # History lives in the CRM; the desk learns it on its first read, like a real install.
        if lifecycle in ("customer", "churned"):
            created = start - timedelta(days=rng.randint(200, 700))
            closed = start - timedelta(days=rng.randint(100, 190))
            db.run(cur, """insert into sim_crm_deals (crm_id, account_id, name, amount_cents, stage, created_at, updated_at,
                                                     closed_at, won, close_on, will_win)
                           values (%s,%s,%s,%s,'Closed Won',%s,%s,%s,true,%s,true)""",
                   f"CRM-O{aid}", aid, f"{name} new business", rng.randint(24, 140) * 100000, created, closed, closed, closed)
        elif lifecycle == "open_opp":
            created = start - timedelta(days=rng.randint(5, 60))
            db.run(cur, """insert into sim_crm_deals (crm_id, account_id, name, amount_cents, stage, created_at, updated_at,
                                                     close_on, will_win)
                           values (%s,%s,%s,%s,'Evaluation',%s,%s,%s,%s)""",
                   f"CRM-O{aid}", aid, f"{name} new business", rng.randint(24, 140) * 100000, created, created,
                   start + timedelta(days=rng.randint(10, 50)), rng.random() < 0.4)
        elif lifecycle == "prospect" and rng.random() < 0.06:
            created = start - timedelta(days=rng.randint(200, 420))
            closed = created + timedelta(days=rng.randint(30, 80))
            reason = rng.choice(["timing", "timing", "budget", "competitor", "no decision"])
            db.run(cur, """insert into sim_crm_deals (crm_id, account_id, name, amount_cents, stage, created_at, updated_at,
                                                     closed_at, won, loss_reason, close_on, will_win)
                           values (%s,%s,%s,%s,'Closed Lost',%s,%s,%s,false,%s,%s,false)""",
                   f"CRM-O{aid}", aid, f"{name} new business", rng.randint(24, 140) * 100000, created, closed, closed,
                   reason, closed)
    return {"accounts": len(accounts), "people": people}
