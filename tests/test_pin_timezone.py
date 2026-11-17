"""The replayed demo build must not depend on the zone Postgres runs in (decision 104)."""
import dataclasses
import uuid

import psycopg
import pytest
from conftest import BASE, PREFIX, _admin

from outbound import db
from outbound.__main__ import JOURNAL_TIMEZONE
from outbound.config import CONFIG


def test_pin_timezone_sets_the_zone_for_every_new_connection():
    name = f"{PREFIX}tz_{uuid.uuid4().hex[:8]}"
    url = BASE.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'create database "{name}"')
        c.execute(f'alter database "{name}" set timezone = \'UTC\'')
    before = db._url
    try:
        db.configure(url, max_size=2)
        assert db.read1("show timezone")["TimeZone"] == "UTC"
        db.pin_timezone(JOURNAL_TIMEZONE)
        assert db.read1("show timezone")["TimeZone"] == JOURNAL_TIMEZONE
        # the day boundary is the pinned zone's: 02:00 UTC is still the evening before in Santo Domingo
        assert str(db.read1("select ('2026-08-14 02:00+00'::timestamptz)::date as d")["d"]) == "2026-08-13"
        with psycopg.connect(url) as c:  # a later process
            assert c.execute("show timezone").fetchone()[0] == JOURNAL_TIMEZONE
    finally:
        db.close()
        if before:
            db.configure(before, max_size=6)
        with psycopg.connect(_admin(BASE), autocommit=True) as c:
            c.execute(f'drop database if exists "{name}" with (force)')


def _scratch_db(zone="UTC"):
    name = f"{PREFIX}tz_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'create database "{name}"')
        c.execute(f'alter database "{name}" set timezone = \'{zone}\'')
    return name, BASE.rsplit("/", 1)[0] + "/" + name


def _drop(name):
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'drop database if exists "{name}" with (force)')


def test_pin_timezone_unknown_zone_fails_loudly_and_changes_nothing():
    name, url = _scratch_db()
    before = db._url
    try:
        db.configure(url)
        with pytest.raises(psycopg.Error):
            db.pin_timezone("America/Santo_Domingoo")
        assert db.read1("show timezone")["TimeZone"] == "UTC"
    finally:
        db.close()
        if before:
            db.configure(before, max_size=6)
        _drop(name)


def test_pin_timezone_keeps_the_pool_size_and_refuses_live_mode(monkeypatch):
    name, url = _scratch_db()
    before = db._url
    try:
        db.configure(url, min_size=1, max_size=2)
        db.pin_timezone(JOURNAL_TIMEZONE)
        assert (db.pool().min_size, db.pool().max_size) == (1, 2)
        monkeypatch.setattr(db, "CONFIG", dataclasses.replace(CONFIG, mode="live"))
        with pytest.raises(RuntimeError):
            db.pin_timezone("UTC")
        monkeypatch.undo()
        assert db.read1("show timezone")["TimeZone"] == JOURNAL_TIMEZONE
    finally:
        db.close()
        if before:
            db.configure(before, max_size=6)
        _drop(name)


class _Pinned(Exception):
    pass


def test_demo_pins_the_zone_before_a_replay(monkeypatch):
    from datetime import datetime, timezone

    from outbound import __main__ as cli
    from outbound import integration
    from outbound.sim import world_load
    seen = []

    def fake_pin(name):
        seen.append(name)
        raise _Pinned

    monkeypatch.setattr(integration, "world_mode", lambda: "world")
    monkeypatch.setattr(world_load, "window", lambda: (datetime(2026, 8, 13, tzinfo=timezone.utc),
                                                       datetime(2026, 8, 14, tzinfo=timezone.utc)))
    monkeypatch.setattr(cli, "demo_crm", lambda *a, **k: object())
    monkeypatch.setattr(db, "pin_timezone", fake_pin)
    with pytest.raises(_Pinned):
        cli.main(["outbound", "demo", "1"])
    assert seen == [JOURNAL_TIMEZONE]


def test_recorded_crm_pins_the_zone(monkeypatch, tmp_path):
    from outbound.adapters import choose_crm
    journal = tmp_path / "journal.jsonl"
    journal.write_text("")
    seen = []
    monkeypatch.setenv("CRM", "recorded")
    monkeypatch.setenv("JOURNAL_PATH", str(journal))
    monkeypatch.setattr(db, "pin_timezone", seen.append)
    choose_crm(None)
    assert seen == [JOURNAL_TIMEZONE]
