"""Simulated vendors. Each behaves like the real kind it stands for, including its failures: the finder misses,
the verifier calls catch-all addresses risky, the people search returns the wrong titles too."""
from __future__ import annotations

import hashlib
import logging
import random
import re
from datetime import date, timedelta

from .. import db
from . import (
    Adapters,
    Candidate,
    CompanyData,
    CrmDeal,
    CrmOwner,
    DnsResult,
    DomainTelemetry,
    Page,
    PhoneHit,
    PlacementResult,
    SendResult,
    WarmupStatus,
)

log = logging.getLogger("outbound.sim")


DEPARTMENTS = [  # title words -> the department a people-data vendor files them under
    (("revenue operations", "revops", "sales operations", "billing operations"), ["sales_operations", "revenue_operations"]),
    (("controller", "accounting"), ["finance", "accounting"]),
    (("data", "systems", "it ", "information"), ["data", "information_technology"]),
    (("finance", "cfo", "chief financial", "fp&a", "treasur"), ["finance"]),
]


def departments_for(title: str) -> list[str]:
    t = (title or "").lower() + " "
    for words, depts in DEPARTMENTS:
        if any(w in t for w in words):
            return depts
    return ["other"]


WORLD_EPOCH = date(2026, 10, 15)


def _today(cur) -> date:
    return db.val(cur, "select app_now()::date")


def _person_extras(cur, key: str, title: str, country: str | None) -> dict:
    """What a people-data vendor adds: departments, when the role started, city, headline, how sure the match is."""
    rng = random.Random(f"person-extras:{key}")
    # Fixed to the world, not to today: someone who started in October is still the one who started in October next
    # month. A few start inside the simulated months, which is what a new-in-seat signal is for.
    started = WORLD_EPOCH - timedelta(days=int(rng.choice([rng.randint(-10, 60), rng.randint(120, 1400), rng.randint(200, 2400)])))
    started = min(started, _today(cur))
    city = {"US": ["New York", "Chicago", "Austin", "Denver"], "GB": ["London", "Manchester"], "DE": ["Berlin", "Munich"],
            "CA": ["Toronto"], "FR": ["Paris"]}.get(country or "", ["Remote"])
    return {"departments": departments_for(title), "role_started_at": started, "city": rng.choice(city),
            "headline": f"{title}. " + rng.choice(["Scaling finance ops", "Building the revenue stack", "Clean books, faster closes"]),
            "match_confidence": rng.choices(["high", "medium", "low"], [0.8, 0.15, 0.05])[0]}


class SimPeopleSearch:
    def search(self, cur, account: dict, title_patterns: list[str], limit: int) -> list[Candidate]:
        rows = db.all(cur, "select * from sim_hidden_people where account_id = %s and found_person_id is null", account["id"])
        pat = re.compile("|".join(re.escape(t) for t in title_patterns), re.I) if title_patterns else None
        hits = [r for r in rows if pat is None or pat.search(r["title"])]
        return [Candidate(full_name=r["full_name"], first_name=r["first_name"], last_name=r["last_name"], title=r["title"],
                          seniority=r["seniority"], linkedin_url=r["linkedin_url"], country=r["country"],
                          timezone=r["timezone"], vendor_ref=str(r["id"]), photo_url=r["photo_url"],
                          **_person_extras(cur, f"h{r['id']}", r["title"], r["country"])) for r in hits[:limit]]

    def enrich(self, cur, person: dict) -> Candidate | None:
        """A people match on someone the desk already has: same person, fresher details."""
        if not person.get("full_name"):
            return None
        first, _, last = person["full_name"].partition(" ")
        return Candidate(full_name=person["full_name"], first_name=person.get("first_name") or first, last_name=last,
                         title=person.get("title") or "", seniority=person.get("seniority"),
                         linkedin_url=person.get("linkedin_url"), country=person.get("country"),
                         timezone=person.get("timezone"), photo_url=person.get("photo_url"),
                         **_person_extras(cur, f"p{person['id']}", person.get("title") or "", person.get("country")))

    def saved(self, cur, candidate: Candidate, person_id: int) -> None:
        h = db.one(cur, "select * from sim_hidden_people where id = %s", int(candidate.vendor_ref))
        db.run(cur, "update sim_hidden_people set found_person_id = %s where id = %s", person_id, h["id"])
        db.run(cur, """insert into sim_people (person_id, true_email, email_truth, responsiveness, phone_truth)
                       values (%s,%s,%s,%s,%s) on conflict do nothing""",
               person_id, h["true_email"], h["email_truth"], h["responsiveness"], h["phone_truth"])
        if h["is_champion"]:
            db.run(cur, "update people set is_champion = true where id = %s", person_id)


