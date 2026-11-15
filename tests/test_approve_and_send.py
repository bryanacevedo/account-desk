# ruff: noqa: F811  (fixtures shared from test_api are named as parameters)
"""Approve and send (bl_122, decision 88): the slot the sheet shows is the slot approve gives, the dry run is the same
check without a write, and the first edit keeps the original text for per-change restore."""
from __future__ import annotations

import pytest
from test_api import client  # noqa: F401  the shared app client (world fixture)

from outbound import db, gate, outreach, views


class _Back(Exception):
    pass


def _awaiting(cur, *, pending_first: bool = True, staggered: bool | None = None):
    """An email waiting for approval. The finished world has none (its reps approve everything), so one is put back:
    a step-0 email of an enrollment that starts again as pending, at an account with (or without) a colleague already
    underway. Only ever called inside a transaction the test rolls back."""
    rows = db.all(cur, """select m.id, e.id as enrollment_id, ap.account_id, ap.owner_id,
                                 (select count(*) from enrollments x join account_plays y on y.id = x.account_play_id
                                  where y.account_id = ap.account_id and x.id <> e.id and x.started_at is not null) as others,
                                 (select min(x.id) from enrollments x join account_plays y on y.id = x.account_play_id
                                  where y.account_id = ap.account_id and x.id <> e.id) as any_other
                          from messages m join enrollments e on e.id = m.enrollment_id
                          join account_plays ap on ap.id = e.account_play_id join people pe on pe.id = e.person_id
                          where m.channel = 'email' and m.step_index = 0 and ap.owner_id is not null
                            and pe.email is not null and pe.email_status = 'valid'
                            and m.status in ('scheduled', 'sent') order by m.id""")
    for r in rows:
        pid = db.val(cur, "select person_id from enrollments where id = %s", r["enrollment_id"])
        db.run(cur, "delete from touches where person_id = %s", pid)  # the cooldown reads what we already sent them
        db.run(cur, "update enrollments set state = 'done' where person_id = %s and id <> %s and state in ('active', 'paused', 'pending')",
               pid, r["enrollment_id"])
        if any(x.permanent for x in gate.person_reasons(cur, pid, "email")):
            continue
        if staggered is True and not r["any_other"]:
            continue
        db.run(cur, "update enrollments set state = 'pending', started_at = null, next_at = null, step_index = 0 where id = %s",
               r["enrollment_id"])
        db.run(cur, "update messages set status = 'awaiting_approval', scheduled_for = null, planned_for = null, sent_at = null, "
                    "approved_at = null, approved_by = null where id = %s", r["id"])
        if staggered is False:  # nobody else at the account has started: take the others out (the test rolls back)
            db.run(cur, "set local session_replication_role = replica")
            db.run(cur, "delete from messages where enrollment_id in (select x.id from enrollments x join account_plays y on y.id = x.account_play_id "
                        "where y.account_id = %s and x.id <> %s)", r["account_id"], r["enrollment_id"])
            db.run(cur, "delete from enrollments x using account_plays y where y.id = x.account_play_id and y.account_id = %s and x.id <> %s",
                   r["account_id"], r["enrollment_id"])
            db.run(cur, "set local session_replication_role = origin")
        if staggered:  # a colleague at the account who started today: this one waits two business days behind them
            db.run(cur, "update enrollments set started_at = app_now(), state = 'active' where id = %s", r["any_other"])
        return {**r, "state": "pending", "step_index": 0}
    return None


def _rolled_back(fn):
    try:
        with db.tx() as cur:
            fn(cur)
            raise _Back
    except _Back:
        pass


@pytest.mark.parametrize("staggered", [False, True])
def test_the_slot_in_the_payload_is_the_slot_approve_writes(world, staggered):
    def go(cur):
        m = _awaiting(cur, staggered=staggered)
        if m is None:
            pytest.skip("this world has no such message to put back")
        shown = views.message(cur, m["id"])
        assert shown["next_slot"] is not None and shown["slot_label"]["recipient_first_name"]
        outreach.approve(cur, m["id"], user_id=m["owner_id"])
        got = db.one(cur, "select status, scheduled_for from messages where id = %s", m["id"])
        assert got["status"] == "scheduled"
        assert got["scheduled_for"] == shown["next_slot"]
    _rolled_back(go)


