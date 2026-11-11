"""The simulated world: invented companies, their people, and the hidden truth about each.

Every company has a hidden `need` between 0 and 1. Signals are drawn more often at companies with more need,
with a different strength of link for each signal type, so the desk's results can show which signals are worth
their weight. Replies come from the same hidden need. The desk never reads `sim_*` tables.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .. import db
from ..db import J
from ..signals import normalize_name
from . import names as N

INDUSTRIES = [("Software", 34), ("Fintech", 14), ("Data infrastructure", 10), ("Developer tools", 10),
              ("Marketplaces", 8), ("Healthcare", 7), ("Retail", 6), ("Manufacturing", 5), ("Media", 4),
              ("Government", 1), ("Education", 1)]
COUNTRIES = [("US", 46), ("GB", 12), ("DE", 8), ("CA", 7), ("FR", 6), ("NL", 6), ("ES", 4), ("IE", 3), ("BR", 3),
             ("AU", 3), ("SG", 2)]
TECH = ["Snowflake", "NetSuite", "Salesforce", "Stripe", "HubSpot", "BigQuery", "Sage Intacct", "QuickBooks",
        "Databricks", "dbt", "Zuora", "Chargebee", "Legacy on-prem ERP"]
BILLING = ["Stripe Billing", "an in-house billing system", "Chargewise", "Meterline", "spreadsheets and Stripe invoices"]
PRODUCTS = ["API platform for logistics data", "workflow automation for clinics", "observability for data pipelines",
            "payments infrastructure for marketplaces", "customer data platform", "AI document processing",
            "fleet telematics software", "expense management for agencies", "identity verification API",
            "e-commerce search", "cloud cost management", "contract lifecycle software", "IoT device management",
            "developer analytics", "streaming data platform", "procurement software", "security posture management",
            "HR and payroll for hourly teams", "booking software for studios", "embedded lending API"]

TITLES = {
    "cfo": [("CFO", "c_suite"), ("Chief Financial Officer", "c_suite"), ("VP Finance", "vp"),
            ("Vice President of Finance", "vp"), ("Head of Finance", "director")],
    "controller": [("Corporate Controller", "director"), ("Controller", "director"), ("Head of Accounting", "director"),
                   ("Director of Accounting", "director"), ("Chief Accounting Officer", "c_suite")],
    "revops": [("VP Revenue Operations", "vp"), ("Head of Revenue Operations", "director"),
               ("Director of Billing Operations", "director"), ("Revenue Operations Manager", "manager"),
               ("Head of Billing", "director")],
    "data": [("Head of Data", "director"), ("Director of Finance Systems", "director"),
             ("Data Engineering Manager", "manager"), ("Business Systems Lead", "manager")],
    None: [("Head of Marketing", "director"), ("Product Manager", "manager"), ("Software Engineer", "ic"),
           ("Account Executive", "ic"), ("Customer Success Manager", "manager"), ("Head of People", "director"),
           ("Senior Accountant", "ic"), ("Financial Analyst", "ic"), ("Office Manager", "ic"), ("CTO", "c_suite"),
           ("VP Sales", "vp"), ("Design Lead", "manager")],
}


def _pick(rng: random.Random, weighted: list[tuple[str, int]]) -> str:
    return rng.choices([w[0] for w in weighted], weights=[w[1] for w in weighted])[0]


def _band(employees: int, rng: random.Random) -> str:
    rev = employees * rng.uniform(0.12, 0.35)  # $M
    for cap, label in [(5, "Under $5M"), (20, "$5M-$20M"), (100, "$20M-$100M"), (500, "$100M-$500M")]:
        if rev < cap:
            return label
    return "$500M+"


def build(cur, *, seed: int = 7, n_accounts: int = 260, start: datetime) -> dict:
    rng = random.Random(seed)
    reps = [r["id"] for r in db.all(cur, "select id from users where role = 'rep' order by id")]
    rep_tz = {r["id"]: r["timezone"] for r in db.all(cur, "select id, timezone from users where role = 'rep'")}
    used_names: set[str] = set()
    used_people: set = set()
    used_emails: set[str] = set()
    accounts: list[int] = []
    for i in range(n_accounts):
        while True:
            name = f"{rng.choice(N.PRE)} {rng.choice(N.POST)}"
            if name not in used_names:
                used_names.add(name)
                break
        slug = name.lower().replace(" ", "")
        domain = slug + rng.choice([".com", ".io", ".co", ".ai", ".com", ".io"])
        industry = _pick(rng, INDUSTRIES)
        country = _pick(rng, COUNTRIES)
        region = N.COUNTRY[country][0]
        employees = int(min(9000, max(12, rng.lognormvariate(5.4, 0.95))))
        tech = sorted(set(rng.sample(TECH, rng.randint(2, 5))))
        product = rng.choice(PRODUCTS)
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
        # Owners by timezone family: Europe to the London rep, the rest round robin.
        if region == "Europe":
            owner = next((r for r in reps if rep_tz[r].startswith("Europe")), reps[0])
        else:
            us_reps = [r for r in reps if not rep_tz[r].startswith("Europe")]
            owner = us_reps[i % len(us_reps)]
        if rng.random() < 0.12:
            owner = None  # unowned accounts get round-robin at proposal time
        desc = f"{name} builds {product}."
        acc = db.one(cur, """
            insert into accounts (name_key, name, primary_domain, industry, employees, revenue_band, hq_country, region, tech,
                                  description, lifecycle, owner_id, crm_id, source, created_at)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'crm',%s) returning id""",
            normalize_name(name), name, domain, industry, employees, _band(employees, rng), country, region, tech, desc, lifecycle, owner,
            f"CRM-A{1000 + i}", start - timedelta(days=rng.randint(60, 900)))
        aid = acc["id"]
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
        billing = rng.choice(BILLING)
        pricing = rng.choice(["seat-based", "usage-based", "a mix of seats and usage", "moving to usage-based"])
        finance_team = max(2, employees // rng.randint(45, 90))
        pages = {
            "about": f"{name} builds {product}. Headquartered in {country}, about {employees} people.",
            "pricing": f"{name} prices its product as {pricing}.",
            "billing": f"Invoices are produced with {billing}.",
            "finance": f"The finance team has about {finance_team} people.",
            "careers": "Open roles include " + ", ".join(rng.sample(
                ["Billing Specialist", "Revenue Accountant", "Senior Software Engineer", "Account Executive",
                 "Data Analyst", "Product Designer", "Customer Success Manager", "Finance Systems Analyst"], 3)) + ".",
        }
        db.run(cur, "insert into sim_accounts (account_id, need, pages) values (%s, %s, %s)", aid, round(need, 3), J(pages))
        # People
        roles: list[str | None] = ["cfo", "controller"]
        if rng.random() < 0.75:
            roles.append("revops")
        if rng.random() < 0.6:
            roles.append("data")
        if rng.random() < 0.25:
            roles.append(rng.choice(["controller", "revops", "cfo"]))
        roles += [None] * rng.randint(1, 4)
        if rng.random() < 0.12:  # some companies are missing a finance leader on record
            roles.remove("cfo")
        for persona in roles:
            for _ in range(20):
                first, last = rng.choice(N.FIRST), rng.choice(N.LAST)
                if (first, last, aid) not in used_people:
                    used_people.add((first, last, aid))
                    break
            title, seniority = rng.choice(TITLES[persona])
            fmt = rng.choice(["{f}.{l}", "{f}", "{fi}{l}", "{f}{l}", "{f}.{l}"])
            local = fmt.format(f=first.lower(), l=last.lower(), fi=first[0].lower()).replace(" ", "").replace("-", "")
            email = f"{local}@{domain}"
            n = 2
            while email in used_emails:
                email = f"{local}{n}@{domain}"
                n += 1
            used_emails.add(email)
            truth = rng.choices(["valid", "invalid", "catch_all"], weights=[84, 9, 7])[0]
            if country == "US":
                tz = rng.choice(N.US_TZ)
            else:
                tz = N.COUNTRY[country][1]
            prefix = "Dr. " if rng.random() < 0.03 else ""
            full = f"{prefix}{first} {last}"
            known = rng.random() < 0.55  # already in the CRM, or only findable through people search
            linkedin = f"https://www.linkedin.com/in/{first.lower()}-{last.lower()}-{aid}{rng.randint(10, 99)}".replace(" ", "")
            phone = f"+1 {rng.randint(201, 989)} {rng.randint(200, 999)} {rng.randint(1000, 9999)}" if rng.random() < 0.7 else None
            resp = round(rng.uniform(0.3, 1.0), 3)
            champion = lifecycle == "customer" and persona in ("controller", "cfo", "revops") and rng.random() < 0.6
            if known:
                pid = db.val(cur, """
                    insert into people (account_id, full_name, first_name, last_name, title, seniority, email,
                                        email_status, linkedin_url, country, timezone, source, crm_id, created_at,
                                        is_champion)
                    values (%s,%s,%s,%s,%s,%s,%s,'unknown',%s,%s,%s,'crm',%s,%s,%s) returning id""",
                    aid, full, first, last, title, seniority, email, linkedin, country, tz,
                    f"CRM-C{aid}-{len(used_people)}", start - timedelta(days=rng.randint(10, 700)), champion)
                db.run(cur, "insert into sim_people (person_id, true_email, email_truth, responsiveness, phone_truth) "
                            "values (%s,%s,%s,%s,%s)", pid, email, truth, resp, phone)
            else:
                db.run(cur, """insert into sim_hidden_people (account_id, full_name, first_name, last_name, title, seniority,
                                 linkedin_url, country, timezone, true_email, email_truth, responsiveness, phone_truth,
                                 is_champion)
                               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                       aid, full, first, last, title, seniority, linkedin, country, tz, email, truth, resp, phone, champion)
        if lifecycle in ("customer", "churned"):
            db.run(cur, """insert into opportunities (account_id, crm_id, name, amount_cents, stage, created_at, closed_at,
                                                      won, attribution)
                           values (%s, %s, %s, %s, 'Closed Won', %s, %s, true, 'none')""",
                   aid, f"CRM-O{aid}", f"{name} new business", rng.randint(24, 140) * 100000,
                   start - timedelta(days=rng.randint(200, 700)), start - timedelta(days=rng.randint(100, 190)))
        if lifecycle == "open_opp":
            db.run(cur, """insert into opportunities (account_id, crm_id, name, amount_cents, stage, created_at, attribution)
                           values (%s, %s, %s, %s, 'Evaluation', %s, 'none')""",
                   aid, f"CRM-O{aid}", f"{name} new business", rng.randint(24, 140) * 100000,
                   start - timedelta(days=rng.randint(5, 60)))
    return {"accounts": len(accounts)}
