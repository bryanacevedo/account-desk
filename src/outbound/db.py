"""Postgres access: one pool, plain SQL, rows as dicts. Migrations are numbered .sql files applied once each."""
from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg.types.numeric import FloatLoader
from psycopg_pool import ConnectionPool

from .config import CONFIG

# Numeric columns come back as float: scores, rates and shares are measurements, not money (money is integer cents).
psycopg.adapters.register_loader("numeric", FloatLoader)

log = logging.getLogger("outbound.db")
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
_pool: ConnectionPool | None = None
_url: str | None = None


def configure(url: str | None = None, *, min_size: int = 1, max_size: int = 10) -> None:
    """(Re)point the pool. Tests call this with their own database."""
    global _pool, _url
    if _pool is not None:
        _pool.close()
    _url = url or CONFIG.database_url
    _pool = ConnectionPool(_url, min_size=min_size, max_size=max_size, open=True,
                           kwargs={"row_factory": dict_row, "autocommit": False})


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def pool() -> ConnectionPool:
    if _pool is None:
        configure()
    assert _pool is not None
    return _pool


@contextlib.contextmanager
def tx() -> Iterator[psycopg.Cursor]:
    """One transaction. Commits on success, rolls back on any exception."""
    with pool().connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                yield cur


def all(cur: psycopg.Cursor, sql: str, *args: Any) -> list[dict]:
    cur.execute(sql, args or None)
    return cur.fetchall() if cur.description else []


def one(cur: psycopg.Cursor, sql: str, *args: Any) -> dict | None:
    cur.execute(sql, args or None)
    return cur.fetchone() if cur.description else None


def val(cur: psycopg.Cursor, sql: str, *args: Any) -> Any:
    row = one(cur, sql, *args)
    return None if row is None else next(iter(row.values()))


def run(cur: psycopg.Cursor, sql: str, *args: Any) -> int:
    cur.execute(sql, args or None)
    return cur.rowcount


def read(sql: str, *args: Any) -> list[dict]:
    with tx() as cur:
        return all(cur, sql, *args)


def read1(sql: str, *args: Any) -> dict | None:
    with tx() as cur:
        return one(cur, sql, *args)


def migrate(url: str | None = None) -> list[str]:
    """Apply every migration not yet applied, in order, each in its own transaction."""
    applied: list[str] = []
    with psycopg.connect(url or _url or CONFIG.database_url, autocommit=True) as conn:
        # One migrator at a time, so two app instances starting together never apply the same file twice.
        conn.execute("select pg_advisory_lock(7342001)")
        conn.execute("create table if not exists schema_migrations (name text primary key, at timestamptz default now())")
        done = {r[0] for r in conn.execute("select name from schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("insert into schema_migrations (name) values (%s)", (path.name,))
            applied.append(path.name)
            log.info("migrated %s", path.name)
    return applied


J = Jsonb  # wrap dicts and lists going into jsonb columns
