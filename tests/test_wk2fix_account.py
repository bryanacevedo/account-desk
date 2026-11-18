# ruff: noqa: F811
"""Integrated week 2, Account Desk fixes (decisions 107 to 115): trace links on outbox rows and messages, a person who
just replied is read first, the CRM gets the reply and closes its Hot reply task, a person's label wins, an SDR puts a
person on Do not contact, a booked meeting can be moved, owners that differ are said, and the small screen fixes.

Database cases roll back (`_rolled_back`); an API case runs its route inside that same transaction by pointing `db.tx`
at it. The web app has no browser harness, so its strings are pinned by reading the source, as in test_simfix.py."""
from __future__ import annotations

import contextlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from outbound import adapters, crmq, db, pipeline, plays, replies, telemetry, views  # noqa: E402
from outbound.adapters import crmdesk  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"


def web(name: str) -> str:
    return (WEB / name).read_text()


class _Back(Exception):
    pass


def _rolled_back(fn):
    try:
        with db.tx() as cur:
            fn(cur)
            raise _Back
    except _Back:
        pass


@pytest.fixture(scope="module")
def client(world):
    from outbound.api.app import app
    return TestClient(app)


@contextlib.contextmanager
def _inside(cur, monkeypatch):
    """Run API routes inside the test's own transaction, which is then rolled back."""
    @contextlib.contextmanager
    def same():
        yield cur
    monkeypatch.setattr(db, "tx", same)
    yield


def _user(cur, role: str, n: int = 0) -> dict:
    return db.all(cur, "select * from users where role = %s and active order by id", role)[n]


def _reply(cur, label: str = "meeting_request") -> dict:
    """A new reply from a person who is in a play, with this label and open (the test rolls back). It is new, so no CRM
    row from the world's own days exists for it."""
    p = db.one(cur, """select p.id, p.email, e.account_play_id from people p join enrollments e on e.person_id = p.id
                       where p.email is not null and p.status = 'active' and p.account_id is not null order by e.id limit 1""")
    rid = replies.ingest(cur, from_addr=p["email"], subject="Re: hello", raw="Yes, send me times for Thursday.",
                         received_at=db.val(cur, "select app_now()"), provider_id=f"wk2fix-{uuid.uuid4().hex}")
    db.run(cur, "update replies set label = %s, hot = %s, classified_by = 'model', confidence = 0.95 where id = %s", label, label in replies.HOT, rid)
    return db.one(cur, "select * from replies where id = %s", rid)


# ---------------------------------------------------------------- decision 110: a person's label wins

def test_relabelling_a_hot_reply_as_not_interested_closes_its_task_audits_it_and_cancels_the_crm_task(world):
    def go(cur):
        r = _reply(cur)
        replies.act(cur, r)
        assert db.val(cur, "select count(*) from tasks where reply_id = %s and kind = 'reply' and status = 'open'", r["id"]) == 1
        assert db.val(cur, "select exists (select 1 from crm_outbox where idempotency_key = %s)", f"task:reply:{r['id']}")
        uid = _user(cur, "sdr")["id"]
        replies.handle(cur, r["id"], user_id=uid, outcome="labelled", label="not_interested")
        after = db.one(cur, "select label, classified_by from replies where id = %s", r["id"])
        assert after == {"label": "not_interested", "classified_by": "person"}
        assert db.val(cur, "select count(*) from tasks where reply_id = %s and kind = 'reply' and status = 'open'", r["id"]) == 0
        assert db.val(cur, "select status from tasks where reply_id = %s and kind = 'reply'", r["id"]) == "skipped"
        a = db.one(cur, "select detail from audit_log where action = 'reply_relabelled' and object_id = %s", r["id"])
        assert a["detail"] == {"from": "meeting_request", "to": "not_interested"}
        close = db.one(cur, "select payload from crm_outbox where idempotency_key = %s", f"task_close:{r['id']}")
        assert close["payload"]["outcome"] == "cancelled"
    _rolled_back(go)


def test_labelling_a_hot_reply_does_not_answer_it_and_a_second_hot_label_leaves_one_open_task(world):
    def go(cur):
        r = _reply(cur)
        replies.act(cur, r)
        uid = _user(cur, "sdr")["id"]
        replies.handle(cur, r["id"], user_id=uid, outcome="labelled", label="interested")
        row = db.one(cur, "select label, handled_at, handled_by from replies where id = %s", r["id"])
        assert row["label"] == "interested" and row["handled_at"] is None and row["handled_by"] is None   # still open
        assert db.val(cur, "select count(*) from tasks where reply_id = %s and kind = 'reply' and status = 'open'", r["id"]) == 1
        assert db.val(cur, "select count(*) from audit_log where action = 'reply_relabelled' and object_id = %s", r["id"]) == 1
        # Saving the same label again changes nothing and still does not close it.
        replies.handle(cur, r["id"], user_id=uid, outcome="labelled", label="interested")
        assert db.val(cur, "select handled_at from replies where id = %s", r["id"]) is None
    _rolled_back(go)


def test_who_may_relabel_what():
    base = {"label": "interested", "needs_review": False, "handled_at": None}
    assert replies.relabel_refusal(base, "not_now") is None and replies.can_relabel(base)
    assert replies.relabel_refusal(base, "interested") is None                       # no change is no refusal
    assert replies.relabel_refusal({**base, "label": None}, "other") is None          # unread
    closed = {**base, "handled_at": datetime(2026, 11, 1, tzinfo=timezone.utc)}
    assert "closed" in replies.relabel_refusal(closed, "not_now") and not replies.can_relabel(closed)
    for kept in ("unsubscribe", "bounce", "left_company"):
        assert "acted for good" in replies.relabel_refusal({**base, "label": kept}, "interested")
        assert not replies.can_relabel({**base, "label": kept})
    flagged = {**base, "label": "unsubscribe", "needs_review": True}                  # nothing acted yet: a person decides
    assert replies.relabel_refusal(flagged, "interested") is None and replies.can_relabel(flagged)


def test_the_api_refuses_relabelling_an_opt_out_and_a_closed_reply(world, client, monkeypatch):
    def go(cur):
        r = _reply(cur, "unsubscribe")
        h = {"X-Acting-As": str(_user(cur, "manager")["id"])}
        with _inside(cur, monkeypatch):
            res = client.post(f"/api/replies/{r['id']}/handle", headers=h, json={"outcome": "labelled", "label": "interested"})
            assert res.status_code == 409 and "acted for good" in res.json()["detail"]
            db.run(cur, "update replies set label = 'not_now', handled_at = app_now() where id = %s", r["id"])
            res = client.post(f"/api/replies/{r['id']}/handle", headers=h, json={"outcome": "labelled", "label": "interested"})
            assert res.status_code == 409 and "closed" in res.json()["detail"]
    _rolled_back(go)


