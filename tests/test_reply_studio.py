# ruff: noqa: F811  (fixtures shared from test_api are named as parameters)
"""Reply studio (bl_121, decision 90): answering a reply from the desk goes through its own guard, its own reasons and
the same mailbox and domain caps as any send."""
from __future__ import annotations

import dataclasses

import psycopg
import pytest
from test_api import client  # noqa: F401  the shared app client (world fixture)

from outbound import db, outreach, reply_send, views


class _Back(Exception):
    pass


def _rolled_back(fn):
    try:
        with db.tx() as cur:
            fn(cur)
            raise _Back
    except _Back:
        pass


def _answerable(cur, label="meeting_request"):
    """A reply a person may answer: put the world's first suitable one back to unanswered (the test rolls back)."""
    for r in db.all(cur, """select r.id from replies r join people p on p.id = r.person_id
                            where p.email is not null and p.status = 'active' and r.account_id is not null order by r.id limit 60"""):
        db.run(cur, "update replies set label = %s, needs_review = false, review_reason = null, same_person = true, "
                    "handled_at = null, outcome = null, cleaned = 'Can we find a time next week to talk?' where id = %s", label, r["id"])
        full = views.reply(cur, r["id"])
        db.run(cur, "delete from suppressions where kind in ('email', 'person', 'account', 'domain')")
        db.run(cur, "update people set country = 'US' where id = %s", full["person_id"])
        if reply_send.refusal(cur, full) is None:
            return views.reply(cur, r["id"])
    return None


def _sdr_of(cur, r):
    return {"id": reply_send.owner_of(cur, r) or db.val(cur, "select id from users where role = 'sdr' limit 1")}


def test_a_reply_that_asks_to_stop_or_is_automatic_cannot_be_answered(world):
    def go(cur):
        r = _answerable(cur)
        assert r is not None
        for label in ("unsubscribe", "bounce", "out_of_office", "auto_reply"):
            assert reply_send.refusal(cur, {**r, "label": label}).code == "label"
        assert reply_send.refusal(cur, {**r, "cleaned": "Please stop emailing me. But sure, thanks."}).code == "asked_to_stop"
        assert reply_send.refusal(cur, {**r, "needs_review": True, "review_reason": "They may want to opt out"}).code == "asked_to_stop"
        assert reply_send.refusal(cur, {**r, "needs_review": True, "review_reason": "Unclear"}).code == "needs_review"
        assert reply_send.refusal(cur, {**r, "same_person": False}).code == "someone_else"
        with pytest.raises(ValueError):
            reply_send.queue(cur, {**r, "label": "unsubscribe"}, _sdr_of(cur, r), "Thanks, noted.")
    _rolled_back(go)


def test_suppression_a_blocked_country_and_the_kill_switch_refuse_it(world):
    def go(cur):
        r = _answerable(cur)
        person = db.one(cur, "select * from people where id = %s", r["person_id"])
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email', %s, 'test', 'test')", person["email"])
        assert reply_send.refusal(cur, r).code == "suppressed"
        db.run(cur, "delete from suppressions where kind = 'email'")
        db.run(cur, "set local session_replication_role = replica")  # a rule change needs its history row; this is not that test
        db.run(cur, "update region_rules set rule = 'blocked' where country = %s", person["country"])
        assert reply_send.refusal(cur, r).code == "region_blocked"
        db.run(cur, "update region_rules set rule = 'allowed' where country = %s", person["country"])
        db.run(cur, "set local session_replication_role = origin")
        db.run(cur, "update settings set value = 'true'::jsonb where key = 'kill_switch'")
        assert reply_send.refusal(cur, r).code == "kill_switch"
    _rolled_back(go)


