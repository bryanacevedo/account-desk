# ruff: noqa: F811  (fixtures shared from test_guarantees and test_postmaster are named as parameters)
"""The final review's gates: compliance (fail closed), security checks at the edge of the API, and the copy fixes
that change behaviour. Each test tries the case the finding named."""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import logging
import time
from datetime import date, datetime, timezone

import pytest
from test_guarantees import refused, scene, send  # noqa: F401  the shared scene fixture
from test_postmaster import box, run_telemetry  # noqa: F401  the shared box fixture

from outbound import copy_gate, db, gate, outreach, plays, privacy, replies, signals, views

# ---------------------------------------------------------------- compliance


def test_spain_and_the_netherlands_need_consent():
    from outbound.seed import catalog
    rules = dict(catalog.REGION_RULES)
    assert rules["ES"] == "consent_required" and rules["NL"] == "consent_required"


def test_the_migration_moves_an_existing_desk_to_consent(cur):
    db.run(cur, "insert into region_rules (country, rule) values ('ES', 'basis_required') "
                "on conflict (country) do update set rule = 'basis_required'")
    text = (db.MIGRATIONS / "0028_compliance_gates.sql").read_text()
    sql = text[text.index("update region_rules set rule"):].split(";")[0]
    db.run(cur, sql)
    assert db.val(cur, "select rule from region_rules where country = 'ES'") == "consent_required"


def _live_env(monkeypatch, **extra):
    for k in ("LIVE_SEND", "PUBLIC_DEMO", "SENDER_COMPANY", "SENDER_ADDRESS", "PRIVACY_URL"):
        monkeypatch.delenv(k, raising=False)
    env = {"MODE": "live", "WEBHOOK_SECRET": "s" * 40, "AUTH_MODE": "header", "CF_ACCESS_TEAM_DOMAIN": "t.example",
           "CF_ACCESS_AUD": "aud", **extra}
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_live_mode_refuses_the_demo_sender_details(monkeypatch):
    from outbound.config import Config
    _live_env(monkeypatch)
    with pytest.raises(SystemExit, match="SENDER_COMPANY"):
        Config().validate()
    _live_env(monkeypatch, SENDER_COMPANY="Acme Ltd", SENDER_ADDRESS="Lumen Ledger, 400 Market Street, Suite 210, "
                                                                     "Philadelphia, PA 19106, USA")
    with pytest.raises(SystemExit, match="SENDER_ADDRESS"):
        Config().validate()
    _live_env(monkeypatch, SENDER_COMPANY="Acme Ltd", SENDER_ADDRESS="Acme Ltd, 1 High St, Leeds", PRIVACY_URL=" ")
    with pytest.raises(SystemExit, match="PRIVACY_URL"):
        Config().validate()
    _live_env(monkeypatch, SENDER_COMPANY="Acme Ltd", SENDER_ADDRESS="Acme Ltd, 1 High St, Leeds",
              PRIVACY_URL="https://acme.example/privacy")
    Config().validate()  # every value its own: starts


def test_live_mode_refuses_demo_auth(monkeypatch):
    from outbound.config import Config
    _live_env(monkeypatch, AUTH_MODE="demo", SENDER_COMPANY="Acme Ltd", SENDER_ADDRESS="Acme Ltd, 1 High St, Leeds",
              PRIVACY_URL="https://acme.example/privacy")
    with pytest.raises(SystemExit, match="AUTH_MODE=header"):
        Config().validate()


def test_the_app_validates_settings_when_it_starts(monkeypatch):
    import asyncio

    from outbound.api import app as api
    bad = dataclasses.replace(api.CONFIG, mode="live", auth_mode="demo")
    monkeypatch.setattr(api, "CONFIG", bad)

    async def start():
        async with api.lifespan(api.app):
            pass

    with pytest.raises(SystemExit):
        asyncio.run(start())


def _uk(cur, scene, subscriber):
    db.run(cur, "insert into region_rules (country, rule) values ('GB', 'basis_required') on conflict do nothing")
    db.run(cur, "update people set country = 'GB', timezone = 'Europe/London' where id = %s", scene["person"])
    db.run(cur, "update accounts set hq_country = 'GB', subscriber_type = %s where id = %s", subscriber, scene["account"])
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'legitimate_interest:LIA-1') "
                "on conflict (person_id) do update set basis = excluded.basis", scene["person"])


