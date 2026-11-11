"""Pure logic: scoring, the copy checks, reply cleaning and rules, statistics, business time."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from outbound import copy_gate, replies, scoring, stats, timeutil

# ---------------------------------------------------------------- scoring


def _inputs(signals, fit=90, tier="A", replies_=0, meetings=0):
    return {"fit": fit, "fit_tier": tier, "signals": signals, "positive_replies_90d": replies_, "meetings_held_90d": meetings}


def sig(i, t, w, hl, s=1.0, age=0.0):
    return {"id": i, "type": t, "weight": w, "half_life": hl, "strength": s, "age_days": age}


def test_decay_halves_at_half_life():
    fresh = scoring.compute(_inputs([sig(1, "a", 20, 10, age=0)]))
    half = scoring.compute(_inputs([sig(1, "a", 10, 10, age=0)]))
    aged = scoring.compute(_inputs([sig(1, "a", 20, 10, age=10)]))
    assert aged["intent"] == half["intent"] < fresh["intent"]


def test_convergence_rewards_distinct_types_not_repeats():
    same = scoring.compute(_inputs([sig(1, "a", 15, 30), sig(2, "a", 15, 30)]))
    distinct = scoring.compute(_inputs([sig(1, "a", 15, 30), sig(2, "b", 15, 30)]))
    assert distinct["intent"] > same["intent"]
    assert distinct["convergence"] == 1.15


def test_negative_signals_lower_intent_and_never_below_zero():
    pos = scoring.compute(_inputs([sig(1, "a", 20, 30)]))
    neg = scoring.compute(_inputs([sig(1, "a", 20, 30), sig(2, "layoffs", -15, 45)]))
    assert neg["intent"] < pos["intent"]
    assert scoring.compute(_inputs([sig(2, "layoffs", -50, 45)]))["intent"] == 0


def test_tier_c_has_no_priority():
    assert scoring.compute(_inputs([sig(1, "a", 30, 30)], fit=40, tier="C"))["priority"] == 0


def test_score_reproduces_from_its_inputs():
    i = _inputs([sig(1, "a", 22, 45, 0.8, 3.2), sig(2, "b", 14, 30, 0.6, 12.0)], replies_=1)
    assert scoring.compute(i) == scoring.compute(dict(i))


def test_fit_rules_and_excludes():
    rules = {"factors": [{"key": "industry", "field": "industry", "op": "in", "value": ["Software"], "weight": 50},
                         {"key": "size", "field": "employees", "op": "between", "value": [100, 1000], "weight": 50}],
             "excludes": [{"field": "industry", "op": "in", "value": ["Government"], "reason": "No public sector"}],
             "tiers": {"A": 85, "B": 50}}
    assert scoring.fit(rules, {"industry": "Software", "employees": 200})["tier"] == "A"
    assert scoring.fit(rules, {"industry": "Software", "employees": 20})["tier"] == "B"
    assert scoring.fit(rules, {"industry": "Government", "employees": 200})["tier"] == "X"
    assert scoring.fit(rules, {"industry": "Software", "employees": 200, "lifecycle": "customer"})["tier"] == "X"


# ---------------------------------------------------------------- copy checks

PERSON = {"first_name": "Maya", "last_name": "Okafor", "full_name": "Maya Okafor"}
ACCOUNT = {"name": "Quillridge Systems"}
FACTS = {1: "Posted a job for a Billing Specialist.", 2: "Invoices are produced with Chargewise.",
         3: "Raised a $25M Series B on 2 October."}


def draft(*sentences, subject="billing at Quillridge"):
    return {"subject": subject, "sentences": [{"text": t, "kind": k, "fact_ids": ids} for t, k, ids in sentences]}


GOOD = draft(("Maya,", "courtesy", []),
             ("Saw that Quillridge Systems posted a job for a Billing Specialist.", "claim", [1]),
             ("Your docs say invoices are produced with Chargewise.", "claim", [2]),
             ("That is usually when revenue recognition moves back into spreadsheets for the controller's team.", "courtesy", []),
             ("Worth 20 minutes next week to compare how other finance teams handled it?", "ask", []))


def check(d, job="open", **kw):
    return copy_gate.check(d, job=job, person=PERSON, account=ACCOUNT, facts=FACTS, our_names=["Lumen Ledger"],
                           other_bodies=kw.pop("others", []), **kw)


def codes(v):
    return {f["code"] for f in v.failures}


def test_a_good_draft_passes():
    v = check(GOOD)
    assert v.passed, v.failures


def test_uncited_claim_fails():
    d = draft(("Maya,", "courtesy", []), ("Quillridge is growing fast and needs a new billing system soon.", "claim", []),
              ("Saw that Quillridge Systems posted a job for a Billing Specialist recently, which is worth a look.", "claim", [1]),
              ("Worth a short call to compare notes on invoicing next week?", "ask", []))
    assert "uncited_claim" in codes(check(d))


def test_number_not_in_a_cited_fact_fails_but_a_meeting_length_does_not():
    d = draft(*GOOD["sentences"][0:1] and [(s["text"], s["kind"], s["fact_ids"]) for s in GOOD["sentences"]],
              ("Teams like yours cut close time by 43% in a quarter.", "courtesy", []))
    v = check(d)
    assert "unsourced_number" in codes(v)
    assert all("20" not in f["message"] for f in v.failures)


def test_cited_number_passes():
    d = draft(("Maya,", "courtesy", []), ("Congratulations on the $25M Series B announced in October.", "claim", [3]),
              ("Saw that Quillridge Systems posted a job for a Billing Specialist as well.", "claim", [1]),
              ("Boards tend to ask finance for cleaner revenue numbers after a round like that.", "courtesy", []),
              ("Is this on your list for this quarter?", "ask", []))
    assert check(d).passed, check(d).failures


def test_banned_phrases_dashes_and_links():
    d = draft(("Maya,", "courtesy", []), ("I hope this email finds you well.", "courtesy", []),
              *[(s["text"], s["kind"], s["fact_ids"]) for s in GOOD["sentences"][1:-1]],
              ("Worth a look — see https://lumen.example/demo for more?", "ask", []))
    c = codes(check(d))
    assert {"banned_phrase", "dash", "link"} <= c


def test_must_open_with_the_recorded_first_name_without_a_title():
    d = draft(*[(("Dr. Maya," if i == 0 else s["text"]), s["kind"], s["fact_ids"]) for i, s in enumerate(GOOD["sentences"])])
    assert "opening" in codes(check(d))
    assert copy_gate.clean_first_name("Dr. Maya", None) == "Maya"


def test_unknown_fact_ids_and_private_signals():
    d = draft(*[(s["text"], s["kind"], [99] if s["fact_ids"] == [2] else s["fact_ids"]) for s in GOOD["sentences"]])
    assert "unknown_fact" in codes(check(d))
    assert "private_signal" in codes(check(GOOD, private_ids={1}))


def test_invented_proper_noun_fails():
    d = draft(*[(s["text"], s["kind"], s["fact_ids"]) for s in GOOD["sentences"][:-1]],
              ("Your peers at Stripe moved last year; worth comparing notes next week?", "ask", []))
    assert "unsourced_name" in codes(check(d))


def test_near_duplicate_of_a_colleague_email_fails():
    text = " ".join(s["text"] for s in GOOD["sentences"])
    assert "near_duplicate" in codes(check(GOOD, others=[text]))


def test_length_limits_by_step():
    short = draft(("Maya,", "courtesy", []), ("Saw the Billing Specialist role.", "claim", [1]), ("Thoughts?", "ask", []))
    assert "length" in codes(check(short, job="open"))


# ---------------------------------------------------------------- replies

QUOTED = """Thanks, not for us right now.

