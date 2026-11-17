"""The replayed demo build must not depend on the zone Postgres runs in (decision 104)."""
import uuid

import psycopg
from conftest import BASE, PREFIX, _admin

from outbound import db
from outbound.__main__ import JOURNAL_TIMEZONE


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