@pytest.mark.parametrize("subscriber,code", [("unknown", "pecr_unknown"), ("individual", "pecr_individual")])
def test_uk_individual_or_unknown_subscribers_are_not_cold_emailed(cur, scene, subscriber, code):
    _uk(cur, scene, subscriber)
    assert code in [r.code for r in gate.person_reasons(cur, scene["person"], "email")]
    refused(cur, scene["message"], "UK subscriber")


def test_a_uk_limited_company_may_be_emailed_and_consent_lifts_the_rule(cur, scene):
    _uk(cur, scene, "corporate")
    assert not [r for r in gate.person_reasons(cur, scene["person"], "email") if r.code.startswith("pecr")]
    send(cur, scene["message"])


def test_consent_lifts_the_uk_rule_for_a_sole_trader(cur, scene):
    _uk(cur, scene, "individual")
    db.run(cur, "update contact_basis set basis = 'consent' where person_id = %s", scene["person"])
    assert not [r for r in gate.person_reasons(cur, scene["person"], "email") if r.code.startswith("pecr")]


def _play(**kw):
    return {"sequence": [{"channel": "email"}], "lia_ref": "LIA-1", "lia_review_due": date(2099, 1, 1), **kw}


def test_a_play_on_legitimate_interest_needs_a_current_assessment(cur):
    db.run(cur, "insert into region_rules (country, rule) values ('FR', 'basis_required') on conflict do nothing")
    assert plays.lia_problem(cur, _play()) is None
    assert "reference" in plays.lia_problem(cur, _play(lia_ref=None))
    assert "next reviewed" in plays.lia_problem(cur, _play(lia_review_due=None))
    assert "due for review" in plays.lia_problem(cur, _play(lia_review_due=date(2000, 1, 1)))
    # No email, no reliance on it.
    assert plays.lia_problem(cur, _play(sequence=[{"channel": "call"}], lia_ref=None)) is None


def test_an_expired_assessment_records_no_new_basis(cur, scene):
    db.run(cur, "insert into region_rules (country, rule) values ('FR', 'basis_required') on conflict do nothing")
    person = {"id": scene["person"], "country": "FR"}
    outreach._record_basis(cur, person, _play(lia_review_due=date(2000, 1, 1)))
    assert db.val(cur, "select basis from contact_basis where person_id = %s", scene["person"]) is None
    outreach._record_basis(cur, person, _play())
    assert db.val(cur, "select basis from contact_basis where person_id = %s", scene["person"]).startswith("legitimate")


@pytest.mark.parametrize("country", ["NO", "IS", "LI", "CH", "BR", "DE"])
def test_the_first_contact_notice_names_the_source_and_the_right_to_object(database, country):
    f = outreach.footer_for({"id": 7, "country": country, "source": "people_search"}, "x")
    assert "We found your work details in a business contact database" in f
    assert "object" in f and "How we use them: " in f
    assert all(len(line) <= 120 for line in f.split("\n")[:4])


def test_no_notice_where_none_is_owed(database):
    assert "object" not in outreach.footer_for({"id": 7, "country": "US", "source": "crm"}, "x")


def _old_person(cur, account, *, email=None, phone=None, linkedin=None, months=13):
    return db.val(cur, """insert into people (account_id, full_name, email, phone, linkedin_url, source, created_at)
                          values (%s, 'Old Prospect', %s, %s, %s, 'people_search', app_now() - make_interval(months => %s))
                          returning id""", account, email, phone, linkedin, months)