def test_a_sent_answer_uses_the_sdrs_mailbox_marks_the_reply_answered_and_is_idempotent(world):
    def go(cur):
        r = _answerable(cur)
        user = _sdr_of(cur, r)
        text = "Thanks. Tuesday at 10:00 or Wednesday at 14:00 your time both work on my side."
        row = reply_send.queue(cur, r, user, text)
        again = reply_send.queue(cur, r, user, text)
        assert row["id"] == again["id"] and row["status"] == "queued"
        assert db.val(cur, "select user_id from mailboxes where id = %s", row["mailbox_id"]) == user["id"]
        assert "To stop hearing from us" in row["body"] and row["subject"].startswith("Re: ")
        reply_send.send_reply(cur, {"reply_send_id": row["id"]})
        assert db.val(cur, "select status from reply_sends where id = %s", row["id"]) == "sending"
        reply_send.send_reply_provider(cur, {"reply_send_id": row["id"]})
        done = db.one(cur, "select * from reply_sends where id = %s", row["id"])
        assert done["status"] == "sent" and done["provider_id"]
        after = db.one(cur, "select outcome, handled_at from replies where id = %s", r["id"])
        assert after["outcome"] == "answered" and after["handled_at"]
        assert db.val(cur, "select count(*) from audit_log where action = 'reply_sent' and object_id = %s", r["id"]) == 1
        assert outreach.sent_today(cur, row["mailbox_id"]) >= 1
    _rolled_back(go)


def test_the_guard_counts_reply_sends_in_the_mailbox_and_domain_caps_and_refuses_a_late_unsubscribe(world):
    def go(cur):
        r = _answerable(cur)
        user = _sdr_of(cur, r)
        row = reply_send.queue(cur, r, user, "Thanks, happy to talk.")
        mb = row["mailbox_id"]
        cap = int(db.val(cur, "select mailbox_cap(%s)", mb))
        before = outreach.sent_today(cur, mb)
        for i in range(max(0, cap - before)):  # fill today's cap with answers already sent
            db.run(cur, """insert into reply_sends (reply_id, user_id, person_id, mailbox_id, subject, body, status, sent_at)
                           values (%s,%s,%s,%s,'Re: x',%s,'sent',app_now())""", r["id"], user["id"], r["person_id"], mb, f"filler {i}")
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            with cur.connection.transaction():
                db.run(cur, "update reply_sends set status = 'sending', sent_at = app_now() where id = %s", row["id"])
        assert "daily cap" in str(exc.value)
        # A late label: the guard and the job refuse it though the row was queued while the reply was fine.
        db.run(cur, "delete from reply_sends where body like 'filler %'")
        db.run(cur, "update replies set label = 'unsubscribe' where id = %s", r["id"])
        with pytest.raises(psycopg.errors.RaiseException):
            with cur.connection.transaction():
                db.run(cur, "update reply_sends set status = 'sending', sent_at = app_now() where id = %s", row["id"])
        reply_send.send_reply(cur, {"reply_send_id": row["id"]})
        assert db.val(cur, "select status from reply_sends where id = %s", row["id"]) == "cancelled"
    _rolled_back(go)


def test_the_message_guard_counts_a_reply_send_toward_the_same_cap(world):
    def go(cur):
        r = _answerable(cur)
        user = _sdr_of(cur, r)
        row = reply_send.queue(cur, r, user, "Thanks, happy to talk.")
        mb = row["mailbox_id"]
        cap = int(db.val(cur, "select mailbox_cap(%s)", mb))
        sent = outreach.sent_today(cur, mb)
        assert sent == db.val(cur, "select count(*) from messages where mailbox_id = %s and status in ('sent','sending','send_unknown') "
                                   "and sent_at >= date_trunc('day', app_now())", mb)
        db.run(cur, """insert into reply_sends (reply_id, user_id, person_id, mailbox_id, subject, body, status, sent_at)
                       values (%s,%s,%s,%s,'Re: x','one more','sent',app_now())""", r["id"], user["id"], r["person_id"], mb)
        assert outreach.sent_today(cur, mb) == sent + 1 and cap >= 1
        # And the message guard in the database counts them in both caps, so a first email cannot slip past an answer.
        src = db.val(cur, "select prosrc from pg_proc where proname = 'message_send_guard'")
        assert src.count("reply_sends") == 2
    _rolled_back(go)


