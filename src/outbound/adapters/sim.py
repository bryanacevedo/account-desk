"""Simulated vendors. Each behaves like the real kind it stands for, including its failures: the finder misses,
the verifier calls catch-all addresses risky, the people search returns the wrong titles too."""
from __future__ import annotations

import hashlib
import logging
import random
import re

from .. import db
from . import Adapters, Candidate, DomainTelemetry, Page, PlacementResult, SendResult

log = logging.getLogger("outbound.sim")


class SimPeopleSearch:
    def search(self, cur, account: dict, title_patterns: list[str], limit: int) -> list[Candidate]:
        rows = db.all(cur, "select * from sim_hidden_people where account_id = %s and found_person_id is null", account["id"])
        pat = re.compile("|".join(re.escape(t) for t in title_patterns), re.I) if title_patterns else None
        hits = [r for r in rows if pat is None or pat.search(r["title"])]
        return [Candidate(full_name=r["full_name"], first_name=r["first_name"], last_name=r["last_name"], title=r["title"],
                          seniority=r["seniority"], linkedin_url=r["linkedin_url"], country=r["country"],
                          timezone=r["timezone"], vendor_ref=str(r["id"]), photo_url=r["photo_url"]) for r in hits[:limit]]

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
            return None
        rng = random.Random(f"find:{person['id']}")
        if rng.random() < 0.12:
            return None                                   # not found
        if rng.random() < 0.06:                           # a confident wrong guess, as real finders make
            return f"{person['first_name'].lower()}@{domain}"
        return truth["true_email"]


class SimVerifier:
    name = "sim_verifier"

    def verify(self, cur, email: str) -> str:
        truth = db.one(cur, "select email_truth from sim_people where lower(true_email) = %s", email.lower())
        if truth is None:
            return "invalid"
        return {"valid": "valid", "invalid": "invalid", "catch_all": "risky"}[truth["email_truth"]]


class SimPhone:
    def find(self, cur, person: dict) -> str | None:
        return db.val(cur, "select phone_truth from sim_people where person_id = %s", person["id"])


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
            out.append(DomainTelemetry(d, round(rate, 5), "compliant" if rate < 0.003 else "at_risk"))
        return out


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


class SimCrm:
    def push(self, cur, kind: str, payload: dict, idempotency_key: str) -> str:
        rng = random.Random(f"crm:{idempotency_key}:{db.val(cur, 'select attempts from crm_outbox where idempotency_key = %s', idempotency_key)}")
        if rng.random() < 0.03:
            raise ConnectionError("CRM returned 503")
        return f"CRM-{kind[:3].upper()}-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:8]}"


def adapters() -> Adapters:
    return Adapters(people=SimPeopleSearch(), finder=SimFinder(), verifier=SimVerifier(), phone=SimPhone(),
                    research=SimResearch(), email=SimEmail(), telemetry=SimTelemetry(), chat=SimChat(), crm=SimCrm(),
                    notes=["All vendors simulated"])
