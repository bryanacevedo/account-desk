"""Accept answers at once and the queued work runs in a background worker (decision 98)."""
from __future__ import annotations

import os
import threading
import time

import pytest

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from outbound import db, jobs, plays  # noqa: E402


@pytest.fixture(scope="module")
def client(world):
    from outbound.api.app import app
    return TestClient(app)


def headers(role: str = "manager") -> dict:
    with db.tx() as cur:
        return {"X-Acting-As": str(db.val(cur, "select id from users where role = %s and active order by id limit 1", role))}


_used: set[int] = set()


def proposal() -> int:
    """A proposed play on an account of the shared world that has none open, committed so the API can see it."""
    with db.tx() as cur:
        pid = db.val(cur, "select id from plays where status = 'live' order by id limit 1")
        acct = db.val(cur, """select a.id from accounts a where a.fit_tier in ('A','B') and a.lifecycle = 'prospect'
                              and not exists (select 1 from account_plays x where x.account_id = a.id and x.state in
                                ('proposed','accepted','researching','approving','active','engaged','meeting'))
                              and not exists (select 1 from holds h where h.account_id = a.id and h.until > app_now())
                              and a.id <> all(%s) order by a.id limit 1""", list(_used) or [0])
        _used.add(acct)
        sig = db.val(cur, """insert into signals (type_key, source, external_id, account_id, observed_at, strength, evidence, status)
                             values ('hiring_function', 'jobs_feed', %s, %s, app_now(), 0.8, '{"summary": "x", "url": "https://x"}', 'matched')
                             returning id""", f"bg-{acct}-{time.time_ns()}", acct)
        db.run(cur, """insert into people (account_id, full_name, first_name, title, linkedin_url, phone, phone_status, source)
                       values (%s, 'Test Controller', 'Test', 'Corporate Controller', %s, '+1 555 0100', 'valid', 'test')""",
               acct, f"https://www.linkedin.com/in/bg-{acct}")
        play = db.one(cur, "select * from plays where id = %s", pid)
        signal = db.one(cur, """select s.id, s.type_key, s.observed_at, s.strength, s.evidence, s.person_id, t.label,
                                t.because, t.weight from signals s join signal_types t on t.key = s.type_key where s.id = %s""", sig)
        return plays.propose(cur, acct, {**play, "holdout_pct": 0}, signal, {"priority": 60, "inputs": {"signals": []}})


def accept(client, ap: int):
    return client.post(f"/api/account-plays/{ap}/decide", json={"accept": True}, headers=headers())


def request_jobs(ap: int) -> list[dict]:
    with db.tx() as cur:
        return db.all(cur, "select * from jobs where request_ref = %s order by id", f"account_play:{ap}")


@pytest.fixture(autouse=True)
def calm_queue(world):
    """Start each test with nothing ready in the request lane, and leave nothing behind."""
    jobs.run_ready(lane="request")
    yield
    jobs.run_ready(lane="request")


def test_accept_answers_at_once_and_runs_nothing(client):
    ap = proposal()
    started = time.perf_counter()
    r = accept(client, ap)
    elapsed = time.perf_counter() - started
    assert r.status_code == 200 and r.json()["queued"] is True
    assert elapsed < 2.0
    js = request_jobs(ap)
    assert [(j["kind"], j["status"], j["lane"]) for j in js] == [("research", "queued", "request")]
    with db.tx() as cur:
        assert db.val(cur, "select state from account_plays where id = %s", ap) == "accepted"
        assert db.val(cur, """select count(*) from messages m join enrollments e on e.id = m.enrollment_id
                              where e.account_play_id = %s""", ap) == 0
    # The account shows the request as queued.
    with db.tx() as cur:
        acct = db.val(cur, "select account_id from account_plays where id = %s", ap)
    work = client.get(f"/api/accounts/{acct}", headers=headers()).json()["work"]
    assert work["state"] == "queued" and work["active"] and work["queued"] == 1


def test_the_worker_drains_the_request_and_its_followers(client):
    from outbound.api import app as api
    ap = proposal()
    accept(client, ap)
    assert api.worker_pass() >= 1
    js = request_jobs(ap)
    assert js[0]["kind"] == "research" and js[0]["status"] == "done"
    assert all(j["lane"] == "request" for j in js)  # what the research queued belongs to the request too
    with db.tx() as cur:
        acct = db.val(cur, "select account_id from account_plays where id = %s", ap)
        assert db.val(cur, "select state from account_plays where id = %s", ap) in ("approving", "active")
    work = client.get(f"/api/accounts/{acct}", headers=headers()).json()["work"]
    assert work["done"] >= 1 and work["failed"] == 0 and not work["queued"] and not work["running"]


def test_the_simulated_clock_worker_leaves_the_simulations_own_jobs(client):
    from outbound.api import app as api
    with db.tx() as cur:
        jid = jobs.enqueue(cur, "bg_test_ok", {"n": 1})
    jobs.HANDLERS["bg_test_ok"] = lambda cur, payload: None
    try:
        api.worker_pass()
        with db.tx() as cur:
            assert db.val(cur, "select status from jobs where id = %s", jid) == "queued"
        jobs.run_ready()
        with db.tx() as cur:
            assert db.val(cur, "select status from jobs where id = %s", jid) == "done"
    finally:
        del jobs.HANDLERS["bg_test_ok"]


