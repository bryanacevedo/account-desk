"""A job queue in Postgres. Claimed with FOR UPDATE SKIP LOCKED, so any number of workers can drain it safely.

A handler gets (cur, payload) and runs inside the job's own transaction: its writes and the job's 'done'
commit together, or roll back together and the job is retried with backoff.
"""
from __future__ import annotations

import logging
import os
import socket
import time
import traceback
from datetime import timedelta
from typing import Any, Callable

from . import db
from .db import J

log = logging.getLogger("outbound.jobs")
Handler = Callable[[Any, dict], None]
HANDLERS: dict[str, Handler] = {}
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def handler(kind: str) -> Callable[[Handler], Handler]:
    def wrap(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn
    return wrap


def enqueue(cur, kind: str, payload: dict | None = None, *, delay: timedelta | None = None,
            run_at=None, dedupe_key: str | None = None, max_attempts: int = 5) -> int | None:
    """Queue a job. With a dedupe_key, a second enqueue while the first is queued or running is a no-op."""
    row = db.one(cur, """
        insert into jobs (kind, payload, run_at, dedupe_key, max_attempts)
        values (%s, %s, coalesce(%s, app_now() + coalesce(%s, interval '0')), %s, %s)
        on conflict (dedupe_key) where dedupe_key is not null and status in ('queued', 'running') do nothing
        returning id""", kind, J(payload or {}), run_at, delay, dedupe_key, max_attempts)
    return row["id"] if row else None


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(3600, 30 * 2 ** max(0, attempts - 1)))


def adapters_missing() -> type[Exception]:
    from .adapters import VendorMissing
    return VendorMissing


def _play_of(cur, payload: dict) -> int | None:
    if payload.get("account_play_id"):
        return db.val(cur, "select play_id from account_plays where id = %s", payload["account_play_id"])
    if payload.get("enrollment_id"):
        return db.val(cur, """select ap.play_id from enrollments e join account_plays ap on ap.id = e.account_play_id
                              where e.id = %s""", payload["enrollment_id"])
    if payload.get("person_id"):
        return db.val(cur, """select ap.play_id from enrollments e join account_plays ap on ap.id = e.account_play_id
                              where e.person_id = %s and e.state in ('pending','active','paused')
                              order by e.created_at desc limit 1""", payload["person_id"])
    if payload.get("reply_id"):
        return db.val(cur, """select ap.play_id from replies r join account_plays ap on ap.account_id = r.account_id
                              where r.id = %s and ap.state in ('approving','active','engaged','meeting')
                              order by ap.proposed_at desc limit 1""", payload["reply_id"])
    return None


def run_ready(limit: int = 200) -> int:
    """Run jobs whose time has come, one transaction each. Returns how many ran."""
    ran = 0
    while ran < limit:
        with db.pool().connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    job = db.one(cur, """
                        select * from jobs where status = 'queued' and run_at <= app_now()
                        order by run_at, id limit 1 for update skip locked""")
                    if job is None:
                        return ran
                    db.run(cur, "update jobs set status = 'running', locked_at = now(), locked_by = %s, "
                                "attempts = attempts + 1 where id = %s", WORKER_ID, job["id"])
            fn = HANDLERS.get(job["kind"])
            error = None
            from . import spend
            try:
                if fn is None:
                    raise RuntimeError(f"no handler for job kind {job['kind']}")
                with conn.transaction():
                    with conn.cursor() as cur:
                        # Every charge this job makes is tagged with the play it works for, so the play's cap holds.
                        with spend.for_play(_play_of(cur, job["payload"])):
                            fn(cur, job["payload"])
                        db.run(cur, "update jobs set status = 'done', finished_at = app_now() where id = %s", job["id"])
            except (spend.OverBudget, adapters_missing()) as exc:
                # Out of budget is "not now", never a failure: the job waits a day without using up a retry.
                with conn.transaction():
                    with conn.cursor() as cur:
                        db.run(cur, "update jobs set status = 'queued', attempts = attempts - 1, last_error = %s, "
                                    "run_at = app_now() + interval '1 day' where id = %s", f"Waiting: {exc}", job["id"])
                        from . import alerts
                        month = db.val(cur, "select to_char(app_now(), 'YYYY-MM')")
                        alerts.raise_alert(cur, kind="budget_wait", severity="warn", channel="#outbound-ops",
                                           title=f"Work is waiting: {exc}",
                                           body="It runs again tomorrow, or as soon as the cap is raised or the vendor is set up.",
                                           dedup_key=f"budget_wait:{exc}:{month}")
                ran += 1
                continue
            except Exception as exc:  # the job's own writes rolled back; record the failure
                error = f"{type(exc).__name__}: {exc}"
                log.warning("job %s %s failed: %s", job["id"], job["kind"], error)
                log.debug(traceback.format_exc())
            if error is not None:
                with conn.transaction():
                    with conn.cursor() as cur:
                        attempts = job["attempts"] + 1
                        if attempts >= job["max_attempts"]:
                            db.run(cur, "update jobs set status = 'dead', last_error = %s, finished_at = app_now() "
                                        "where id = %s", error[:2000], job["id"])
                            from . import alerts
                            alerts.raise_alert(cur, kind="job_dead", severity="warn", channel="#outbound-ops",
                                               title=f"A {job['kind']} job stopped after {attempts} tries",
                                               body=error[:500], object_kind="job", object_id=job["id"],
                                               dedup_key=f"job_dead:{job['id']}")
                        else:
                            db.run(cur, "update jobs set status = 'queued', last_error = %s, "
                                        "run_at = app_now() + %s where id = %s", error[:2000], _backoff(attempts), job["id"])
        ran += 1
    return ran


def reap(cur, stale_minutes: int = 10) -> int:
    """Jobs a dead worker left in 'running' go back in line (or die after their last try). Uses the real clock:
    a lock is held in real time even when the demo's clock is simulated."""
    n = db.run(cur, """update jobs set status = case when attempts >= max_attempts then 'dead' else 'queued' end,
                       last_error = coalesce(last_error, '') || ' [reclaimed after the worker stopped]',
                       locked_by = null, run_at = app_now()
                       where status = 'running' and locked_at < now() - (%s || ' minutes')::interval""", stale_minutes)
    return n


def run_forever(poll_seconds: float = 2.0) -> None:  # pragma: no cover - the live worker loop
    while True:
        try:
            if run_ready() == 0:
                time.sleep(poll_seconds)
        except Exception:
            log.exception("worker loop error")
            time.sleep(poll_seconds)