def test_an_unread_reply_cannot_be_answered_from_the_desk(world):
    from outbound import reply_send

    def go(cur):
        r = _reply(cur)
        db.run(cur, "update replies set label = null, hot = false where id = %s", r["id"])
        why = reply_send.refusal(cur, db.one(cur, "select * from replies where id = %s", r["id"]))
        assert why.code == "unread" and "Label it first" in why.message
    _rolled_back(go)


# ---------------------------------------------------------------- decision 109: the CRM gets the reply and closes its task

def test_answering_a_hot_reply_sends_the_reply_to_the_crm_and_closes_its_task(world):
    def go(cur):
        r = _reply(cur)
        replies.act(cur, r)
        uid = _user(cur, "sdr")["id"]
        replies.handle(cur, r["id"], user_id=uid, outcome="answered")
        got = db.one(cur, "select kind, payload from crm_outbox where idempotency_key = %s", f"reply_in:{r['id']}")
        assert got["kind"] == "reply_in" and got["payload"]["reply_id"] == r["id"] and got["payload"]["person_id"] == r["person_id"]
        close = db.one(cur, "select kind, payload from crm_outbox where idempotency_key = %s", f"task_close:{r['id']}")
        assert close["kind"] == "task_close" and close["payload"]["outcome"] == "done" and close["payload"]["note"] == "Answered"
    _rolled_back(go)


def test_booking_a_meeting_from_a_reply_closes_the_task_with_that_note(world, client, monkeypatch):
    def go(cur):
        r = _reply(cur)
        replies.act(cur, r)
        h = {"X-Acting-As": str(_user(cur, "manager")["id"])}
        when = (db.val(cur, "select app_now()") + timedelta(days=3)).isoformat()
        with _inside(cur, monkeypatch):
            res = client.post(f"/api/replies/{r['id']}/handle", headers=h, json={"outcome": "meeting_booked", "meeting_at": when})
            assert res.status_code == 200, res.text
        close = db.one(cur, "select payload from crm_outbox where idempotency_key = %s", f"task_close:{r['id']}")
        assert close["payload"]["note"] == "Meeting booked"
        assert db.val(cur, "select exists (select 1 from crm_outbox where idempotency_key = %s)", f"reply_in:{r['id']}")
        assert res.json()["meeting"]["starts_at"]            # the closed reply says when the meeting is
    _rolled_back(go)


def test_no_close_is_queued_for_a_reply_that_never_made_a_crm_task(world):
    def go(cur):
        r = _reply(cur, "not_now")
        db.run(cur, "delete from crm_outbox where idempotency_key in (%s, %s)", f"task:reply:{r['id']}", f"task_close:{r['id']}")
        replies.handle(cur, r["id"], user_id=_user(cur, "sdr")["id"], outcome="answered")
        assert db.val(cur, "select exists (select 1 from crm_outbox where idempotency_key = %s)", f"reply_in:{r['id']}")
        assert not db.val(cur, "select exists (select 1 from crm_outbox where idempotency_key = %s)", f"task_close:{r['id']}")
    _rolled_back(go)


def _crm(handler):
    return crmdesk.CrmDeskCrm("http://crm.test", "k", client=httpx.Client(base_url="http://crm.test", transport=httpx.MockTransport(handler)))


def _sent_to_crm(cur, kind, payload, key, handler):
    calls = []

    def seen(request):
        calls.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        return handler(request)
    ref = _crm(seen).push(cur, kind, payload, key)
    return ref, calls


def test_the_crm_adapter_closes_the_task_by_its_external_id(world):
    def go(cur):
        r = _reply(cur)
        replies.act(cur, r)
        db.run(cur, "update crm_outbox set status = 'done', payload = payload || '{\"crm_ref\": \"tsk_1\"}' where idempotency_key = %s",
               f"task:reply:{r['id']}")
        payload = {"reply_id": r["id"], "person_id": r["person_id"], "outcome": "done", "note": "Answered"}
        ref, calls = _sent_to_crm(cur, "task_close", payload, f"task_close:{r['id']}",
                                  lambda q: httpx.Response(200, json={"id": "tsk_1", "status": "done"}))
        assert ref == "tsk_1"
        assert calls == [("POST", "/api/v1/tasks/close", {"external_id": f"reply:{r['id']}", "outcome": "done", "note": "Answered"})]
        # An older CRM Desk, or no open task by that id, is a finished write with a note, never an error.
        for status, note in ((404, "skipped:no_open_task"), (405, "skipped:unsupported")):
            ref, _ = _sent_to_crm(cur, "task_close", payload, f"task_close:{r['id']}", lambda q, s=status: httpx.Response(s, json={}))
            assert ref == note
    _rolled_back(go)


def test_the_task_is_closed_only_after_it_reached_the_crm(world):
    def go(cur):
        r = _reply(cur)
        replies.act(cur, r)       # the task row is still pending
        with pytest.raises(crmdesk.CrmDeskUnresolved):
            _sent_to_crm(cur, "task_close", {"reply_id": r["id"], "person_id": r["person_id"]}, "x",
                         lambda q: httpx.Response(200, json={"id": "t"}))
        db.run(cur, "update crm_outbox set status = 'done', payload = payload || '{\"crm_ref\": \"refused:erased\"}' where idempotency_key = %s",
               f"task:reply:{r['id']}")
        ref, calls = _sent_to_crm(cur, "task_close", {"reply_id": r["id"], "person_id": r["person_id"]}, "x",
                                  lambda q: httpx.Response(200, json={"id": "t"}))
        assert ref == "refused:erased" and calls == []
    _rolled_back(go)


def test_the_crm_adapter_sends_what_the_person_wrote_as_an_inbound_email(world):
    def go(cur):
        r = _reply(cur)
        db.run(cur, "update replies set cleaned = 'Yes, Thursday works.', subject = 'Re: hello' where id = %s", r["id"])
        ref, calls = _sent_to_crm(cur, "reply_in", {"reply_id": r["id"], "person_id": r["person_id"]}, f"reply_in:{r['id']}",
                                  lambda q: httpx.Response(201, json={"id": "act_5"}))
        assert ref == "act_5"
        method, path, body = next(c for c in calls if c[1] == "/api/v1/activities")
        assert (method, body["type"], body["direction"], body["body"], body["subject"]) == ("POST", "email", "in", "Yes, Thursday works.", "Re: hello")
        assert body["external_id"] == f"reply_in:{r['id']}" and body["occurred_at"]
    _rolled_back(go)


