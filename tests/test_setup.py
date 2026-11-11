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



def test_the_team_changes_without_losing_work_or_its_last_manager(empty):
    from outbound import admin
    setup_desk.init(empty, cfg())
    ids = {r["email"]: r["id"] for r in db.all(empty, "select id, email from users")}
    mgr, sdr = ids["avery@yourcompany.example"], ids["riley@yourcompany.example"]
    with pytest.raises(admin.AdminError, match="at least one manager"):
        admin.change_user(empty, mgr, role="sdr", by=mgr)
    new = admin.add_user(empty, name="Sky Doe", email="Sky@YourCompany.example", role="sdr", timezone="UTC", slack_id=None, by=mgr)
    with pytest.raises(admin.AdminError, match="already on the desk"):
        admin.add_user(empty, name="Sky Again", email="sky@yourcompany.example", role="sdr", timezone="UTC", slack_id=None, by=mgr)
    setup_desk.import_accounts(empty, "name,domain,owner_email\nOwned Co,ownedco.example,riley@yourcompany.example\n")
    with pytest.raises(admin.AdminError, match="Name an active SDR"):
        admin.deactivate(empty, sdr, successor=None, by=mgr)
    moved = admin.deactivate(empty, sdr, successor=new, by=mgr)
    assert moved["accounts"] == 1 and moved["mailboxes"] == 1
    assert db.val(empty, "select owner_id from accounts where primary_domain = 'ownedco.example'") == new
    assert db.val(empty, "select active from users where id = %s", sdr) is False
    assert db.val(empty, "select status from mailboxes where user_id = %s", sdr) == "retired"


def test_sending_setup_keeps_its_limits(empty):
    from datetime import date

    from outbound import admin
    setup_desk.init(empty, cfg())
    mgr = db.val(empty, "select id from users where role = 'manager'")
    sdr = db.val(empty, "select id from users where role = 'sdr'")
    d = admin.add_domain(empty, domain="https://Send.Example.com/", registered=date(2026, 1, 1), dkim_selector=None, by=mgr)
    assert d == "send.example.com" and db.val(empty, "select spf or dkim from sending_domains where domain = %s", d) is False
    for n in range(3):
        admin.add_mailbox(empty, address=f"a{n}@send.example.com", user_id=sdr, provider="google", warmup_started=date(2026, 2, 1), by=mgr)
    with pytest.raises(admin.AdminError, match="at most three"):
        admin.add_mailbox(empty, address="a3@send.example.com", user_id=sdr, provider="google", warmup_started=date(2026, 2, 1), by=mgr)
    with pytest.raises(admin.AdminError, match="sending domain first"):
        admin.add_mailbox(empty, address="x@unknown.example", user_id=sdr, provider="google", warmup_started=date(2026, 2, 1), by=mgr)
    mid = db.val(empty, "select id from mailboxes where address = 'a0@send.example.com'")
    with pytest.raises(admin.AdminError, match="Say why"):
        admin.set_mailbox(empty, mid, status="paused", reason=None, by=mgr)
    admin.set_mailbox(empty, mid, status="retired", reason="domain burned", by=mgr)
    with pytest.raises(admin.AdminError, match="stays retired"):
        admin.set_mailbox(empty, mid, status="active", reason=None, by=mgr)
