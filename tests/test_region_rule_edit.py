# ruff: noqa: F811  (fixtures shared from test_guarantees are named as parameters)
"""Country email rules you can edit (bl_130, decision 85): the starting rows live in migration 0035, every change has a
history row, the endpoint holds the roles, the reason and the typed name, and the guards read the edited rule next time."""
from __future__ import annotations

import dataclasses
import os

import psycopg
import pytest
from conftest import ensure_rule
from test_guarantees import refused, scene, send  # noqa: F401  the shared scene fixture

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from outbound import db, gate, region_rules, views  # noqa: E402
from outbound.seed import catalog  # noqa: E402

WHY = "Counsel confirmed in writing"


@pytest.fixture(scope="module")
def client(database):
    from outbound.api.app import app
    return TestClient(app)


@pytest.fixture
def mgr(database):
    with db.tx() as cur:
        uid = db.val(cur, "insert into users (name, email, role) values ('Rule Manager', %s, 'manager') returning id",
                     f"rm{os.urandom(3).hex()}@x.example")
    yield {"X-Acting-As": str(uid)}
    with db.tx() as cur:
        db.run(cur, "delete from region_rule_changes where changed_by = %s", uid)
        db.run(cur, "delete from audit_log where actor_id = %s", uid)
        db.run(cur, "delete from users where id = %s", uid)


def _sdr():
    with db.tx() as cur:
        return {"X-Acting-As": str(db.val(cur, "select id from users where role = 'sdr' and active order by id limit 1")
                                   or db.val(cur, "insert into users (name, email, role) values ('Rule Sdr', 'rs@x.example', 'sdr') returning id"))}


@pytest.fixture
def restore(database):
    """Endpoint tests commit; put the rules back afterwards (the history rows go with them)."""
    with db.tx() as cur:
        before = db.all(cur, "select country, rule, individual_consent from region_rules")
    yield
    with db.tx() as cur:
        db.run(cur, "set local session_replication_role = replica")
        for r in before:
            db.run(cur, "update region_rules set rule = %s, individual_consent = %s where country = %s",
                   r["rule"], r["individual_consent"], r["country"])
        db.run(cur, "delete from region_rule_changes where changed_by is null or reason = %s", WHY)


def test_the_starting_rows_are_the_catalog_and_the_database_agrees(cur):
    rows = {r["country"]: r for r in db.all(cur, "select * from region_rules")}
    for country, rule in catalog.REGION_RULES:
        r = rows[country]
        call_rule, register = catalog.CALL_RULES.get(country, ("blocked", None))
        assert (r["rule"], r["call_rule"], r["dnc_register"], r["individual_consent"], r["note"]) == (
            rule, call_rule, register, country in catalog.INDIVIDUAL_CONSENT,
            catalog.REGION_NOTES.get(country, "Counsel to confirm."))
    for c in ("IT", "CH", "SE", "DK", "BE", "AT", "NO"):
        assert rows[c]["rule"] == "consent_required"
    assert rows["MX"]["rule"] == "allowed"
    assert {c for c, r in rows.items() if r["individual_consent"]} == {"GB", "FI", "PT"}


def test_a_change_writes_who_from_to_and_why(cur, scene):
    region_rules.change(cur, "IT", "blocked", False, WHY, scene["user"])
    h = db.one(cur, "select * from region_rule_changes where country = 'IT' order by id desc limit 1")
    assert (h["changed_by"], h["from_rule"], h["to_rule"], h["reason"]) == (scene["user"], "consent_required", "blocked", WHY)
    assert db.val(cur, "select rule from region_rules where country = 'IT'") == "blocked"
    assert views.settings(cur)["region_changes"][0]["country"] == "IT"


def test_a_raw_update_without_a_history_row_is_refused(cur):
    with pytest.raises(psycopg.errors.RaiseException, match="recorded reason"):
        with cur.connection.transaction():
            db.run(cur, "update region_rules set rule = 'allowed' where country = 'IT'")
    with pytest.raises(psycopg.errors.RaiseException, match="recorded reason"):
        with cur.connection.transaction():
            db.run(cur, "update region_rules set individual_consent = true where country = 'US'")


def test_a_raw_insert_or_delete_is_refused(cur):
    with pytest.raises(psycopg.errors.RaiseException, match="recorded reason"):
        with cur.connection.transaction():
            db.run(cur, "insert into region_rules (country, rule) values ('QQ', 'allowed')")
    with pytest.raises(psycopg.errors.RaiseException, match="never deleted"):
        with cur.connection.transaction():
            db.run(cur, "delete from region_rules where country = 'US'")


