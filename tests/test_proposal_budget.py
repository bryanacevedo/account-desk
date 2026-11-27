"""BL-172: a weekly cap on the accounts proposed to one SDR, highest priority first, nothing changed when no cap is set."""
from __future__ import annotations

import time

import pytest

from outbound import budget, db, jobs, plays, views
from outbound.db import J


def _sdr(cur, name="Budget SDR", tz="America/New_York"):
    return db.val(cur, "insert into users (name, email, role, timezone) values (%s, %s, 'sdr', %s) returning id",
                  name, f"{name.replace(' ', '').lower()}{id(cur)}{time.monotonic_ns()}@x.example", tz)


def _manager(cur, n=[0]):
    n[0] += 1
    return db.val(cur, "insert into users (name, email, role) values ('Budget Mgr', %s, 'manager') returning id", f"m{n[0]}{id(cur)}@x.example")


def _play(cur, *, urgent=False, holdout=0, key=None, pause=True):
    if pause:
        db.run(cur, "update plays set status = 'paused' where status = 'live'")
    key = key or f"bud{id(cur)}"
    who = db.val(cur, "insert into users (name, email, role) values ('Launcher', %s, 'gtm') returning id", f"l{id(cur)}{key}@x.example")
    db.run(cur, "insert into signal_types (key, label, because, level, weight, half_life_days) values "
                "('bud_sig', 'Budget test', 'Because of a test signal', 'account', 10, 10) on conflict do nothing")
    db.run(cur, "insert into signal_sources (key, label, adapter, cadence_minutes) values ('bud_src', 'B', 'sim', 60) on conflict do nothing")
    return db.val(cur, """insert into plays (key, name, hypothesis, trigger, personas, sequence, angle, status, urgent, holdout_pct,
                                             launched_by, launched_at)
                          values (%s, 'Budget play', 'h', %s, '{cfo}', '[]', 'a', 'live', %s, %s, %s, now()) returning id""",
                  key, J({"any_of": ["bud_sig"], "min_strength": 0, "within_days": 30}), urgent, holdout, who)


def _account(cur, owner, priority, n=[0]):
    n[0] += 1
    a = db.val(cur, "insert into accounts (name, primary_domain, fit_tier, owner_id) values (%s, %s, 'A', %s) returning id",
               f"Bud Co {n[0]}", f"bud{n[0]}-{id(cur)}.example", owner)
    db.run(cur, "insert into account_scores (account_id, computed_at, fit, intent, engagement, priority, inputs, breakdown) values (%s,app_now(),50,50,0,%s,'{}','{}')",
           a, priority)
    db.run(cur, """insert into signals (type_key, source, external_id, account_id, observed_at, strength, evidence, status)
                   values ('bud_sig', 'bud_src', %s, %s, app_now(), 0.5, %s, 'matched')""",
           f"b{n[0]}-{id(cur)}", a, J({"summary": "s", "url": "https://x"}))
    return a


def _proposed(cur, owner):
    return db.val(cur, "select count(*) from account_plays where owner_id = %s and state = 'proposed' and arm = 'treated'", owner)


def _run_release(cur, owner):
    budget.release(cur, {"owner_id": owner})


@pytest.fixture
def team(cur):
    _play(cur)
    return _sdr(cur)


def test_no_cap_proposes_at_once_as_before(cur, team):
    a = _account(cur, team, 60)
    assert plays.match(cur, a) is not None
    assert _proposed(cur, team) == 1
    assert db.val(cur, "select count(*) from proposal_waits") == 0
    assert budget.room(cur, team) is None


def test_a_capped_match_waits_and_the_release_proposes_highest_first(cur, team):
    mgr = _manager(cur)
    budget.set_cap(cur, team, 2, "two a week while testing", by=mgr)
    accounts = {p: _account(cur, team, p) for p in (30, 90, 10, 70)}
    for a in accounts.values():
        assert plays.match(cur, a) is None            # nothing is proposed on the spot
    assert db.val(cur, "select count(*) from proposal_waits where owner_id = %s", team) == 4
    _run_release(cur, team)
    got = {r["account_id"] for r in db.all(cur, "select account_id from account_plays where owner_id = %s and state = 'proposed'", team)}
    assert got == {accounts[90], accounts[70]}
    assert db.val(cur, "select count(*) from proposal_waits where owner_id = %s", team) == 2
    assert budget.usage(cur, team)["left"] == 0


