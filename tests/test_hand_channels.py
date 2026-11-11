"""LinkedIn and calls as real channels: drafted through the same checks, sent through the same guard, every outcome a
touch, and nobody emailed after engaging elsewhere (guarantee 20)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from test_guarantees import refused, scene  # noqa: F401  (the scene fixture: an approved email ready to send)

from outbound import copy_gate, db, sdr_steps


def q(sql, *args):
    with db.tx() as cur:
        return db.all(cur, sql, *args)


def v(sql, *args):
    with db.tx() as cur:
        return db.val(cur, sql, *args)


# ---------------------------------------------------------------- in the simulated world

def test_linkedin_steps_are_drafted_and_recorded(world):
    assert v("select count(*) from tasks where kind like 'linkedin%%'") > 0
    assert v("select count(*) from tasks where kind like 'linkedin%%' and message_id is null") == 0
    assert v("select count(*) from messages where channel = 'linkedin' and subject is not null") == 0
    sent = v("select count(*) from messages where channel = 'linkedin' and status = 'sent'")
    assert sent > 0
    # Every LinkedIn note sent is a touch, so cooldowns and results see it.
    assert v("""select count(*) from messages m where m.channel = 'linkedin' and m.status = 'sent' and not exists
                (select 1 from touches t where t.message_id = m.id and t.channel = 'linkedin' and t.direction = 'out')""") == 0


def test_no_linkedin_note_reached_a_held_back_account(world):
    assert v("""select count(*) from messages m join enrollments e on e.id = m.enrollment_id
                join account_plays ap on ap.id = e.account_play_id where m.channel = 'linkedin' and ap.arm = 'holdout'""") == 0


def test_a_call_where_they_spoke_stops_the_desk_for_that_person(world):
    spoke = q("select distinct person_id from touches where kind = 'call_connected'")
    for r in spoke:
        assert v("""select count(*) from enrollments where person_id = %s and state in ('pending', 'active')""",
                 r["person_id"]) == 0


def test_calls_record_outcomes(world):
    kinds = {r["kind"] for r in q("select distinct kind from touches where channel = 'call'")}
    assert kinds <= {"call_connected", "call_voicemail", "call_no_answer", "call_wrong_number", "they_called"}
    # Every call the SDR finished (not skipped) left a touch with its outcome.
    assert v("""select count(*) from tasks t where t.kind = 'call' and t.status = 'done' and not exists
                (select 1 from touches x where x.dedup_key = 'task:' || t.id and x.channel = 'call')""") == 0


# ---------------------------------------------------------------- the checks

FACTS = {1: "Posted a job for a Billing Operations Manager."}
PERSON = {"first_name": "Ana", "last_name": "Ruiz", "full_name": "Ana Ruiz"}
ACCOUNT = {"name": "Acme Pay"}


def li(*texts, kinds=None):
    kinds = kinds or ["courtesy"] + ["claim"] * (len(texts) - 1)
    return {"sentences": [{"text": t, "kind": k, "fact_ids": [1] if k == "claim" else []} for t, k in zip(texts, kinds)]}


def check(draft, job="connect", max_chars=200):
    return copy_gate.check(draft, job=job, person=PERSON, account=ACCOUNT, facts=FACTS, our_names=["Lumen"],
                           other_bodies=[], channel="linkedin", max_chars=max_chars)


def test_a_good_connect_note_passes():
    v_ = check(li("Ana,", "Saw that Acme Pay posted a job for a Billing Operations Manager."))
    assert v_.passed, v_.failures


def test_a_connect_note_over_the_cap_fails():
    long = "Saw that Acme Pay posted a job for a Billing Operations Manager, " + "and more words " * 12 + "."
    codes = {f["code"] for f in check(li("Ana,", long), max_chars=120).failures}
    assert "too_long" in codes


def test_linkedin_text_carries_no_links():
    codes = {f["code"] for f in check(li("Ana,", "Saw that Acme Pay posted a job for a Billing Operations Manager.",
                                         "More at https://example.com",
                                         kinds=["courtesy", "claim", "courtesy"])).failures}
    assert "link" in codes


def test_a_note_about_nothing_sourced_fails():
    codes = {f["code"] for f in check(li("Ana,", "Would be glad to connect.", kinds=["courtesy", "courtesy"])).failures}
    assert "not_about_them" in codes


# ---------------------------------------------------------------- the guard and the task outcomes

def test_no_email_after_a_linkedin_reply_in_the_same_play(cur, scene):  # noqa: F811
    db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source, dedup_key)
                   values (%s, %s, %s, 'linkedin', 'in', 'reply', now(), 'test', 'li-reply-test')""",
           scene["account"], scene["person"], scene["ap"])
    refused(cur, scene["message"], "engaged on another channel")


