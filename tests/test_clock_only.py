"""Moving the simulated clock without the simulated reps (decision 97): only the time changes."""
from __future__ import annotations

import os
from datetime import timedelta

import pytest

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from outbound import db  # noqa: E402

TABLES = ("messages", "tasks", "signals", "replies", "enrollments", "account_plays", "meetings", "jobs", "touches", "audit_log")


@pytest.fixture(scope="module")
def client(world):
    from outbound.api.app import app
    return TestClient(app)


def as_(role: str) -> dict:
    with db.tx() as cur:
        return {"X-Acting-As": str(db.val(cur, "select id from users where role = %s and active order by id limit 1", role))}


def snapshot() -> dict:
    with db.tx() as cur:
        out = {t: db.val(cur, f"select count(*) from {t}") for t in TABLES if t != "audit_log"}
        out["now"] = db.val(cur, "select app_now()")
        return out


@pytest.fixture
def keep_clock(world):
    """The clock is shared by the session's tests: put it back after."""
    with db.tx() as cur:
        before = db.one(cur, "select enabled, at from sim_clock")
    yield before
    with db.tx() as cur:
        db.run(cur, "update sim_clock set enabled = %s, at = %s", before["enabled"], before["at"])


def test_a_manager_moves_the_clock_and_nothing_else_happens(client, keep_clock):
    before = snapshot()
    with db.tx() as cur:
        audits = db.val(cur, "select count(*) from audit_log where action = 'clock_advanced'")
    r = client.post("/api/sim/clock", json={"days": 3}, headers=as_("manager"))
    assert r.status_code == 200, r.text
    after = snapshot()
    assert after["now"] == before["now"] + timedelta(days=3)
    # No simulated rep acted, no buyer wrote, no job ran, no schedule ticked: every count is where it was.
    assert {k: v for k, v in after.items() if k != "now"} == {k: v for k, v in before.items() if k != "now"}
    with db.tx() as cur:
        row = db.one(cur, "select actor_id, detail from audit_log where action = 'clock_advanced' order by id desc limit 1")
        assert db.val(cur, "select count(*) from audit_log where action = 'clock_advanced'") == audits + 1
    assert row["detail"]["days"] == 3 and row["actor_id"] is not None
    assert client.get("/api/me", headers=as_("manager")).json()["now"].startswith(after["now"].isoformat()[:16])


def test_gtm_may_too_and_a_rep_may_not(client, keep_clock):
    before = snapshot()["now"]
    assert client.post("/api/sim/clock", json={"days": 1}, headers=as_("sdr")).status_code == 403
    assert snapshot()["now"] == before
    assert client.post("/api/sim/clock", json={"days": 1}, headers=as_("gtm")).status_code == 200
    assert snapshot()["now"] == before + timedelta(days=1)


@pytest.mark.parametrize("days", [0, -1, 31, 1000])
def test_backwards_zero_and_too_far_are_refused(client, keep_clock, days):
    before = snapshot()["now"]
    assert client.post("/api/sim/clock", json={"days": days}, headers=as_("manager")).status_code == 422
    assert snapshot()["now"] == before


def test_thirty_days_is_the_most_in_one_move(client, keep_clock):
    before = snapshot()["now"]
    assert client.post("/api/sim/clock", json={"days": 30}, headers=as_("manager")).status_code == 200
    assert snapshot()["now"] == before + timedelta(days=30)


def test_refused_when_the_desk_is_on_the_real_clock(client, keep_clock):
    with db.tx() as cur:
        db.run(cur, "update sim_clock set enabled = false")
    r = client.post("/api/sim/clock", json={"days": 1}, headers=as_("manager"))
    assert r.status_code == 409 and "simulated" in r.json()["detail"]
    with db.tx() as cur:
        assert db.val(cur, "select at from sim_clock") == keep_clock["at"]  # untouched


def test_refused_on_the_public_demo(client, keep_clock, monkeypatch):
    import dataclasses

    from outbound.api import app as api
    monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, public_demo=True))
    before = snapshot()["now"]
    assert client.post("/api/sim/clock", json={"days": 1}, headers=as_("manager")).status_code == 403
    assert snapshot()["now"] == before


def test_what_is_due_reads_the_new_time(client, keep_clock):
    """Nothing is rewritten: a task due in 2 days is overdue after the clock moves 3 days, by its own due date."""
    with db.tx() as cur:
        now = db.val(cur, "select app_now()")
        owner = db.val(cur, "select id from users where role = 'sdr' and active order by id limit 1")
        tid = db.val(cur, """insert into tasks (kind, title, due_at, owner_id) values ('call', 'Clock test', app_now() + interval '2 days', %s)
                             returning id""", owner)
        assert not db.val(cur, "select due_at <= app_now() from tasks where id = %s", tid)
    try:
        client.post("/api/sim/clock", json={"days": 3}, headers=as_("manager"))
        with db.tx() as cur:
            assert db.val(cur, "select due_at <= app_now() from tasks where id = %s", tid)
            assert db.val(cur, "select status from tasks where id = %s", tid) == "open"
        assert now < snapshot()["now"]
    finally:
        with db.tx() as cur:
            db.run(cur, "delete from tasks where id = %s", tid)