On Tue, 6 Oct 2026 at 09:12, Maya Okafor wrote:
> Maya here. If this isn't relevant, reply "no thanks" or unsubscribe here and I won't write again.
"""
LEGAL = """Happy to talk next week.

Ana Silva | Controller
This email and any attachments are confidential. If you received it in error, please unsubscribe the sender and delete it."""


def test_clean_strips_quoted_history_signature_and_legal_footer():
    assert replies.clean(QUOTED) == "Thanks, not for us right now."
    assert "unsubscribe" not in replies.clean(LEGAL).lower()


def test_an_unsubscribe_inside_a_quote_or_footer_is_not_an_opt_out():
    assert replies.rules_label("ana@x.com", "Re: billing", replies.clean(QUOTED)) is None
    assert replies.rules_label("ana@x.com", "Re: billing", replies.clean(LEGAL)) is None


@pytest.mark.parametrize("text", ["Please remove me from your list.", "Unsubscribe", "Bitte keine weiteren E-Mails.",
                                  "Por favor, no me envíen más correos.", "Merci de ne plus me contacter."])
def test_opt_outs_in_five_languages(text):
    assert replies.rules_label("a@b.com", "Re: x", text)[0] == "unsubscribe"


@pytest.mark.parametrize("text", ["I'm out of the office until 14 October.", "Automatic reply: I am on leave.",
                                  "Abwesenheitsnotiz: Ich bin bis 11 October nicht im Büro.", "Estoy fuera de la oficina."])
def test_out_of_office_in_several_languages(text):
    assert replies.rules_label("a@b.com", "Re: x", text)[0] == "out_of_office"


def test_bounces_are_recognised_by_sender():
    assert replies.rules_label("MAILER-DAEMON@mx.example.com", "Delivery Status Notification", "x")[0] == "bounce"


def test_return_dates():
    got = replies.parse_return("back on 14 october", datetime(2026, 10, 2, tzinfo=timezone.utc))
    assert got.month == 10 and got.day == 14
    assert replies.parse_return("january", datetime(2026, 11, 2, tzinfo=timezone.utc)).year == 2027


# ---------------------------------------------------------------- statistics


def test_wilson_known_value():
    lo, hi = stats.wilson(81, 263, conf=0.95)
    assert math.isclose(lo, 0.2553, abs_tol=0.001) and math.isclose(hi, 0.3662, abs_tol=0.001)


def test_newcombe_known_value():
    # Newcombe (1998), example (a): 56/70 vs 48/80, 95% interval 0.0524 to 0.3339.
    d, lo, hi = stats.newcombe(56, 70, 48, 80, conf=0.95)
    assert math.isclose(d, 0.2, abs_tol=1e-9)
    assert math.isclose(lo, 0.0524, abs_tol=0.0005) and math.isclose(hi, 0.3339, abs_tol=0.0005)


def test_small_samples_say_not_enough():
    r = stats.lift_report(3, 40, 0, 10)
    assert r["enough"] is False and r["needed"]["holdout"] > 10


# ---------------------------------------------------------------- business time

WINDOW = timeutil.windows([["08:30", "11:30"], ["13:30", "16:00"]])


def test_next_slot_skips_weekend_and_holiday():
    timeutil._holiday_cache.clear()
    timeutil._holiday_cache["US"] = {datetime(2026, 11, 26).date()}
    fri_evening = datetime(2026, 11, 20, 23, 0, tzinfo=timezone.utc)  # Friday 18:00 in New York
    slot = timeutil.next_slot(fri_evening, timezone="America/New_York", country="US", window=WINDOW)
    local = slot.astimezone(timeutil.tz("America/New_York"))
    assert local.weekday() == 0 and local.hour == 8 and local.minute >= 30
    wed_evening = datetime(2026, 11, 25, 23, 0, tzinfo=timezone.utc)
    after_holiday = timeutil.next_slot(wed_evening, timezone="America/New_York", country="US", window=WINDOW)
    assert after_holiday.astimezone(timeutil.tz("America/New_York")).day == 27


def test_business_hours_for_reply_deadlines():
    fri_5pm = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)  # 17:00 New York
    due = timeutil.add_business_hours(fri_5pm, 4, timezone="America/New_York")
    local = due.astimezone(timeutil.tz("America/New_York"))
    assert local.weekday() == 0 and local.hour == 12


def test_only_first_party_sources_are_free():
    """Website visits need a de-anonymization vendor; reviews, funding and news come from paid data vendors.
    Only data the company owns is free."""
    from outbound.seed.catalog import SIGNAL_SOURCES
    free = {key for key, _label, _adapter, _cadence, paid, _provider in SIGNAL_SOURCES if not paid}
    assert free == {"product", "crm", "events", "webhook"}
    assert all(provider for *_rest, provider in SIGNAL_SOURCES)


def test_ordinary_business_terms_are_not_unsourced_names():
    d = draft(*[(s["text"], s["kind"], s["fact_ids"]) for s in GOOD["sentences"][:-2]],
              ("That is usually where billing and the CRM stop agreeing on what was sold for SaaS teams.", "courtesy", []),
              ("Open to a short call next week?", "ask", []))
    assert "unsourced_name" not in codes(check(d))


def test_the_public_demo_links_to_itself_not_localhost():
    from pathlib import Path
    docker = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert "PUBLIC_URL=https://outbound-desk.onrender.com" in docker
