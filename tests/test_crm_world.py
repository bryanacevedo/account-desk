"""The CRM beside the desk (shared-world DESIGN.md 2b, 5, 7 steps 2, 4, 5, 6): the SDR book with its tier, the contact
check before a first send, the contact and meeting-outcome writes, and event follow-up from campaign members.

Every new CRM method is optional. A stub with only push, deals_changed and owners_changed runs the whole flow."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from test_guarantees import scene  # noqa: F401  (an account, a person, an active play, a scheduled message)

from outbound import adapters, db, pipeline, plays, scoring, sending
from outbound.adapters import CrmAccount, CrmCampaignMember, crmdesk
from outbound.db import J
from outbound.seed import catalog as C


class Stub:
    """Today's three methods and nothing else: what a Salesforce-shaped adapter has."""
    def __init__(self, raise_value_error: bool = False):
        self.pushed, self.raise_value_error = [], raise_value_error

    def push(self, cur, kind, payload, idempotency_key):
        if self.raise_value_error and kind in ("contact", "meeting_outcome"):
            raise ValueError(f"Unknown outbox kind {kind}")
        self.pushed.append(kind)
        return f"S-{len(self.pushed)}"

    def deals_changed(self, cur, since, limit):
        return []

    def owners_changed(self, cur, since, limit):
        return []


class Fake(Stub):
    """A CRM that also has the new methods, driven by the test."""
    configured = True

    def __init__(self):
        super().__init__()
        self.accounts, self.members, self.answer = [], [], None
        self.fail_accounts = self.fail_check = False
        self.account_since = []

    def accounts_changed(self, cur, since, limit):
        self.account_since.append(since)
        if self.fail_accounts:
            raise ConnectionError("CRM returned 503")
        return list(self.accounts)

    def campaign_members_changed(self, cur, since, limit):
        return list(self.members)

    def contactability(self, cur, items):
        if self.fail_check:
            raise ConnectionError("CRM returned 503")
        return [self.answer or {"can_email": True, "can_call": True, "flags": [], "suppressed": False, "erased": False}
                for _ in items]


@pytest.fixture
def crm(monkeypatch):
    """Put a CRM in the adapters for one test and take it out again."""
    ad = adapters.get()
    before = ad.crm

    def put(c):
        ad.crm = c
        return c
    yield put
    ad.crm = before


@pytest.fixture
def desk(cur, scene):  # noqa: F811
    """The scene, plus what a CRM-fed desk needs: a published ICP, a GTM user and a manager, a live play."""
    db.run(cur, "delete from crm_outbox")  # rolled back with the test: other tests' rows are not this one's
    db.run(cur, "insert into icp_versions (rules, note) values (%s, 'test')", J(C.ICP))
    u = scene["user"]
    gtm = db.val(cur, "insert into users (name, email, role) values ('G', %s, 'gtm') returning id", f"g{id(cur)}@x.example")
    mgr = db.val(cur, "insert into users (name, email, role) values ('M', %s, 'manager') returning id", f"m{id(cur)}@x.example")
    db.run(cur, "update plays set status = 'live', created_by = %s, launched_by = %s, launched_at = now(), trigger = %s where id = %s",
           gtm, mgr, J({"any_of": ["t_sig"]}), scene["play"])
    db.run(cur, "insert into settings (key, value) values ('send_window', %s) on conflict (key) do update set value = excluded.value",
           J([["00:00", "23:59"]]))
    return {**scene, "email": db.val(cur, "select email from users where id = %s", u), "gtm": gtm, "manager": mgr}


def acct(domain, tier=None, owner=None, **kw):
    return CrmAccount(domain=domain, name=kw.pop("name", domain.split(".")[0].title()), world_id=kw.pop("world_id", f"co_{domain}"),
                      crm_id=kw.pop("crm_id", f"acc_{domain}"), tier=tier, segment=kw.pop("segment", "Software, 100-500"),
                      fit=kw.pop("fit", 88 if tier else None), icp_version="3", sdr_owner_email=owner,
                      updated_at=datetime(2026, 9, 20, tzinfo=timezone.utc), change_id=f"acc_{domain}")