def test_change_works_inside_a_nested_transaction(cur):
    with cur.connection.transaction():
        with cur.connection.transaction():
            region_rules.change(cur, "IT", "blocked", False, WHY, None)
            region_rules.change(cur, "QQ", "allowed", False, WHY, None, allow_new=True)
    assert db.val(cur, "select rule from region_rules where country = 'IT'") == "blocked"
    assert db.val(cur, "select rule from region_rules where country = 'QQ'") == "allowed"
    # The flag is cleared again: a raw update after the change is still refused.
    with pytest.raises(psycopg.errors.RaiseException, match="recorded reason"):
        with cur.connection.transaction():
            db.run(cur, "update region_rules set rule = 'allowed' where country = 'IT'")


def test_the_seed_adds_nothing_to_a_desk_that_already_has_rules(cur):
    text = (db.MIGRATIONS / "0035_region_rule_changes.sql").read_text()
    end = "where not exists (select 1 from region_rules);"
    seed = text[text.index("insert into region_rules"):text.index(end) + len(end)]
    assert "on conflict" not in seed
    db.run(cur, "create temp table rr (like region_rules including defaults)")
    sql = seed.replace("insert into region_rules", "insert into rr").replace("from region_rules", "from rr")
    db.run(cur, "insert into rr (country, rule) values ('US', 'blocked')")
    db.run(cur, sql)
    assert db.val(cur, "select count(*) from rr") == 1
    db.run(cur, "delete from rr")
    db.run(cur, sql)
    assert db.val(cur, "select count(*) from rr") == len(catalog.REGION_RULES)


def test_a_history_row_for_another_change_does_not_open_the_guard(cur):
    region_rules.change(cur, "IT", "blocked", False, WHY, None)
    with pytest.raises(psycopg.errors.RaiseException, match="recorded reason"):
        with cur.connection.transaction():
            db.run(cur, "update region_rules set rule = 'allowed' where country = 'IT'")


def test_the_guards_follow_an_edited_rule_on_the_next_check(cur, scene):
    db.run(cur, "update people set country = 'IT' where id = %s", scene["person"])
    db.run(cur, "update accounts set hq_country = 'IT', subscriber_type = 'corporate' where id = %s", scene["account"])
    assert "no_consent" in [r.code for r in gate.person_reasons(cur, scene["person"], "email")]
    refused(cur, scene["message"], "basis")
    region_rules.change(cur, "IT", "allowed", False, WHY, None, confirm="Italy")
    assert not {"no_consent", "no_basis", "region_blocked"} & {r.code for r in gate.person_reasons(cur, scene["person"], "email")}
    send(cur, scene["message"])           # the database guard reads the new rule too


def test_tightening_blocks_the_send_guard_and_the_gate(cur, scene):
    region_rules.change(cur, "US", "blocked", False, WHY, None)
    assert "region_blocked" in [r.code for r in gate.person_reasons(cur, scene["person"], "email")]
    refused(cur, scene["message"], "region blocked")


def test_the_individual_consent_flag_is_read_at_send_time(cur, scene):
    db.run(cur, "update accounts set subscriber_type = 'individual' where id = %s", scene["account"])
    send_ok = lambda: send(cur, scene["message"])   # noqa: E731
    region_rules.change(cur, "US", "allowed", True, WHY, None)
    refused(cur, scene["message"], "not a limited company")
    region_rules.change(cur, "US", "allowed", False, WHY, None, confirm="United States")
    send_ok()


def test_the_play_check_sees_an_edit(cur):
    from outbound import plays
    play = {"sequence": [{"channel": "email"}], "lia_ref": None, "lia_review_due": None}
    for c in [r["country"] for r in db.all(cur, "select country from region_rules where rule = 'basis_required'")]:
        ensure_rule(cur, c, "allowed")
    assert plays.lia_problem(cur, play) is None
    region_rules.change(cur, "FR", "basis_required", False, WHY, None)
    assert plays.lia_problem(cur, play) is not None


def test_a_call_task_reads_the_register_of_the_current_rule(cur):
    db.run(cur, "update region_rules set dnc_register = 'A new register' where country = 'FR'")   # call fields are not guarded
    assert db.val(cur, "select dnc_register from region_rules where country = 'FR'") == "A new register"


