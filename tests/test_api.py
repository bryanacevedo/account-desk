"""The HTTP surface: signatures, roles, the one-click unsubscribe, erasure, and that a rep's read carries no money."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

import pytest

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from outbound import db, outreach  # noqa: E402
from outbound.config import CONFIG  # noqa: E402


@pytest.fixture(scope="module")
def client(world):
    from outbound.api.app import app
    return TestClient(app)


def user(role: str) -> int:
    with db.tx() as cur:
        return db.val(cur, "select id from users where role = %s order by id limit 1", role)


def signed(body: dict, secret: str | None = None, ts: int | None = None) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    ts = ts or int(time.time())
    sig = hmac.new((secret or CONFIG.webhook_secret).encode(), str(ts).encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, {"X-Signature": sig, "X-Signature-Timestamp": str(ts), "Content-Type": "application/json"}


def test_reads_work_and_sdrs_see_no_money(client):
    sdr = {"X-Acting-As": str(user("sdr"))}
    mgr = {"X-Acting-As": str(user("manager"))}
    for path in ("/api/health", "/api/me", "/api/today", "/api/accounts", "/api/signals", "/api/plays", "/api/replies",
                 "/api/results", "/api/deliverability", "/api/settings"):
        assert client.get(path, headers=sdr).status_code == 200, path
    r = client.get("/api/results", headers=sdr).json()
    assert "spend" not in r and "sourced_cents" not in r["opportunities"]
    assert all("pipeline_cents" not in p for p in client.get("/api/plays", headers=sdr).json()["plays"])
    assert "spend" in client.get("/api/results", headers=mgr).json()
    assert client.get("/api/ops", headers=sdr).status_code == 403


def test_webhook_rejects_bad_and_stale_signatures(client):
    body = {"provider_id": "t-1", "from_addr": "x@y.example", "body": "hi", "received_at": "2026-10-01T10:00:00+00:00"}
    raw, h = signed(body, secret="wrong")
    assert client.post("/api/webhooks/reply", content=raw, headers=h).status_code == 401
    raw, h = signed(body, ts=int(time.time()) - 3600)
    assert client.post("/api/webhooks/reply", content=raw, headers=h).status_code == 401


def test_webhook_reply_is_stored_once(client):
    body = {"provider_id": "t-dup", "from_addr": "someone@unknown.example", "body": "Thanks, not now.",
            "received_at": "2026-10-01T10:00:00+00:00"}
    raw, h = signed(body)
    first = client.post("/api/webhooks/reply", content=raw, headers=h).json()
    second = client.post("/api/webhooks/reply", content=raw, headers=h).json()
    assert first["reply_id"] and second["duplicate"] is True


def test_signal_webhook_needs_evidence(client):
    raw, h = signed({"type": "funding", "external_id": "w1", "observed_at": "2026-10-01T10:00:00+00:00",
                     "domain": "nowhere.example", "evidence": {"summary": "Raised"}})
    assert client.post("/api/webhooks/signal", content=raw, headers=h).status_code == 422


def test_unsubscribe_get_does_nothing_post_suppresses(client):
    with db.tx() as cur:
        p = db.one(cur, "select id, email from people where email is not null order by id limit 1")
    token = outreach.unsubscribe_token(p["id"])
    assert client.get(f"/u/{p['id']}/badtoken").status_code == 404
    assert client.get(f"/u/{p['id']}/{token}").status_code == 200
    with db.tx() as cur:
        assert not db.val(cur, "select exists (select 1 from suppressions where kind = 'email' and value = %s)", p["email"])
    assert client.post(f"/u/{p['id']}/{token}").status_code == 200
    with db.tx() as cur:
        assert db.val(cur, "select exists (select 1 from suppressions where kind = 'email' and value = %s)", p["email"])


def test_the_short_link_in_todays_footer_works_and_guesses_do_not(client):
    with db.tx() as cur:
        p = db.one(cur, "select id, email from people where email is not null order by id desc limit 1")
    short = outreach.unsubscribe_token(p["id"])[:12]
    assert client.get(f"/u/{p['id']}-{short}").status_code == 200
    assert client.get(f"/u/{p['id']}-{short[:11]}x").status_code == 404
    assert client.get(f"/u/{p['id'] + 1}-{short}").status_code == 404
    assert client.post(f"/u/{p['id']}-{short}").status_code == 200
    with db.tx() as cur:
        assert db.val(cur, "select exists (select 1 from suppressions where kind = 'person' and value = %s)", str(p["id"]))


def test_an_sdr_cannot_approve_another_sdrs_email_or_change_a_play(client):
    with db.tx() as cur:
        m = db.one(cur, """select m.id, ap.owner_id from messages m join enrollments e on e.id = m.enrollment_id
                           join account_plays ap on ap.id = e.account_play_id where ap.owner_id is not null limit 1""")
        other = db.val(cur, "select id from users where role = 'sdr' and id <> %s limit 1", m["owner_id"])
        play = db.val(cur, "select id from plays limit 1")
    r = client.post(f"/api/messages/{m['id']}/approve", json={}, headers={"X-Acting-As": str(other)})
    assert r.status_code == 403
    r = client.post(f"/api/plays/{play}", json={"status": "paused", "reason": "test"}, headers={"X-Acting-As": str(other)})
    assert r.status_code == 403


def test_promotion_is_refused_until_the_checks_pass(client):
    with db.tx() as cur:
        play = db.one(cur, "select id, autonomy from plays where autonomy = 'research' limit 1")
    if play:
        r = client.post(f"/api/plays/{play['id']}", json={"autonomy": "draft", "reason": "test"},
                        headers={"X-Acting-As": str(user("manager"))})
        assert r.status_code == 422


def test_security_headers(client):
    h = client.get("/api/health").headers
    assert h["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["X-Content-Type-Options"] == "nosniff"


def test_erasure_removes_the_person_and_keeps_them_out(client):
    with db.tx() as cur:
        p = db.one(cur, """select p.id, p.email from people p where p.email is not null and exists
                           (select 1 from enrollments e where e.person_id = p.id) order by p.id desc limit 1""")
    r = client.post(f"/api/people/{p['id']}/erase", headers={"X-Acting-As": str(user("gtm"))})
    assert r.status_code == 200 and r.json()["ok"]
    with db.tx() as cur:
        assert db.val(cur, "select count(*) from people where id = %s", p["id"]) == 0
        assert db.val(cur, "select count(*) from replies where person_id = %s", p["id"]) == 0
        assert db.val(cur, "select exists (select 1 from suppressions where kind = 'email_hash' and "
                           "value = encode(sha256(convert_to(%s, 'UTF8')), 'hex'))", p["email"])
    assert client.post(f"/api/people/{p['id']}/erase", headers={"X-Acting-As": str(user("sdr"))}).status_code == 403


def test_opt_out_links_in_sent_emails_still_open(client):
    """The link is signed with a secret kept in the database, so it works from any process, not only the one
    that drafted the email."""
    import re

    from outbound import outreach as o
    with db.tx() as cur:
        body = db.val(cur, "select body from messages where body like '%%/u/%%' order by id limit 1")
    path = re.search(r"/u/\d+[-/][0-9a-f]+", body).group(0)
    o._unsub_secret = None  # a fresh process
    assert client.get(path).status_code == 200


PLAY = {"name": "Test play from the editor", "hypothesis": "Companies hiring billing staff feel the manual work.",
        "angle": "The roles they are hiring for and the work those people would do.", "personas": ["controller", "cfo"],
        "max_people": 2, "holdout_pct": 20, "urgent": False, "latency_hours": 48,
        "trigger": {"any_of": ["hiring_function"], "fit_tiers": ["A", "B"], "min_priority": 30, "within_days": 30},
        "sequence": [{"day": 0, "channel": "email", "job": "open", "by": "desk"},
                     {"day": 4, "channel": "call", "job": "call", "by": "sdr"}]}


def test_gtm_writes_a_play_and_only_another_manager_launches_it(client):
    gtm, mgr, sdr = (str(user(r)) for r in ("gtm", "manager", "sdr"))
    assert client.post("/api/plays", json=PLAY, headers={"X-Acting-As": sdr}).status_code == 403
    r = client.post("/api/plays", json=PLAY, headers={"X-Acting-As": gtm})
    assert r.status_code == 200
    pid = r.json()["id"]
    with db.tx() as cur:
        assert db.val(cur, "select status from plays where id = %s", pid) == "draft"
    edited = {**PLAY, "max_people": 3}
    assert client.put(f"/api/plays/{pid}", json=edited, headers={"X-Acting-As": gtm}).status_code == 200
    assert client.post(f"/api/plays/{pid}", json={"status": "live", "reason": "test"}, headers={"X-Acting-As": gtm}).status_code == 403
    assert client.post(f"/api/plays/{pid}", json={"status": "live", "reason": "test"}, headers={"X-Acting-As": mgr}).status_code == 200
    with db.tx() as cur:
        row = db.one(cur, "select status, max_people, version, launched_by from plays where id = %s", pid)
    assert row["status"] == "live" and row["max_people"] == 3 and row["version"] == 2 and row["launched_by"] == int(mgr)


def test_preview_checks_the_play_and_hides_cost_from_sdrs(client):
    sdr, mgr = str(user("sdr")), str(user("manager"))
    assert client.post("/api/play-preview", json={**PLAY, "trigger": {**PLAY["trigger"], "any_of": ["nonsense"]}},
                       headers={"X-Acting-As": mgr}).status_code == 422
    bad = {**PLAY, "sequence": [{"day": 0, "channel": "call", "job": "call", "by": "desk"}]}
    assert client.post("/api/play-preview", json=bad, headers={"X-Acting-As": mgr}).status_code == 422
    r = client.post("/api/play-preview", json=PLAY, headers={"X-Acting-As": mgr}).json()
    assert {"free_now", "per_month", "sample"} <= set(r["preview"]) and r["cost"]["per_account"]["credits"]["phone_finder"] == 2
    assert "cost" not in client.post("/api/play-preview", json=PLAY, headers={"X-Acting-As": sdr}).json()


def test_a_play_without_emails_runs_on_calls_and_linkedin(client):
    """No email step: people are chosen without needing an address, nothing waits for approval, and the steps
    become the SDR's tasks."""
    from outbound import outreach, plays
    gtm, mgr = str(user("gtm")), str(user("manager"))
    body = {**PLAY, "name": "Call and connect only",
            "sequence": [{"day": 0, "channel": "linkedin_connect", "job": "connect", "by": "sdr"},
                         {"day": 2, "channel": "call", "job": "call", "by": "sdr"}]}
    pid = client.post("/api/plays", json=body, headers={"X-Acting-As": gtm}).json()["id"]
    client.post(f"/api/plays/{pid}", json={"status": "live", "reason": "test"}, headers={"X-Acting-As": mgr})
    with db.tx() as cur:
        acct = db.val(cur, """select a.id from accounts a where a.fit_tier in ('A','B') and a.lifecycle = 'prospect'
                              and not exists (select 1 from account_plays x where x.account_id = a.id and x.state in
                                ('proposed','accepted','researching','approving','active','engaged','meeting'))
                              and not exists (select 1 from holds h where h.account_id = a.id and h.until > app_now())
                              and exists (select 1 from people p where p.account_id = a.id and p.linkedin_url is not null
                                and p.title ~* '(controller|accounting|cfo|finance)')
                              order by a.id limit 1""")
        sig = db.val(cur, "select id from signals where account_id = %s order by id desc limit 1", acct) or db.val(
            cur, """insert into signals (type_key, source, external_id, account_id, observed_at, strength, evidence, status)
                    values ('hiring_function', 'jobs_feed', 'test-noemail', %s, app_now(), 0.8,
                            '{"summary": "x", "url": "https://x"}', 'matched') returning id""", acct)
        # A reachable controller of its own, so the test does not depend on who the simulated world left free.
        db.run(cur, """insert into people (account_id, full_name, first_name, title, linkedin_url, phone, phone_status, source)
                       values (%s, 'Test Controller', 'Test', 'Corporate Controller', %s, '+1 555 0100', 'valid', 'test')""",
               acct, f"https://www.linkedin.com/in/test-controller-{acct}")
        play = db.one(cur, "select * from plays where id = %s", pid)
        score = {"priority": 60, "inputs": {"signals": []}}
        signal = db.one(cur, """select s.id, s.type_key, s.observed_at, s.strength, s.evidence, s.person_id, t.label,
                                t.because, t.weight from signals s join signal_types t on t.key = s.type_key where s.id = %s""", sig)
        ap = plays.propose(cur, acct, {**play, "holdout_pct": 0}, signal, score)
        owner = db.val(cur, "select owner_id from account_plays where id = %s", ap)
        plays.decide(cur, ap, accept=True, user_id=owner or int(gtm))
        outreach.research_job(cur, {"account_play_id": ap})
        state = db.val(cur, "select state from account_plays where id = %s", ap)
        emails = db.val(cur, """select count(*) from messages m join enrollments e on e.id = m.enrollment_id
                                where e.account_play_id = %s""", ap)
        active = db.val(cur, "select count(*) from enrollments where account_play_id = %s and state = 'active'", ap)
        db.run(cur, "rollback")  # leave the shared world as it was
    assert state == "active" and emails == 0 and active >= 1


def test_a_calendar_booking_and_its_cancellation(client):
    with db.tx() as cur:
        p = db.one(cur, "select id, email, account_id from people where email is not null and status = 'active' order by id desc limit 1")
    booked = {"event": "booked", "external_id": "cal-test-1", "invitee_email": p["email"],
              "starts_at": "2026-12-01T15:00:00+00:00", "inbound": True}
    raw, h = signed(booked)
    mid = client.post("/api/webhooks/meeting", content=raw, headers=h).json()["meeting_id"]
    raw, h = signed(booked)
    assert client.post("/api/webhooks/meeting", content=raw, headers=h).json()["meeting_id"] == mid  # once
    with db.tx() as cur:
        m = db.one(cur, "select source, status, person_id from meetings where id = %s", mid)
    assert (m["source"], m["status"], m["person_id"]) == ("inbound", "booked", p["id"])
    raw, h = signed({"event": "cancelled", "external_id": "cal-test-1", "invitee_email": p["email"]})
    client.post("/api/webhooks/meeting", content=raw, headers=h)
    with db.tx() as cur:
        assert db.val(cur, "select status from meetings where id = %s", mid) == "cancelled"
    assert client.get(f"/api/meetings/{mid}").status_code == 200