def test_retention_deletes_stale_prospects_and_keeps_opt_outs_as_hashes(cur, scene):
    quiet = _old_person(cur, scene["account"], email=f"quiet{id(cur)}@x.example")
    gone = _old_person(cur, scene["account"], email=f"optout{id(cur)}@x.example", phone="+44 20 7946 0000",
                       linkedin=f"https://www.linkedin.com/in/optout{id(cur)}")
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email', %s, 'Unsubscribed', 'link')",
           f"optout{id(cur)}@x.example")
    recent = _old_person(cur, scene["account"], months=2)
    out = privacy.purge_stale(cur, batch=1_000_000)
    left = {r["id"] for r in db.all(cur, "select id from people where id = any(%s)", [quiet, gone, recent])}
    assert left == {recent} and out["opt_outs_kept"] >= 1
    assert privacy.erased(cur, email=f"optout{id(cur)}@x.example", linkedin_url=None)
    assert db.val(cur, "select exists (select 1 from suppressions where kind = 'phone_hash' and value = %s)",
                  privacy.phone_hash("+442079460000"))
    assert not db.val(cur, "select exists (select 1 from suppressions where kind = 'email' and value = %s)",
                      f"optout{id(cur)}@x.example")
    # The hashed number still blocks a call to the same number on someone new.
    newp = db.val(cur, "insert into people (account_id, full_name, phone, source, country) values (%s, 'New', "
                       "'+44 (20) 7946-0000', 'import', 'GB') returning id", scene["account"])
    assert "suppressed" in [r.code for r in gate.person_reasons(cur, newp, "call")]


def test_retention_keeps_anyone_with_a_reply_or_recent_activity(cur, scene):
    replied = _old_person(cur, scene["account"])
    db.run(cur, """insert into replies (person_id, account_id, from_addr, raw, cleaned, received_at, provider_id)
                   values (%s, %s, 'a@b.example', 'x', 'x', app_now() - interval '400 days', %s)""",
           replied, scene["account"], f"old-{id(cur)}")
    touched = _old_person(cur, scene["account"])
    db.run(cur, """insert into touches (account_id, person_id, channel, direction, kind, at, source, dedup_key)
                   values (%s, %s, 'email', 'out', 'email', app_now() - interval '30 days', 'desk', %s)""",
           scene["account"], touched, f"t-{id(cur)}")
    privacy.purge_stale(cur, batch=1_000_000)
    assert db.val(cur, "select count(*) from people where id = any(%s)", [replied, touched]) == 2


def test_retention_runs_as_a_periodic_job():
    from outbound import jobs, scheduler
    assert "retention_purge" in scheduler.PERIODIC and "retention_purge" in jobs.HANDLERS


def test_calls_follow_the_country_call_rule(cur, scene):
    pid = scene["person"]
    db.run(cur, "update people set phone = '+1 215 555 0100', country = null where id = %s", pid)
    assert "no_call_rule" in [r.code for r in gate.person_reasons(cur, pid, "call")]
    db.run(cur, "update people set country = 'ZZ' where id = %s", pid)
    assert "no_call_rule" in [r.code for r in gate.person_reasons(cur, pid, "call")]
    db.run(cur, "insert into region_rules (country, rule, call_rule) values ('ZY', 'allowed', 'blocked')")
    db.run(cur, "update people set country = 'ZY' where id = %s", pid)
    assert "call_blocked" in [r.code for r in gate.person_reasons(cur, pid, "call")]
    db.run(cur, "update region_rules set call_rule = 'allowed', dnc_register = 'National Do Not Call Registry' "
                "where country = 'US'")
    db.run(cur, "update people set country = 'US' where id = %s", pid)
    assert not [r for r in gate.person_reasons(cur, pid, "call") if r.code in ("no_call_rule", "call_blocked")]


def test_calls_wait_for_calling_hours_in_their_own_time(cur):
    london = {"country": "GB", "timezone": "Europe/London"}
    monday_8am = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)
    assert not gate.in_call_hours(cur, london, monday_8am)
    nxt = gate.next_call_time(cur, london, monday_8am)
    assert nxt == datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
    saturday = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    assert gate.next_call_time(cur, london, saturday).weekday() == 0
    # Not knowing where in the US: only when it is calling hours on both coasts.
    us = {"country": "US", "timezone": None}
    assert not gate.in_call_hours(cur, us, datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc))  # 7:00 in LA
    assert gate.in_call_hours(cur, us, datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc))
    assert gate.call_zones({"country": "XX", "timezone": None}) is None


def test_a_call_task_records_the_register_and_waits_for_calling_hours(cur, scene):
    from outbound import sdr_steps
    db.run(cur, "update region_rules set call_rule = 'allowed', dnc_register = 'National Do Not Call Registry' "
                "where country = 'US'")
    db.run(cur, "update people set phone = '+1 215 555 0100', phone_status = 'valid' where id = %s", scene["person"])
    e = db.one(cur, "select e.*, ap.owner_id from enrollments e join account_plays ap on ap.id = e.account_play_id "
                    "where e.id = %s", scene["enrollment"])
    saturday = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)
    tid = sdr_steps.make_task(cur, e, {"channel": "call"}, saturday)
    t = db.one(cur, "select * from tasks where id = %s", tid)
    assert t["dnc_register"] == "National Do Not Call Registry"
    assert t["due_at"].weekday() == 0 and gate.in_call_hours(cur, {"country": "US", "timezone": "America/New_York"},
                                                              t["due_at"])


