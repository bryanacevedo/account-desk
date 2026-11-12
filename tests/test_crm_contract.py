"""The CRM contract (crm-desk repository, docs/CONTRACT-TESTS.md) for Account Desk: tests 1, 2, 4, 6 and 7.

Each contract test runs once per CRM. "default" is the CRM this desk uses today (the simulated one in demo mode);
this desk has no Salesforce adapter yet, so today's CRM stands in that half and CRM=salesforce is refused. "crmdesk"
runs against a running CRM Desk named by CRM_DESK_URL, with CRM_DESK_KEY (a key made with --desk account_desk) and
CRM_DESK_ADMIN_KEY (to set up the records the desk writes about); without them that half is skipped and says so.
Test 7 is the rest of this suite, unchanged, with CRM unset."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from outbound import adapters, db
from outbound.adapters import crmdesk
from outbound.adapters.sim import SimCrm

LIVE = all(os.environ.get(k) for k in ("CRM_DESK_URL", "CRM_DESK_KEY", "CRM_DESK_ADMIN_KEY"))


class _Admin:
    """Sets up, in CRM Desk, the accounts, contacts and changes this desk then reads or writes about."""
    def __init__(self):
        self.c = httpx.Client(base_url=os.environ["CRM_DESK_URL"].rstrip("/") + "/api/v1", timeout=15.0,
                              headers={"authorization": f"Bearer {os.environ['CRM_DESK_ADMIN_KEY']}", "content-type": "application/json"})

    def call(self, method, path, body=None):
        r = self.c.request(method, path, json=body if body is not None else ({} if method != "GET" else None))
        assert r.status_code < 300, r.text
        return r.json()


def _world(cur, crm_name: str):
    """One account and two people in this desk, and the same in CRM Desk when that is the CRM under test."""
    tag = uuid.uuid4().hex[:8]
    domain = f"contract-{tag}.example"
    acc = db.one(cur, "insert into accounts (name, primary_domain) values (%s, %s) returning id", f"Contract {tag}", domain)["id"]
    people = [db.one(cur, "insert into people (account_id, full_name, email, source) values (%s, %s, %s, 'import') returning id",
                     acc, f"Ana {tag}{i}", f"ana{i}.{tag}@{domain}")["id"] for i in range(2)]
    user = db.one(cur, "select id, email from users order by id limit 1") or {"id": None, "email": None}
    if crm_name == "crmdesk":
        a = _Admin()
        cid = a.call("PUT", f"/accounts/by-domain/{domain}", {"name": f"Contract {tag}"})["id"]
        for i in range(2):
            a.call("PUT", f"/contacts/by-email/ana{i}.{tag}@{domain}", {"first_name": "Ana", "account_id": cid})
    return {"tag": tag, "domain": domain, "account": acc, "people": people, "user": user}


def _crm(name: str):
    if name == "default":
        return SimCrm()
    return crmdesk.CrmDeskCrm(os.environ["CRM_DESK_URL"], os.environ["CRM_DESK_KEY"])


CRMS = ["default", pytest.param("crmdesk", marks=pytest.mark.skipif(not LIVE, reason="no running CRM Desk named in CRM_DESK_URL"))]


# Test 1: every outbox kind lands once on a retry.
@pytest.mark.parametrize("name", CRMS)
def test_1_every_outbox_kind_lands_once_on_a_retry(cur, name):
    w = _world(cur, name)
    crm = _crm(name)
    p0 = w["people"][0]
    outbox = [
        ("activity", {"type": "email_sent", "person_id": p0, "message_id": f"{w['tag']}1", "subject": "Usage pricing"}),
        ("activity", {"task_id": f"{w['tag']}2", "kind": "call", "outcome": "no_answer", "person_id": p0}),
        ("activity", {"task_id": f"{w['tag']}3", "kind": "linkedin_connect", "outcome": "skipped", "person_id": p0}),
        ("activity", {"task_id": f"{w['tag']}4", "kind": "linkedin_message", "outcome": "sent", "person_id": p0}),
        ("meeting", {"meeting_id": f"{w['tag']}5", "account_id": w["account"], "person_id": p0,
                     "starts_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()}),
        ("task", {"type": "hot_reply", "reply_id": f"{w['tag']}6", "person_id": p0, "owner": w["user"]["id"]}),
        ("opt_out", {"email": f"ana1.{w['tag']}@{w['domain']}", "person_id": w["people"][1]}),
    ]
    def push(k, p, key):
        """As the outbox does: a failure is tried again with the attempt counted."""
        if not db.val(cur, "select 1 from crm_outbox where idempotency_key = %s", key):
            db.run(cur, "insert into crm_outbox (kind, payload, idempotency_key) values (%s, %s, %s)", k, db.J(p), key)
        for _ in range(5):
            try:
                return crm.push(cur, k, p, key)
            except Exception:
                db.run(cur, "update crm_outbox set attempts = attempts + 1 where idempotency_key = %s", key)
        raise AssertionError(f"{key} failed five times")
    first = [push(k, p, f"contract:{w['tag']}:{i}") for i, (k, p) in enumerate(outbox)]
    again = [push(k, p, f"contract:{w['tag']}:{i}") for i, (k, p) in enumerate(outbox)]
    assert first == again and all(first)


# Test 1, the erased half: a person this desk erased is a finished write with nothing written.
def test_1_an_erased_person_is_a_finished_write():
    crm = crmdesk.CrmDeskCrm("http://crm.test", "k", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    assert crm.push(_FakeCur(rows={}), "activity", {"type": "email_sent", "person_id": 99, "message_id": 1, "subject": "s"}, "k") == "refused:erased"
    with pytest.raises(crmdesk.CrmDeskUnresolved):
        crm.push(_FakeCur(rows={99: {"id": 99, "email": None}}), "opt_out", {"email": None, "person_id": 99}, "k")


# Test 2: the deals and owners feeds give every change once across pages, read the way this desk reads them.
@pytest.mark.parametrize("name", CRMS)
def test_2_feeds_give_every_change_once_across_pages(cur, name):
    w = _world(cur, name)
    crm = _crm(name)
    names = {f"Contract {w['tag']} deal {i}" for i in range(5)}
    start = None    # today's CRM is read from the beginning; CRM Desk from just before this test's changes
    if name == "default":
        at = db.val(cur, "select app_now() - interval '1 minute'")
        for n in sorted(names):
            db.run(cur, """insert into sim_crm_deals (crm_id, account_id, name, amount_cents, stage, created_at, updated_at, close_on, will_win)
                           values (%s, %s, %s, 100000, 'Discovery', %s, %s, %s, false)""", f"SIM-{uuid.uuid4().hex[:10]}", w["account"], n, at, at, at)
            db.run(cur, "insert into sim_crm_owner_changes (account_id, owner_email, updated_at) values (%s, %s, %s)",
                   w["account"], f"{n.split()[-1]}@seller.example", at)
    else:
        a = _Admin()
        pid = a.call("GET", "/meta/pipelines")["data"][0]
        stage = next(s["id"] for s in pid["stages"] if s["outcome"] == "open")
        acc = a.call("GET", f"/accounts/domain:{w['domain']}")
        made = [a.call("POST", "/opportunities", {"name": n, "account_id": acc["id"], "pipeline_id": pid["id"], "stage_id": stage,
                                                   "amount_cents": 100000}) for n in sorted(names)]
        # A desk resumes from its saved cursor; this one starts a second before these changes, not at the beginning.
        start = (datetime.fromisoformat(min(m["updated_at"] for m in made)) - timedelta(seconds=1)).isoformat() + "|"
        users = [u for u in a.call("GET", "/meta/users")["data"] if u["active"] and u["role"] != "viewer"][:3]
        for u in users:
            a.call("PATCH", f"/accounts/{acc['id']}", {"owner_id": u["id"]})
        time.sleep(2.5)    # CRM Desk's feeds show a change once it has settled for two seconds (its DECISIONS 6)
    seen, since = [], start
    for _ in range(10_000):
        batch = crm.deals_changed(cur, since, 2)
        seen += [d.name for d in batch if d.name in names]
        if batch:
            d = batch[-1]
            since = (d.updated_at.isoformat() if hasattr(d.updated_at, "isoformat") else str(d.updated_at)) + "|" + d.crm_id
        if len(batch) < 2:
            break
    assert sorted(seen) == sorted(names)
    owners, since = [], start
    for _ in range(10_000):
        batch = crm.owners_changed(cur, since, 1)
        owners += [(o.change_id, o.owner_email) for o in batch if o.account_domain == w["domain"]]
        if batch:
            o = batch[-1]
            since = (o.updated_at.isoformat() if hasattr(o.updated_at, "isoformat") else str(o.updated_at)) + "|" + o.change_id
        if len(batch) < 1:
            break
    assert owners and len({c for c, _ in owners}) == len(owners)


# Test 4: CRM Desk not answering pauses the work; nothing is treated as done.
@pytest.mark.parametrize("answer", ["timeout", 503, 429])
def test_4_fails_closed(answer):
    def handler(request):
        if answer == "timeout":
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(answer, json={"error": "down"})
    crm = crmdesk.CrmDeskCrm("http://crm.test", "k", client=httpx.Client(base_url="http://crm.test", transport=httpx.MockTransport(handler)))
    with pytest.raises(crmdesk.CrmDeskDown):
        crm.deals_changed(None, None, 10)
    with pytest.raises(crmdesk.CrmDeskDown):
        crm.owners_changed(None, None, 10)
    with pytest.raises(crmdesk.CrmDeskDown):
        crm.push(_FakeCur(rows={1: {"id": 1, "email": "x@y.example"}}), "opt_out", {"email": "x@y.example", "person_id": 1}, "k")


# Test 6: configuration picks one CRM, and the default is today's.
def test_6_configuration_picks_one_crm(monkeypatch):
    today = object()
    monkeypatch.delenv("CRM", raising=False)
    assert adapters.choose_crm(today) is today
    monkeypatch.setenv("CRM", "salesforce")
    with pytest.raises(SystemExit):
        adapters.choose_crm(today)
    monkeypatch.setenv("CRM", "crmdesk")
    monkeypatch.delenv("CRM_DESK_URL", raising=False)
    with pytest.raises(SystemExit):
        adapters.choose_crm(today)
    monkeypatch.setenv("CRM_DESK_URL", "http://crm.test")
    monkeypatch.setenv("CRM_DESK_KEY", "k")
    assert isinstance(adapters.choose_crm(today), crmdesk.CrmDeskCrm)
    monkeypatch.setenv("CRM", "nonsense")
    with pytest.raises(SystemExit):
        adapters.choose_crm(today)


class _FakeCur:
    """Enough of a cursor for the adapter's two lookups (a person by id, an account's domain)."""
    description = True

    def __init__(self, rows: dict):
        self.rows, self._last = rows, None

    def execute(self, sql, args=None):
        self._last = self.rows.get(args[0]) if args else None

    def fetchone(self):
        return self._last

    def fetchall(self):
        return [self._last] if self._last else []
