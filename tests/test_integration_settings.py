"""INTEGRATED_WITH and DESK_LINKS, each in both states (shared-world DESIGN 2b): unset is exactly today's desk."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from test_go_links import own_database  # noqa: E402,F401

from outbound import db, integration, setup_desk, views  # noqa: E402


@pytest.fixture(scope="module")
def client(own_database):
    from outbound.api.app import app
    return TestClient(app)


@pytest.fixture(scope="module")
def who(own_database):
    with db.tx() as cur:
        ids = {}
        for role in ("gtm", "sdr"):
            ids[role] = db.val(cur, "insert into users (name, email, role) values (%s, %s, %s) returning id",
                               f"Int {role}", f"int-{role}@x.example", role)
        db.run(cur, "insert into icp_versions (rules, note) values ('{\"factors\": [], \"tiers\": {\"A\": 70, \"B\": 40}}', 'seed')")
    return ids


def h(who, role="gtm"):
    return {"X-Acting-As": str(who[role])}


CSV = "name,domain\nImport Co,import-co.example\n"
RULES = {"factors": [{"key": "industry", "field": "industry", "op": "in", "value": ["Fintech"], "weight": 20}], "tiers": {"A": 70, "B": 40},
         "note": "Because a test says so"}


@pytest.fixture
def alone(monkeypatch):
    for k in ("INTEGRATED_WITH", "DESK_LINKS"):
        monkeypatch.delenv(k, raising=False)


# ---- parsing

def test_unset_means_alone(alone):
    assert integration.integrated_with() == frozenset() and integration.desk_links() == {}
    assert views.integration_state() == {"integrated_with": [], "links": {}}


def test_desk_links_parsing(monkeypatch):
    monkeypatch.setenv("DESK_LINKS", "crm_desk=https://crm.example/, market_desk=https://md.example,events_desk=http://insecure.example,bogus=https://x.example,junk")
    assert integration.desk_links() == {"crm_desk": "https://crm.example", "market_desk": "https://md.example"}
    assert integration.integrated_with() == frozenset()  # links never switch anything


def test_integrated_with_parsing_and_unknown_names(monkeypatch):
    monkeypatch.setenv("INTEGRATED_WITH", "market_desk, events_desk")
    assert integration.integrated_with() == {"market_desk", "events_desk"}
    monkeypatch.setenv("INTEGRATED_WITH", "market_desk,nonsense")
    with pytest.raises(SystemExit, match="nonsense"):
        integration.integrated_with()


# ---- the app state

def test_me_carries_the_integration_state(client, who, alone, monkeypatch):
    me = client.get("/api/me", headers=h(who)).json()
    assert me["integration"] == {"integrated_with": [], "links": {}}
    monkeypatch.setenv("INTEGRATED_WITH", "market_desk")
    monkeypatch.setenv("DESK_LINKS", "crm_desk=https://crm.example,market_desk=https://md.example")
    me = client.get("/api/me", headers=h(who)).json()
    assert me["integration"] == {"integrated_with": ["market_desk"],
                                 "links": {"crm_desk": "https://crm.example", "market_desk": "https://md.example"}}


# ---- market_desk: the accounts import and publishing

def test_alone_the_accounts_import_and_publishing_work(client, who, alone):
    r = client.post("/api/import/accounts", json={"csv": CSV}, headers=h(who))
    assert r.status_code == 200 and r.json()["imported"] == 1
    assert client.put("/api/icp", json=RULES, headers=h(who)).status_code == 200
    s = client.get("/api/settings", headers=h(who)).json()
    assert s["kept"] is None and s["integration"]["integrated_with"] == []


def test_with_market_desk_the_api_refuses_both_with_a_409_naming_it(client, who, monkeypatch):
    monkeypatch.setenv("INTEGRATED_WITH", "market_desk")
    r = client.post("/api/import/accounts", json={"csv": CSV.replace("import-co", "import-co2")}, headers=h(who))
    assert r.status_code == 409 and "Market Desk" in r.json()["detail"]
    r = client.put("/api/icp", json=RULES, headers=h(who))
    assert r.status_code == 409 and "Market Desk" in r.json()["detail"]
    with db.tx() as cur:
        assert db.val(cur, "select count(*) from accounts where primary_domain = 'import-co2.example'") == 0
        assert db.val(cur, "select count(*) from icp_versions where note = 'Because a test says so'") == 1  # the earlier one only
    # People still import.
    ok = client.post("/api/import/people", json={"csv": "full_name,company_domain,email\n"}, headers=h(who))
    assert ok.status_code == 200


def test_the_command_line_path_refuses_too(own_database, monkeypatch):
    monkeypatch.setenv("INTEGRATED_WITH", "market_desk")
    with db.tx() as cur:
        with pytest.raises(setup_desk.KeptElsewhere, match="Market Desk"):
            setup_desk.import_accounts(cur, CSV)
    monkeypatch.delenv("INTEGRATED_WITH")
    with db.tx() as cur:
        assert setup_desk.import_accounts(cur, "name,domain\nCli Co,cli-co.example\n")["imported"] == 1


def test_settings_show_what_market_desk_keeps(client, who, monkeypatch):
    monkeypatch.setenv("INTEGRATED_WITH", "market_desk")
    s = client.get("/api/settings", headers=h(who)).json()
    assert s["kept"]["icp"]["id"] and "accounts_read_at" in s["kept"]


def test_events_desk_changes_nothing_here(client, who, monkeypatch):
    monkeypatch.setenv("INTEGRATED_WITH", "events_desk")
    assert client.post("/api/import/accounts", json={"csv": "name,domain\nEv Co,ev-co.example\n"}, headers=h(who)).status_code == 200
    assert client.put("/api/icp", json=RULES, headers=h(who)).status_code == 200
    assert client.get("/api/settings", headers=h(who)).json()["kept"] is None


def test_the_account_payload_carries_the_ids_and_the_record_columns(client, who):
    with db.tx() as cur:
        a = db.val(cur, "insert into accounts (name, primary_domain, world_id, crm_id) values ('Ids Co', 'ids-co.example', 'co_ids', 'crm-ids') returning id")
    d = client.get(f"/api/accounts/{a}", headers=h(who)).json()["account"]
    assert d["world_id"] == "co_ids" and d["crm_id"] == "crm-ids" and d.get("crm_tier") is None
    with db.tx() as cur:
        db.run(cur, "update accounts set crm_tier = 'A', crm_segment = 'Mid-market' where id = %s", a)
    d = client.get(f"/api/accounts/{a}", headers=h(who)).json()["account"]
    assert d["crm_tier"] == "A" and d["crm_segment"] == "Mid-market"
