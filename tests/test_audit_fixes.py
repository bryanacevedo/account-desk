"""Regression tests for the audit of the demo's data against the desk's own rules (2026-11-11)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from test_guarantees import refused, scene, send  # noqa: F401

from outbound import db, enrichment, gate, outreach, pipeline, plays, signals, spend, timeutil
from outbound.db import J

MONDAY = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)  # 10:00 in New York


def _clock(cur, at: datetime) -> None:
    db.run(cur, "update sim_clock set enabled = true, at = %s", at)


def _colleague(cur, scene, name: str = "Bo Lind", state: str = "pending") -> tuple[int, int]:  # noqa: F811
    p = db.val(cur, """insert into people (account_id, full_name, first_name, email, email_status, email_verified_at, source,
                                           country, timezone)
                       values (%s, %s, %s, %s, 'valid', now(), 'test', 'US', 'America/New_York') returning id""",
               scene["account"], name, name.split()[0], f"{name.split()[0].lower()}{id(cur)}@x.example")
    e = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, mailbox_id)
                       values (%s, %s, 'cfo', %s, %s) returning id""", scene["ap"], p, state, scene["mailbox"])
    return p, e


def _types(cur, *keys: str) -> None:
    for k in keys:
        db.run(cur, """insert into signal_types (key, label, because, level, weight, half_life_days)
                       values (%s, %s, 'Because of a test signal', 'account', 10, 30) on conflict do nothing""", k, k)
    db.run(cur, "insert into signal_sources (key, label, adapter, cadence_minutes) values ('news_feed', 'News', 'sim', 720) "
                "on conflict do nothing")


# ---------------------------------------------------------------- 5. the two-business-day stagger

def test_a_colleague_starts_two_business_days_after_the_first_email_goes_not_after_the_first_start(cur, scene):  # noqa: F811
    _clock(cur, MONDAY)
    db.run(cur, "insert into settings (key, value) values ('stagger_days', '2') on conflict (key) do update set value = '2'")
    timeutil.load_holidays(cur)
    # The first colleague started on Monday, but their first email waits until Thursday (a full mailbox, say).
    thursday = MONDAY + timedelta(days=3)
    db.run(cur, "update enrollments set started_at = %s where id = %s", MONDAY, scene["enrollment"])
    db.run(cur, "update messages set scheduled_for = %s where id = %s", thursday, scene["message"])
    _, e2 = _colleague(cur, scene)
    outreach.activate(cur, e2)
    start = db.val(cur, "select started_at from enrollments where id = %s", e2)
    assert start >= timeutil.add_business_days(thursday, 2, country="US", timezone="America/New_York")


def test_a_first_email_waits_when_a_colleague_heard_from_us_the_day_before(cur, scene):  # noqa: F811
    _clock(cur, MONDAY)
    timeutil.load_holidays(cur)
    send(cur, scene["message"])
    db.run(cur, "update messages set sent_at = %s where id = %s", MONDAY, scene["message"])
    p2, e2 = _colleague(cur, scene, state="active")
    e2row = db.one(cur, "select * from enrollments where id = %s", e2)
    p2row = db.one(cur, "select * from people where id = %s", p2)
    wait = outreach.colleague_clear(cur, e2row, p2row, MONDAY + timedelta(days=1))
    assert wait == timeutil.add_business_days(MONDAY, 2, country="US", timezone="America/New_York")
    assert outreach.colleague_clear(cur, e2row, p2row, MONDAY + timedelta(days=3)) is None


# ---------------------------------------------------------------- 6. a country with no rule

def test_no_cold_email_to_a_country_without_a_rule(cur, scene):  # noqa: F811
    db.run(cur, "delete from region_rules where country = 'SG'")
    db.run(cur, "update people set country = 'SG' where id = %s", scene["person"])
    reasons = gate.person_reasons(cur, scene["person"], "email", enrollment_id=scene["enrollment"])
    assert [(r.code, r.permanent, r.message) for r in reasons if r.code == "no_region_rule"] == [
        ("no_region_rule", True, "Email in Singapore needs a region rule first")]
    refused(cur, scene["message"], "no region rule for SG")
    db.run(cur, "update people set country = null where id = %s", scene["person"])
    assert "Their country is not known, so no cold email until it is" in [
        r.message for r in gate.person_reasons(cur, scene["person"], "email", enrollment_id=scene["enrollment"])]
    refused(cur, scene["message"], "no region rule")
    # Recorded consent is enough anywhere.
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'consent')", scene["person"])
    send(cur, scene["message"])


# ---------------------------------------------------------------- 2. and 8. a new finance leader