def test_refine_is_capped_and_checked(world):
    def go(cur):
        r = _answerable(cur)
        out = reply_send.refine(cur, r, "shorter", "Thanks for the note. Happy to find a time that suits you next week.")
        assert out["body"] and "problems" in out and out["refines_left"] == reply_send.MAX_REFINES - 1
        db.run(cur, "update replies set extracted = jsonb_set(extracted, '{_refines}', '10') where id = %s", r["id"])
        with pytest.raises(ValueError):
            reply_send.refine(cur, r, "shorter", "x")
    _rolled_back(go)


def test_routes_roles_public_demo_and_the_check(client, world, monkeypatch):
    with db.tx() as cur:
        r = db.one(cur, "select id, label, needs_review, review_reason from replies where account_id is not null and person_id is not null order by id limit 1")
        db.run(cur, "update replies set label = 'unsubscribe', needs_review = false, review_reason = null where id = %s", r["id"])
        owner = reply_send.owner_of(cur, views.reply(cur, r["id"]))
        other = db.val(cur, "select id from users where role = 'sdr' and id <> %s limit 1", owner)
        manager = db.val(cur, "select id from users where role = 'manager' limit 1")
    try:
        assert client.post(f"/api/replies/{r['id']}/send", json={"body": "Thanks"}, headers={"X-Acting-As": str(other)}).status_code == 403
        assert client.post(f"/api/replies/{r['id']}/send", json={"body": "Thanks"}, headers={"X-Acting-As": str(manager)}).status_code == 409
        ok = client.post(f"/api/replies/{r['id']}/check", json={"body": "Our plan costs $4,000 a month."}, headers={"X-Acting-As": str(manager)})
        assert ok.status_code == 200 and ok.json()["problems"]
        page = client.get(f"/api/replies/{r['id']}", headers={"X-Acting-As": str(manager)}).json()
        assert page["studio"]["can_send"] is False and page["studio"]["no_send"]["code"] == "label"
        from outbound.api import app as api
        monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, public_demo=True))
        assert client.post(f"/api/replies/{r['id']}/send", json={"body": "Thanks"}, headers={"X-Acting-As": str(manager)}).status_code == 403
        assert client.post(f"/api/replies/{r['id']}/check", json={"body": "Thanks"}, headers={"X-Acting-As": str(manager)}).status_code == 200
    finally:
        with db.tx() as cur:
            db.run(cur, "update replies set label = %s, needs_review = %s, review_reason = %s where id = %s",
                   r["label"], r["needs_review"], r["review_reason"], r["id"])


def test_a_failed_answer_can_be_sent_again_and_a_second_text_waits_for_the_first(world):
    def go(cur):
        r = _answerable(cur)
        user = _sdr_of(cur, r)
        row = reply_send.queue(cur, r, user, "Thanks, happy to talk.")
        with pytest.raises(ValueError):
            reply_send.queue(cur, r, user, "A different answer that says something else entirely.")
        db.run(cur, "update reply_sends set status = 'failed', error = 'provider down' where id = %s", row["id"])
        again = reply_send.queue(cur, r, user, "Thanks, happy to talk.")
        assert again["id"] == row["id"] and again["status"] == "queued" and again["error"] is None
    _rolled_back(go)


def test_a_bounced_address_and_a_newer_unread_message_hold_the_answer(world):
    def go(cur):
        r = _answerable(cur)
        db.run(cur, "update people set email_status = 'invalid', email_verified_at = app_now() where id = %s", r["person_id"])
        assert reply_send.refusal(cur, r).code == "address_invalid"
        db.run(cur, "update people set email_status = 'unknown', email_verified_at = null where id = %s", r["person_id"])
        assert reply_send.refusal(cur, r) is None
        db.run(cur, """insert into replies (person_id, account_id, received_at, from_addr, raw, cleaned, label)
                       values (%s, %s, %s, 'x@x.example', 'Stop writing to me', 'Stop writing to me', null)""",
               r["person_id"], r["account_id"], r["received_at"] + __import__("datetime").timedelta(hours=1))
        assert reply_send.refusal(cur, r).code == "newer_reply"
        row_text = "Thanks, happy to talk."
        with pytest.raises(ValueError):
            reply_send.queue(cur, r, _sdr_of(cur, r), row_text)
    _rolled_back(go)