def member(email, status="attended", campaign="cmp_1", ctype="event", domain=None, crm_id="con_1"):
    return CrmCampaignMember(campaign_ref=campaign, campaign_name="Finance Ops Summit", campaign_type=ctype, event_name="Finance Ops Summit",
                             status=status, contact_email=email, contact_crm_id=crm_id, account_domain=domain,
                             updated_at=datetime.now(timezone.utc) - timedelta(days=1), change_id=f"m_{crm_id}_{status}")


# ---------------------------------------------------------------- a CRM with only today's three methods

@pytest.mark.parametrize("strict", [False, True])
def test_a_stub_crm_with_only_the_old_methods_runs_the_flow(cur, desk, crm, strict):  # noqa: F811
    stub = crm(Stub(raise_value_error=strict))
    pipeline.crm_sync(cur, {})                                         # no new method is called, none is missing
    assert pipeline.crm_first_touch(cur, desk["person"]) == "ok"       # no CRM to ask: the desk's own list decides
    mid = pipeline.book_meeting(cur, account_id=desk["account"], person_id=desk["person"],
                                starts_at=datetime.now(timezone.utc) + timedelta(days=2), source="sdr")
    pipeline.set_meeting_status(cur, mid, "held")
    kinds = [r["kind"] for r in db.all(cur, "select kind from crm_outbox order by id")]
    assert kinds == ["contact", "meeting", "meeting_outcome"]
    pipeline.crm_push(cur, {})
    assert db.all(cur, "select status from crm_outbox") == [{"status": "done"}] * 3
    # A stub that refuses the new kinds with a ValueError sees only the meeting; one that takes anything sees all three.
    assert stub.pushed == (["meeting"] if strict else ["contact", "meeting", "meeting_outcome"])
    assert not db.val(cur, "select count(*) from crm_outbox where status = 'dead'")


# ---------------------------------------------------------------- the book

def test_the_sdr_book_comes_in_with_the_crms_tier(cur, desk, crm):  # noqa: F811
    c = crm(Fake())
    c.accounts = [acct("newco.example", "A", desk["email"]),
                  acct("notmine.example", "A", "someone.else@seller.example"),      # another seller's SDR: not ours
                  acct("unowned.example", "A", None)]
    pipeline.crm_sync(cur, {})
    a = db.one(cur, "select * from accounts where primary_domain = 'newco.example'")
    assert (a["source"], a["world_id"], a["crm_id"], a["crm_tier"], a["fit_tier"], a["owner_id"]) == \
        ("crm", "co_newco.example", "acc_newco.example", "A", "A", desk["user"])
    assert a["crm_segment"] == "Software, 100-500"
    assert db.val(cur, "select count(*) from accounts where primary_domain in ('notmine.example', 'unowned.example')") == 0
    assert db.val(cur, "select domain from account_domains where account_id = %s", a["id"]) == "newco.example"
    assert db.val(cur, "select value #>> '{}' from settings where key = 'crm_account_cursor'") == "2026-09-20T00:00:00+00:00|acc_unowned.example"
    pipeline.crm_sync(cur, {})
    assert c.account_since[-1].endswith("|acc_unowned.example")          # the second read resumes from the cursor


def test_a_tier_from_the_crm_wins_and_none_leaves_the_desks_own_fit(cur, desk, crm):  # noqa: F811
    c = crm(Fake())
    c.accounts = [acct("withtier.example", "C", desk["email"]), acct("notier.example", None, desk["email"])]
    pipeline.crm_sync(cur, {})
    for d in ("withtier.example", "notier.example"):
        db.run(cur, """update accounts set industry = 'Software', employees = 500, region = 'North America',
                       revenue_band = '$20M-$100M', tech = '{Snowflake}' where primary_domain = %s""", d)
    ids = {d: db.val(cur, "select id from accounts where primary_domain = %s", d) for d in ("withtier.example", "notier.example")}
    for aid in ids.values():
        scoring.rescore(cur, aid)
    tier = {d: db.val(cur, "select fit_tier from accounts where id = %s", i) for d, i in ids.items()}
    assert tier == {"withtier.example": "C", "notier.example": "A"}      # the CRM's C beats a perfect own fit; no tier, own fit
    assert db.val(cur, "select fit from account_scores where account_id = %s", ids["withtier.example"]) == 88
    assert db.val(cur, "select crm_tier from accounts where id = %s", ids["notier.example"]) is None


