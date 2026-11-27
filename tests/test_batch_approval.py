"""BL-170: a person approves ticked drafts of one play and one email together; each stays its own approval and can be taken back."""
from __future__ import annotations

import psycopg
import pytest
from test_guarantees import scene  # noqa: F401

from outbound import db, outreach, views
from outbound.db import J

KEY = "batch:v1:0"


def _settings(cur):
    db.run(cur, "insert into settings (key, value) values ('send_window', %s), ('stagger_days', '2'), ('person_cooldown_days', '90') "
                "on conflict (key) do update set value = excluded.value", J([["00:00", "23:59"]]))


def _draft(cur, scene, n, *, key=KEY, status="awaiting_approval", owner=None):  # noqa: F811
    _settings(cur)
    a = db.val(cur, "insert into accounts (name, primary_domain, fit_tier) values (%s, %s, 'A') returning id",
               f"Batch Co {n}-{id(cur)}", f"batch{n}-{id(cur)}.example")
    p = db.val(cur, """insert into people (account_id, full_name, first_name, email, email_status, email_verified_at, source, country, timezone)
                       values (%s, %s, %s, %s, 'valid', now(), 'test', 'US', 'America/New_York') returning id""",
               a, f"Pat {n}", "Pat", f"pat{n}-{id(cur)}@x.example")
    ap = db.val(cur, """insert into account_plays (account_id, play_id, trigger_signal_id, arm, state, why_now, owner_id)
                        values (%s,%s,%s,'treated','approving','{}',%s) returning id""", a, scene["play"], scene["signal"], owner or scene["user"])
    e = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, mailbox_id)
                       values (%s,%s,'cfo','pending',%s) returning id""", ap, p, scene["mailbox"])
    m = db.val(cur, """insert into messages (enrollment_id, step_index, channel, subject, body, status, body_hash, template_key, mailbox_id, gate)
                       values (%s,0,'email',%s,%s,%s,'',%s,%s,%s) returning id""",
               e, f"Subject {n}", f"Pat, hello {n}.\n\n--\nTo stop hearing from us, reply stop.", status, key, scene["mailbox"],
               J({"passed": status == "awaiting_approval"}))
    return {"m": m, "e": e, "ap": ap, "p": p, "a": a}


def _status(cur, m):
    return db.val(cur, "select status from messages where id = %s", m)


def test_each_ticked_draft_is_its_own_approval_with_its_own_hash(cur, scene):  # noqa: F811
    ds = [_draft(cur, scene, i) for i in range(3)]
    out = outreach.approve_batch(cur, [d["m"] for d in ds[:2]], user_id=scene["user"], role="sdr")
    assert out["approved"] == [ds[0]["m"], ds[1]["m"]] and out["skipped"] == []
    assert _status(cur, ds[2]["m"]) == "awaiting_approval"                      # not ticked, not approved
    for d in ds[:2]:
        row = db.one(cur, "select status, approved_hash = body_hash as same, approval_mode, approval_batch_id from messages where id = %s", d["m"])
        assert row["status"] in ("approved", "scheduled") and row["same"] and row["approval_mode"] == "person"
        assert row["approval_batch_id"] == out["batch"]
        assert db.val(cur, "select count(*) from audit_log where action = 'approved' and object_id = %s", d["m"]) == 1
    assert db.val(cur, "select approved from approval_batches where id = %s", out["batch"]) == 2


def test_a_changed_body_after_a_batch_approval_still_blocks_the_send(cur, scene):  # noqa: F811
    d = _draft(cur, scene, 0)
    outreach.approve_batch(cur, [d["m"]], user_id=scene["user"], role="sdr")
    db.run(cur, "update messages set body = 'Pat, something else.' where id = %s", d["m"])
    with pytest.raises(psycopg.errors.RaiseException, match="body changed after approval"):
        with cur.connection.transaction():
            db.run(cur, "update messages set status = 'sending', sent_at = now() where id = %s", d["m"])


def test_a_draft_that_failed_its_checks_never_batches_and_the_rest_go_through(cur, scene):  # noqa: F811
    good, bad = _draft(cur, scene, 0), _draft(cur, scene, 1, status="failed_gate")
    out = outreach.approve_batch(cur, [good["m"], bad["m"]], user_id=scene["user"], role="sdr")
    assert out["approved"] == [good["m"]] and out["skipped"][0]["id"] == bad["m"] and "rewrite" in out["skipped"][0]["reason"]
    assert _status(cur, bad["m"]) == "failed_gate"


def test_the_single_approval_refusals_still_apply_per_draft(cur, scene):  # noqa: F811
    ok, blocked = _draft(cur, scene, 0), _draft(cur, scene, 1)
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email', (select email from people where id = %s), 'asked to stop', 'test')", blocked["p"])
    out = outreach.approve_batch(cur, [ok["m"], blocked["m"]], user_id=scene["user"], role="sdr")
    assert out["approved"] == [ok["m"]] and "cannot be emailed" in out["skipped"][0]["reason"]
    assert _status(cur, blocked["m"]) == "awaiting_approval"


def test_one_batch_is_one_play_and_one_email(cur, scene):  # noqa: F811
    a, b = _draft(cur, scene, 0), _draft(cur, scene, 1, key="other:v1:0")
    with pytest.raises(outreach.BatchRefused, match="single group"):
        outreach.approve_batch(cur, [a["m"], b["m"]], user_id=scene["user"], role="sdr")
    assert _status(cur, a["m"]) == "awaiting_approval"


def test_a_batch_has_a_size_limit_and_an_sdr_stays_in_their_own_accounts(cur, scene):  # noqa: F811
    with pytest.raises(outreach.BatchRefused, match="at most 25"):
        outreach.approve_batch(cur, list(range(1, 30)), user_id=scene["user"], role="sdr")
    with pytest.raises(outreach.BatchRefused, match="Tick at least one"):
        outreach.approve_batch(cur, [], user_id=scene["user"], role="sdr")
    other = db.val(cur, "insert into users (name, email, role) values ('Other', %s, 'sdr') returning id", f"o{id(cur)}@x.example")
    mine, theirs = _draft(cur, scene, 0), _draft(cur, scene, 1, owner=other)
    with pytest.raises(outreach.BatchRefused) as e:
        outreach.approve_batch(cur, [mine["m"], theirs["m"]], user_id=scene["user"], role="sdr")
    assert e.value.status == 403
    manager = outreach.approve_batch(cur, [mine["m"], theirs["m"]], user_id=scene["user"], role="manager")
    assert len(manager["approved"]) == 2


def test_nothing_is_approved_automatically_by_a_batch_request_that_names_nobody(cur, scene):  # noqa: F811
    d = _draft(cur, scene, 0)
    assert _status(cur, d["m"]) == "awaiting_approval"
    views.today(cur, db.one(cur, "select * from users where id = %s", scene["user"]))
    assert _status(cur, d["m"]) == "awaiting_approval"           # reading the page approves nothing


def test_take_back_returns_a_first_email_and_its_sequence_to_waiting(cur, scene):  # noqa: F811
    d = _draft(cur, scene, 0)
    outreach.approve_batch(cur, [d["m"]], user_id=scene["user"], role="sdr")
    assert db.val(cur, "select state from enrollments where id = %s", d["e"]) == "active"
    assert db.val(cur, "select state from account_plays where id = %s", d["ap"]) == "active"
    out = outreach.take_back(cur, d["m"], user_id=scene["user"], role="sdr")
    assert out["status"] == "awaiting_approval" and out["approved_hash"] is None and out["approval_mode"] is None
    assert out["scheduled_for"] is None and out["taken_back_by"] == scene["user"]
    assert db.val(cur, "select state from enrollments where id = %s", d["e"]) == "pending"
    assert db.val(cur, "select state from account_plays where id = %s", d["ap"]) == "approving"
    assert db.val(cur, "select count(*) from audit_log where action = 'approval_taken_back' and object_id = %s", d["m"]) == 1
    # and it can be approved again, on its own
    outreach.approve(cur, d["m"], user_id=scene["user"])
    assert _status(cur, d["m"]) in ("approved", "scheduled")


def test_take_back_is_refused_once_it_went_out_and_for_someone_elses_approval(cur, scene):  # noqa: F811
    d = _draft(cur, scene, 0)
    outreach.approve_batch(cur, [d["m"]], user_id=scene["user"], role="sdr")
    other = db.val(cur, "insert into users (name, email, role) values ('Other', %s, 'sdr') returning id", f"o{id(cur)}@x.example")
    with pytest.raises(PermissionError):
        outreach.take_back(cur, d["m"], user_id=other, role="sdr")
    outreach.take_back(cur, d["m"], user_id=other, role="manager")       # a manager may
    outreach.approve(cur, d["m"], user_id=scene["user"])
    db.run(cur, "update messages set status = 'sending', sent_at = now() where id = %s", d["m"])
    with pytest.raises(ValueError, match="cannot be taken back"):
        outreach.take_back(cur, d["m"], user_id=scene["user"], role="sdr")


def test_an_automatic_approval_cannot_be_taken_back_this_way(cur, scene):  # noqa: F811
    d = _draft(cur, scene, 0)
    outreach.approve(cur, d["m"], user_id=scene["user"])
    db.run(cur, "update messages set approval_mode = 'auto_supervised' where id = %s", d["m"])
    with pytest.raises(ValueError, match="standing approval"):
        outreach.take_back(cur, d["m"], user_id=scene["user"], role="manager")


def test_the_approvals_page_carries_whole_groups_with_their_text(cur, scene):  # noqa: F811
    d = _draft(cur, scene, 0)
    page = views.approvals_page(cur, db.one(cur, "select * from users where id = %s", scene["user"]))
    row = next(r for r in page["approvals"] if r["id"] == d["m"])
    assert page["total"] >= 1 and row["template_key"] == KEY and row["body"].startswith("Pat, hello") and row["fit_tier"] == "A"
    assert {"priority", "angle", "persona_key", "play_version", "email_no"} <= set(row)
    m = views.message(cur, d["m"])
    assert m["can_take_back"] is False
    outreach.approve(cur, d["m"], user_id=scene["user"])
    m = views.message(cur, d["m"])
    assert m["can_take_back"] is True and m["approver"] == "T"


def test_the_play_stays_active_when_a_colleague_of_the_play_already_went_out(cur, scene):  # noqa: F811
    d = _draft(cur, scene, 0)
    outreach.approve_batch(cur, [d["m"]], user_id=scene["user"], role="sdr")
    other = _draft(cur, scene, 1)
    db.run(cur, "update enrollments set account_play_id = %s, state = 'stopped', stop_reason = 'unsubscribed' where id = %s", d["ap"], other["e"])
    db.run(cur, "set local session_replication_role = replica")      # a bare 'sent' row for the test, past the send guard
    db.run(cur, "update messages set status = 'sent', sent_at = now(), approved_hash = body_hash, approved_at = now(), approval_mode = 'person' where id = %s", other["m"])
    db.run(cur, "set local session_replication_role = origin")
    outreach.take_back(cur, d["m"], user_id=scene["user"], role="sdr")
    assert db.val(cur, "select state from account_plays where id = %s", d["ap"]) == "active"