def test_an_accepted_connection_does_not_stop_email(cur, scene):  # noqa: F811
    db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source, dedup_key)
                   values (%s, %s, %s, 'linkedin', 'in', 'linkedin_accepted', now(), 'test', 'li-accept-test')""",
           scene["account"], scene["person"], scene["ap"])
    with cur.connection.transaction():
        db.run(cur, "update messages set status = 'sending', sent_at = now() where id = %s", scene["message"])


def _linkedin_task(cur, sc, body="Ana, saw that Test Co is hiring.") -> int:
    m = db.val(cur, """insert into messages (enrollment_id, step_index, channel, body, status, body_hash)
                       values (%s, 1, 'linkedin', %s, 'awaiting_approval', '') returning id""", sc["enrollment"], body)
    return db.val(cur, """insert into tasks (account_play_id, person_id, message_id, kind, title, due_at, owner_id)
                          values (%s, %s, %s, 'linkedin_connect', 'Connect', now(), %s) returning id""",
                  sc["ap"], sc["person"], m, sc["user"])


def test_marking_a_note_sent_records_a_touch(cur, scene):  # noqa: F811
    tid = _linkedin_task(cur, scene)
    user = {"id": scene["user"], "role": "sdr"}
    sdr_steps.complete(cur, tid, user=user, outcome="sent")
    m = db.one(cur, "select m.status, m.approved_by from tasks t join messages m on m.id = t.message_id where t.id = %s", tid)
    assert m["status"] == "sent" and m["approved_by"] == scene["user"]
    assert db.val(cur, "select count(*) from touches where dedup_key = %s and channel = 'linkedin'", f"task:{tid}") == 1


def test_a_note_cannot_go_after_they_replied(cur, scene):  # noqa: F811
    tid = _linkedin_task(cur, scene)
    db.run(cur, "update enrollments set state = 'paused', pause_reason = 'reply_received' where id = %s", scene["enrollment"])
    with pytest.raises(ValueError, match="refused"):
        sdr_steps.complete(cur, tid, user={"id": scene["user"], "role": "sdr"}, outcome="sent")
    assert db.val(cur, "select count(*) from touches where dedup_key = %s", f"task:{tid}") == 0


def test_an_edited_note_is_checked_again(cur, scene):  # noqa: F811
    tid = _linkedin_task(cur, scene)
    with pytest.raises(ValueError, match="no links"):
        sdr_steps.complete(cur, tid, user={"id": scene["user"], "role": "sdr"}, outcome="sent",
                           text="Ana, see https://example.com")


def test_another_sdrs_task_is_refused(cur, scene):  # noqa: F811
    tid = _linkedin_task(cur, scene)
    with pytest.raises(ValueError, match="another SDR"):
        sdr_steps.complete(cur, tid, user={"id": scene["user"] + 999, "role": "sdr"}, outcome="sent")


def test_a_wrong_number_marks_the_phone_and_logs_the_call(cur, scene):  # noqa: F811
    tid = db.val(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                         values (%s, %s, 'call', 'Call', now(), %s) returning id""", scene["ap"], scene["person"], scene["user"])
    sdr_steps.complete(cur, tid, user={"id": scene["user"], "role": "sdr"}, outcome="wrong_number")
    assert db.val(cur, "select phone_status from people where id = %s", scene["person"]) == "invalid"
    assert db.val(cur, "select kind from touches where dedup_key = %s", f"task:{tid}") == "call_wrong_number"


def test_a_linkedin_reply_stops_their_emails_first(cur, scene):  # noqa: F811
    rid = sdr_steps.linkedin_reply(cur, scene["person"], text="Happy to chat next week.",
                                   received_at=datetime.now(timezone.utc), provider_id=f"li-test-{scene['person']}")
    assert rid is not None
    assert db.val(cur, "select channel from replies where id = %s", rid) == "linkedin"
    assert db.val(cur, "select state from enrollments where id = %s", scene["enrollment"]) == "paused"