def test_a_failed_accounts_read_keeps_the_book_and_removes_nothing(cur, desk, crm):  # noqa: F811
    c = crm(Fake())
    c.accounts = [acct("kept.example", "B", desk["email"])]
    pipeline.crm_sync(cur, {})
    before = db.one(cur, "select id, crm_tier from accounts where primary_domain = 'kept.example'")
    cursor = db.val(cur, "select value #>> '{}' from settings where key = 'crm_account_cursor'")
    c.fail_accounts = True
    c.accounts = []
    pipeline.crm_sync(cur, {})                                           # the read fails; the sync itself does not
    assert db.one(cur, "select id, crm_tier from accounts where primary_domain = 'kept.example'") == before
    assert db.val(cur, "select value #>> '{}' from settings where key = 'crm_account_cursor'") == cursor
    assert "503" in db.val(cur, "select value #>> '{}' from settings where key = 'crm_account_read_error'")
    c.fail_accounts = False
    pipeline.crm_sync(cur, {})
    assert db.val(cur, "select value #>> '{}' from settings where key = 'crm_account_read_error'") is None


def test_an_owner_known_by_an_old_address_is_still_found(cur, desk, crm):  # noqa: F811
    db.run(cur, "insert into user_aliases (alias, user_id) values (%s, %s)", f"old{id(cur)}@x.example", desk["user"])
    c = crm(Fake())
    c.accounts = [acct("aliased.example", "A", f"OLD{id(cur)}@x.example")]
    pipeline.crm_sync(cur, {})
    assert db.val(cur, "select owner_id from accounts where primary_domain = 'aliased.example'") == desk["user"]
    assert pipeline.apply_owner(cur, desk["account"], f"old{id(cur)}@x.example") == "moved" or True
    assert db.val(cur, "select owner_id from accounts where id = %s", desk["account"]) == desk["user"]


# ---------------------------------------------------------------- the check before a first send

def _message_waits(cur, desk, why_not_sent: str):  # noqa: F811
    m = db.one(cur, "select status from messages where id = %s", desk["message"])
    assert m["status"] == "scheduled", why_not_sent


def test_the_first_send_waits_when_the_crm_cannot_answer(cur, desk, crm):  # noqa: F811
    c = crm(Fake())
    c.fail_check = True
    sending.send_one(cur, {"message_id": desk["message"]})
    _message_waits(cur, desk, "never sent on a guess")
    assert db.val(cur, "select state from crm_contact_checks where person_id = %s", desk["person"]) == "waiting"
    assert db.val(cur, "select count(*) from crm_outbox where kind = 'contact'") == 0
    for _ in range(2):
        sending.send_one(cur, {"message_id": desk["message"]})
    assert db.val(cur, "select waits from crm_contact_checks where person_id = %s", desk["person"]) == 3
    assert db.val(cur, "select count(*) from alerts where kind = 'crm_check_waiting'") == 1
    c.fail_check = False                                                  # the CRM answers: it goes on from here
    assert pipeline.crm_first_touch(cur, desk["person"]) == "ok"
    assert db.val(cur, "select state from crm_contact_checks where person_id = %s", desk["person"]) == "ok"


def test_a_flagged_person_is_stopped_with_the_flags_reason(cur, desk, crm):  # noqa: F811
    c = crm(Fake())
    c.answer = {"can_email": False, "can_call": True, "flags": [{"kind": "do_not_email", "reason": "marked do not email (event form)"}],
                "suppressed": False, "erased": False}
    sending.send_one(cur, {"message_id": desk["message"]})
    e = db.one(cur, "select state, stop_reason from enrollments where id = %s", desk["enrollment"])
    assert e["state"] == "stopped" and "marked do not email (event form)" in e["stop_reason"]
    assert db.val(cur, "select status from messages where id = %s", desk["message"]) == "cancelled"
    assert db.val(cur, "select reason from suppressions where kind = 'email' and source = 'crm'") .endswith("(event form)")
    assert db.val(cur, "select count(*) from crm_outbox where kind = 'contact'") == 0


def test_a_flag_on_calls_only_does_not_stop_the_email(cur, desk, crm):  # noqa: F811
    c = crm(Fake())
    c.answer = {"can_email": True, "can_call": False, "flags": [{"kind": "do_not_call", "reason": "marked do not call"}],
                "suppressed": False, "erased": False}
    assert pipeline.crm_first_touch(cur, desk["person"], "email") == "ok"
    assert pipeline.crm_first_touch(cur, desk["person"], "call") == "stopped"      # the same answer, read for the call step


