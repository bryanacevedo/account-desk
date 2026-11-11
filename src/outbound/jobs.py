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
            try:
                if fn is None:
                    raise RuntimeError(f"no handler for job kind {job['kind']}")
                with conn.transaction():
                    with conn.cursor() as cur:
                        fn(cur, job["payload"])
                        db.run(cur, "update jobs set status = 'done', finished_at = app_now() where id = %s", job["id"])
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


def run_forever(poll_seconds: float = 2.0) -> None:  # pragma: no cover - the live worker loop
    while True:
        try:
            if run_ready() == 0:
                time.sleep(poll_seconds)
        except Exception:
            log.exception("worker loop error")
            time.sleep(poll_seconds)