def test_an_urgent_play_goes_ahead_of_a_higher_priority_one(cur):
    team = _sdr(cur)
    _play(cur, key=f"calm{id(cur)}")
    urgent = _play(cur, urgent=True, key=f"urgent{id(cur)}", pause=False)
    db.run(cur, "update plays set trigger = jsonb_set(trigger, '{any_of}', '[\"bud_sig2\"]') where id = %s", urgent)
    db.run(cur, "insert into signal_types (key, label, because, level, weight, half_life_days) values "
                "('bud_sig2', 'Urgent test', 'Because of a test signal', 'account', 10, 10) on conflict do nothing")
    budget.set_cap(cur, team, 1, "one a week", by=_manager(cur))
    calm_high = _account(cur, team, 95)
    urgent_low = _account(cur, team, 20)
    db.run(cur, "update signals set type_key = 'bud_sig2' where account_id = %s", urgent_low)
    plays.match(cur, calm_high)
    plays.match(cur, urgent_low)
    _run_release(cur, team)
    assert db.val(cur, "select account_id from account_plays where owner_id = %s and state = 'proposed'", team) == urgent_low


def test_the_comparison_group_never_counts_and_is_drawn_after_the_wait(cur):
    team = _sdr(cur)
    key = f"hold{id(cur)}"
    _play(cur, holdout=50, key=key)
    budget.set_cap(cur, team, 1, "one a week", by=_manager(cur))
    held_a = _account(cur, team, 90)
    while not plays.holdout_draw(key, held_a, 50):      # the draw is fixed by play and account
        held_a = _account(cur, team, 90)
    treated = _account(cur, team, 40)
    while plays.holdout_draw(key, treated, 50):
        treated = _account(cur, team, 40)
    for a in (held_a, treated):
        assert plays.match(cur, a) is None              # both wait, so the draw is made on the same top-priority batch
    _run_release(cur, team)
    arms = {r["account_id"]: r["arm"] for r in db.all(cur, "select account_id, arm from account_plays where owner_id = %s", team)}
    assert arms == {held_a: "holdout", treated: "treated"}   # the comparison group used no slot, so the treated one still fit
    assert budget.usage(cur, team)["used"] == 1 and db.val(cur, "select count(*) from proposal_waits") == 0


def test_the_week_turning_frees_the_slots(cur, team):
    budget.set_cap(cur, team, 1, "one a week", by=_manager(cur))
    first, second = _account(cur, team, 80), _account(cur, team, 40)
    plays.match(cur, first)
    plays.match(cur, second)
    _run_release(cur, team)
    assert budget.usage(cur, team)["used"] == 1 and budget.usage(cur, team)["waiting"] == 1
    # move the proposal back into last week: the budget is empty again and the waiting account is proposed
    db.run(cur, "update account_plays set proposed_at = proposed_at - interval '8 days' where owner_id = %s", team)
    _run_release(cur, team)
    assert budget.usage(cur, team)["used"] == 1 and budget.usage(cur, team)["waiting"] == 0
    assert db.val(cur, "select count(*) from account_plays where owner_id = %s and state = 'proposed'", team) == 2


def test_the_week_starts_monday_in_the_sdrs_own_time_zone(cur):
    sdr = _sdr(cur, "Zone SDR", "Pacific/Auckland")
    u = budget.usage(cur, sdr)
    assert u["week_starts_on"].isoweekday() == 1 and (u["resets_on"] - u["week_starts_on"]).days == 7
    local = db.one(cur, "select extract(isodow from %s at time zone 'Pacific/Auckland') as d, extract(hour from %s at time zone 'Pacific/Auckland') as h",
                   u["week_start"], u["week_start"])
    assert (local["d"], local["h"]) == (1, 0)


def test_raising_the_cap_releases_the_waiting_accounts_at_once(cur, team):
    mgr = _manager(cur)
    budget.set_cap(cur, team, 1, "one a week", by=mgr)
    for p in (50, 60):
        plays.match(cur, _account(cur, team, p))
    _run_release(cur, team)
    assert budget.usage(cur, team)["waiting"] == 1
    budget.set_cap(cur, team, 5, "more room now", by=mgr)
    assert budget.usage(cur, team)["waiting"] == 0 and _proposed(cur, team) == 2