def test_an_opt_out_also_blocks_the_phone_and_the_linkedin_profile(cur, scene):
    url = f"https://www.linkedin.com/in/ana{id(cur)}"
    db.run(cur, "update people set phone = '+1 215 555 0101', linkedin_url = %s where id = %s", url, scene["person"])
    privacy.suppress_other_channels(cur, scene["person"], reason="Unsubscribed by reply", source="reply")
    assert db.val(cur, "select exists (select 1 from suppressions where kind = 'phone' and value = '+1 215 555 0101')")
    assert db.val(cur, "select exists (select 1 from suppressions where kind = 'linkedin_hash' and value = %s)",
                  privacy.linkedin_hash(url))
    assert "suppressed" in [r.code for r in gate.person_reasons(cur, scene["person"], "linkedin")]


def test_a_long_reply_with_an_opt_out_goes_to_a_person(cur, scene, monkeypatch):
    from outbound import llm
    text = ("Thanks for the note. We already run billing on a tool we like and our renewal is two years out, so the "
            "timing is wrong for us and I would not want to waste your time. Please take me off your list.")
    rid = db.val(cur, """insert into replies (person_id, account_id, from_addr, raw, cleaned, received_at, provider_id)
                         values (%s, %s, 'ana@x.example', %s, %s, app_now(), %s) returning id""",
                 scene["person"], scene["account"], text, text, f"long-{id(cur)}")
    monkeypatch.setattr(llm, "run", lambda *a, **k: {"label": "not_interested", "confidence": 0.95, "same_person": True,
                                                     "instructs_system": False})
    replies.classify_job(cur, {"reply_id": rid})
    r = db.one(cur, "select needs_review, review_reason from replies where id = %s", rid)
    assert r["needs_review"] and r["review_reason"] == "The reply may ask to stop hearing from us"


def test_imported_people_record_where_they_came_from(cur, scene):
    from outbound import setup_desk
    dom = db.val(cur, "select primary_domain from accounts where id = %s", scene["account"])
    db.run(cur, "insert into account_domains (domain, account_id) values (%s, %s) on conflict do nothing", dom, scene["account"])
    out = setup_desk.import_people(cur, f"full_name,company_domain,source\nIvo Prov,{dom},Trade show list 2026\n")
    assert out["imported"] == 1
    assert db.val(cur, "select source_origin from people where full_name = 'Ivo Prov'") == "Trade show list 2026"


def test_a_spam_rate_at_point_one_percent_warns(cur, box, monkeypatch):  # noqa: F811
    run_telemetry(cur, monkeypatch, 0.0015, "compliant")
    assert db.val(cur, "select count(*) from alerts where kind = 'spam_rate_warn' and title like %s", f"%{box['domain']}%") == 1
    assert db.val(cur, "select status from mailboxes where id = %s", box["id"]) == "active"


def test_old_complaint_data_is_not_known_for_a_promotion(cur, scene):
    pl = db.one(cur, "select * from plays where id = %s", scene["play"])

    def known() -> bool:
        return next(c for c in views.promotion_check(cur, {**pl, "autonomy": "draft"})["checks"]
                    if c["label"].startswith("Complaint data"))["ok"]

    db.run(cur, "update sending_domains set spam_rate = 0.0004, spam_rate_at = app_now()")
    assert known()
    # The domain went silent a week ago: the rate it last reported is not known any more.
    dom = db.val(cur, "select domain from mailboxes where id = %s", scene["mailbox"])
    db.run(cur, "update sending_domains set spam_rate_at = app_now() - interval '8 days' where domain = %s", dom)
    assert not known()



# ---------------------------------------------------------------- copy checks that change behaviour

