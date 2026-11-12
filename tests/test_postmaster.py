"""Google Postmaster Tools as the source of sending-domain reputation, and the warm-up vendor slot. No test calls
Google: the live adapter is given a fake HTTP function that returns canned answers in Google's v2 shapes."""
from __future__ import annotations

import urllib.error
from datetime import date

import pytest

from outbound import adapters, db, monitors, sending, vendors, views
from outbound.adapters import DomainTelemetry, live, sim


@pytest.fixture
def box(cur):
    u = db.val(cur, "insert into users (name, email, role) values ('Pat Test', %s, 'sdr') returning id", f"p{id(cur)}@x.example")
    dom = f"send{id(cur)}.example"
    db.run(cur, """insert into sending_domains (domain, spf, dkim, dmarc, dmarc_policy, dmarc_aligned, registered_at,
                                                checked_at, spam_rate, spam_rate_at, postmaster_status)
                   values (%s, true, true, true, 'quarantine', true, app_now()::date - 200, app_now(), 0.0004, app_now(), 'compliant')""",
           dom)
    mb = db.val(cur, """insert into mailboxes (address, domain, provider, display_name, user_id, warmup_started, ramp_start)
                        values (%s, %s, 'google', 'Pat Test', %s, app_now()::date - 120, app_now()::date - 100) returning id""",
                f"pat@{dom}", dom, u)
    return {"id": mb, "domain": dom}


class Fixed:
    """A telemetry vendor that answers exactly this, for every domain asked about."""
    def __init__(self, spam, status):
        self.spam, self.status = spam, status

    def domains(self, cur, domains):
        return [DomainTelemetry(d, self.spam, self.status) for d in domains]

    def placement(self, cur, mailbox):
        return []


def run_telemetry(cur, monkeypatch, spam, status):
    monkeypatch.setattr(adapters.get(), "telemetry", Fixed(spam, status))
    sending.telemetry(cur, {})


def mb(cur, mailbox_id):
    return db.one(cur, "select * from mailboxes where id = %s", mailbox_id)


# ---- the desk's rules

def test_a_failing_compliance_verdict_pauses_the_domains_mailboxes(cur, box, monkeypatch):
    run_telemetry(cur, monkeypatch, 0.0005, "needs_work")  # the spam rate is fine; the verdict is not
    m = mb(cur, box["id"])
    assert m["status"] == "paused" and "Postmaster" in m["pause_reason"]
    assert db.val(cur, "select postmaster_status from sending_domains where domain = %s", box["domain"]) == "needs_work"
    assert db.val(cur, "select count(*) from alerts where kind = 'spam_rate' and title like %s", f"%{box['domain']}%") == 1


def test_a_verdict_alone_with_no_spam_rate_still_pauses(cur, box, monkeypatch):
    run_telemetry(cur, monkeypatch, None, "needs_work")
    assert mb(cur, box["id"])["status"] == "paused"
    assert float(db.val(cur, "select spam_rate from sending_domains where domain = %s", box["domain"])) == 0.0004  # kept


def test_a_spam_rate_past_point_three_percent_pauses(cur, box, monkeypatch):
    run_telemetry(cur, monkeypatch, 0.004, "compliant")
    m = mb(cur, box["id"])
    assert m["status"] == "paused" and "0.3%" in m["pause_reason"]


def test_a_compliant_domain_keeps_sending(cur, box, monkeypatch):
    run_telemetry(cur, monkeypatch, 0.0008, "compliant")
    assert mb(cur, box["id"])["status"] == "active"
    assert db.val(cur, "select postmaster_status from sending_domains where domain = %s", box["domain"]) == "compliant"


def test_no_data_is_unknown_and_pauses_nothing(cur, box, monkeypatch):
    run_telemetry(cur, monkeypatch, None, None)
    assert mb(cur, box["id"])["status"] == "active"
    assert db.val(cur, "select postmaster_status from sending_domains where domain = %s", box["domain"]) == "unknown"


def test_the_monitor_finds_a_failing_domain_with_an_active_mailbox(cur, box):
    assert monitors.run_one(cur, "postmaster_failing")["found"] == 0
    db.run(cur, "update sending_domains set postmaster_status = 'needs_work' where domain = %s", box["domain"])
    r = monitors.run_one(cur, "postmaster_failing")
    assert r["found"] == 1 and r["sample"][0]["domain"] == box["domain"]
    db.run(cur, "update mailboxes set status = 'paused', pause_reason = 'x' where id = %s", box["id"])
    assert monitors.run_one(cur, "postmaster_failing")["found"] == 0


# ---- the simulation

def test_the_sim_has_a_domain_with_no_data_and_a_domain_with_a_verdict(cur, box):
    db.run(cur, "insert into sending_domains (domain, spf, dkim, dmarc, dmarc_aligned, registered_at) "
                "values ('new.example', true, true, true, true, app_now()::date - 10)")
    out = {t.domain: t for t in sim.SimTelemetry().domains(cur, ["new.example", box["domain"]])}
    assert (out["new.example"].spam_rate, out["new.example"].status) == (None, None)
    assert out[box["domain"]].status == "compliant" and out[box["domain"]].spam_rate is not None


def test_the_sim_warmup_reports_each_mailbox(cur, box):
    w = sim.SimWarmup()
    old = w.status(cur, mb(cur, box["id"]))
    assert old.state == "maintaining" and 0 <= old.score <= 100
    db.run(cur, "update mailboxes set warmup_started = app_now()::date - 5 where id = %s", box["id"])
    young = w.status(cur, mb(cur, box["id"]))
    assert (young.state, young.day, young.score) == ("warming", 5, None)


