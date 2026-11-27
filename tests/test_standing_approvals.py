"""BL-171: a standing approval is an owned policy; the Supervised stage's automatic approval needs one and never covers what a person judges."""
from __future__ import annotations

import time
from datetime import timedelta

import pytest
from test_guarantees import scene  # noqa: F401
from test_review_fixes import _fresh_draft  # noqa: F401

from outbound import db, outreach, plays, standing
from outbound.db import J


def _manager(cur):
    return db.val(cur, "insert into users (name, email, role) values ('Policy Mgr', %s, 'manager') returning id", f"pm{time.monotonic_ns()}@x.example")


def _setup(cur, scene, *, tier="B", country="US"):  # noqa: F811
    """A supervised live play whose sequence is email, email; the person's first email approved by a person."""
    seq = [{"channel": "email", "by": "desk", "job": "open", "day": 0}, {"channel": "email", "by": "desk", "job": "bump", "day": 3},
           {"channel": "email", "by": "desk", "job": "break_up", "day": 6}]
    db.run(cur, "update plays set sequence = %s, autonomy = 'supervised', status = 'live', launched_by = %s, launched_at = now() where id = %s",
           J(seq), scene["user"], scene["play"])
    db.run(cur, "update accounts set fit_tier = %s where id = %s", tier, scene["account"])
    db.run(cur, "update people set country = %s where id = %s", country, scene["person"])
    db.run(cur, "update enrollments set state = 'active' where id = %s", scene["enrollment"])
    mgr = _manager(cur)
    return mgr


def _follow_up(cur, scene, step=1):  # noqa: F811
    # the scene's message (step 0) is person-approved and scheduled; make a fresh follow-up draft
    return _fresh_draft(cur, scene, step)


def _sampled(mid):
    return outreach._sample(mid)


def _draft_not_sampled(cur, scene, step=1):  # noqa: F811
    for _ in range(40):
        mid = _follow_up(cur, scene, step)
        if not _sampled(mid):
            return mid
        db.run(cur, "delete from messages where id = %s", mid)
        step += 1
    raise AssertionError("no unsampled id")


def test_without_a_standing_approval_a_supervised_follow_up_waits_for_a_person(cur, scene):  # noqa: F811
    _setup(cur, scene)
    m = _draft_not_sampled(cur, scene)
    assert not outreach.maybe_auto_approve(cur, m)
    assert db.val(cur, "select status from messages where id = %s", m) == "awaiting_approval"


