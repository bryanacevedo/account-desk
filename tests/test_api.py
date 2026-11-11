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
    path = re.search(r"/u/\d+/[0-9a-f]+", body).group(0)
    o._unsub_secret = None  # a fresh process
    assert client.get(path).status_code == 200