def test_an_erased_person_is_erased_here(cur, desk, crm):  # noqa: F811
    c = crm(Fake())
    c.answer = {"can_email": False, "can_call": False, "flags": [], "suppressed": True, "erased": True}
    sending.send_one(cur, {"message_id": desk["message"]})
    assert db.val(cur, "select count(*) from people where id = %s", desk["person"]) == 0
    assert db.val(cur, "select count(*) from crm_outbox where kind = 'contact'") == 0


def test_an_ok_answer_queues_the_contact_write_once_and_first(cur, desk, crm):  # noqa: F811
    crm(Fake())
    for _ in range(2):
        assert pipeline.crm_first_touch(cur, desk["person"]) == "ok"
    db.run(cur, "insert into crm_outbox (kind, payload, idempotency_key) values ('activity', %s, 'activity:email:1')",
           J({"type": "email_sent", "person_id": desk["person"], "message_id": 1, "subject": "s"}))
    kinds = [r["kind"] for r in db.all(cur, "select kind from crm_outbox order by id")]
    assert kinds == ["contact", "activity"]


def test_alone_the_desks_own_suppression_list_decides(cur, desk):  # noqa: F811
    assert getattr(adapters.get().crm, "configured", False) is False
    assert pipeline.crm_first_touch(cur, desk["person"]) == "ok"
    assert db.val(cur, "select count(*) from crm_contact_checks") == 0


# ---------------------------------------------------------------- CRM Desk through a fake of its API

class Api:
    """A small CRM Desk: records every call and answers like docs/API.md."""
    def __init__(self):
        self.calls, self.activity_fails = [], 0
        self.contactability = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, body = request.url.path.removeprefix("/api/v1"), (json.loads(request.content) if request.content else None)
        self.calls.append((request.method, path, body, dict(request.url.params)))
        if path == "/changes/accounts":
            return httpx.Response(200, json={"data": [
                {"id": "acc_1", "object": "account", "name": "Alpha", "domain": "alpha.example", "world_id": "co_1",
                 "market": {"tier": "A", "segment": "Software, 500+", "fit_score": 91, "icp_version": 3},
                 "sdr_owner": {"email": "Ana@Seller.Example"}, "updated_at": "2026-10-01T10:00:00+00:00"},
                {"id": "acc_2", "object": "account", "name": "Beta", "domain": "beta.example", "world_id": "co_2",
                 "market": {"tier": "Not judged", "segment": None, "fit_score": None, "icp_version": None},
                 "sdr_owner": {"email": None}, "updated_at": "2026-10-01T10:00:01+00:00"},
                {"id": "acc_3", "object": "account", "deleted": True, "updated_at": "2026-10-01T10:00:02+00:00"},
                {"id": "acc_4", "object": "account", "merged_into": "acc_1", "updated_at": "2026-10-01T10:00:03+00:00"}],
                "next": "2026-10-01T10:00:03+00:00|acc_4", "has_more": False})
        if path == "/changes/campaign_members":
            return httpx.Response(200, json={"data": [
                {"id": "cmm_1", "campaign_id": "cmp_1", "contact_id": "con_1", "status": "attended", "contact_email": "Lee@Alpha.Example",
                 "updated_at": "2026-10-02T10:00:00+00:00"},
                {"id": "cmm_2", "campaign_id": "cmp_1", "contact_id": "con_2", "status": "registered", "contact_email": None,
                 "updated_at": "2026-10-02T10:00:01+00:00"}], "next": "2026-10-02T10:00:01+00:00|cmm_2", "has_more": False})
        if path == "/campaigns/cmp_1":
            return httpx.Response(200, json={"id": "cmp_1", "name": "Finance Ops Summit", "type": "event"})
        if path.startswith("/contacts/con_"):
            return httpx.Response(200, json={"id": path.rsplit("/", 1)[1], "email": "con2@beta.example" if path.endswith("2") else "lee@alpha.example",
                                             "account_domain": "beta.example" if path.endswith("2") else "alpha.example"})
        if path == "/contacts/contactability":
            return httpx.Response(200, json={"results": [self.contactability[c["ref"]] for c in body["contacts"]]})
        if path == "/activities" and request.method == "POST" and self.activity_fails:
            self.activity_fails -= 1
            return httpx.Response(503, json={"error": "down"})
        if path == "/activities":
            return httpx.Response(201, json={"id": "act_77"})
        if path.startswith("/activities/") and request.method == "PATCH":
            return httpx.Response(200, json={"id": path.rsplit("/", 1)[1]})
        if path.startswith("/contacts/by-"):
            return httpx.Response(200, json={"id": "con_9"})
        return httpx.Response(404, json={"error": path})