def test_a_waiting_account_that_stops_matching_is_dropped_with_a_reason(cur, team):
    budget.set_cap(cur, team, 1, "one a week", by=_manager(cur))
    keep, gone = _account(cur, team, 90), _account(cur, team, 10)
    plays.match(cur, keep)
    plays.match(cur, gone)
    db.run(cur, "update accounts set lifecycle = 'customer' where id = %s", gone)
    budget.set_cap(cur, team, 3, "room for both", by=_manager(cur))
    _run_release(cur, team)
    assert _proposed(cur, team) == 1
    assert db.val(cur, "select count(*) from proposal_waits") == 0
    assert db.val(cur, "select count(*) from audit_log where action = 'proposal_wait_dropped' and object_id = %s", gone) == 1


def test_an_unowned_account_goes_to_an_sdr_who_still_has_room(cur):
    _play(cur)
    full, free = _sdr(cur, "Full SDR"), _sdr(cur, "Free SDR")
    plays.match(cur, _account(cur, free, 50))      # Free SDR carries an open play, so only the limit can put them ahead
    db.run(cur, "update users set active = false where role = 'sdr' and id not in (%s, %s)", full, free)
    budget.set_cap(cur, full, 1, "one a week", by=_manager(cur))
    plays.match(cur, _account(cur, full, 50))
    _run_release(cur, full)                         # Full SDR has used the week
    nobody = _account(cur, None, 50)
    plays.match(cur, nobody)
    assert db.val(cur, "select owner_id from account_plays where account_id = %s", nobody) == free


def test_who_may_set_a_cap_and_what_a_cap_is(cur, team):
    mgr = _manager(cur)
    with pytest.raises(ValueError):
        budget.set_cap(cur, team, 0, "zero", by=mgr)
    with pytest.raises(ValueError):
        budget.set_cap(cur, team, 5, "x", by=mgr)                  # a reason of a few words
    with pytest.raises(ValueError):
        budget.set_cap(cur, mgr, 5, "a manager has none", by=mgr)  # only an SDR has a limit
    out = budget.set_cap(cur, team, 7, "seven a week", by=mgr)
    assert out["cap"] == 7 and out["left"] == 7
    assert budget.changes(cur)[0]["new_cap"] == 7
    assert db.val(cur, "select count(*) from audit_log where action = 'proposal_cap_set' and object_id = %s", team) == 1
    budget.set_cap(cur, team, None, "no limit again", by=mgr)
    assert budget.room(cur, team) is None


def test_the_capacity_message_names_the_people_and_what_to_do(cur, team):
    budget.set_cap(cur, team, 1, "one a week", by=_manager(cur))
    for p in (50, 60, 70):
        plays.match(cur, _account(cur, team, p))
    _run_release(cur, team)
    msg = budget.capacity_message(budget.team(cur))
    assert "2 accounts are waiting" in msg and "Add a person" in msg and "highest priority first" in msg
    assert budget.capacity_message([]) is None
    budget.set_cap(cur, team, 9, "room again", by=_manager(cur))
    assert budget.capacity_message(budget.team(cur)) is None      # nobody waits once there is room


def test_the_message_is_silent_while_an_sdr_with_room_has_a_batch_waiting(cur, team):
    budget.set_cap(cur, team, 5, "five a week", by=_manager(cur))
    plays.match(cur, _account(cur, team, 50))                    # waits for its batch, but the week has room
    assert budget.usage(cur, team)["waiting"] == 1 and budget.capacity_message(budget.team(cur)) is None


def test_a_waiting_account_follows_its_new_owner(cur):
    _play(cur)
    old, new = _sdr(cur, "Old Owner"), _sdr(cur, "New Owner")
    mgr = _manager(cur)
    budget.set_cap(cur, old, 3, "three a week", by=mgr)
    budget.set_cap(cur, new, 3, "three a week", by=mgr)
    a = _account(cur, old, 70)
    plays.match(cur, a)
    db.run(cur, "update accounts set owner_id = %s where id = %s", new, a)      # the CRM moved it while it waited
    _run_release(cur, old)
    assert db.val(cur, "select count(*) from proposal_waits where owner_id = %s", new) == 1   # queued for them, through their cap
    _run_release(cur, new)
    assert db.val(cur, "select owner_id from account_plays where account_id = %s", a) == new