def test_a_loosening_needs_the_typed_name_and_a_reason(cur):
    with pytest.raises(region_rules.RuleError, match="Type Italy"):
        region_rules.change(cur, "IT", "allowed", False, WHY, None)
    with pytest.raises(region_rules.RuleError, match="Type Italy"):
        region_rules.change(cur, "IT", "allowed", False, WHY, None, confirm="Germany")
    with pytest.raises(region_rules.RuleError, match="why"):
        region_rules.change(cur, "IT", "blocked", False, "too short", None)
    region_rules.change(cur, "IT", "allowed", False, WHY, None, confirm=" italy ")
    assert db.val(cur, "select rule from region_rules where country = 'IT'") == "allowed"


def test_dropping_individual_consent_is_a_loosening(cur):
    assert region_rules.is_loosening("basis_required", True, "basis_required", False)
    assert not region_rules.is_loosening("basis_required", False, "basis_required", True)
    assert not region_rules.is_loosening("allowed", False, "blocked", False)


def test_setup_config_goes_through_the_write_function(cur):
    region_rules.change(cur, "NL", "basis_required", False, "desk setup config", None, skip_confirm=True)
    h = db.one(cur, "select * from region_rule_changes where country = 'NL'")
    assert h["changed_by"] is None and h["reason"] == "desk setup config"


def test_a_new_country_is_a_change_from_none(cur):
    region_rules.change(cur, "PL", "consent_required", False, WHY, None, allow_new=True)
    assert db.val(cur, "select from_rule from region_rule_changes where country = 'PL'") == "none"
    assert db.val(cur, "select rule from region_rules where country = 'PL'") == "consent_required"


def test_the_endpoint_changes_a_rule_and_logs_it(client, mgr, restore):
    r = client.put("/api/region-rules/CH", headers=mgr, json={"rule": "blocked", "individual_consent": False, "reason": WHY})
    assert r.status_code == 200, r.text
    got = client.get("/api/settings", headers=mgr).json()
    assert {x["country"]: x["rule"] for x in got["regions"]}["CH"] == "blocked"
    assert got["region_changes"][0]["reason"] == WHY and got["region_changes"][0]["changed_by_name"] == "Rule Manager"
    assert client.get("/api/region-rules/CH/changes", headers=mgr).json()["changes"][0]["to_rule"] == "blocked"
    with db.tx() as cur:
        assert db.val(cur, "select count(*) from audit_log where action = 'region_rule_changed' and actor_id = %s", int(mgr["X-Acting-As"]))


def test_the_endpoint_refuses_no_reason_and_a_short_one(client, mgr, restore):
    for reason in ("", "short"):
        r = client.put("/api/region-rules/CH", headers=mgr, json={"rule": "blocked", "individual_consent": False, "reason": reason})
        assert r.status_code == 422


def test_the_endpoint_refuses_a_loosening_without_the_typed_name(client, mgr, restore):
    body = {"rule": "allowed", "individual_consent": False, "reason": WHY}
    assert client.put("/api/region-rules/CH", headers=mgr, json=body).status_code == 422
    assert client.put("/api/region-rules/CH", headers=mgr, json={**body, "confirm": "Austria"}).status_code == 422
    assert client.put("/api/region-rules/CH", headers=mgr, json={**body, "confirm": "switzerland"}).status_code == 200


def test_the_endpoint_other_failures(client, mgr, restore):
    same = {"rule": "consent_required", "individual_consent": False, "reason": WHY}
    assert client.put("/api/region-rules/CH", headers=mgr, json=same).status_code == 422          # no change
    assert client.put("/api/region-rules/ZZ", headers=mgr, json=same).status_code == 404
    stale = {"rule": "blocked", "individual_consent": False, "reason": WHY, "from_rule": "allowed"}
    assert client.put("/api/region-rules/CH", headers=mgr, json=stale).status_code == 409


def test_an_sdr_cannot_change_a_rule(client, restore):
    r = client.put("/api/region-rules/CH", headers=_sdr(), json={"rule": "blocked", "individual_consent": False, "reason": WHY})
    assert r.status_code == 403


def test_the_public_demo_refuses_a_rule_change(client, mgr, monkeypatch):
    from outbound.api import app as api
    monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, public_demo=True))
    r = client.put("/api/region-rules/CH", headers=mgr, json={"rule": "blocked", "individual_consent": False, "reason": WHY})
    assert r.status_code == 403 and r.json()["detail"] == "Not available in the public demo."
