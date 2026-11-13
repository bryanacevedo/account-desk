"""Links from the other desks: /go/account and /go/contact open the desk's own sheet, say plainly when there is none,
take no address, and need the same sign-in as the app (shared-world DESIGN 9)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

import uuid  # noqa: E402

import psycopg  # noqa: E402
from conftest import BASE, PREFIX, _admin  # noqa: E402

from outbound import db  # noqa: E402
from outbound.config import CONFIG  # noqa: E402


@pytest.fixture(scope="module")
def own_database(database):
    """A database of this module's own, for tests that commit (an API test that writes rows). The pool points at it for
    the module and back at the shared test database after, so the shared one is never changed."""
    name = f"{PREFIX}own_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'create database "{name}"')
    url = BASE.rsplit("/", 1)[0] + "/" + name
    db.configure(url, max_size=4)
    db.migrate(url)
    yield url
    db.configure(database, max_size=6)
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture(scope="module")
def client(own_database):
    from outbound.api.app import app
    return TestClient(app, follow_redirects=False)


@pytest.fixture(scope="module")
def ids(own_database):
    with db.tx() as cur:
        db.run(cur, "insert into users (name, email, role) values ('Go SDR', 'go-sdr@x.example', 'sdr') on conflict do nothing")
        a = db.val(cur, """insert into accounts (name, primary_domain, world_id, crm_id) values
                           ('Go Co', 'go-co.example', 'co_go1', 'crm-go-1') returning id""")
        p = db.val(cur, """insert into people (account_id, full_name, email, world_id, crm_id, source)
                           values (%s, 'Go Person', 'go.person@go-co.example', 'pe_go1', 'con-go-1', 'test') returning id""", a)
    yield {"account": a, "person": p}
    with db.tx() as cur:
        db.run(cur, "delete from people where id = %s", p)
        db.run(cur, "delete from accounts where id = %s", a)


@pytest.mark.parametrize("ref", ["world:co_go1", "domain:go-co.example", "domain:GO-CO.example", "crm:crm-go-1"])
def test_an_account_ref_opens_the_account_sheet(client, ids, ref):
    r = client.get(f"/go/account/{ref}")
    assert r.status_code == 302 and r.headers["location"] == f"/accounts?sheet=account:{ids['account']}"


@pytest.mark.parametrize("ref", ["world:pe_go1", "crm:con-go-1"])
def test_a_contact_ref_opens_the_person_sheet(client, ids, ref):
    r = client.get(f"/go/contact/{ref}")
    assert r.status_code == 302 and r.headers["location"] == f"/accounts?sheet=person:{ids['person']}"


@pytest.mark.parametrize("path", ["/go/account/world:co_nope", "/go/account/domain:nowhere.example", "/go/account/crm:nope",
                                  "/go/account/nonsense", "/go/account/world:", "/go/contact/world:pe_nope", "/go/contact/crm:nope"])
def test_an_unknown_ref_is_a_plain_404_that_says_so(client, ids, path):
    r = client.get(path)
    assert r.status_code == 404 and "holds no" in r.text and "text/html" in r.headers["content-type"]


def test_an_address_is_never_accepted(client, ids):
    for path in ("/go/contact/email:go.person@go-co.example", "/go/account/email:go.person@go-co.example"):
        r = client.get(path)
        assert r.status_code == 404 and "go.person" not in r.text


def test_signed_out_requests_learn_nothing(client, ids):
    old = CONFIG.auth_mode
    object.__setattr__(CONFIG, "auth_mode", "header")
    try:
        known = client.get("/go/account/world:co_go1")
        unknown = client.get("/go/account/world:co_nope")
        contact = client.get("/go/contact/world:pe_go1")
    finally:
        object.__setattr__(CONFIG, "auth_mode", old)
    assert known.status_code == unknown.status_code == contact.status_code == 401
    assert known.text == unknown.text and "location" not in known.headers