def test_the_dry_run_returns_what_approve_refuses_and_writes_nothing(world):
    def go(cur):
        m = _awaiting(cur)
        before = db.one(cur, "select subject, body, edited, original_body from messages where id = %s", m["id"])
        text = before["body"].replace("\n\n--\n", " Join us at https://example.com now, free of charge \u2014 act today.\n\n--\n", 1)
        r = outreach.check_edit(cur, m["id"], None, text)
        assert db.one(cur, "select subject, body, edited, original_body from messages where id = %s", m["id"]) == before
        assert not before["edited"] and r["problems"] and r["limit"][0] < r["limit"][1]
        with pytest.raises(ValueError) as exc:
            outreach.approve(cur, m["id"], user_id=m["owner_id"], body=text)
        assert "; ".join(r["problems"]) == str(exc.value)
    _rolled_back(go)


def test_the_word_limit_and_a_removed_footer_are_named(world):
    def go(cur):
        m = _awaiting(cur)
        body = db.val(cur, "select body from messages where id = %s", m["id"])
        short = outreach.check_edit(cur, m["id"], None, "Hi,\n\nOk.\n\nName\n\n--\nx")
        nofooter = outreach.check_edit(cur, m["id"], None, body.split("\n\n--\n")[0])
        assert any("words; this step needs" in p for p in short["problems"])
        assert any("opt-out line" in p for p in nofooter["problems"])
        assert not any("words; this step needs" in p for p in outreach.check_edit(cur, m["id"], None, body)["problems"])
    _rolled_back(go)


def test_the_first_edit_keeps_the_original_and_a_second_does_not_overwrite_it(world):
    def go(cur):
        m = _awaiting(cur)
        was = db.one(cur, "select subject, body from messages where id = %s", m["id"])
        paras = was["body"].split("\n\n")
        edited = "\n\n".join(paras[:1] + [paras[1] + " Short one."] + paras[2:])
        outreach.approve(cur, m["id"], user_id=m["owner_id"], body=edited)
        row = db.one(cur, "select original_subject, original_body, edited from messages where id = %s", m["id"])
        assert row["edited"] and row["original_body"] == was["body"] and row["original_subject"] == was["subject"]
        db.run(cur, "update messages set status = 'awaiting_approval' where id = %s", m["id"])
        outreach.approve(cur, m["id"], user_id=m["owner_id"], body=edited.replace("Short one.", "Short."))
        assert db.val(cur, "select original_body from messages where id = %s", m["id"]) == was["body"]
    _rolled_back(go)


def test_check_route_roles_and_state(client, world):
    with db.tx() as cur:
        m = db.one(cur, """select m.id, m.status, m.scheduled_for, m.body, ap.owner_id from messages m
                           join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
                           where m.channel = 'email' and m.status in ('scheduled', 'sent') and ap.owner_id is not null limit 1""")
        other = db.val(cur, "select id from users where role = 'sdr' and id <> %s limit 1", m["owner_id"])
        body = m["body"]
    as_owner, as_other = {"X-Acting-As": str(m["owner_id"])}, {"X-Acting-As": str(other)}
    assert client.post(f"/api/messages/{m['id']}/check", json={"body": body}, headers=as_other).status_code == 403
    assert client.post(f"/api/messages/{m['id']}/check", json={"body": body}, headers=as_owner).status_code == 409
    try:
        with db.tx() as cur:
            db.run(cur, "set local session_replication_role = replica")  # the send guard would refuse a stopped enrollment
            db.run(cur, "update messages set status = 'awaiting_approval' where id = %s", m["id"])
        ok = client.post(f"/api/messages/{m['id']}/check", json={"body": body}, headers=as_owner)
        assert ok.status_code == 200 and set(ok.json()) == {"problems", "words", "limit"}
    finally:
        with db.tx() as cur:
            db.run(cur, "set local session_replication_role = replica")
            db.run(cur, "update messages set status = %s where id = %s", m["status"], m["id"])