def _announce(cur, scene, name="Lena Hart", title="VP Finance", days_ago=5):  # noqa: F811
    _types(cur, "new_exec")
    when = db.val(cur, "select app_now()") - timedelta(days=days_ago)
    signals.ingest(cur, "news_feed", [{
        "type": "new_exec", "external_id": f"ann-{name}", "account_id": scene["account"], "observed_at": when,
        "strength": 0.9, "evidence": {"summary": f"Appointed {name} as {title} on {when.day} {when:%B}.", "quote": "x"},
        "person": {"full_name": name, "title": title}}])
    return when


def test_an_announced_leader_is_put_in_the_seat_from_the_day_they_started(cur, scene):  # noqa: F811
    when = _announce(cur, scene)
    p = db.one(cur, "select * from people where account_id = %s and full_name = 'Lena Hart'", scene["account"])
    assert (p["title"], p["role_started_at"]) == ("VP Finance", when.date())
    assert db.val(cur, "select person_id from signals where external_id = 'ann-Lena Hart'") == p["id"]
    assert db.val(cur, "select person_id from facts where account_id = %s and kind = 'signal:new_exec'", scene["account"]) == p["id"]
    # Someone already on record by that name is updated, not duplicated.
    db.run(cur, "update people set full_name = 'Ana Test', title = 'Controller', role_started_at = '2023-06-19' where id = %s",
           scene["person"])
    _announce(cur, scene, name="Ana Test", title="CFO", days_ago=2)
    ana = db.one(cur, "select * from people where id = %s", scene["person"])
    assert ana["title"] == "CFO" and ana["role_started_at"] > datetime(2026, 1, 1).date()


def test_news_of_a_new_leader_is_never_written_to_someone_long_in_that_seat(cur, scene):  # noqa: F811
    _announce(cur, scene)
    fact = db.one(cur, "select * from facts where account_id = %s and kind = 'signal:new_exec'", scene["account"])
    db.run(cur, "update people set title = 'CFO', role_started_at = '2023-06-19' where id = %s", scene["person"])
    long_seated = db.one(cur, "select * from people where id = %s", scene["person"])
    lena = db.one(cur, "select * from people where account_id = %s and full_name = 'Lena Hart'", scene["account"])
    assert outreach.seat_news_not_theirs(cur, fact, long_seated)
    assert not outreach.seat_news_not_theirs(cur, fact, lena)
    # A controller may hear that their company has a new finance leader; it does not congratulate them.
    db.run(cur, "update people set title = 'Controller' where id = %s", scene["person"])
    assert not outreach.seat_news_not_theirs(cur, fact, db.one(cur, "select * from people where id = %s", scene["person"]))
    # News that names nobody is not written to someone who has sat in the seat for years.
    db.run(cur, "update people set title = 'CFO' where id = %s", scene["person"])
    nameless = {**fact, "person_id": None}
    assert outreach.seat_news_not_theirs(cur, nameless, long_seated)


def test_a_new_controller_is_not_a_new_finance_leader(cur, scene):  # noqa: F811
    _types(cur, "new_exec")
    started = db.val(cur, "select (app_now() - interval '20 days')::date")
    db.run(cur, "update people set title = 'Corporate Controller' where id = %s", scene["person"])
    enrichment.apply_person(cur, scene["person"], {"departments": ["finance", "accounting"], "role_started_at": started,
                                                   "match_confidence": "high"}, "test_people")
    assert db.val(cur, "select count(*) from signals where account_id = %s and type_key = 'new_exec'", scene["account"]) == 0
    db.run(cur, "update people set title = 'VP Finance' where id = %s", scene["person"])
    enrichment.apply_person(cur, scene["person"], {"role_started_at": started, "match_confidence": "high"}, "test_people")
    assert db.val(cur, "select count(*) from signals where account_id = %s and type_key = 'new_exec'", scene["account"]) == 1


# ---------------------------------------------------------------- 3. and nits: what a signal may say

def test_a_competitor_review_is_never_shown_to_the_drafter(cur, scene):  # noqa: F811
    db.run(cur, """insert into facts (account_id, kind, text, source, observed_at)
                   values (%s, 'signal:competitor_review', 'Left a review of Chargewise.', 'reviews_feed', app_now())""",
           scene["account"])
    assert "signal:competitor_review" in {f"signal:{k}" for k in outreach.PRIVATE_SIGNALS}
    assert all(f["kind"] != "signal:competitor_review" for f in outreach.account_facts(cur, scene["account"]))