def test_a_new_leader_fact_is_a_whole_clause_with_its_own_subject(cur, scene):
    from outbound import enrichment
    db.run(cur, "update accounts set name = 'Brightwave Apps' where id = %s", scene["account"])
    db.run(cur, "update people set title = 'VP Finance', role_started_at = app_now()::date - 5, full_name = 'Ana Diaz' "
                "where id = %s", scene["person"])
    db.run(cur, "insert into signal_types (key, label, because, level, weight, half_life_days) values "
                "('new_exec', 'New finance leader', 'A new finance leader reviews the tools', 'account', 22, 45) "
                "on conflict do nothing")
    db.run(cur, "insert into signal_sources (key, label, adapter, cadence_minutes) values ('enrichment', 'E', "
                "'enrichment', 60) on conflict do nothing")
    enrichment._new_in_seat(cur, scene["person"])
    text = db.val(cur, "select text from facts where account_id = %s and kind = 'signal:new_exec'", scene["account"])
    assert text.startswith("Brightwave Apps appointed Ana Diaz as VP Finance on ")
    from outbound.sim_llm import clause
    assert clause("Brightwave Apps", text) == text.rstrip(".")
    assert clause("X", "A new controller started.") == "a new controller started"


def test_a_capital_article_after_that_fails_the_copy_check():
    draft = {"subject": "Billing", "sentences": [
        {"text": "Ana,", "kind": "courtesy", "fact_ids": []},
        {"text": "Saw that A new VP Finance started on 15 Sep 2026 at Brightwave.", "kind": "claim", "fact_ids": [1]},
        {"text": "Would a short call next week help?", "kind": "ask", "fact_ids": []}]}
    v = copy_gate.check(draft, job="follow_up", person={"first_name": "Ana"}, account={"name": "Brightwave"},
                        facts={1: "A new VP Finance started on 15 Sep 2026."}, our_names=[], other_bodies=[])
    assert "broken_clause" in [f["code"] for f in v.failures]
    draft["sentences"][1]["text"] = "Saw that Brightwave appointed a VP Finance on 15 Sep 2026."
    v = copy_gate.check(draft, job="follow_up", person={"first_name": "Ana"}, account={"name": "Brightwave"},
                        facts={1: "Brightwave appointed a VP Finance on 15 Sep 2026."}, our_names=[], other_bodies=[])
    assert "broken_clause" not in [f["code"] for f in v.failures]


# ---------------------------------------------------------------- security

@pytest.fixture(scope="module")
def client(world):
    from fastapi.testclient import TestClient

    from outbound.api.app import app
    return TestClient(app)


def _user(role: str) -> dict:
    with db.tx() as cur:
        return {"X-Acting-As": str(db.val(cur, "select id from users where role = %s and active order by id limit 1", role))}


@pytest.fixture
def public_demo(monkeypatch):
    from outbound.api import app as api
    monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, public_demo=True))
    return api


@pytest.mark.parametrize("method,path,body,role", [
    ("post", "/api/kill-switch", {"on": True, "reason": "testing"}, "manager"),
    ("post", "/api/users", {"name": "New Person", "email": "new@x.example", "role": "sdr"}, "manager"),
    ("patch", "/api/users/1", {"name": "Renamed"}, "manager"),
    ("post", "/api/people/1/erase", None, "gtm"),
    ("put", "/api/icp", {"factors": [{"key": "a", "field": "industry", "op": "in", "value": ["x"], "weight": 1}],
                         "tiers": {"A": 80, "B": 60}, "note": "test"}, "gtm"),
    ("post", "/api/import/accounts", {"csv": "name,domain\nA,a.example\n"}, "manager"),
])
def test_the_public_demo_refuses_what_would_change_it_for_everyone(client, public_demo, method, path, body, role):
    r = getattr(client, method)(path, headers=_user(role), **({"json": body} if body is not None else {}))
    assert r.status_code == 403 and r.json()["detail"] == "Not available in the public demo."


def test_the_simulated_clock_moves_one_request_at_a_time(client, public_demo):
    public_demo._sim_lock.acquire()
    try:
        r = client.post("/api/sim/advance", json={"hours": 300}, headers=_user("sdr"))
    finally:
        public_demo._sim_lock.release()
    assert r.status_code in (404, 409)
    if r.status_code == 409:
        assert "already moving" in r.json()["detail"]


def test_a_large_body_is_refused_before_it_is_read(client):
    big = json.dumps({"kind": "email", "value": "a@b.example", "reason": "x" * 1_100_000})
    r = client.post("/api/suppressions", content=big, headers={**_user("manager"), "Content-Type": "application/json"})
    assert r.status_code == 413


