"""Enrichment: company data and what changes between reads, catch-all resolution, kept answers, people details."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from test_guarantees import scene  # noqa: F401

from outbound import adapters, db, enrichment, outreach
from outbound.adapters import CompanyData


@pytest.fixture
def no_meter(monkeypatch):
    """Paid calls are recorded in a list instead of the ledger (the ledger commits on its own connection)."""
    calls = []

    @contextmanager
    def record(cur, adapter, operation, **kw):
        info = {}
        yield info
        calls.append((adapter, info.get("charged_qty", kw["qty"])))

    monkeypatch.setattr(enrichment.spend, "paid_call", record)
    monkeypatch.setattr(outreach.spend, "paid_call", record)
    return calls


@pytest.fixture(autouse=True)
def signal_types(cur):
    for key, level in (("new_exec", "person"), ("hiring_function", "account"), ("tech_added", "account"),
                       ("tech_removed", "account"), ("funding", "account")):
        db.run(cur, """insert into signal_types (key, label, because, level, weight, half_life_days)
                       values (%s, %s, 'Because of a test signal', %s, 10, 30) on conflict do nothing""", key, key, level)


class Reads:
    """A company-data vendor that returns the next read each time it is asked."""
    name = "test_company"

    def __init__(self, *reads):
        self.reads = list(reads)

    def enrich(self, cur, account):
        return self.reads.pop(0)


def test_company_data_fills_blanks_and_two_reads_raise_signals(cur, scene, no_meter, monkeypatch):  # noqa: F811
    db.run(cur, "update accounts set industry = null, employees = null, tech = '{}' where id = %s", scene["account"])
    first = CompanyData(industry="Software", employees=300, technologies=["Stripe"], headcount={"finance": 10},
                        open_roles=[], confidence=0.9)
    second = CompanyData(industry="Fintech", employees=320, technologies=["Stripe", "Snowflake"], headcount={"finance": 13},
                         open_roles=[{"title": "Revenue Accountant"}, {"title": "Billing Specialist"}],
                         latest_funding_round="Series B", latest_funding_at="2026-11-01", confidence=0.9)
    monkeypatch.setattr(adapters.get(), "company", Reads(first, second))
    monkeypatch.setattr(enrichment, "bought", lambda cur, kind, key, buy, keep_days=None: enrichment._plain(buy()))
    a = db.one(cur, "select * from accounts where id = %s", scene["account"])
    assert enrichment.enrich_company(cur, a, force=True)
    a = db.one(cur, "select * from accounts where id = %s", scene["account"])
    assert (a["industry"], a["employees"], a["tech"]) == ("Software", 300, ["Stripe"])
    assert db.val(cur, "select vendor from field_sources where object_id = %s and field = 'industry'", scene["account"]) == "test_company"
    enrichment.enrich_company(cur, a, force=True)
    a = db.one(cur, "select * from accounts where id = %s", scene["account"])
    assert a["industry"] == "Software"  # filled once, never overwritten by a vendor's later guess
    assert "Snowflake" in a["tech"]
    types = {r["type_key"] for r in db.all(cur, "select type_key from signals where account_id = %s and source = 'enrichment'",
                                           scene["account"])}
    assert {"hiring_function", "tech_added", "funding"} <= types
    assert db.val(cur, "select count(*) from account_snapshots where account_id = %s", scene["account"]) == 2


class Verifier:
    name = "test_verifier"

    def __init__(self, verdict):
        self.verdict, self.asked = verdict, 0

    def verify(self, cur, email):
        self.asked += 1
        return self.verdict


class Resolver:
    name = "test_resolver"

    def __init__(self, verdict):
        self.verdict = verdict

    def resolve(self, cur, email):
        return self.verdict


def test_a_catch_all_address_is_resolved_or_stops_without_paying_again(cur, scene, no_meter, monkeypatch):  # noqa: F811
    ad = adapters.get()
    v = Verifier("catch_all")
    monkeypatch.setattr(ad, "verifier", v)
    monkeypatch.setattr(ad, "resolver", Resolver(("valid", 0.85)))
    db.run(cur, "update people set email = 'resolve.me@x.example', email_status = 'unknown', email_verified_at = null where id = %s",
           scene["person"])
    person = db.one(cur, "select * from people where id = %s", scene["person"])
    account = db.one(cur, "select * from accounts where id = %s", scene["account"])
    assert outreach._ensure_email(cur, person, account) == "valid"
    assert float(db.val(cur, "select email_confidence from people where id = %s", scene["person"])) == 0.85
    # Unresolved, it is a stop for that person, and asking again within the window does not buy another check.
    monkeypatch.setattr(ad, "resolver", Resolver(("catch_all", 0.4)))
    db.run(cur, "update people set email = 'still.unsure@x.example', email_status = 'unknown', email_verified_at = null where id = %s",
           scene["person"])
    person = db.one(cur, "select * from people where id = %s", scene["person"])
    assert outreach._ensure_email(cur, person, account) == "catch_all"
    asked = v.asked
    person = db.one(cur, "select * from people where id = %s", scene["person"])
    assert outreach._ensure_email(cur, person, account) == "catch_all"
    assert v.asked == asked
    from outbound import gate
    reasons = gate.person_reasons(cur, scene["person"], "email")
    assert any(r.code == "email_unconfirmed" and r.permanent for r in reasons)


def test_a_paid_answer_is_kept_when_the_job_rolls_back(cur, scene):  # noqa: F811
    bought = []

    def buy():
        bought.append(1)
        return "kept@x.example"

    key = f"rollback-test:{scene['person']}"
    assert enrichment.bought(cur, "email_finder:test", key, buy) == "kept@x.example"
    assert enrichment.bought(cur, "email_finder:test", key, buy) == "kept@x.example"
    assert bought == [1]
    with db.tx() as own:
        db.run(own, "delete from enrichment_results where key = %s", key)


def test_someone_new_in_a_finance_seat_is_a_signal(cur, scene):  # noqa: F811
    db.run(cur, "update people set title = 'VP Finance' where id = %s", scene["person"])
    started = db.val(cur, "select (app_now() - interval '20 days')::date")
    enrichment.apply_person(cur, scene["person"], {"departments": ["finance"], "role_started_at": started,
                                                   "match_confidence": "high", "city": "Austin"}, "test_people")
    assert db.val(cur, "select count(*) from signals where account_id = %s and type_key = 'new_exec' and source = 'enrichment'",
                  scene["account"]) == 1
    assert db.val(cur, "select city from people where id = %s", scene["person"]) == "Austin"


def test_a_low_confidence_match_writes_nothing(cur, scene):  # noqa: F811
    enrichment.apply_person(cur, scene["person"], {"departments": ["finance"], "city": "Nowhere", "match_confidence": "low"},
                            "test_people")
    assert db.val(cur, "select city from people where id = %s", scene["person"]) is None


def test_one_person_per_profile_however_the_url_is_written(cur, scene):  # noqa: F811
    db.run(cur, "update people set linkedin_url = 'https://www.linkedin.com/in/ana-key/', linkedin_key = %s where id = %s",
           enrichment.linkedin_key("https://www.linkedin.com/in/ana-key/"), scene["person"])
    assert enrichment.linkedin_key("http://linkedin.com/in/Ana-Key") == "linkedin.com/in/ana-key"
    assert db.val(cur, "select id from people where linkedin_key = %s",
                  enrichment.linkedin_key("linkedin.com/in/ana-key")) == scene["person"]


def test_a_do_not_call_number_is_never_dialled(cur, scene):  # noqa: F811
    from outbound import gate
    db.run(cur, "update people set phone = '+15550001111', phone_status = 'valid', phone_dnc = true where id = %s", scene["person"])
    reasons = gate.person_reasons(cur, scene["person"], "call")
    assert any(r.permanent and "call" in r.message.lower() for r in reasons)