class SimFinder:
    name = "sim_finder"

    def find(self, cur, person: dict, domain: str) -> str | None:
        truth = db.one(cur, "select true_email from sim_people where person_id = %s", person["id"])
        if truth is None:
            # Someone the desk learned of another way (a referral, an import): a real finder looks them up by name
            # and company, so the simulated one matches its hidden people the same way.
            h = db.one(cur, """select * from sim_hidden_people where account_id = %s and lower(full_name) = lower(%s)
                               and found_person_id is null limit 1""", person["account_id"], person["full_name"])
            if h is None:
                return None
            db.run(cur, "update sim_hidden_people set found_person_id = %s where id = %s", person["id"], h["id"])
            db.run(cur, """insert into sim_people (person_id, true_email, email_truth, responsiveness, phone_truth)
                           values (%s,%s,%s,%s,%s) on conflict do nothing""",
                   person["id"], h["true_email"], h["email_truth"], h["responsiveness"], h["phone_truth"])
            truth = {"true_email": h["true_email"]}
        rng = random.Random(f"find:{person['id']}")
        if rng.random() < 0.12:
            return None                                   # not found
        if rng.random() < 0.06:                           # a confident wrong guess, as real finders make
            return f"{person['first_name'].lower()}@{domain}"
        return truth["true_email"]


class SimWaterfallStep:
    """One finder in the waterfall. Each step sees the same hidden truth but covers a different share of people,
    as real finders do; a later step only matters for the people the earlier ones missed."""

    def __init__(self, provider: str, miss: float, wrong: float):
        self.provider, self.miss, self.wrong = provider, miss, wrong
        self.name = f"sim_{provider}"
        self._base = SimFinder()

    def find(self, cur, person: dict, domain: str) -> str | None:
        rng = random.Random(f"find:{self.provider}:{person['id']}")
        if rng.random() < self.miss:
            return None
        truth = db.one(cur, "select true_email from sim_people where person_id = %s", person["id"])
        if truth is None:
            got = self._base.find(cur, person, domain)  # learns the person the way SimFinder does
            truth = db.one(cur, "select true_email from sim_people where person_id = %s", person["id"])
            if truth is None:
                return got
        if rng.random() < self.wrong:
            return f"{person['first_name'].lower()}@{domain}"
        return truth["true_email"]


# The order we would run: the most accurate finder first, broader ones after it for the people it misses.
WATERFALL = [("findymail", 0.22, 0.02), ("prospeo", 0.35, 0.04), ("leadmagic", 0.45, 0.05)]


class SimVerifier:
    name = "sim_verifier"

    def verify(self, cur, email: str) -> str:
        truth = db.one(cur, "select email_truth from sim_people where lower(true_email) = %s", email.lower())
        if truth is None:
            return "invalid"
        return {"valid": "valid", "invalid": "invalid", "catch_all": "catch_all"}[truth["email_truth"]]