def test_a_streamed_body_over_the_limit_is_cut_off(client):
    def chunks():
        for _ in range(12):
            yield b"x" * 100_000
    r = client.post("/api/suppressions", content=chunks(), headers={**_user("manager"), "Content-Type": "application/json"})
    assert r.status_code == 413


def test_cross_site_writes_and_non_json_bodies_are_refused(client):
    body = {"kind": "email", "value": "cross@site.example", "reason": "testing"}
    h = _user("manager")
    assert client.post("/api/suppressions", json=body, headers={**h, "Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/suppressions", json=body, headers={**h, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    r = client.post("/api/suppressions", content="kind=email", headers={**h, "Content-Type": "text/plain"})
    assert r.status_code == 415
    ok = client.post("/api/suppressions", json=body, headers={**h, "Origin": "http://testserver",
                                                               "Sec-Fetch-Site": "same-origin"})
    assert ok.status_code == 200


def _signed(body: dict, ts: int | None = None) -> tuple[bytes, dict]:
    from outbound.config import CONFIG
    raw = json.dumps(body).encode()
    ts = ts or int(time.time())
    sig = hmac.new(CONFIG.webhook_secret.encode(), str(ts).encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, {"X-Signature": sig, "X-Signature-Timestamp": str(ts), "Content-Type": "application/json"}


def test_a_webhook_without_signature_headers_is_refused(client):
    r = client.post("/api/webhooks/reply", content=b"{}", headers={"Content-Type": "application/json"})
    assert r.status_code == 401


def test_a_replayed_webhook_is_refused(client):
    body = {"provider_id": f"replay-{time.time()}", "from_addr": "someone@unknown.example", "body": "Not now.",
            "received_at": "2026-10-01T10:00:00+00:00"}
    raw, h = _signed(body)
    assert client.post("/api/webhooks/reply", content=raw, headers=h).status_code == 200
    assert client.post("/api/webhooks/reply", content=raw, headers=h).status_code == 409


def test_a_signal_link_that_is_not_http_is_refused(client):
    raw, h = _signed({"type": "funding", "external_id": f"js-{time.time()}", "observed_at": "2026-10-01T10:00:00+00:00",
                      "domain": "nowhere.example", "evidence": {"summary": "Raised", "url": "javascript:alert(1)"}})
    assert client.post("/api/webhooks/signal", content=raw, headers=h).status_code == 422


def test_only_http_links_are_kept():
    assert signals.http_url("https://a.example/x") == "https://a.example/x"
    assert signals.http_url("HTTP://a.example") == "HTTP://a.example"
    for bad in ("javascript:alert(1)", "data:text/html,x", "a.example", "", None, "https://"):
        assert signals.http_url(bad) is None


def test_ingest_drops_a_link_that_is_not_http(cur, scene):
    db.run(cur, "insert into account_domains (domain, account_id) values ('ingest.example', %s) on conflict do nothing",
           scene["account"])
    signals.ingest(cur, "t_src", [{"type": "t_sig", "external_id": f"bad-{id(cur)}", "domain": "ingest.example",
                                   "observed_at": datetime.now(timezone.utc),
                                   "evidence": {"summary": "x", "url": "javascript:alert(1)", "quote": "q"}}])
    ev = db.val(cur, "select evidence from signals where external_id = %s", f"bad-{id(cur)}")
    assert "url" not in ev and ev["quote"] == "q"


def test_settings_show_only_the_allowed_keys(client):
    keys = set(client.get("/api/settings", headers=_user("sdr")).json()["settings"])
    assert keys <= set(views.SETTINGS_SHOWN) and "unsubscribe_secret" not in keys and "kill_switch" in keys


def test_a_search_treats_percent_and_underscore_as_text():
    assert views.like_pattern("50%_off") == "%50\\%\\_off%"


def test_the_postmaster_domain_is_one_path_segment():
    from outbound.adapters import live
    seen = []

    def fake(method, url, token, body=None, form=None):
        seen.append(url)
        return {"access_token": "tok"} if url == live.POSTMASTER_TOKEN_URL else {}

    live.PostmasterTelemetry("c", "s", "r", http=fake, today=lambda: date(2026, 11, 11)).domains(None, ["a/../b.example"])
    assert any("/domains/a%2F..%2Fb.example/" in u for u in seen)


def test_the_linkedin_token_never_reaches_a_log_line():
    from outbound.api import app as api
    assert api.redact_path("/api/webhooks/linkedin/s3cret-token") == "/api/webhooks/linkedin/[redacted]"
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "POST", "/api/webhooks/linkedin/s3cret-token?x=1", "1.1", 200), None)
    api._RedactAccessLog().filter(rec)
    assert "s3cret" not in rec.getMessage()


def _request(peer: str, xff: str | None):
    from starlette.requests import Request
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1234),
                    "query_string": b""})


