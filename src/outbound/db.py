"""Postgres access: one pool, plain SQL, rows as dicts. Migrations are numbered .sql files applied once each."""
from __future__ import annotations

import contextlib
import logging
import secrets
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
_demo_key: str | None = None  # the demo-only key read from (or written to) settings, kept per database


def _erasure_key_for(conn: psycopg.Connection) -> str | None:
    """This install's erasure key. ERASURE_KEY from the environment wins. Without it, in demo mode only, a random key
    is made once and kept in settings (key 'erasure_key_demo'): it protects nothing a demo has and lets the demo's
    erasure tests run. Live mode never reaches the fallback (config.validate refuses to start without ERASURE_KEY).
    Before the migrations have run there is no settings table, and no key yet."""
    global _demo_key
    if CONFIG.erasure_key():
        return CONFIG.erasure_key()
    if CONFIG.mode == "live":
        return None
    if _demo_key:
        return _demo_key
    if not conn.execute("select to_regclass('settings') is not null as there").fetchone()["there"]:
        return None
    conn.execute("""insert into settings (key, value) values ('erasure_key_demo', to_jsonb(%s::text))
                    on conflict (key) do nothing""", (secrets.token_hex(32),))
    row = conn.execute("select value #>> '{}' as k from settings where key = 'erasure_key_demo'").fetchone()
    conn.commit()
    _demo_key = row["k"]
    return _demo_key


def erasure_key() -> str | None:
    """The key the keyed erasure hashes use, as this process holds it (None before the first migration in demo)."""
    if CONFIG.erasure_key() or _demo_key:
        return CONFIG.erasure_key() or _demo_key
    with pool().connection() as conn:
        return _erasure_key_for(conn)


def _set_session_key(conn: psycopg.Connection) -> None:
    """Pool configure callback: every pooled connection carries the key as the session setting the database's send
    guard reads (outbound.erasure_key). Session level, so it survives the transaction that follows."""
    key = _erasure_key_for(conn)
    if key:
        conn.execute("select set_config('outbound.erasure_key', %s, false)", (key,))
    conn.commit()


def configure(url: str | None = None, *, min_size: int = 1, max_size: int = 10) -> None:
    """(Re)point the pool. Tests call this with their own database."""
    global _pool, _url, _demo_key
    if _pool is not None:
        _pool.close()
    _url = url or CONFIG.database_url
    _demo_key = None
    _pool = ConnectionPool(_url, min_size=min_size, max_size=max_size, open=True, configure=_set_session_key,
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
    if applied and _pool is not None and (url or _url) == _url:
        _pool.drain()  # connections opened before the schema existed carry no erasure key; open new ones
    return applied


J = Jsonb  # wrap dicts and lists going into jsonb columns