def test_with_one_in_force_a_covered_follow_up_is_approved_and_records_the_policy(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    sid = standing.sign(cur, scene["play"], owner_id=mgr, reason="Reviewed the last 50 drafts, clean", tiers=["A", "B"],
                        ends_on=db.val(cur, "select app_now()::date + 30"))
    m = _draft_not_sampled(cur, scene)
    assert outreach.maybe_auto_approve(cur, m)
    row = db.one(cur, "select approval_mode, standing_approval_id from messages where id = %s", m)
    assert row == {"approval_mode": "auto_supervised", "standing_approval_id": sid}


def test_a_first_email_a_failed_draft_and_a_tier_outside_the_policy_never_go(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene, tier="A")
    standing.sign(cur, scene["play"], owner_id=mgr, reason="Tier B only, as agreed", tiers=["B"], ends_on=db.val(cur, "select app_now()::date + 30"))
    m = _draft_not_sampled(cur, scene)
    assert not outreach.maybe_auto_approve(cur, m)                       # tier A is not in the policy
    db.run(cur, "update accounts set fit_tier = 'B' where id = %s", scene["account"])
    db.run(cur, "update messages set status = 'awaiting_approval' where id = %s", scene["message"])      # the first email, waiting
    assert not outreach.maybe_auto_approve(cur, scene["message"])         # a first email is never covered
    db.run(cur, "update messages set status = 'failed_gate' where id = %s", m)
    assert not outreach.maybe_auto_approve(cur, m)                        # a failed draft never reaches it


def test_a_play_that_opens_with_a_linkedin_step_still_needs_a_person_for_its_first_email(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    seq = [{"channel": "linkedin", "by": "sdr", "job": "connect", "day": 0}, {"channel": "email", "by": "desk", "job": "open", "day": 1},
           {"channel": "email", "by": "desk", "job": "bump", "day": 4}]
    db.run(cur, "update plays set sequence = %s where id = %s", J(seq), scene["play"])
    standing.sign(cur, scene["play"], owner_id=mgr, reason="Follow-ups only, as agreed", tiers=["B"], ends_on=db.val(cur, "select app_now()::date + 30"))
    m = _draft_not_sampled(cur, scene, 2)                      # email 2 of the play, but nobody approved email 1 (step 1)
    assert not outreach.maybe_auto_approve(cur, m)
    assert standing.covered(cur, standing.in_force(cur, scene["play"]), standing.message_context(cur, m)) == "The first email was not approved by a person"
    assert standing.covered(cur, standing.in_force(cur, scene["play"]), {**standing.message_context(cur, m), "step_index": 1}) == "It is not a follow-up"


def test_a_country_that_needs_judgment_or_an_hq_in_one_goes_to_a_person(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene, country="GB")
    from conftest import ensure_rule
    ensure_rule(cur, "GB", "basis_required")
    ensure_rule(cur, "US", "allowed")
    standing.sign(cur, scene["play"], owner_id=mgr, reason="Follow-ups for tier B", tiers=["B"], ends_on=db.val(cur, "select app_now()::date + 30"))
    m = _draft_not_sampled(cur, scene)
    ctx = standing.message_context(cur, m)
    assert standing.covered(cur, standing.in_force(cur, scene["play"]), ctx) == "Their country needs a person to judge"
    db.run(cur, "update people set country = 'US' where id = %s", scene["person"])
    db.run(cur, "update accounts set hq_country = 'GB' where id = %s", scene["account"])
    ctx = standing.message_context(cur, m)
    assert standing.covered(cur, standing.in_force(cur, scene["play"]), ctx) == "Their country needs a person to judge"


def test_it_stops_on_its_date_a_revoke_an_edit_and_a_stage_change(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    today = db.val(cur, "select app_now()::date")
    sid = standing.sign(cur, scene["play"], owner_id=mgr, reason="Follow-ups for tier B", ends_on=today + timedelta(days=2))
    assert standing.in_force(cur, scene["play"])
    db.run(cur, "update standing_approvals set ends_on = app_now()::date - 1 where id = %s", sid)
    assert standing.in_force(cur, scene["play"]) is None                       # expired by its date, with no job needed
    db.run(cur, "update standing_approvals set ends_on = app_now()::date + 5 where id = %s", sid)
    db.run(cur, "update plays set version = version + 1 where id = %s", scene["play"])
    assert standing.in_force(cur, scene["play"]) is None                       # the words changed
    db.run(cur, "update plays set version = version - 1 where id = %s", scene["play"])
    assert standing.end(cur, sid, kind="person", reason="Not now", by=mgr) and standing.in_force(cur, scene["play"]) is None
    assert not standing.end(cur, sid, kind="person", reason="again", by=mgr)   # already over


def test_ending_it_returns_the_queued_follow_ups_to_a_person(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    sid = standing.sign(cur, scene["play"], owner_id=mgr, reason="Follow-ups for tier B", ends_on=db.val(cur, "select app_now()::date + 30"))
    m = _draft_not_sampled(cur, scene)
    assert outreach.maybe_auto_approve(cur, m)
    db.run(cur, "update messages set status = 'scheduled', scheduled_for = app_now() + interval '1 day' where id = %s", m)
    standing.end(cur, sid, kind="person", reason="Revoked by the manager", by=mgr)
    row = db.one(cur, "select status, approval_mode, approved_hash from messages where id = %s", m)
    assert row["status"] == "awaiting_approval" and row["approval_mode"] is None and row["approved_hash"] is None
    assert db.val(cur, "select count(*) from audit_log where action = 'auto_approval_returned' and object_id = %s", m) == 1


def test_the_send_path_refuses_an_automatic_approval_with_no_policy_in_force(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    sid = standing.sign(cur, scene["play"], owner_id=mgr, reason="Follow-ups for tier B", ends_on=db.val(cur, "select app_now()::date + 30"))
    m = _draft_not_sampled(cur, scene)
    outreach.maybe_auto_approve(cur, m)
    db.run(cur, "update messages set status = 'scheduled', scheduled_for = app_now() where id = %s", m)
    assert not standing.refuse_at_send(cur, m)
    db.run(cur, "update standing_approvals set revoked_at = now(), revoke_kind = 'person' where id = %s", sid)    # revoked behind its back
    assert standing.refuse_at_send(cur, m)
    assert db.val(cur, "select status from messages where id = %s", m) == "awaiting_approval"


def test_the_carried_over_policy_of_the_simulated_history_sends_as_it_always_did(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    sid = standing.sign(cur, scene["play"], owner_id=mgr, reason="Promoted after the checks", signed_by_person=False, regions="carried_over",
                        ends_on=db.val(cur, "select app_now()::date + 30"))
    m = _draft_not_sampled(cur, scene)
    db.run(cur, "update people set country = 'GB' where id = %s", scene["person"])
    assert outreach.maybe_auto_approve(cur, m)                                   # the old rule for countries
    db.run(cur, "update messages set status = 'scheduled', scheduled_for = app_now() where id = %s", m)
    standing.end(cur, sid, kind="play_changed", reason="Stage changed")
    assert db.val(cur, "select status from messages where id = %s", m) == "scheduled"      # not returned: the history is unchanged
    assert not standing.refuse_at_send(cur, m)


def test_a_stage_change_ends_it_and_promotion_signs_one(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    db.run(cur, "update plays set autonomy = 'draft' where id = %s", scene["play"])
    db.run(cur, "update plays set autonomy = 'supervised' where id = %s", scene["play"])
    sid = standing.on_stage_change(cur, scene["play"], "draft", "supervised", by=mgr, reason="Met every check: 50 drafts, 92% unedited")
    pol = db.one(cur, "select * from standing_approvals where id = %s", sid)
    assert pol["owner_id"] == mgr and pol["signed_by_person"] and pol["regions"] == "allowed_only" and pol["tiers"] == ["A", "B"]
    db.run(cur, "update plays set autonomy = 'autonomous' where id = %s", scene["play"])
    standing.on_stage_change(cur, scene["play"], "supervised", "autonomous", by=mgr, reason="Promoted again")
    assert standing.in_force(cur, scene["play"]) is None
    assert db.val(cur, "select revoke_kind from standing_approvals where id = %s", sid) == "play_changed"
    db.run(cur, "update plays set autonomy = 'supervised' where id = %s", scene["play"])
    standing.on_stage_change(cur, scene["play"], "autonomous", "supervised", by=None, reason="A spam complaint")
    back = standing.in_force(cur, scene["play"])
    assert back["regions"] == "carried_over" and not back["signed_by_person"] and back["id"] != sid     # not the old one


def test_a_complaint_ends_the_policy_with_its_kind(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    standing.sign(cur, scene["play"], owner_id=mgr, reason="Follow-ups for tier B", ends_on=db.val(cur, "select app_now()::date + 30"))
    db.run(cur, "insert into deliveries (message_id, event, at) values (%s, 'complaint', app_now())", scene["message"])
    plays.autonomy_watch(cur, {})
    assert db.val(cur, "select autonomy from plays where id = %s", scene["play"]) == "draft"
    assert db.val(cur, "select revoke_kind from standing_approvals where play_id = %s order by id limit 1", scene["play"]) == "complaint"


def test_only_a_manager_signs_within_the_term_and_signing_again_replaces(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    far = db.val(cur, "select app_now()::date + 30")
    with pytest.raises(ValueError, match="manager"):
        standing.sign(cur, scene["play"], owner_id=scene["user"], reason="An SDR cannot sign this", ends_on=far)
    with pytest.raises(ValueError, match="end date"):
        standing.sign(cur, scene["play"], owner_id=mgr, reason="Too long a term here", ends_on=db.val(cur, "select app_now()::date + 120"))
    with pytest.raises(ValueError, match="Say why"):
        standing.sign(cur, scene["play"], owner_id=mgr, reason="short", ends_on=far)
    first = standing.sign(cur, scene["play"], owner_id=mgr, reason="The first one, for tier B", ends_on=far)
    second = standing.sign(cur, scene["play"], owner_id=mgr, reason="The second one, for tiers A and B", tiers=["A", "B"], ends_on=far)
    assert db.val(cur, "select revoke_kind from standing_approvals where id = %s", first) == "replaced"
    assert standing.in_force(cur, scene["play"])["id"] == second


def test_the_migration_carries_a_supervised_play_over_with_an_owner(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    db.run(cur, "insert into play_stage_changes (play_id, from_stage, to_stage, reason, decided_by) values (%s,'draft','supervised','Met every check',%s)",
           scene["play"], mgr)
    sql = open(__import__("pathlib").Path(standing.__file__).resolve().parents[2] / "migrations" / "0047_standing_approvals.sql").read()
    insert = sql[sql.index("insert into standing_approvals"):sql.index("update messages m")]
    db.run(cur, insert)
    pol = standing.in_force(cur, scene["play"])
    assert pol and pol["owner_id"] == mgr and pol["signed_by_person"] is False and "Sign again to confirm" in pol["reason"]


def test_a_live_desk_signs_nothing_for_a_demotion_and_a_managers_demotion_signs_nothing(cur, scene, monkeypatch):  # noqa: F811
    import dataclasses

    from outbound import standing as st
    mgr = _setup(cur, scene)
    monkeypatch.setattr(st, "CONFIG", dataclasses.replace(st.CONFIG, mode="live"))
    assert st.on_stage_change(cur, scene["play"], "autonomous", "supervised", by=None, reason="A spam complaint") is None
    monkeypatch.undo()
    assert st.on_stage_change(cur, scene["play"], "autonomous", "supervised", by=mgr, reason="I am not sure about this play") is None
    assert st.in_force(cur, scene["play"]) is None


def test_signing_again_relinks_what_the_new_policy_covers_and_returns_the_rest(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    old = standing.sign(cur, scene["play"], owner_id=mgr, reason="Carried over from the history", signed_by_person=False, regions="carried_over",
                        ends_on=db.val(cur, "select app_now()::date + 30"))
    ok, gb = _draft_not_sampled(cur, scene), None
    outreach.maybe_auto_approve(cur, ok)
    db.run(cur, "update messages set status = 'scheduled', scheduled_for = app_now() + interval '1 day' where id = %s", ok)
    new = standing.sign(cur, scene["play"], owner_id=mgr, reason="Signed again under the real rule", tiers=["A", "B"],
                        ends_on=db.val(cur, "select app_now()::date + 30"))
    assert db.val(cur, "select standing_approval_id from messages where id = %s", ok) == new and old != new


def test_an_inactive_promoter_does_not_stop_a_demotion(cur, scene):  # noqa: F811
    from outbound import standing as st
    mgr = _setup(cur, scene)
    db.run(cur, "update users set active = false where id = %s", mgr)
    db.run(cur, "insert into play_stage_changes (play_id, from_stage, to_stage, reason, decided_by) values (%s,'draft','supervised','ok',%s)", scene["play"], mgr)
    st.on_stage_change(cur, scene["play"], "autonomous", "supervised", by=None, reason="A spam complaint")      # no raise


def test_a_returned_email_approved_by_hand_is_not_counted_as_sampled(cur, scene):  # noqa: F811
    mgr = _setup(cur, scene)
    sid = standing.sign(cur, scene["play"], owner_id=mgr, reason="Follow-ups for tier B", ends_on=db.val(cur, "select app_now()::date + 30"))
    m = _draft_not_sampled(cur, scene)
    outreach.maybe_auto_approve(cur, m)
    standing.end(cur, sid, kind="person", reason="Revoked", by=mgr)
    assert db.val(cur, "select standing_approval_id from messages where id = %s", m) is None
