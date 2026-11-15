"""Outbound copy rework (bl_123, decision 89): a plain note to a stranger. The gate holds the stock lines out, accepts a
greeting and a possessive, and the stand-in drafts follow the same three beats the prompt asks of the model."""
from __future__ import annotations

from test_units import ACCOUNT, FACTS, PERSON, codes, draft

from outbound import copy_gate, sim_llm


def check(d, job="open", **kw):
    return copy_gate.check(d, job=job, person=PERSON, account=ACCOUNT, facts=FACTS, our_names=["Lumen Ledger", "Priya Natarajan"],
                           other_bodies=[], **kw)


NOTE = [("Hi Maya,", "courtesy", []),
        ("I saw that Quillridge Systems posted a job for a Billing Specialist.", "claim", [1]),
        ("I'm Priya at Lumen Ledger. We do usage-based billing for finance teams.", "courtesy", []),
        ("If invoicing sits with you, is it worth a conversation?", "ask", []),
        ("If it isn't, say so and I won't follow up.", "courtesy", [])]


def test_a_plain_note_with_a_greeting_passes_and_is_short_enough():
    v = check(draft(*NOTE))
    assert v.passed, v.failures
    assert 30 <= v.words <= 90 and copy_gate.LIMITS["open"][0] == 30


def test_the_stock_lines_are_refused_in_sentences_about_us_but_not_in_a_cited_claim():
    for line in ("Finance teams that shift often find invoicing gets heavier.", "We work with controllers at similar firms.",
                 "I also noticed you are hiring.", "We help teams review rather than assemble invoices."):
        d = draft(*NOTE[:3], (line, "courtesy", []), *NOTE[3:])
        assert "stock_line" in codes(check(d)), line
    d = draft(*NOTE)
    assert "stock_line" not in codes(check(d))
    assert "stock_line" in codes(check(draft(("Maya,", "courtesy", []), *NOTE[1:3], ("Following up on my last note.", "courtesy", []),
                                              *NOTE[3:]), job="follow_up"))


def test_a_greeting_must_still_carry_the_first_name_and_a_possessive_is_the_company():
    bad = draft(("Hi there,", "courtesy", []), *NOTE[1:])
    assert "opening" in codes(check(bad))
    ok = draft(*NOTE[:1], ("I saw that Quillridge's team posted a job for a Billing Specialist.", "claim", [1]), *NOTE[2:])
    assert "unsourced_name" not in codes(check(ok))


def test_a_follow_up_may_not_repeat_a_sentence_of_the_earlier_email():
    earlier = "Hi Maya,\n\nI saw that Quillridge Systems posted a job for a Billing Specialist. We do usage-based billing for finance teams."
    d = draft(("Maya,", "courtesy", []), ("I saw that Quillridge Systems posted a job for a Billing Specialist.", "claim", [1]),
              ("Is that worth a conversation, or should I leave it there?", "ask", []))
    assert "repeats_earlier" in codes(check(d, job="follow_up", earlier=earlier))
    assert "repeats_earlier" not in codes(check(d, job="follow_up"))


def test_the_stand_in_drafts_follow_the_plain_note_and_pass_the_gate():
    base = {"company": "Quillridge Systems", "our_company": "Lumen Ledger", "sender": "Priya Natarajan", "angle": "",
            "play_angle": "", "brief": [], "persona_key": "cfo", "attempt": 2, "failures": [],
            "person": {"id": 7, "first_name": "Maya", "title": "Controller"},
            "facts": [{"id": 1, "kind": "signal:job_posting", "text": "Posted a job for a Billing Specialist."}]}
    for job, idx in (("open", 0), ("follow_up", 2)):
        out = sim_llm.draft({**base, "step": {"index": idx, "job": job}, "previous_subject": "billing"})
        v = copy_gate.check(out, job=job, person={"first_name": "Maya", "full_name": "Maya Okafor"},
                            account=ACCOUNT, facts={1: FACTS[1]}, our_names=["Lumen Ledger", "Priya Natarajan"], other_bodies=[])
        assert v.passed, (job, out, v.failures)
        text = " ".join(s["text"] for s in out["sentences"])
        assert not any(w in text for w in ("often find", "Teams that moved early", "One more thought", "Following up"))
    first = sim_llm.draft({**base, "step": {"index": 0, "job": "open"}, "previous_subject": None})["sentences"]
    assert first[0]["text"] == "Hi Maya," and "I'm Priya at Lumen Ledger" in first[2]["text"]