def test_a_crm_without_these_kinds_finishes_the_row_with_a_note():
    class Old:
        accepts_kinds = {"contact", "meeting_outcome"}

        def push(self, *a):
            raise AssertionError("not asked")
    for kind in ("task_close", "reply_in", "meeting_note"):
        assert pipeline._push(None, Old(), {"kind": kind, "payload": {}, "idempotency_key": "k"}) == "skipped:unsupported"
    assert "task_close" in pipeline.OPTIONAL_KINDS


# ---------------------------------------------------------------- decision 109: the campaign member sync reads contacts in bulk

def _members_api(n_contacts: int, *, batch: str = "ok"):
    calls: list[tuple[str, str, dict | None]] = []
    rows = [{"id": f"m{i}", "campaign_id": "cmp_1", "contact_id": f"con_{i}", "status": "attended",
             "updated_at": "2026-11-01T10:00:00+00:00", "contact_email": None} for i in range(n_contacts)]

    def api(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, path, body))
        if path == "/changes/campaign_members":
            return httpx.Response(200, json={"data": rows, "next": None, "has_more": False})
        if path == "/campaigns/cmp_1":
            return httpx.Response(200, json={"id": "cmp_1", "name": "Summit", "type": "event", "start_date": "2026-08-12", "end_date": "2026-08-13"})
        if path == "/contacts/batch":
            if batch != "ok":
                return httpx.Response(int(batch), json={})
            ids = body["ids"]
            assert len(ids) <= 200
            return httpx.Response(200, json={"contacts": [{"id": i, "email": f"{i}@x.example", "account_domain": "x.example"} for i in ids
                                                          if i != "con_3"], "missing": [i for i in ids if i == "con_3"]})
        if path.startswith("/contacts/con_"):
            cid = path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"id": cid, "email": f"{cid}@x.example", "account_domain": "x.example"})
        return httpx.Response(404, json={})
    return api, calls


def test_campaign_members_read_their_contacts_in_batches_of_200():
    api, calls = _members_api(450)
    out = _crm(api).campaign_members_changed(None, None, 500)
    assert len(out) == 450
    batches = [c for c in calls if c[1] == "/contacts/batch"]
    assert [len(c[2]["ids"]) for c in batches] == [200, 200, 50]
    singles = [c for c in calls if c[1].startswith("/contacts/con_")]
    assert [c[1] for c in singles] == ["/contacts/con_3"]                      # the one the batch called missing
    assert out[0].contact_email == "con_0@x.example" and out[0].account_domain == "x.example"
    assert out[0].event_starts_on == "2026-08-12" and out[0].event_ends_on == "2026-08-13"


@pytest.mark.parametrize("status", ["404", "405"])
def test_a_crm_without_the_batch_route_is_read_one_contact_at_a_time(status):
    api, calls = _members_api(5, batch=status)
    crm = _crm(api)
    out = crm.campaign_members_changed(None, None, 50)
    assert len(out) == 5 and [c[1] for c in calls].count("/contacts/batch") == 1     # asked once, then not again
    assert sorted(c[1] for c in calls if c[1].startswith("/contacts/con_")) == [f"/contacts/con_{i}" for i in range(5)]
    crm.campaign_members_changed(None, None, 50)
    assert [c[1] for c in calls].count("/contacts/batch") == 1


# ---------------------------------------------------------------- decision 108: they replied; read it first

