"""Standing up a real desk on an empty database: init from the example file, then CSV imports that report what they
refuse. Runs on its own database, since init refuses a desk that already has users."""
from __future__ import annotations

import json
import pathlib
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from outbound import db, setup_desk

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def empty(database):
    admin = database.rsplit("/", 1)[0] + "/postgres"
    name = f"outbound_setup_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'create database "{name}"')
    url = database.rsplit("/", 1)[0] + "/" + name
    db.migrate(url)
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            yield cur
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'drop database if exists "{name}" with (force)')


def cfg():
    return setup_desk.DeskConfig.model_validate_json((ROOT / "examples" / "desk.example.json").read_text())


def test_init_builds_a_desk_that_cannot_send_until_dns_is_checked(empty):
    out = setup_desk.init(empty, cfg())
    assert out == {"users": 3, "mailboxes": 1, "draft_plays": out["draft_plays"]} and out["draft_plays"] > 0
    assert db.val(empty, "select count(*) from plays where status <> 'draft'") == 0
    assert db.val(empty, "select bool_and(not spf and not dkim) from sending_domains")
    assert db.val(empty, "select lia_ref from plays limit 1") == "LIA-YOUR-REF"
    assert db.val(empty, "select enabled from signal_sources where key = 'web_visits'") is False  # not in the file
    with pytest.raises(ValueError, match="only runs once"):
        setup_desk.init(empty, cfg())


def test_a_desk_needs_a_manager():
    raw = json.loads((ROOT / "examples" / "desk.example.json").read_text())
    raw["users"] = [u for u in raw["users"] if u["role"] != "manager"]
    with pytest.raises(ValueError, match="manager"):
        setup_desk.DeskConfig.model_validate(raw)


def test_imports_link_parents_and_refuse_bad_rows(empty):
    setup_desk.init(empty, cfg())
    a = setup_desk.import_accounts(empty, (ROOT / "examples" / "accounts.example.csv").read_text()
                                   + "No Domain Co,,Software,10,US,,,prospect,,,\nBad Life,bad.example,,,US,,,friend,,,\n")
    assert a["imported"] == 2 and [r["row"] for r in a["refused"]] == [4, 5]
    assert db.val(empty, """select p.primary_domain from accounts c join accounts p on p.id = c.parent_id
                            where c.primary_domain = 'exampleanalytics-eu.example'""") == "exampleanalytics.example"
    again = setup_desk.import_accounts(empty, (ROOT / "examples" / "accounts.example.csv").read_text())
    assert again["imported"] == 2 and db.val(empty, "select count(*) from accounts") == 2  # updated, not duplicated
    p = setup_desk.import_people(empty, (ROOT / "examples" / "people.example.csv").read_text()
                                 + "Nobody Here,unknown.example,CFO,,,,,\n")
    assert p["imported"] == 1 and p["refused"][0]["row"] == 3
    assert db.val(empty, "select email_status from people where full_name = 'Sam Rivera'") == "unknown"


def test_a_reimport_without_lifecycle_never_unmakes_a_customer(empty):
    setup_desk.init(empty, cfg())
    setup_desk.import_accounts(empty, "name,domain,lifecycle\nBig Customer,bigcustomer.example,customer\n")
    setup_desk.import_accounts(empty, "name,domain,industry\nBig Customer,bigcustomer.example,Software\n")
    assert db.val(empty, "select lifecycle from accounts where primary_domain = 'bigcustomer.example'") == "customer"


def test_imported_accounts_can_reach_a_proposable_tier(empty):
    from outbound import scoring
    setup_desk.init(empty, cfg())
    setup_desk.import_accounts(empty, (ROOT / "examples" / "accounts.example.csv").read_text())
    a = db.one(empty, "select * from accounts where primary_domain = 'exampleanalytics.example'")
    rules = db.val(empty, "select rules from icp_versions order by id desc limit 1")
    assert a["region"] == "North America" and scoring.fit(rules, a)["tier"] in ("A", "B")