class SimResolver:
    """A catch-all resolver: a second vendor that can often tell whether an address on a catch-all server is real."""
    name = "sim_resolver"

    def resolve(self, cur, email: str) -> tuple[str, float]:
        truth = db.val(cur, "select email_truth from sim_people where lower(true_email) = %s", email.lower())
        rng = random.Random(f"resolve:{email.lower()}")
        if truth is None:
            return "invalid", 0.9
        x = rng.random()
        if x < 0.55:
            return "valid", round(rng.uniform(0.72, 0.93), 2)
        if x < 0.70:
            return "invalid", round(rng.uniform(0.7, 0.9), 2)
        return "catch_all", round(rng.uniform(0.3, 0.6), 2)


class SimPhone:
    def find(self, cur, person: dict) -> PhoneHit | None:
        number = db.val(cur, "select phone_truth from sim_people where person_id = %s", person["id"])
        if not number:
            return None
        rng = random.Random(f"phone:{person['id']}")
        return PhoneHit(number=number, type=rng.choices(["mobile", "direct", "office"], [0.55, 0.3, 0.15])[0],
                        dnc=rng.random() < 0.06)


class SimCompany:
    """Company data. Headcount, open roles and tools drift with the account's hidden need, so two reads apart show
    a team growing, a role opening or a tool arriving where the need is real, and little where it is not."""
    name = "sim_company"
    TOOLS = ["Snowflake", "NetSuite", "Stripe", "Salesforce", "HubSpot", "BigQuery", "Chargebee", "Zuora"]

    def enrich(self, cur, account: dict) -> CompanyData | None:
        need = db.val(cur, "select need from sim_accounts where account_id = %s", account["id"])
        if need is None:
            return None
        need = float(need)
        rng = random.Random(f"company:{account['id']}")
        day = (_today(cur) - date(2026, 1, 1)).days
        employees = account.get("employees") or rng.randint(80, 2000)
        growth = 1 + need * 0.0025 * day                      # finance grows faster where the need is real
        finance = max(2, int(employees * 0.03 * growth))
        headcount = {"finance": finance, "accounting": max(1, int(finance * 0.5)),
                     "sales_operations": max(1, int(employees * 0.015)), "engineering": int(employees * 0.35),
                     "sales": int(employees * 0.18)}
        tools = list(account.get("tech") or [])
        for i, t in enumerate(self.TOOLS):
            if t not in tools and random.Random(f"tool:{account['id']}:{t}").random() < need * 0.25 * min(1.0, day / 300 + i * 0.02):
                tools.append(t)
        roles = [{"title": rng.choice(["Revenue Accountant", "Billing Specialist", "Senior Billing Analyst", "FP&A Manager"]),
                  "department": "finance", "seen_at": str(_today(cur) - timedelta(days=rng.randint(1, 30)))}
                 for _ in range(int(need * 4 * (1 + day / 365)) if random.Random(f"roles:{account['id']}:{day // 14}").random() < need else 0)]
        frng = random.Random(f"funding:{account['id']}")  # its own seed, so a filled field never moves the round
        funded = frng.random() < 0.45
        return CompanyData(
            industry=account.get("industry"), employees=employees, revenue_band=account.get("revenue_band"),
            technologies=tools, keywords=rng.sample(["usage-based pricing", "subscriptions", "b2b saas", "payments",
                                                      "fintech", "data platform", "marketplace"], 3),
            founded_year=rng.randint(2008, 2021),
            total_funding_cents=frng.choice([5, 12, 30, 60, 110]) * 100_000_000 if funded else None,
            latest_funding_round=frng.choice(["Series A", "Series B", "Series C"]) if funded else None,
            latest_funding_at=WORLD_EPOCH - timedelta(days=frng.randint(40, 900)) if funded else None,
            headcount=headcount, open_roles=roles, confidence=0.9)


class SimResearch:
    def pages(self, cur, account: dict) -> list[Page]:
        pages = db.val(cur, "select pages from sim_accounts where account_id = %s", account["id"]) or {}
        base = f"https://{account['primary_domain']}"
        paths = {"about": "/about", "pricing": "/pricing", "billing": "/docs/invoices", "finance": "/about/team",
                 "careers": "/careers"}
        return [Page(kind=k, text=v, url=base + paths.get(k, "/")) for k, v in pages.items()]


