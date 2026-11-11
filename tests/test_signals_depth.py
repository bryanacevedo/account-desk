"""The signals layer's second review (2026-11-11): event dates, one event counted once, no stranded moments, a signal
starts at most one play, honest per-signal results."""
from __future__ import annotations

from test_guarantees import scene  # noqa: F401

from outbound import db, enrichment, plays, scoring, views


def _sig(type_, source, age, weight=20, strength=1.0, half_life=30, sid=1):
    return {"id": sid, "type": type_, "source": source, "weight": weight, "strength": strength, "half_life": half_life,
            "age_days": age}


def _intent(sigs):
    return scoring.compute({"fit": 80, "fit_tier": "A", "signals": sigs})["intent"]


def test_the_same_event_from_two_sources_counts_once_with_a_small_bonus():
    one = _intent([_sig("new_exec", "news_feed", 2)])
    two_sources = _intent([_sig("new_exec", "news_feed", 2, sid=1), _sig("new_exec", "enrichment", 3, sid=2)])
    same_source_twice = _intent([_sig("new_exec", "news_feed", 2, sid=1), _sig("new_exec", "news_feed", 3, sid=2)])
    assert one < two_sources < 2 * one          # surer, not double
    assert same_source_twice == one             # a repeat from one source adds nothing


def test_a_daily_signal_cannot_carry_an_account_on_its_own():
    daily = [_sig("site_visit", "web_visits", d, weight=8, half_life=10, sid=d) for d in range(0, 60)]
    capped = scoring.compute({"fit": 80, "fit_tier": "A", "signals": daily})
    total = sum(c["value"] for c in capped["contributions"])
    assert total <= 8 * scoring.TYPE_CAP + 1e-6


def test_enrichment_dates_a_new_seat_by_when_it_started(cur, scene):  # noqa: F811
    db.run(cur, """insert into signal_types (key, label, because, level, weight, half_life_days)
                   values ('new_exec', 'New finance leader', 'Because of a test signal', 'person', 20, 45) on conflict do nothing""")
    db.run(cur, "update people set title = 'VP Finance' where id = %s", scene["person"])
    started = db.val(cur, "select (app_now() - interval '80 days')::date")
    enrichment.apply_person(cur, scene["person"], {"departments": ["finance"], "role_started_at": started,
                                                   "match_confidence": "high"}, "test_people")
    observed = db.val(cur, "select observed_at::date from signals where account_id = %s and type_key = 'new_exec'", scene["account"])
    assert observed == started


def _live_play(cur, scene, any_of):
    db.run(cur, """update plays set status = 'live', launched_by = %s, launched_at = now(), trigger = %s,
                   sequence = %s where id = %s""", scene["user"], db.J({"any_of": any_of, "within_days": 60}),
           db.J([{"day": 0, "channel": "email", "job": "open", "by": "desk"}]), scene["play"])


def test_a_signal_starts_at_most_one_play(cur, scene):  # noqa: F811
    _live_play(cur, scene, ["t_sig"])
    play = db.one(cur, "select * from plays where id = %s", scene["play"])
    # The scene's account play was started by its signal, so that signal cannot start another.
    assert plays._trigger_signal(cur, play, scene["account"]) is None


def test_per_signal_results_say_when_they_are_too_few_or_not_measured(cur, scene):  # noqa: F811
    _live_play(cur, scene, ["t_sig"])
    db.run(cur, """insert into signal_types (key, label, because, level, weight, half_life_days)
                   values ('t_never', 'Never a trigger', 'Because of a test signal', 'account', 5, 10) on conflict do nothing""")
    rows = {r["key"]: r for r in views.signal_performance(cur)}
    assert rows["t_sig"]["starts_plays"] is True
    assert rows["t_sig"]["lift"] is not None and rows["t_sig"]["lift"]["enough"] is False
    assert rows["t_never"]["starts_plays"] is False
