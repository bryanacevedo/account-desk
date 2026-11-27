"""BL-126: the fourth stage is off until a manager turns it on, and nothing changes for a desk that already has it."""
from __future__ import annotations

from test_guarantees import scene  # noqa: F401
from test_review_fixes import _fresh_draft  # noqa: F401

from outbound import db, outreach, views


def _autonomous_tier_b(cur, scene):  # noqa: F811
    db.run(cur, "update plays set autonomy = 'autonomous' where id = %s", scene["play"])
    db.run(cur, "update accounts set fit_tier = 'B' where id = %s", scene["account"])


def test_with_the_stage_off_a_tier_b_message_waits_for_a_person(cur, scene):  # noqa: F811
    _autonomous_tier_b(cur, scene)
    db.run(cur, "insert into settings (key, value) values ('autonomous_stage', 'false'::jsonb) on conflict (key) do update set value = 'false'::jsonb")
    m = _fresh_draft(cur, scene, 3)
    assert not outreach.maybe_auto_approve(cur, m)
    assert db.val(cur, "select status from messages where id = %s", m) == "awaiting_approval"


def test_with_the_stage_on_or_no_row_the_desk_sends_tier_b_as_before(cur, scene):  # noqa: F811
    _autonomous_tier_b(cur, scene)
    db.run(cur, "delete from settings where key = 'autonomous_stage'")
    assert outreach.autonomous_enabled(cur)
    assert outreach.maybe_auto_approve(cur, _fresh_draft(cur, scene, 3))
    db.run(cur, "insert into settings (key, value) values ('autonomous_stage', 'true'::jsonb) on conflict (key) do update set value = 'true'::jsonb")
    assert outreach.maybe_auto_approve(cur, _fresh_draft(cur, scene, 4))


def test_a_new_desk_seeds_it_off_and_the_promotion_check_says_so(cur, scene):  # noqa: F811
    from outbound.seed import catalog
    assert catalog.SETTINGS["autonomous_stage"] is False
    db.run(cur, "update plays set autonomy = 'supervised' where id = %s", scene["play"])
    db.run(cur, "insert into settings (key, value) values ('autonomous_stage', 'false'::jsonb) on conflict (key) do update set value = 'false'::jsonb")
    play = db.one(cur, "select * from plays where id = %s", scene["play"])
    check = views.promotion_check(cur, play)
    row = next(c for c in check["checks"] if c["label"] == "Autonomous stage turned on by a manager")
    assert row["ok"] is False and row["value"] == "Off" and check["ready"] is False