def test_the_rate_limit_keys_on_the_first_forwarded_hop_only_behind_a_trusted_proxy(monkeypatch):
    from outbound.api import app as api
    monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, forwarded_allow_ips="10.0.0.0/8"))
    assert api.client_ip(_request("10.1.2.3", "203.0.113.9, 10.1.2.3")) == "203.0.113.9"
    assert api.client_ip(_request("198.51.100.7", "203.0.113.9")) == "198.51.100.7"  # a client cannot pick its key
    assert api.client_ip(_request("10.1.2.3", None)) == "10.1.2.3"


def test_the_rate_limit_forgets_quiet_clients(monkeypatch):
    from collections import deque

    from outbound.api import app as api
    api._hits["write:old"] = deque([time.monotonic() - 3600])
    monkeypatch.setattr(api, "_hits_calls", 499)
    api.rate_limit(_request("192.0.2.1", None))
    assert "write:old" not in api._hits


@pytest.mark.parametrize("bucket,call", [
    ("preview", lambda c, h: c.post("/api/play-preview", json={}, headers=h)),
    ("search", lambda c, h: c.get("/api/accounts?q=a", headers=h)),
])
def test_previews_and_searches_are_rate_limited(client, bucket, call):
    from collections import deque

    from outbound.api import app as api
    key = f"{bucket}:testclient"
    api._hits[key] = deque([time.monotonic()] * 100)
    try:
        assert call(client, _user("gtm")).status_code == 429
    finally:
        api._hits.pop(key, None)


def test_the_launch_gate_is_wired_into_the_api(client):
    with db.tx() as cur:
        pl = db.one(cur, "select id, lia_review_due from plays where status = 'live' order by id limit 1")
        db.run(cur, "insert into region_rules (country, rule) values ('FR', 'basis_required') on conflict do nothing")
        db.run(cur, "update plays set status = 'paused', lia_review_due = '2000-01-01' where id = %s", pl["id"])
    try:
        r = client.post(f"/api/plays/{pl['id']}", json={"status": "live", "reason": "back on"}, headers=_user("manager"))
        assert r.status_code == 422 and "due for review" in r.json()["detail"]
    finally:
        with db.tx() as cur:
            db.run(cur, "update plays set status = 'live', lia_review_due = %s where id = %s", pl["lia_review_due"], pl["id"])



# ---------------------------------------------------------------- copy that comes from code

def test_alerts_name_jobs_and_waits_in_words():
    from outbound import jobs, spend
    from outbound.adapters import VendorMissing
    assert jobs.job_name("autonomy_watch") == "Checking plays for a stage change"
    assert jobs.waiting_title(spend.OverBudget("phone_finder")) == "Phone finder work is waiting: monthly cap reached"
    assert jobs.waiting_title(spend.PlayOverBudget("Raised a round: email_finder")) == (
        "Email finder work for Raised a round is waiting: the play's monthly cap is reached")
    missing = VendorMissing("no people_search configured")
    missing.vendor = "people_search"
    assert jobs.waiting_title(missing) == "People search work is waiting: no vendor is connected for it"


def test_a_demotion_alert_names_the_stage_in_words():
    assert plays.STAGE_WORDS["supervised"] == "SDR approves first emails and checks a sample of the rest"
    assert set(plays.STAGE_WORDS) == set(views.STAGES)


def test_review_reasons_are_plain():
    import inspect
    import re
    src = re.sub(r"[\"']\s+[\"']", "", inspect.getsource(replies.classify_job))  # strings split across lines
    assert "The desk is not sure what this reply means" in src
    assert "The reply contains instructions aimed at the desk" in src