def test_the_inboxes_page_data_carries_warmup_and_postmaster(cur, box):
    d = views.deliverability(cur)
    mine = next(m for m in d["mailboxes"] if m["id"] == box["id"])
    assert mine["warmup"].state == "maintaining"
    assert next(x for x in d["domains"] if x["domain"] == box["domain"])["postmaster_status"] == "compliant"


# ---- the live adapter, with Google faked

COMPLIANT = {"complianceData": {"deliverabilityStatusVerdict": {"state": {"status": "COMPLIANT"}}}}
STATS = {"domainStats": [
    {"metric": "spam_rate", "date": {"year": 2026, "month": 11, "day": 9}, "value": {"doubleValue": 0.0011}},
    {"metric": "spam_rate", "date": {"year": 2026, "month": 11, "day": 10}, "value": {"doubleValue": 0.0007}},
    {"metric": "spam_rate", "date": {"year": 2026, "month": 11, "day": 8}, "value": {"doubleValue": 0.0021}}]}


def test_the_mapping_takes_the_latest_day_and_the_verdict():
    t = live.postmaster_telemetry("a.example", COMPLIANT, STATS)
    assert (t.spam_rate, t.status, t.as_of) == (0.0007, "compliant", date(2026, 11, 10))
    bad = {"complianceData": {"deliverabilityStatusVerdict": {"state": {"status": "NEEDS_WORK"}, "reason": "SPAM_RATE_HIGH"}}}
    assert live.postmaster_telemetry("a.example", bad, STATS).status == "needs_work"


def test_the_mapping_says_no_data_when_google_has_none():
    assert live.postmaster_telemetry("a.example", None, None) == DomainTelemetry("a.example", None, None, None)
    low = {"complianceData": {"deliverabilityStatusVerdict": {"state": {"status": "COMPLIANT"}, "reason": "MESSAGE_VOLUME_LOW"}}}
    t = live.postmaster_telemetry("a.example", low, {"domainStats": []})
    assert (t.spam_rate, t.status) == (None, None)  # low volume is no verdict, never a pass


def test_the_mapping_falls_back_to_the_requirement_rows():
    rows = {"complianceData": {"rowData": [{"requirement": "SPF", "status": {"status": "COMPLIANT"}},
                                           {"requirement": "DKIM", "status": {"status": "NEEDS_WORK"}}]}}
    assert live.postmaster_telemetry("a.example", rows, None).status == "needs_work"


def http_error(code):
    return urllib.error.HTTPError("https://x", code, "x", {}, None)


def test_the_live_adapter_asks_google_per_domain_and_treats_unverified_as_no_data():
    calls = []

    def fake(method, url, token, body=None, form=None):
        calls.append((method, url, token))
        if url == live.POSTMASTER_TOKEN_URL:
            assert form["refresh_token"] == "r" and form["grant_type"] == "refresh_token"
            return {"access_token": "tok"}
        if "unverified.example" in url:
            raise http_error(404)
        if url.endswith("/complianceStatus"):
            return COMPLIANT
        assert body["metricDefinitions"][0]["baseMetric"]["standardMetric"] == "SPAM_RATE"
        return STATS

    a = live.PostmasterTelemetry("c", "s", "r", http=fake, today=lambda: date(2026, 11, 11))
    good, none = a.domains(None, ["good.example", "unverified.example"])
    assert (good.spam_rate, good.status) == (0.0007, "compliant")
    assert (none.spam_rate, none.status) == (None, None)
    assert all(t == "tok" for _, u, t in calls if u != live.POSTMASTER_TOKEN_URL)
    assert a.placement(None, {}) == []


def test_other_google_errors_are_not_swallowed():
    def fake(method, url, token, body=None, form=None):
        if url == live.POSTMASTER_TOKEN_URL:
            return {"access_token": "tok"}
        raise http_error(500)

    with pytest.raises(urllib.error.HTTPError):
        live.PostmasterTelemetry("c", "s", "r", http=fake).domains(None, ["a.example"])


def test_live_mode_uses_postmaster_only_with_all_three_credentials(monkeypatch):
    from outbound import config
    base = sim.adapters()
    assert not isinstance(live.adapters(base).telemetry, live.PostmasterTelemetry)
    monkeypatch.setenv("POSTMASTER_CLIENT_ID", "c")
    monkeypatch.setenv("POSTMASTER_CLIENT_SECRET", "s")
    monkeypatch.setenv("POSTMASTER_REFRESH_TOKEN", "r")
    monkeypatch.setattr(config, "CONFIG", config.Config())
    assert isinstance(live.adapters(base).telemetry, live.PostmasterTelemetry)
    assert live.Missing("warm-up").vendor  # the warm-up slot stays empty in a live desk until a vendor is connected
    assert live.adapters(base).warmup is None


# ---- the vendor catalog

def test_the_catalog_lists_postmaster_as_free_and_a_warmup_slot(cur):
    rows = {v["key"]: v for v in vendors.costs(cur)["vendors"]}
    assert rows["postmaster"]["paid"] == "free" and rows["postmaster"]["name"] == "Google Postmaster Tools"
    assert rows["warmup"]["group"] == "Sending" and rows["warmup"]["suggest"].startswith("Mailivery")
    assert rows["warmup"]["status"] == "simulated"