def test_propose_again_is_a_persons_choice_so_the_cap_does_not_stop_it_but_counts_it(cur, team):
    mgr = _manager(cur)
    a = _account(cur, team, 60)
    ap = plays.match(cur, a)
    plays.set_state(cur, ap, "expired", reason="expired", cooldown_key="expired")
    db.run(cur, "update account_plays set close_reason = 'expired' where id = %s", ap)
    budget.set_cap(cur, team, 1, "one a week", by=mgr)
    assert budget.usage(cur, team)["left"] == 0
    plays.propose_again(cur, ap, user_id=mgr)
    assert budget.usage(cur, team)["used"] == 2


def test_a_dropped_account_is_counted_for_the_manager(cur, team):
    budget.set_cap(cur, team, 1, "one a week", by=_manager(cur))
    a = _account(cur, team, 10)
    plays.match(cur, a)
    db.run(cur, "update accounts set lifecycle = 'customer' where id = %s", a)
    _run_release(cur, team)
    assert budget.usage(cur, team)["dropped_7d"] == 1


def test_today_carries_the_budget_for_each_role(cur, team):
    budget.set_cap(cur, team, 4, "four a week", by=_manager(cur))
    sdr = db.one(cur, "select * from users where id = %s", team)
    mine = views.today(cur, sdr)["budget"]
    assert mine["mine"]["cap"] == 4 and mine["team"] is None
    mgr = db.one(cur, "select * from users where id = %s", _manager(cur))
    boss = views.today(cur, mgr)["budget"]
    assert boss["mine"] is None and any(u["user_id"] == team for u in boss["team"])


def test_the_release_job_is_scheduled_and_registered():
    from outbound import scheduler
    assert "release_proposals" in scheduler.PERIODIC and "release_proposals" in jobs.HANDLERS


# ---------------------------------------------------------------- the HTTP surface

@pytest.fixture(scope="module")
def client(world):
    import os
    os.environ.setdefault("NO_WORKER", "1")
    from fastapi.testclient import TestClient
    from outbound.api.app import app
    return TestClient(app)


def _first(role):
    with db.tx() as cur:
        return db.val(cur, "select id from users where role = %s and active order by id limit 1", role)


def test_only_a_manager_or_gtm_sets_a_cap_and_the_settings_page_shows_it(client):
    sdr, mgr = _first("sdr"), _first("manager")
    body = {"cap": 6, "reason": "six a week for now"}
    assert client.put(f"/api/proposal-budget/{sdr}", json=body, headers={"X-Acting-As": str(sdr)}).status_code == 403
    try:
        r = client.put(f"/api/proposal-budget/{sdr}", json=body, headers={"X-Acting-As": str(mgr)})
        assert r.status_code == 200 and r.json()["usage"]["cap"] == 6
        page = client.get("/api/settings", headers={"X-Acting-As": str(mgr)}).json()["proposal_budget"]
        assert any(u["user_id"] == sdr and u["cap"] == 6 for u in page["team"]) and page["changes"][0]["reason"] == "six a week for now"
        assert "proposal_budget" not in client.get("/api/settings", headers={"X-Acting-As": str(sdr)}).json()
        assert client.put(f"/api/proposal-budget/{sdr}", json={"cap": 0, "reason": "zero is not a limit"}, headers={"X-Acting-As": str(mgr)}).status_code == 422
        assert client.put(f"/api/proposal-budget/{mgr}", json=body, headers={"X-Acting-As": str(mgr)}).status_code == 422
    finally:
        with db.tx() as cur:
            db.run(cur, "update users set weekly_proposal_cap = null where id = %s", sdr)
            db.run(cur, "delete from proposal_cap_changes where user_id = %s", sdr)
            db.run(cur, "delete from audit_log where action = 'proposal_cap_set' and object_id = %s", sdr)


def test_the_public_demo_refuses_to_change_a_cap(client, monkeypatch):
    import dataclasses
    from outbound.api import app as app_mod
    monkeypatch.setattr(app_mod, "CONFIG", dataclasses.replace(app_mod.CONFIG, public_demo=True))
    sdr, mgr = _first("sdr"), _first("manager")
    assert client.put(f"/api/proposal-budget/{sdr}", json={"cap": 6, "reason": "six a week"}, headers={"X-Acting-As": str(mgr)}).status_code == 403