class SimEmail:
    """Accepts the send, then lets the simulated recipient react later."""

    def __init__(self) -> None:
        self.unknown_rate = 0.004

    def send(self, cur, message: dict, mailbox: dict, person: dict, headers: dict) -> SendResult:
        rng = random.Random(f"send:{message['id']}")
        if rng.random() < self.unknown_rate:
            return SendResult("unknown", None, "timeout talking to the mail provider")
        from ..sim import recipients
        at = db.val(cur, "select app_now()")
        recipients.on_send(cur, message, person["id"], mailbox, at)
        return SendResult("sent", f"sim-{message['id']}")

    def lookup(self, cur, idempotency_key: str) -> SendResult:
        # The simulated provider always knows: a timed-out send had in fact gone out half the time.
        rng = random.Random(f"lookup:{idempotency_key}")
        return SendResult("sent" if rng.random() < 0.5 else "failed", f"sim-{idempotency_key}")


def sim_inbox_rate(cur, mailbox_id: int, provider: str) -> float:
    """The simulated truth: how often this mailbox's mail reaches the inbox at a provider today."""
    t = db.one(cur, "select *, (worsens_from is not null and app_now() >= worsens_from) as worse from sim_mailboxes "
                    "where mailbox_id = %s", mailbox_id)
    if t is None:
        return 0.95
    if provider == "outlook" and t["worse"]:
        return float(t["worse_outlook"])
    return float(t[provider])


class SimTelemetry:
    def placement(self, cur, mailbox: dict) -> list[PlacementResult]:
        day = db.val(cur, "select app_now()::date")
        rng = random.Random(f"seed:{mailbox['id']}:{day}")
        out = []
        for provider in ("gmail", "outlook"):
            rate, seeds = sim_inbox_rate(cur, mailbox["id"], provider), 20
            inbox = sum(rng.random() < rate for _ in range(seeds))
            missing = sum(rng.random() < 0.15 for _ in range(seeds - inbox))
            out.append(PlacementResult(provider, seeds, inbox, seeds - inbox - missing, missing))
        return out

    def domains(self, cur, domains: list[str]) -> list[DomainTelemetry]:
        out = []
        for d in domains:
            row = db.one(cur, "select registered_at, spam_rate from sending_domains where domain = %s", d)
            age = db.val(cur, "select (app_now()::date - %s)", row["registered_at"])
            if age < 45:  # Postmaster shows nothing until there is enough volume
                out.append(DomainTelemetry(d, None, None))
                continue
            complaints = db.val(cur, """select count(*) from deliveries dl join mailboxes m on m.id = dl.mailbox_id
                                        where m.domain = %s and dl.event = 'complaint' and dl.at > app_now() - interval '7 days'""", d)
            sends = db.val(cur, """select count(*) from deliveries dl join mailboxes m on m.id = dl.mailbox_id
                                   where m.domain = %s and dl.event = 'sent' and dl.at > app_now() - interval '7 days'""", d)
            # Postmaster measures all traffic to Gmail, warm-up included (about 40 a day per mailbox here).
            mailboxes = db.val(cur, "select count(*) from mailboxes where domain = %s", d)
            rate = complaints / (sends + 7 * 40 * max(mailboxes, 1))
            out.append(DomainTelemetry(d, round(rate, 5), "compliant" if rate < 0.003 else "needs_work"))
        return out


class SimWarmup:
    """A warm-up vendor's report. Stands in for a real one; the desk's own ramp is separate and unchanged."""
    name = "sim:warmup"

    def status(self, cur, mailbox: dict) -> WarmupStatus:
        day = db.val(cur, "select app_now()::date - %s", mailbox["warmup_started"])
        if day < 14:
            return WarmupStatus("warming", day)
        # Once warm it keeps swapping a little mail to hold the reputation; the score is stable per mailbox.
        score = 86 + int(hashlib.sha256(str(mailbox["id"]).encode()).hexdigest(), 16) % 13
        return WarmupStatus("maintaining", day, score)