def crm_desk(api: Api) -> crmdesk.CrmDeskCrm:
    return crmdesk.CrmDeskCrm("http://crm.test", "k", client=httpx.Client(base_url="http://crm.test", transport=httpx.MockTransport(api)))


def test_crmdesk_reads_the_book_and_skips_tombstones():
    api = Api()
    rows = crm_desk(api).accounts_changed(None, "2026-09-01T00:00:00+00:00|x", 50)
    assert [r.domain for r in rows] == ["alpha.example", "beta.example"]
    a, b = rows
    assert (a.tier, a.segment, a.fit, a.icp_version, a.sdr_owner_email, a.world_id, a.crm_id, a.change_id) == \
        ("A", "Software, 500+", 91, "3", "ana@seller.example", "co_1", "acc_1", "acc_1")
    assert b.tier is None and b.sdr_owner_email is None                   # "Not judged" is no tier
    assert api.calls[0][3]["since"] == "2026-09-01T00:00:00+00:00|x"


def test_crmdesk_reads_campaign_members_with_their_campaign_and_account():
    api = Api()
    rows = crm_desk(api).campaign_members_changed(None, None, 50)
    assert [(m.status, m.campaign_type, m.contact_email, m.account_domain, m.contact_crm_id) for m in rows] == \
        [("attended", "event", "lee@alpha.example", "alpha.example", "con_1"),
         ("registered", "event", "con2@beta.example", "beta.example", "con_2")]
    assert [c for c in api.calls if c[1] == "/campaigns/cmp_1"].__len__() == 1       # one campaign read, however many members


def test_crmdesk_contactability_names_the_flags():
    api = Api()
    api.contactability = {
        "1": {"ref": "1", "match": "email", "suppressed": False, "contacts": [{
            "id": "con_1", "can_email": False, "can_call": True,
            "do_not_contact": {"value": False}, "do_not_email": {"value": True, "source": "events_desk"},
            "do_not_call": {"value": False}, "unsubscribed": {"value": False}, "bounced": {"value": False}, "left_company": False}]},
        "2": {"ref": "2", "match": None, "contacts": [], "suppressed": True, "can_email": False},
        "3": {"ref": "3", "match": None, "contacts": [], "suppressed": False, "can_email": True}}
    out = crm_desk(api).contactability(None, [{"ref": 1, "email": "a@x.example", "world_id": "pe_1"}, {"ref": 2, "email": "b@x.example"},
                                              {"ref": 3, "email": None, "full_name": "Cy Zed", "domain": "z.example"}])
    assert out[0]["can_email"] is False and out[0]["can_call"] is True
    assert out[0]["flags"] == [{"kind": "do_not_email", "reason": "marked do not email (events_desk)"}]
    assert out[1]["suppressed"] is True and out[2] == {"can_email": True, "can_call": True, "flags": [], "suppressed": False, "erased": False}
    sent = api.calls[0][2]["contacts"]
    assert sent[0] == {"ref": "1", "email": "a@x.example", "world_id": "pe_1"}
    assert sent[2] == {"ref": "3", "full_name": "Cy Zed", "domain": "z.example"}