def test_a_competing_billing_tool_arriving_is_not_good_news_and_only_one_leaving_is(cur, scene):  # noqa: F811
    _types(cur, "tech_added", "tech_removed")
    db.run(cur, """insert into settings (key, value) values ('competing_tools', %s)
                   on conflict (key) do update set value = excluded.value""", J(["Chargewise", "Chargebee"]))
    account = db.one(cur, "select * from accounts where id = %s", scene["account"])
    since = db.val(cur, "select app_now() - interval '30 days'")
    enrichment._changes(cur, account, {"technologies": ["Chargewise", "Stripe", "HubSpot"]},
                        {"technologies": ["Stripe", "Chargebee", "Snowflake"]}, since=since)
    said = {r["type_key"]: r["s"] for r in db.all(cur, """select type_key, evidence->>'summary' as s from signals
                                                          where account_id = %s and source = 'enrichment'""", scene["account"])}
    assert said == {"tech_added": "Started using Snowflake.", "tech_removed": "Stopped using Chargewise."}


def test_reasons_read_as_sentences(cur, scene):  # noqa: F811
    db.run(cur, "update accounts set lifecycle = 'open_opp' where id = %s", scene["account"])
    assert "Account is an open opportunity" in [r.message for r in gate.account_reasons(cur, scene["account"])]


# ---------------------------------------------------------------- 7. one deal, one meeting, its own contact

def test_a_deal_is_credited_to_the_meeting_held_with_its_contact(cur, scene):  # noqa: F811
    now = db.val(cur, "select app_now()")
    bo, _ = _colleague(cur, scene, state="active")
    db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source, dedup_key)
                   values (%s, %s, %s, 'email', 'out', 'email_sent', %s, 'desk', %s)""",
           scene["account"], scene["person"], scene["ap"], now - timedelta(days=20), f"t{id(cur)}")
    meetings = {}
    for who, days in ((scene["person"], 10), (bo, 5)):  # the deal's contact met first; a colleague met later
        meetings[who] = db.val(cur, """insert into meetings (account_play_id, account_id, person_id, booked_at, starts_at, status, source)
                                       values (%s, %s, %s, %s, %s, 'held', 'sdr') returning id""",
                               scene["ap"], scene["account"], who, now - timedelta(days=days), now - timedelta(days=days - 1))
    ana_email = db.val(cur, "select email from people where id = %s", scene["person"])
    o = db.val(cur, """insert into opportunities (account_id, crm_id, name, amount_cents, stage, created_at, contact_email)
                       values (%s, %s, 'Deal', 100, 'Discovery', %s, %s) returning id""",
               scene["account"], f"crm{id(cur)}", now - timedelta(days=1), ana_email.upper())
    assert pipeline.attribute(cur, o) == "sourced"
    assert db.val(cur, "select attribution_meeting_id from opportunities where id = %s", o) == meetings[scene["person"]]
    # When the contact's own meeting was an inbound request, a colleague's outbound meeting does not source the deal.
    db.run(cur, "update meetings set source = 'inbound' where id = %s", meetings[scene["person"]])
    assert pipeline.attribute(cur, o) == "influenced"


# ---------------------------------------------------------------- nits: costs and research-stage plays

def test_reading_a_website_is_logged_as_free_with_no_ledger_row(cur):
    with spend.free_call(cur, "research", "pages") as info:
        info["pages"] = 3
    with db.tx() as own:
        call = db.one(own, "select * from adapter_calls where adapter = 'research' order by id desc limit 1")
        assert call["paid"] is False and call["ok"] is True
        assert db.val(own, "select count(*) from ledger where adapter_call_id = %s", call["id"]) == 0
    assert "research" not in spend.RATES


def test_a_research_stage_play_stays_open_while_the_sdr_writes(cur, scene):  # noqa: F811
    db.run(cur, "update plays set sequence = %s where id = %s",
           J([{"day": 0, "channel": "email", "job": "open", "by": "desk"}, {"day": 10, "channel": "email", "job": "break_up",
                                                                             "by": "desk"}]), scene["play"])
    db.run(cur, "update messages set status = 'cancelled' where id = %s", scene["message"])
    db.run(cur, """update enrollments set state = 'done', stop_reason = 'rep_writes', created_at = app_now() - interval '1 day'
                   where id = %s""", scene["enrollment"])
    plays.close_stale(cur, {})
    assert db.val(cur, "select state from account_plays where id = %s", scene["ap"]) == "active"
    db.run(cur, "update enrollments set created_at = app_now() - interval '20 days' where id = %s", scene["enrollment"])
    plays.close_stale(cur, {})
    assert db.one(cur, "select state, close_reason from account_plays where id = %s", scene["ap"]) == {
        "state": "stopped", "close_reason": "sequence_finished"}