def _held(cur):
    """A person with a draft to approve and a call to make, for whom an unread reply then arrives (the test rolls back)."""
    m = db.one(cur, """select m.id, e.person_id, e.account_play_id, ap.owner_id, p.email from messages m
                       join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
                       join people p on p.id = e.person_id where m.channel = 'email' and ap.owner_id is not null
                       and p.email is not null and p.status = 'active' order by m.id limit 1""")
    assert m is not None, "the world has no email step"
    db.run(cur, "update messages set status = 'awaiting_approval' where id = %s", m["id"])
    task = db.val(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                          values (%s, %s, 'call', 'Call them', app_now(), %s) returning id""", m["account_play_id"], m["person_id"], m["owner_id"])
    return m, task


def _arrives(cur, m) -> int:
    return replies.ingest(cur, from_addr=m["email"], subject="Re: hello", raw="Send me the details.",
                          received_at=db.val(cur, "select app_now()"), provider_id=f"wk2fix-held-{uuid.uuid4().hex}")


def test_a_person_who_just_replied_keeps_no_call_or_draft_until_the_reply_is_read(world):
    def go(cur):
        m, task = _held(cur)
        sdr = db.one(cur, "select * from users where id = %s", m["owner_id"])
        before = views.today(cur, sdr)
        assert m["id"] in [x["id"] for x in before["approvals"]] and task in [x["id"] for x in before["tasks"]]
        n_before = views.badge_counts(cur, sdr)["today"]
        rid = _arrives(cur, m)
        after = views.today(cur, sdr)
        assert m["id"] not in [x["id"] for x in after["approvals"]] and task not in [x["id"] for x in after["tasks"]]
        held = next(x for x in after["read_first"] if x["person_id"] == m["person_id"])
        assert held["reply_id"] == rid and held["tasks_held"] >= 1 and held["drafts_held"] >= 1
        assert views.badge_counts(cur, sdr)["today"] == n_before - 1                  # the badge counts what the list shows
        assert views.task(cur, task)["read_first"] == rid and views.message(cur, m["id"])["read_first"] == rid
        assert views.person(cur, m["person_id"])["read_first"] == rid
        # It cannot be approved or done meanwhile, whoever asks.
        from outbound import outreach, sdr_steps
        with pytest.raises(ValueError, match="They replied; read it first"):
            outreach.approve(cur, m["id"], user_id=sdr["id"])
        with pytest.raises(ValueError, match="They replied; read it first"):
            sdr_steps.complete(cur, task, user=sdr, outcome="skipped")
        # Once a person (or the classifier) labels it, they are back.
        replies.handle(cur, rid, user_id=sdr["id"], outcome="labelled", label="other")
        back = views.today(cur, sdr)
        assert m["id"] in [x["id"] for x in back["approvals"]] and not [x for x in back["read_first"] if x["person_id"] == m["person_id"]]
        assert views.message(cur, m["id"])["read_first"] is None
    _rolled_back(go)


def test_a_reply_flagged_for_a_person_also_holds_them_back(world):
    def go(cur):
        m, task = _held(cur)
        rid = _arrives(cur, m)
        db.run(cur, "update replies set label = 'unsubscribe', needs_review = true, review_reason = 'may opt out' where id = %s", rid)
        assert replies.unread_reply(cur, m["person_id"]) == rid
        db.run(cur, "update replies set needs_review = false where id = %s", rid)
        assert replies.unread_reply(cur, m["person_id"]) is None
        assert replies.unread_reply(cur, None) is None
    _rolled_back(go)


# ---------------------------------------------------------------- decision 111: an SDR puts a person on Do not contact

def test_an_sdr_puts_a_person_on_do_not_contact_with_a_reason(world, client, monkeypatch):
    def go(cur):
        row = db.one(cur, """select p.id, ap.owner_id from people p join account_plays ap on ap.account_id = p.account_id
                             join users u on u.id = ap.owner_id where u.role = 'sdr' and u.active
                             and ap.id = (select x.id from account_plays x where x.account_id = p.account_id
                                          and x.state in ('proposed','accepted','researching','approving','active','engaged','meeting')
                                          order by x.proposed_at desc limit 1) limit 1""")
        h = {"X-Acting-As": str(row["owner_id"])}
        task = db.val(cur, """insert into tasks (person_id, kind, title, due_at, owner_id) values (%s, 'call', 'Call', app_now(), %s) returning id""",
                      row["id"], row["owner_id"])
        with _inside(cur, monkeypatch):
            res = client.post("/api/suppressions", headers=h, json={"kind": "person", "value": str(row["id"]), "reason": "Asked on a call"})
            assert res.status_code == 200, res.text
        s = db.one(cur, "select reason, source from suppressions where kind = 'person' and value = %s", str(row["id"]))
        assert s["reason"] == "Asked on a call" and s["source"] == f"person:{row['owner_id']}"
        assert db.val(cur, "select status from tasks where id = %s", task) == "skipped"
        assert views.person(cur, row["id"])["suppressed"][0]["reason"] == "Asked on a call"
    _rolled_back(go)


def test_an_sdr_cannot_put_another_sdrs_person_on_the_list(world, client, monkeypatch):
    def go(cur):
        row = db.one(cur, """select p.id, ap.owner_id from people p join account_plays ap on ap.account_id = p.account_id
                             join users u on u.id = ap.owner_id where u.role = 'sdr' and u.active
                             and ap.id = (select x.id from account_plays x where x.account_id = p.account_id
                                          and x.state in ('proposed','accepted','researching','approving','active','engaged','meeting')
                                          order by x.proposed_at desc limit 1) limit 1""")
        other = db.val(cur, "select id from users where role = 'sdr' and active and id <> %s limit 1", row["owner_id"])
        with _inside(cur, monkeypatch):
            res = client.post("/api/suppressions", headers={"X-Acting-As": str(other)},
                              json={"kind": "person", "value": str(row["id"]), "reason": "Not mine"})
            assert res.status_code == 403
    _rolled_back(go)


def test_the_person_sheet_has_the_do_not_contact_box_and_the_desk_page_points_to_it():
    sheets = web("sheets.tsx")
    box = sheets[sheets.index("function DoNotContactBox"):sheets.index("/** Erase on request")]
    assert 'api("/api/suppressions", { method: "POST", body: { kind: "person", value: String(personId), reason: reason.trim() } })' in box
    assert "reason.trim().length < 3" in box
    assert "<DoNotContactBox personId={p.id}" in sheets and "data.suppressed.length ? null" in sheets


# ---------------------------------------------------------------- decision 112: move or cancel a booked meeting

def _booked(cur, days: float = 3):
    r = db.one(cur, """select p.id as person_id, p.account_id from people p where p.email is not null and p.account_id is not null limit 1""")
    start = db.val(cur, "select app_now()") + timedelta(days=days)
    mid = pipeline.book_meeting(cur, account_id=r["account_id"], person_id=r["person_id"], starts_at=start, source="sdr",
                                owner_id=_user(cur, "sdr")["id"])
    return mid, start, r


def test_a_booked_meeting_moves_with_a_note_for_the_crm(world):
    def go(cur):
        mid, start, r = _booked(cur)
        uid = _user(cur, "sdr")["id"]
        new = start + timedelta(days=2, hours=1)
        db.run(cur, "update crm_outbox set status = 'done' where idempotency_key = %s", f"meeting:{mid}")   # the booking has reached the CRM
        pipeline.reschedule_meeting(cur, mid, new, uid)
        assert db.val(cur, "select starts_at from meetings where id = %s", mid) == new
        note = db.one(cur, "select kind, payload from crm_outbox where kind = 'meeting_note' and payload->>'meeting_id' = %s", str(mid))
        assert "The meeting moved from" in note["payload"]["text"] and " to " in note["payload"]["text"]
        assert db.val(cur, "select count(*) from audit_log where action = 'meeting_moved' and object_id = %s", mid) == 1
        # The same time again is no change and writes nothing more.
        pipeline.reschedule_meeting(cur, mid, new, uid)
        assert db.val(cur, "select count(*) from crm_outbox where kind = 'meeting_note' and payload->>'meeting_id' = %s", str(mid)) == 1
        with pytest.raises(ValueError, match="has not passed|not passed"):
            pipeline.reschedule_meeting(cur, mid, db.val(cur, "select app_now()") - timedelta(hours=1), uid)
        pipeline.set_meeting_status(cur, mid, "cancelled", user_id=uid)          # cancelling is allowed before it starts
        assert db.val(cur, "select status from meetings where id = %s", mid) == "cancelled"
        with pytest.raises(ValueError, match="not started"):
            pipeline.reschedule_meeting(cur, mid, new + timedelta(days=1), uid)
    _rolled_back(go)


def test_the_meeting_route_moves_it_and_keeps_an_sdr_to_their_own(world, client, monkeypatch):
    def go(cur):
        mid, start, _ = _booked(cur)
        owner = db.val(cur, "select owner_id from meetings where id = %s", mid)
        new = (start + timedelta(days=1)).isoformat()
        with _inside(cur, monkeypatch):
            res = client.post(f"/api/meetings/{mid}/reschedule", headers={"X-Acting-As": str(owner)}, json={"starts_at": new})
            assert res.status_code == 200, res.text
            other = db.val(cur, "select id from users where role = 'sdr' and active and id <> %s limit 1", owner)
            res = client.post(f"/api/meetings/{mid}/reschedule", headers={"X-Acting-As": str(other)}, json={"starts_at": new})
            assert res.status_code == 403
            res = client.post(f"/api/meetings/{mid}/reschedule", headers={"X-Acting-As": str(owner)},
                              json={"starts_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()})
            assert res.status_code == 422
    _rolled_back(go)


def test_the_crm_adapter_writes_a_moved_meeting_as_a_note_on_the_contact(world):
    def go(cur):
        mid, _, r = _booked(cur)
        ref, calls = _sent_to_crm(cur, "meeting_note", {"meeting_id": mid, "person_id": r["person_id"], "key": "20261201T1000",
                                                        "text": "The meeting moved from 1 Dec 2026, 10:00 UTC to 2 Dec 2026, 10:00 UTC."},
                                  f"meeting_note:{mid}:20261201T1000", lambda q: httpx.Response(201, json={"id": "act_9"}))
        body = next(c[2] for c in calls if c[1] == "/api/v1/activities")
        assert ref == "act_9" and body["type"] == "note" and body["subject"] == "Meeting moved" and "moved from" in body["body"]
        assert body["external_id"] == f"meeting_note:{mid}:20261201T1000"
    _rolled_back(go)


def test_the_meeting_sheet_offers_cancel_and_change_the_time_before_it_starts_and_names_the_zone():
    sheets = web("sheets.tsx")
    assert "upcoming ?" in sheets and "Cancel the meeting" in sheets and "Change the time" in sheets
    assert "/api/meetings/${id}/reschedule" in sheets and "New time, your time ({localZone()})" in sheets
    assert 'label="When" sm' in sheets and "dayTimeZ(m.starts_at)" in sheets
    assert "When, your time ({localZone()})" in sheets                       # the reply's booking box and the log box
    lib = web("lib.tsx")
    assert "timeZoneName" in lib and "export function dayTimeZ" in lib and "export function localZone" in lib


# ---------------------------------------------------------------- decision 113: owners, answers, zones, small things

def test_an_account_says_when_the_crm_holds_another_owner(world):
    def go(cur):
        a = db.one(cur, "select id, owner_id from accounts where owner_id is not null limit 1")
        other = db.one(cur, "select id, name, email from users where role = 'sdr' and active and id <> %s limit 1", a["owner_id"])
        mine = db.one(cur, "select email from users where id = %s", a["owner_id"])
        db.run(cur, "update accounts set crm_owner_email = %s where id = %s", other["email"], a["id"])
        d = views.account(cur, a["id"], money=False)["account"]
        assert d["owner_differs"]["crm_owner"] == other["name"] and d["owner_differs"]["here"] == d["owner"]
        assert d["owner_differs"]["here_source"].startswith(("Account owner", "Given this play"))
        db.run(cur, "update accounts set crm_owner_email = %s where id = %s", mine["email"], a["id"])
        assert views.account(cur, a["id"], money=False)["account"]["owner_differs"] is None
        db.run(cur, "update accounts set crm_owner_email = 'someone.else@elsewhere.example' where id = %s", a["id"])
        assert views.account(cur, a["id"], money=False)["account"]["owner_differs"]["crm_owner"] == "someone.else@elsewhere.example"
        db.run(cur, "update accounts set crm_owner_email = null where id = %s", a["id"])
        assert views.account(cur, a["id"], money=False)["account"]["owner_differs"] is None
    _rolled_back(go)


def test_the_account_sheet_says_the_other_owner_and_never_a_bare_profile_version():
    sheets = web("sheets.tsx")
    assert "a.owner_differs" in sheets and "In CRM Desk" in sheets and "Here it is" in sheets
    assert "this desk's own score" in sheets and "from this desk's profile version" not in sheets
    assert "This desk's own score says Tier {a.fit_tier}; the account plan decides." in sheets and "own.toLowerCase()" not in sheets
    assert "plan.toLowerCase()" not in sheets
    assert "Market Desk&rsquo;s tier has not arrived yet." in sheets


def test_an_answer_that_is_queued_leaves_waiting_on_you_and_comes_back_if_it_fails(world):
    def go(cur):
        row = db.one(cur, """select ap.id as ap_id, ap.account_id, ap.owner_id from account_plays ap join plays pl on pl.id = ap.play_id
                             where ap.state in ('accepted','researching','approving','active','engaged','meeting') and ap.arm = 'treated'
                             and exists (select 1 from people p where p.account_id = ap.account_id and p.email is not null) limit 1""")
        person = db.one(cur, "select id from people where account_id = %s and email is not null limit 1", row["account_id"])
        rid = db.val(cur, """insert into replies (person_id, account_id, channel, received_at, from_addr, raw, cleaned, label, hot)
                             values (%s, %s, 'email', app_now(), 'x@y.example', 'hi', 'hi', 'interested', true) returning id""",
                     person["id"], row["account_id"])

        def flight():
            return next(p for p in views.in_flight(cur, {"id": row["owner_id"], "role": "manager"}, mine=False)["plays"] if p["id"] == row["ap_id"])
        assert flight()["reply_id"] == rid and flight()["answer_queued_id"] is None
        send = db.val(cur, """insert into reply_sends (reply_id, user_id, person_id, mailbox_id, subject, body, status)
                              values (%s, %s, %s, (select id from mailboxes limit 1), 'Re: x', 'ok', 'queued') returning id""",
                      rid, row["owner_id"], person["id"])
        assert flight()["reply_id"] is None and flight()["answer_queued_id"] == rid
        db.run(cur, "update reply_sends set status = 'failed' where id = %s", send)
        assert flight()["reply_id"] == rid and flight()["answer_queued_id"] is None
    _rolled_back(go)


def test_a_closed_reply_shows_its_answer_and_the_meeting_time_in_the_sheet():
    sheets = web("sheets.tsx")
    assert '<Section title="Your answer">' in sheets and 'x.status === "sent"' in sheets and "!open && r.studio?.sends" in sheets
    assert "{r.meeting ? `, ${dayTimeZ(r.meeting.starts_at)}` : \"\"}" in sheets
    assert "Answer queued" in web("pages/Flight.tsx")


def test_approving_waits_a_second_before_cmd_enter_counts_and_names_the_next_person():
    sheets = web("sheets.tsx")
    assert "const armedAt = useRef(Date.now() + 1000)" in sheets and "Date.now() >= armedAt.current" in sheets
    assert "`${said} Next: ${out.next}.`" in sheets and 'return `${next.full_name}, ${next.company}`' in sheets
    assert '"Approved. It goes out in their send window."' in sheets and '"Rejected."' in sheets


def test_a_lapsed_proposal_can_be_skipped_with_a_reason(world, client, monkeypatch):
    def go(cur):
        ap = db.one(cur, """select ap.id, ap.owner_id from account_plays ap join plays p on p.id = ap.play_id
                            where ap.state = 'proposed' and ap.arm = 'treated' and p.status = 'live' order by ap.id limit 1""")
        plays.set_state(cur, ap["id"], "expired", reason="expired", cooldown_key="expired")
        sdr = db.one(cur, "select * from users where id = %s", ap["owner_id"])
        assert ap["id"] in [x["id"] for x in views.today(cur, sdr)["expired"]]
        h = {"X-Acting-As": str(ap["owner_id"])}
        with _inside(cur, monkeypatch):
            assert client.post(f"/api/account-plays/{ap['id']}/skip-lapsed", headers=h, json={"reason": "ok"}).status_code == 422   # too short
            res = client.post(f"/api/account-plays/{ap['id']}/skip-lapsed", headers=h, json={"reason": "Wrong time of year"})
            assert res.status_code == 200, res.text
            assert client.post(f"/api/account-plays/{ap['id']}/skip-lapsed", headers=h, json={"reason": "Again please"}).status_code == 409
        assert ap["id"] not in [x["id"] for x in views.today(cur, sdr)["expired"]]
        assert db.val(cur, "select detail->>'reason' from audit_log where action = 'lapsed_skipped' and object_id = %s", ap["id"]) == "Wrong time of year"
    _rolled_back(go)


def test_the_lapsed_note_and_the_hold_agree_and_the_old_date_has_a_year():
    work = web("pages/Work.tsx")
    assert "proposing it again lifts the hold. Skip dismisses it, with a reason." in work and "can be proposed again; its account" not in work
    assert "/api/account-plays/${id}/skip-lapsed" in work
    assert "return dayYear(iso);" in web("lib.tsx")


def test_my_mailbox_says_why_there_are_several_addresses_and_where_the_bounce_check_starts(world, client):
    from outbound import sending
    with db.tx() as cur:
        h = {"X-Acting-As": str(_user(cur, "sdr")["id"])}
    got = client.get("/api/my-mailbox", headers=h).json()
    assert got["bounce_check_from"] == sending.BOUNCE_FLOOR == 50
    desk = web("pages/Desk.tsx")
    assert "from the mailbox that sent them the thread" in desk and "{data.bounce_check_from} emails in 14 days" in desk
    assert 'r["sent"] < BOUNCE_FLOOR' in (ROOT / "src/outbound/sending.py").read_text()


def test_the_acting_as_picker_comes_before_the_clock_controls():
    app = web("App.tsx")
    side = app[app.index('<div className="side-foot">'):app.index("</aside>")]
    assert side.index('className="acting"') < side.index("<Clock me={me} />")
    assert 'timeZoneName: "short"' in app


def test_a_person_sees_their_own_results(world, client):
    with db.tx() as cur:
        sdr = _user(cur, "sdr")["id"]
        n = db.val(cur, "select count(*) from account_plays where owner_id = %s and arm = 'treated'", sdr)
    got = client.get("/api/results", headers={"X-Acting-As": str(sdr)}).json()
    assert got["mine"]["funnel"]["proposed"] == n
    assert set(got["mine"]) == {"funnel", "answered", "median_hours", "meetings"}
    assert '<Section title="Yours">' in web("pages/Desk.tsx")


# ---------------------------------------------------------------- decision 114: an event signal is dated by the event

def _member(status, updated, starts="2026-08-12", ends="2026-08-13"):
    return adapters.CrmCampaignMember(campaign_ref="cmp_1", campaign_name="Summit", campaign_type="event", event_name="Summit", status=status,
                                      contact_email="a@x.example", contact_crm_id="con_1", account_domain="x.example", updated_at=updated,
                                      change_id="m1", event_starts_on=starts, event_ends_on=ends)


def test_attending_is_dated_no_later_than_the_events_last_day():
    late = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)                       # the CRM touched the row months later
    end = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)                         # the end of 13 August
    for status in ("attended", "met", "no_show"):
        assert pipeline._happened_at(_member(status, late)) == end
    # A row touched before the event ended keeps its own time, and so does anything that is not "at the event".
    early = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    assert pipeline._happened_at(_member("attended", early)) == early
    assert pipeline._happened_at(_member("registered", late)) == late and pipeline._happened_at(_member("targeted", late)) == late
    # No dates from the CRM: as before. Only a start date: that day is the end.
    assert pipeline._happened_at(_member("attended", late, starts=None, ends=None)) == late
    assert pipeline._happened_at(_member("attended", late, ends=None)) == datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc)
    assert pipeline._happened_at(_member("attended", late, ends="garbage-in")) == late
    assert pipeline._happened_at(_member("attended", None)) is None


def test_an_attended_signal_is_stored_with_the_event_date_not_the_crm_update(world):
    def go(cur):
        a = db.one(cur, "select id, primary_domain from accounts order by id limit 1")
        m = _member("attended", db.val(cur, "select app_now()") - timedelta(hours=2))   # the CRM touched the row two hours ago
        m.account_domain, m.contact_email, m.contact_crm_id = a["primary_domain"], None, "con_wk2fix_unknown"
        m.campaign_ref = "cmp_wk2fix"
        plays.ensure_event_play(cur)                      # the signal types and play the event feed needs
        made = pipeline.ingest_members(cur, [m])
        assert made == 1
        s = db.one(cur, "select observed_at from signals where external_id like 'member:cmp_wk2fix:%%' order by id desc limit 1")
        assert s["observed_at"] == datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    _rolled_back(go)


# ---------------------------------------------------------------- decision 107: trace links

@pytest.fixture
def tracing(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(telemetry, "_on", True)
    yield provider, exporter


def test_with_tracing_off_nothing_is_stored_and_the_spans_do_nothing(world):
    def go(cur):
        assert telemetry.current_traceparent() is None
        crmq.enqueue(cur, "activity", {"person_id": 1}, "wk2fix-off")
        assert db.val(cur, "select trace_parent from crm_outbox where idempotency_key = 'wk2fix-off'") is None
        with telemetry.linked_span("crm push activity", "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"):
            pass
        assert crmq.enqueue(cur, "activity", {"person_id": 1}, "wk2fix-off") is False        # a second row is ignored
    _rolled_back(go)


def test_an_outbox_row_keeps_the_requests_trace_and_the_push_is_a_linked_span(world, tracing):
    from opentelemetry import trace
    provider, exporter = tracing
    seen = []

    class Crm:
        configured = True

        def push(self, cur, kind, payload, key):
            seen.append(key)
            return "ref_1"
    was = adapters._cached

    def go(cur):
        with provider.get_tracer("test").start_as_current_span("POST /api/replies/1/handle") as request:
            trace_id = f"{request.get_span_context().trace_id:032x}"
            crmq.enqueue(cur, "activity", {"person_id": 1, "type": "email_sent"}, "wk2fix-linked")
        stored = db.val(cur, "select trace_parent from crm_outbox where idempotency_key = 'wk2fix-linked'")
        assert stored and stored.split("-")[1] == trace_id
        assert trace.get_current_span().get_span_context().trace_id == 0           # the worker is outside any request
        a = adapters.get()
        adapters.override(adapters.Adapters(**{**a.__dict__, "crm": Crm()}))
        try:
            pipeline.crm_push(cur, {})
        finally:
            adapters.override(was)
        assert "wk2fix-linked" in seen
        push = next(s for s in exporter.get_finished_spans() if s.name == "crm push activity")
        assert [f"{link.context.trace_id:032x}" for link in push.links] == [trace_id]    # kept as a link
        assert push.parent is not None and f"{push.context.trace_id:032x}" == trace_id   # and the request is its parent: one trace
    _rolled_back(go)


def test_an_approved_message_keeps_the_approving_requests_trace_and_the_send_check_links_to_it(world, tracing):
    provider, exporter = tracing

    class Crm:
        configured = True

        def push(self, cur, kind, payload, key):
            return "r"

        def contactability(self, cur, items):
            return [{"can_email": True, "can_call": True, "flags": [], "suppressed": False, "erased": False} for _ in items]
    was = adapters._cached

    def go(cur):
        m, _ = _held(cur)
        sdr = _user(cur, "manager")
        db.run(cur, "delete from crm_contact_checks where person_id = %s", m["person_id"])
        with provider.get_tracer("test").start_as_current_span("POST /api/messages/1/approve") as request:
            trace_id = f"{request.get_span_context().trace_id:032x}"
            from outbound import outreach
            outreach.approve(cur, m["id"], user_id=sdr["id"])
        stored = db.val(cur, "select trace_parent from messages where id = %s", m["id"])
        assert stored and stored.split("-")[1] == trace_id
        a = adapters.get()
        adapters.override(adapters.Adapters(**{**a.__dict__, "crm": Crm()}))
        try:
            assert pipeline.crm_first_touch(cur, m["person_id"], "email", trace_parent=stored) == "ok"
        finally:
            adapters.override(was)
        check = next(s for s in exporter.get_finished_spans() if s.name == "crm contactability")
        assert [f"{link.context.trace_id:032x}" for link in check.links] == [trace_id]
    _rolled_back(go)


def test_the_send_passes_the_messages_trace_to_the_crm_check():
    assert "telemetry.current_traceparent()" in (ROOT / "src/outbound/outreach.py").read_text()
    sql = (ROOT / "migrations/0043_trace_parent_outbox_messages.sql").read_text()
    assert "crm_outbox add column if not exists trace_parent text" in sql and "messages add column if not exists trace_parent text" in sql


# ---------------------------------------------------------------- the replayed demo build keeps working

def test_the_recorded_crm_finishes_the_new_kinds_with_a_note_unless_its_journal_has_them():
    from outbound.adapters.recorded import RecordedCrm
    old = RecordedCrm([{"actor": "account_desk", "method": "POST", "path": "/activities", "body": {"type": "email", "direction": "out"}, "status": 200,
                        "answer": {"id": "a"}}])
    assert old.accepts_kinds == {"contact", "meeting_outcome"} and old._crm.bulk_contacts is False
    new = RecordedCrm([{"actor": "account_desk", "method": "POST", "path": "/tasks/close", "body": {}, "status": 200, "answer": {}},
                       {"actor": "account_desk", "method": "POST", "path": "/contacts/batch", "body": {}, "status": 200, "answer": {}},
                       {"actor": "account_desk", "method": "POST", "path": "/activities", "body": {"type": "email", "direction": "in"}, "status": 200, "answer": {}}])
    assert {"task_close", "reply_in"} <= new.accepts_kinds and "meeting_note" not in new.accepts_kinds and new._crm.bulk_contacts is True


# ---------------------------------------------------------------- decision 115: product facts a reply may state

def test_a_reply_may_state_a_product_fact_the_desks_facts_say():
    from outbound.copy_gate import check_suggestion
    theirs = "How long does the rollout take, and do you integrate with NetSuite?"
    body = "Setup takes 12 weeks, and we connect natively to NetSuite."
    assert {x["code"] for x in check_suggestion(body, theirs)} == {"invented_number", "product_claim"}
    facts = ["Setup takes 12 weeks.", "We connect natively to NetSuite."]
    assert check_suggestion(body, theirs, facts) == []
    # Other product claims and other numbers are still invention.
    found = check_suggestion("We are SOC 2 certified and setup takes 60 weeks.", theirs, facts)
    assert {x["code"] for x in found} == {"invented_number", "product_claim"}


def test_facts_reach_the_model_after_the_cache_breakpoint_and_only_when_there_are_some(world, monkeypatch):
    from outbound import llm
    plain = llm.system_blocks("suggest_reply", {"label": "question"})
    assert plain == llm.system_blocks("suggest_reply") and len(plain) == 1 and plain[0]["cache_control"] == {"type": "ephemeral"}
    withf = llm.system_blocks("suggest_reply", {"product_facts": ["Setup takes 12 weeks."]})
    assert withf[0] == plain[0] and withf[1] == {"type": "text", "text": llm.PRODUCT_FACTS_NOTE}
    assert "Setup takes 12 weeks." not in json.dumps(withf)             # the facts are in the user message, not before the breakpoint
    seen = []

    def fake(cur, task, payload, **kw):
        seen.append(payload)
        return {"body": "Setup takes 12 weeks. Want a call on Thursday at 10:00?"}

    def go(cur):
        db.run(cur, "insert into settings (key, value) values ('product_facts', %s) on conflict (key) do update set value = excluded.value",
               db.J(["Setup takes 12 weeks."]))
        monkeypatch.setattr(llm, "run", fake)
        out = replies.suggest(cur, "question", "How long is the rollout?", "Elif")
        assert out and seen[0]["product_facts"] == ["Setup takes 12 weeks."]
        db.run(cur, "delete from settings where key = 'product_facts'")
        seen.clear()
        assert replies.suggest(cur, "question", "How long is the rollout?", "Elif") is None      # the 4 weeks is invented now
        assert "product_facts" not in seen[0]
    _rolled_back(go)


def test_only_a_manager_or_gtm_keeps_the_product_facts_and_anyone_reads_them(world, client, monkeypatch):
    def go(cur):
        with _inside(cur, monkeypatch):
            mgr = {"X-Acting-As": str(_user(cur, "manager")["id"])}
            sdr = {"X-Acting-As": str(_user(cur, "sdr")["id"])}
            assert client.put("/api/product-facts", headers=sdr, json={"facts": ["Setup takes 12 weeks."]}).status_code == 403
            assert client.put("/api/product-facts", headers=mgr, json={"facts": ["Pick [a number]."]}).status_code == 422
            assert client.put("/api/product-facts", headers=mgr, json={"facts": ["x" * 301]}).status_code == 422
            res = client.put("/api/product-facts", headers=mgr, json={"facts": ["  Setup takes   12 weeks. ", "", "Data stays in the EU."]})
            assert res.status_code == 200 and res.json()["facts"] == ["Setup takes 12 weeks.", "Data stays in the EU."]
            assert client.get("/api/product-facts", headers=sdr).json()["facts"] == ["Setup takes 12 weeks.", "Data stays in the EU."]
            assert db.val(cur, "select count(*) from audit_log where action = 'product_facts_set'") >= 1
    _rolled_back(go)


def test_settings_keeps_the_facts_and_the_composer_shows_what_it_may_state():
    desk = web("pages/Desk.tsx")
    assert 'function ProductFacts' in desk and 'api("/api/product-facts", { method: "PUT"' in desk and "<ProductFacts canEdit=" in desk
    assert "May state: {studio.product_facts.join" in web("sheets.tsx")


# ---------------------------------------------------------------- the review's fixes

def test_an_automatic_approval_waits_while_the_person_has_an_unread_reply(world):
    from outbound import outreach

    def go(cur):
        m, _ = _held(cur)
        db.run(cur, "update plays set autonomy = 'autonomous' where id = (select ap.play_id from account_plays ap where ap.id = %s)", m["account_play_id"])
        db.run(cur, "update accounts set fit_tier = 'B' where id = (select account_id from account_plays where id = %s)", m["account_play_id"])
        rid = _arrives(cur, m)
        assert outreach.maybe_auto_approve(cur, m["id"]) is False
        assert db.val(cur, "select status from messages where id = %s", m["id"]) == "awaiting_approval"
        replies.handle(cur, rid, user_id=_user(cur, "sdr")["id"], outcome="labelled", label="other")
        assert outreach.maybe_auto_approve(cur, m["id"]) is True
    _rolled_back(go)


def test_a_meeting_moved_before_its_booking_reaches_the_crm_sends_the_new_time(world):
    def go(cur):
        mid, start, _ = _booked(cur)
        uid = _user(cur, "sdr")["id"]
        new = start + timedelta(days=2)
        assert db.val(cur, "select status from crm_outbox where idempotency_key = %s", f"meeting:{mid}") == "pending"
        pipeline.reschedule_meeting(cur, mid, new, uid)
        assert db.val(cur, "select payload->>'starts_at' from crm_outbox where idempotency_key = %s", f"meeting:{mid}") == new.isoformat()
        assert db.val(cur, "select count(*) from crm_outbox where kind = 'meeting_note' and payload->>'meeting_id' = %s", str(mid)) == 0
        # Once the booking is delivered, a move is a note; moving back and forth is three notes, not two.
        db.run(cur, "update crm_outbox set status = 'done' where idempotency_key = %s", f"meeting:{mid}")
        pipeline.reschedule_meeting(cur, mid, start, uid)
        pipeline.reschedule_meeting(cur, mid, new, uid)
        pipeline.reschedule_meeting(cur, mid, start, uid)
        assert db.val(cur, "select count(*) from crm_outbox where kind = 'meeting_note' and payload->>'meeting_id' = %s", str(mid)) == 3
    _rolled_back(go)


def test_the_approvals_count_leaves_out_held_drafts(world, client, monkeypatch):
    def go(cur):
        m, _ = _held(cur)
        h = {"X-Acting-As": str(m["owner_id"])}
        with _inside(cur, monkeypatch):
            before = client.get("/api/me", headers=h).json()["counts"]["approvals"]
            _arrives(cur, m)
            assert client.get("/api/me", headers=h).json()["counts"]["approvals"] == before - 1
    _rolled_back(go)


def test_a_naive_time_for_a_move_is_a_422_not_a_500(world, client):
    with db.tx() as cur:
        h = {"X-Acting-As": str(_user(cur, "sdr")["id"])}
    assert client.post("/api/meetings/1/reschedule", headers=h, json={"starts_at": "2030-01-01T10:00:00"}).status_code == 422


def test_a_linkedin_reply_goes_to_the_crm_as_a_linkedin_message(world):
    def go(cur):
        r = _reply(cur)
        db.run(cur, "update replies set channel = 'linkedin' where id = %s", r["id"])
        ref, calls = _sent_to_crm(cur, "reply_in", {"reply_id": r["id"], "person_id": r["person_id"]}, f"reply_in:{r['id']}",
                                  lambda q: httpx.Response(201, json={"id": "act_6"}))
        body = next(c[2] for c in calls if c[1] == "/api/v1/activities")
        assert body["type"] == "linkedin" and body["direction"] == "in"
    _rolled_back(go)


def test_labelling_an_unread_reply_is_audited(world):
    def go(cur):
        r = _reply(cur)
        db.run(cur, "update replies set label = null, hot = false where id = %s", r["id"])
        replies.handle(cur, r["id"], user_id=_user(cur, "sdr")["id"], outcome="labelled", label="other")
        assert db.one(cur, "select detail from audit_log where action = 'reply_labelled' and object_id = %s", r["id"])["detail"] == {"from": None, "to": "other"}
    _rolled_back(go)