def test_dev_can_run_the_drain_before_answering(client, monkeypatch):
    import dataclasses

    from outbound.api import app as api
    monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, sync_drain=True))
    ap = proposal()
    assert accept(client, ap).status_code == 200
    assert request_jobs(ap)[0]["status"] == "done"


def test_two_workers_never_take_the_same_job(world):
    seen: list[int] = []
    lock = threading.Lock()

    def handler(cur, payload):
        with lock:
            seen.append(payload["i"])
        time.sleep(0.01)

    jobs.HANDLERS["bg_test_once"] = handler
    try:
        with db.tx() as cur:
            for i in range(24):
                jobs.enqueue(cur, "bg_test_once", {"i": i}, request_ref="test:double-claim")
        workers = [threading.Thread(target=jobs.run_ready, kwargs={"lane": "request"}) for _ in range(4)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        assert sorted(seen) == list(range(24))  # every job once, none twice
        with db.tx() as cur:
            assert db.val(cur, "select count(*) from jobs where request_ref = 'test:double-claim' and status = 'done'") == 24
    finally:
        del jobs.HANDLERS["bg_test_once"]


def test_a_failure_is_recorded_with_its_reason_and_shown(world):
    def boom(cur, payload):
        raise RuntimeError("the vendor said no")

    jobs.HANDLERS["bg_test_fail"] = boom
    try:
        with db.tx() as cur:
            jid = jobs.enqueue(cur, "bg_test_fail", {}, request_ref="test:failure", max_attempts=1)
        jobs.run_ready(lane="request")
        with db.tx() as cur:
            j = db.one(cur, "select status, last_error, finished_at from jobs where id = %s", jid)
            progress = jobs.request_progress(cur, "test:failure")
            assert db.val(cur, "select count(*) from alerts where dedup_key = %s", f"job_dead:{jid}") == 1
        assert j["status"] == "dead" and "the vendor said no" in j["last_error"] and j["finished_at"] is not None
        assert progress["state"] == "failed" and progress["failed"] == 1 and not progress["active"]
        assert "the vendor said no" in progress["reason"]
        with db.tx() as cur:  # the shared world must not keep a dead job (test_flow checks there is none)
            db.run(cur, "delete from alerts where dedup_key = %s", f"job_dead:{jid}")
            db.run(cur, "delete from jobs where id = %s", jid)
    finally:
        del jobs.HANDLERS["bg_test_fail"]


def test_a_failing_job_tries_again_and_says_why(world):
    jobs.HANDLERS["bg_test_flaky"] = lambda cur, payload: (_ for _ in ()).throw(RuntimeError("timeout"))
    try:
        with db.tx() as cur:
            jid = jobs.enqueue(cur, "bg_test_flaky", {}, request_ref="test:retry", max_attempts=3)
        jobs.run_ready(lane="request")
        with db.tx() as cur:
            j = db.one(cur, "select status, attempts, last_error from jobs where id = %s", jid)
            progress = jobs.request_progress(cur, "test:retry")
            db.run(cur, "update jobs set status = 'done' where id = %s", jid)  # leave the queue clear
        assert (j["status"], j["attempts"]) == ("queued", 1) and "timeout" in j["last_error"]
        assert progress["state"] == "queued" and progress["active"] and "timeout" in progress["reason"]
    finally:
        del jobs.HANDLERS["bg_test_flaky"]


def test_a_restart_resumes_what_the_last_process_left(world):
    done: list[int] = []
    jobs.HANDLERS["bg_test_resume"] = lambda cur, payload: done.append(payload["i"])
    try:
        with db.tx() as cur:
            dead = jobs.enqueue(cur, "bg_test_resume", {"i": 1}, request_ref="test:restart")
            alive = jobs.enqueue(cur, "bg_test_resume", {"i": 2}, request_ref="test:restart")
            other = jobs.enqueue(cur, "bg_test_resume", {"i": 3}, request_ref="test:restart")
            host = jobs.WORKER_HOST
            # one held by a process that is gone, one by a live process, one by another machine
            db.run(cur, "update jobs set status = 'running', attempts = 1, locked_at = now(), locked_by = %s where id = %s",
                   f"{host}:999999", dead)
            db.run(cur, "update jobs set status = 'running', attempts = 1, locked_at = now(), locked_by = %s where id = %s",
                   f"{host}:{os.getppid()}", alive)
            db.run(cur, "update jobs set status = 'running', attempts = 1, locked_at = now(), locked_by = %s where id = %s",
                   "another-machine:4242", other)
        with db.tx() as cur:
            assert jobs.reap_orphans(cur) == 1
        with db.tx() as cur:
            states = {r["id"]: r["status"] for r in db.all(cur, "select id, status from jobs where request_ref = 'test:restart'")}
        assert states == {dead: "queued", alive: "running", other: "running"}
        jobs.run_ready(lane="request")
        assert done == [1]
        with db.tx() as cur:
            assert db.val(cur, "select status from jobs where id = %s", dead) == "done"
            assert "reclaimed after a restart" in db.val(cur, "select last_error from jobs where id = %s", dead)
            db.run(cur, "update jobs set status = 'done' where request_ref = 'test:restart'")  # leave the queue clear
    finally:
        del jobs.HANDLERS["bg_test_resume"]


def test_a_job_the_worker_stopped_on_dies_after_its_last_try(world):
    jobs.HANDLERS["bg_test_never"] = lambda cur, payload: None
    try:
        with db.tx() as cur:
            jid = jobs.enqueue(cur, "bg_test_never", {}, request_ref="test:last-try", max_attempts=1)
            db.run(cur, "update jobs set status = 'running', attempts = 1, locked_at = now(), locked_by = %s where id = %s",
                   f"{jobs.WORKER_HOST}:999998", jid)
            assert jobs.reap_orphans(cur) == 1
            assert db.val(cur, "select status from jobs where id = %s", jid) == "dead"
            db.run(cur, "delete from jobs where id = %s", jid)  # no dead job may stay in the shared world
    finally:
        del jobs.HANDLERS["bg_test_never"]


def test_a_lock_from_another_container_with_the_same_host_name_is_left_alone(world, monkeypatch):
    """Two containers can share a host name (host networking) with their own process ids. A process id is checked only
    in its own namespace; a lock from another namespace waits for `reap`, so a job a live process runs is never run twice."""
    jobs.HANDLERS["bg_test_ns"] = lambda cur, payload: None
    monkeypatch.setattr(jobs, "WORKER_HOST", "box/4026531836")
    try:
        with db.tx() as cur:
            mine = jobs.enqueue(cur, "bg_test_ns", {}, request_ref="test:namespace")
            theirs = jobs.enqueue(cur, "bg_test_ns", {}, request_ref="test:namespace")
            prefix_only = jobs.enqueue(cur, "bg_test_ns", {}, request_ref="test:namespace")
            for jid, holder in ((mine, "box/4026531836:999997"), (theirs, "box/4026532999:999997"),
                                (prefix_only, "box:999997")):
                db.run(cur, "update jobs set status = 'running', attempts = 1, locked_at = now(), locked_by = %s where id = %s",
                       holder, jid)
            assert jobs.reap_orphans(cur) == 1
            states = {r["id"]: r["status"] for r in db.all(cur, "select id, status from jobs where request_ref = 'test:namespace'")}
            assert states == {mine: "queued", theirs: "running", prefix_only: "running"}
            db.run(cur, "delete from jobs where request_ref = 'test:namespace'")
    finally:
        del jobs.HANDLERS["bg_test_ns"]


def test_an_sdr_sees_that_work_failed_but_not_the_raw_error(client):
    """The raw error can carry a vendor's answer: like Health, only a manager or GTM reads it on the account."""
    def boom(cur, payload):
        raise RuntimeError("vendor answered 401 for https://vendor.example/find?key=secret")

    ap = proposal()
    with db.tx() as cur:
        acct = db.val(cur, "select account_id from account_plays where id = %s", ap)
    real = jobs.HANDLERS["research"]
    jobs.HANDLERS["research"] = boom
    try:
        assert accept(client, ap).status_code == 200
        with db.tx() as cur:
            db.run(cur, "update jobs set max_attempts = 1 where request_ref = %s", f"account_play:{ap}")
        jobs.run_ready(lane="request")
        as_sdr = client.get(f"/api/accounts/{acct}", headers=headers("sdr")).json()["work"]
        as_manager = client.get(f"/api/accounts/{acct}", headers=headers("manager")).json()["work"]
        assert as_sdr["state"] == as_manager["state"] == "failed"
        assert "secret" not in as_sdr["reason"] and "Health" in as_sdr["reason"]
        assert "secret" in as_manager["reason"]
    finally:
        jobs.HANDLERS["research"] = real
        with db.tx() as cur:  # no dead job or its alert may stay in the shared world
            ids = [r["id"] for r in db.all(cur, "select id from jobs where request_ref = %s", f"account_play:{ap}")]
            db.run(cur, "delete from alerts where dedup_key = any(%s)", [f"job_dead:{i}" for i in ids])
            db.run(cur, "delete from jobs where id = any(%s)", ids)


def test_the_worker_starts_once_and_stops(monkeypatch):
    import dataclasses

    from outbound.api import app as api
    monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, worker_inline=True))
    passes: list[int] = []
    monkeypatch.setattr(api, "worker_pass", lambda: passes.append(1) or 0)
    api.start_worker()
    first = api._worker
    api.start_worker()  # a second start in the same process does nothing
    assert api._worker is first and first.is_alive()
    api._wake_worker()
    api.stop_worker(timeout=10)
    assert not first.is_alive() and api._worker is None and passes
    monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, worker_inline=False))
    api.start_worker()  # NO_WORKER=1: no thread
    assert api._worker is None