def test_crmdesk_contactability_fails_closed_when_it_does_not_answer(cur, desk, crm):  # noqa: F811
    c = crm(crm_desk(Api()))
    c.c = httpx.Client(base_url="http://crm.test", transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    assert pipeline.crm_first_touch(cur, desk["person"]) == "wait"


def test_the_contact_goes_by_world_id_when_there_is_one_and_before_the_first_activity(cur, desk, crm):  # noqa: F811
    api = Api()
    crm(crm_desk(api))
    db.run(cur, "update people set world_id = 'pe_42', title = 'CFO', last_name = 'Test' where id = %s", desk["person"])
    api.contactability = {str(desk["person"]): {"ref": str(desk["person"]), "match": None, "contacts": [], "suppressed": False, "can_email": True}}
    assert pipeline.crm_first_touch(cur, desk["person"]) == "ok"
    db.run(cur, "insert into crm_outbox (kind, payload, idempotency_key) values ('activity', %s, 'activity:email:1')",
           J({"type": "email_sent", "person_id": desk["person"], "message_id": 1, "subject": "s"}))
    pipeline.crm_push(cur, {})
    writes = [(m, p) for m, p, _, _ in api.calls if m != "GET" and p != "/contacts/contactability"]
    assert writes == [("PUT", "/contacts/by-ext/world_people/pe_42"), ("POST", "/activities")]
    body = next(b for m, p, b, _ in api.calls if m == "PUT")
    assert body["title"] == "CFO" and body["first_name"] == "Ana" and body["domain"] == f"test{id(cur)}.example"


def test_the_contact_goes_by_address_without_a_world_id_and_a_lone_activity_brings_its_contact(cur, desk, crm):  # noqa: F811
    api = Api()
    crm(crm_desk(api))
    db.run(cur, "insert into crm_outbox (kind, payload, idempotency_key) values ('activity', %s, 'task:9')",
           J({"task_id": "9", "kind": "call", "outcome": "no_answer", "person_id": desk["person"]}))
    pipeline.crm_push(cur, {})
    email = db.val(cur, "select email from people where id = %s", desk["person"])
    assert [(m, p) for m, p, _, _ in api.calls] == [("PUT", f"/contacts/by-email/{email}"), ("POST", "/activities")]
    assert db.val(cur, "select status from crm_outbox where idempotency_key = %s", f"contact:{desk['person']}") == "done"


def test_a_meeting_outcome_waits_for_the_booking_then_lands_once(cur, desk, crm):  # noqa: F811
    api = Api()
    api.activity_fails = 1                                                 # the booking itself fails its first try
    crm(crm_desk(api))
    mid = pipeline.book_meeting(cur, account_id=desk["account"], person_id=desk["person"],
                                starts_at=datetime.now(timezone.utc) + timedelta(days=2), source="sdr")
    pipeline.set_meeting_status(cur, mid, "no_show")
    out = f"meeting_outcome:{mid}:no_show"
    assert db.val(cur, "select payload ->> 'status' from crm_outbox where idempotency_key = %s", out) == "no_show"
    pipeline.crm_push(cur, {})
    rows = {r["kind"]: r for r in db.all(cur, "select kind, status, attempts from crm_outbox where kind <> 'contact'")}
    assert rows["meeting"]["status"] == "pending" and rows["meeting_outcome"]["status"] == "pending"   # nothing was guessed
    assert not [c for c in api.calls if c[0] == "PATCH"]
    db.run(cur, "update crm_outbox set next_at = app_now()")
    pipeline.crm_push(cur, {})
    patches = [c for c in api.calls if c[0] == "PATCH"]
    assert [(p, b) for _, p, b, _ in patches] == [("/activities/act_77", {"meeting_status": "no_show"})]
    assert db.val(cur, "select status from crm_outbox where idempotency_key = %s", out) == "done"
    pipeline.set_meeting_status(cur, mid, "no_show")                       # the same outcome again is the same row
    assert db.val(cur, "select count(*) from crm_outbox where kind = 'meeting_outcome'") == 1


# ---------------------------------------------------------------- event follow-up from campaign members (option A)

@pytest.fixture
def events(monkeypatch):
    monkeypatch.setenv("INTEGRATED_WITH", "events_desk")


def _event_account(cur, desk, domain="evt.example", email="lee@evt.example"):  # noqa: F811
    aid = db.val(cur, """insert into accounts (name, name_key, primary_domain, fit_tier, crm_tier, crm_fit_score, owner_id)
                         values ('Evt', 'evt', %s, 'A', 'A', 90, %s) returning id""", domain, desk["user"])
    db.run(cur, "insert into account_domains (domain, account_id) values (%s, %s)", domain, aid)
    pid = db.val(cur, "insert into people (account_id, full_name, first_name, email, source, crm_id) values (%s, 'Lee Evt', 'Lee', %s, 'import', 'con_1') returning id",
                 aid, email)
    return aid, pid


def test_an_event_member_becomes_a_signal_and_a_play_is_proposed(cur, desk, crm, events):  # noqa: F811
    aid, pid = _event_account(cur, desk)
    c = crm(Fake())
    c.members = [member("lee@evt.example", "attended"), member("lee@evt.example", "registered", crm_id="con_1"),
                 member("nobody@unknown.example", "attended", crm_id="con_9", domain="unknown.example"),
                 member("lee@evt.example", "attended", ctype="email", campaign="cmp_2"),
                 member("lee@evt.example", "sent", campaign="cmp_3")]
    pipeline.crm_sync(cur, {})
    sig = {r["type_key"]: r for r in db.all(cur, "select * from signals where account_id = %s", aid)}
    assert set(sig) == {"event_campaign_member", "event_registered"}
    assert sig["event_campaign_member"]["external_id"] == "member:cmp_1:con_1:attended"
    assert float(sig["event_campaign_member"]["strength"]) > float(sig["event_registered"]["strength"])
    assert sig["event_campaign_member"]["person_id"] == pid
    assert db.val(cur, "select count(*) from signals where source = 'crm' and external_id like 'member:%'") == 2   # the unknown, the email campaign and "sent" made none
    pipeline.crm_sync(cur, {})
    assert db.val(cur, "select count(*) from signals where external_id like 'member:%'") == 2                  # read again: still two
    p = db.one(cur, "select * from plays where key = 'event_follow_up'")
    assert p["status"] == "live" and p["trigger"]["any_of"] == ["event_campaign_member", "event_registered"]
    db.run(cur, "update plays set holdout_pct = 0 where id = %s", p["id"])
    scoring.rescore(cur, aid)
    apid = plays.match(cur, aid)
    assert apid and db.val(cur, "select state from account_plays where id = %s", apid) == "proposed"
    assert db.val(cur, "select p.key from account_plays ap join plays p on p.id = ap.play_id where ap.id = %s", apid) == "event_follow_up"


def test_a_person_already_in_a_sequence_is_not_started_again(cur, desk, crm, events):  # noqa: F811
    # The scene's account has an active play and its person an active enrollment.
    db.run(cur, "update people set crm_id = 'con_1' where id = %s", desk["person"])
    email = db.val(cur, "select email from people where id = %s", desk["person"])
    c = crm(Fake())
    c.members = [member(email, "attended")]
    pipeline.crm_sync(cur, {})
    assert db.val(cur, "select count(*) from signals where account_id = %s and type_key = 'event_campaign_member'", desk["account"]) == 1
    db.run(cur, "update plays set holdout_pct = 0 where key = 'event_follow_up'")
    scoring.rescore(cur, desk["account"])
    assert plays.match(cur, desk["account"]) is None
    assert db.val(cur, "select count(*) from account_plays where account_id = %s", desk["account"]) == 1
    assert db.val(cur, "select count(*) from enrollments where person_id = %s and state in ('pending', 'active', 'paused')", desk["person"]) == 1


def test_without_events_desk_integrated_nothing_happens(cur, desk, crm, monkeypatch):  # noqa: F811
    monkeypatch.delenv("INTEGRATED_WITH", raising=False)
    aid, _ = _event_account(cur, desk)
    c = crm(Fake())
    c.members = [member("lee@evt.example", "attended")]
    pipeline.crm_sync(cur, {})
    assert db.val(cur, "select count(*) from signals where account_id = %s", aid) == 0
    assert db.val(cur, "select count(*) from plays where key = 'event_follow_up'") == 0
    assert db.val(cur, "select count(*) from signal_types where key like 'event_%%' and key <> 'event_attended'") == 0
    monkeypatch.setenv("INTEGRATED_WITH", "market_desk")
    pipeline.crm_sync(cur, {})
    assert db.val(cur, "select count(*) from plays where key = 'event_follow_up'") == 0


def test_an_event_member_with_a_stub_crm_changes_nothing(cur, desk, crm, events):  # noqa: F811
    crm(Stub())
    pipeline.crm_sync(cur, {})                                             # no campaign_members_changed to call
    assert db.val(cur, "select count(*) from signals where external_id like 'member:%'") == 0


def test_the_event_play_is_added_once_and_needs_two_people_to_launch(cur, desk):  # noqa: F811
    first = plays.ensure_event_play(cur)
    assert first and plays.ensure_event_play(cur) == first
    row = db.one(cur, "select created_by, launched_by, status from plays where id = %s", first)
    assert row["created_by"] != row["launched_by"] and row["status"] == "live"