class SimChat:
    def __init__(self) -> None:
        self.posts: list[tuple[str, str]] = []
        self.channels: set[str] = {"#outbound-ops"}

    def post(self, channel: str, text: str, blocks: list | None = None) -> bool:
        self.posts.append((channel, text))
        return True

    def ensure_channel(self, name: str, invite: list[str]) -> str:
        self.channels.add(name)
        return name


class SimDns:
    """What DNS would say: the seeded records, except while a simulated DNS edit has broken DKIM."""
    def check(self, cur, domain: str, dkim_selector: str | None) -> DnsResult:
        d = db.one(cur, "select * from sending_domains where domain = %s", domain)
        broken = db.val(cur, """select exists (select 1 from sim_dns where domain = %s and app_now() >= dkim_broken_from
                                 and app_now() < dkim_broken_until)""", domain)
        seeded = d["dns_detail"].get("seeded") or {"spf": True, "dkim": True, "dmarc": True, "aligned": True,
                                                    "policy": d["dmarc_policy"] or "quarantine"}
        return DnsResult(domain, seeded["spf"], seeded["dkim"] and not broken, seeded["dmarc"], seeded["policy"],
                         seeded["aligned"] and not broken, [], {"seeded": seeded, "dkim_record": not broken})


class SimCrm:
    def deals_changed(self, cur, since, limit: int) -> list[CrmDeal]:
        ts, _, last = (since or "").partition("|")
        rows = db.all(cur, """select d.*, a.primary_domain from sim_crm_deals d join accounts a on a.id = d.account_id
                              where (d.updated_at, d.crm_id) > (coalesce(nullif(%s, '')::timestamptz, '-infinity'), %s)
                                and d.updated_at <= app_now()
                              order by d.updated_at, d.crm_id limit %s""", ts, last, limit)
        return [CrmDeal(r["crm_id"], r["primary_domain"], r["name"], r["amount_cents"], r["stage"], r["created_at"],
                        r["updated_at"], r["closed_at"], r["won"], r["loss_reason"], r["contact_email"]) for r in rows]

    def owners_changed(self, cur, since, limit: int) -> list[CrmOwner]:
        ts, _, last = (since or "").partition("|")
        rows = db.all(cur, """select c.*, a.primary_domain from sim_crm_owner_changes c join accounts a on a.id = c.account_id
                              where (c.updated_at, lpad(c.id::text, 12, '0')) > (coalesce(nullif(%s, '')::timestamptz, '-infinity'), %s)
                                and c.updated_at <= app_now()
                              order by c.updated_at, c.id limit %s""", ts, last, limit)
        return [CrmOwner(r["primary_domain"], r["owner_email"], r["updated_at"], str(r["id"]).zfill(12)) for r in rows]

    def push(self, cur, kind: str, payload: dict, idempotency_key: str) -> str:
        rng = random.Random(f"crm:{idempotency_key}:{db.val(cur, 'select attempts from crm_outbox where idempotency_key = %s', idempotency_key)}")
        if rng.random() < 0.03:
            raise ConnectionError("CRM returned 503")
        return f"CRM-{kind[:3].upper()}-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:8]}"


def adapters() -> Adapters:
    return Adapters(people=SimPeopleSearch(), finder=SimFinder(), verifier=SimVerifier(), phone=SimPhone(),
                    research=SimResearch(), email=SimEmail(), telemetry=SimTelemetry(), dns=SimDns(), chat=SimChat(), crm=SimCrm(),
                    notes=["All vendors simulated"], finders=[SimWaterfallStep(*w) for w in WATERFALL],
                    company=SimCompany(), resolver=SimResolver(), warmup=SimWarmup())
