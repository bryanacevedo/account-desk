"""Every test runs on real Postgres. Each test session gets its own database, dropped at the end."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from outbound import db

BASE = os.environ.get("TEST_DATABASE_URL", "postgres://postgres@127.0.0.1:54329/postgres")
START = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def _admin(url: str) -> str:
    return url.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture(scope="session")
def database():
    name = f"outbound_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'create database "{name}"')
    url = BASE.rsplit("/", 1)[0] + "/" + name
    db.configure(url, max_size=6)
    db.migrate(url)
    yield url
    db.close()
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture(scope="session")
def world(database):
    """A small simulated world, run forward 21 days. Shared by the flow tests, which only read it."""
    from outbound import monitors, outreach, pipeline, replies, scheduler, scoring, sending  # noqa: F401
    from outbound.sim import runner
    runner.setup(start=START, seed=3, n_accounts=140)
    totals = runner.run(21, seed=5, slow_last_days=0, idle_hours=0)
    return totals


@pytest.fixture(scope="session")
def built_demo(database):
    """The demo exactly as `python -m outbound demo` builds it, in a database of its own, shared by the tests that read a
    whole demo. Slow (several minutes). DEMO_DATABASE_URL names one already built to read instead; it is never changed."""
    import subprocess
    import sys
    from pathlib import Path
    reuse = os.environ.get("DEMO_DATABASE_URL")
    if reuse:
        yield reuse
        return
    name = f"outbound_demo_{uuid.uuid4().hex[:8]}"
    url = BASE.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'create database "{name}"')
    try:
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(root / "src")}
        subprocess.run([sys.executable, "-m", "outbound", "demo"], cwd=root, env=env, check=True, capture_output=True)
        yield url
    finally:
        with psycopg.connect(_admin(BASE), autocommit=True) as c:
            c.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture
def cur(database):
    """A transaction that is rolled back after the test, so unit tests leave nothing behind."""
    with db.pool().connection() as conn:
        tx = conn.transaction()
        tx.__enter__()
        with conn.cursor() as c:
            yield c
        tx.__exit__(psycopg.Rollback, psycopg.Rollback(), None)
