"""People who come from replies: a referral becomes a person and, when it can, an enrollment; someone who left
becomes a job-change signal at their new company; a role that empties is refilled or explained."""
from __future__ import annotations

from test_guarantees import scene  # noqa: F401  (an account, a person, an active play)

from outbound import db, outreach, replies
from outbound.db import J


def _reply(cur, sc, text: str, label: str, extracted: dict) -> int:
    return db.val(cur, """insert into replies (message_id, person_id, account_id, received_at, from_addr, raw, cleaned, label,
                                               extracted, confidence, classified_by)
                          values (%s, %s, %s, now(), 'ana@x.example', %s, %s, %s, %s, 0.9, 'rules') returning id""",
                  sc["message"], sc["person"], sc["account"], text, text, label, J(extracted))


def test_a_referral_becomes_a_person_and_a_citable_fact(cur, scene):  # noqa: F811
    rid = _reply(cur, scene, "Talk to Bruno Diaz, our controller.", "referral",
                 {"referral": {"name": "Bruno Diaz", "title": "Corporate Controller"}})
    outreach.enroll_referral(cur, {"reply_id": rid})
    p = db.one(cur, "select id, source, title from people where account_id = %s and full_name = 'Bruno Diaz'", scene["account"])
    assert p and p["source"] == "referral"
    fact = db.val(cur, "select text from facts where person_id = %s and kind = 'referral'", p["id"])
    assert fact == "Ana Test suggested speaking with Bruno Diaz."
    # Either enrolled from the referral, or a task that says why not: never a silent stop.
    enrolled = db.val(cur, "select count(*) from enrollments where person_id = %s and via_referral", p["id"])
    task_note = db.val(cur, "select note from tasks where reply_id = %s and kind = 'referral'", rid)
    assert enrolled == 1 or task_note


def test_a_referral_with_no_open_play_leaves_a_task(cur, scene):  # noqa: F811
    db.run(cur, "update account_plays set state = 'stopped', close_reason = 'manual', closed_at = now() where id = %s", scene["ap"])
    rid = _reply(cur, scene, "Talk to Carla Ruiz.", "referral", {"referral": {"name": "Carla Ruiz"}})
    outreach.enroll_referral(cur, {"reply_id": rid})
    assert "No open play" in db.val(cur, "select note from tasks where reply_id = %s", rid)


def test_someone_who_left_raises_a_signal_at_their_new_company(cur, scene):  # noqa: F811
    db.run(cur, """insert into signal_types (key, label, because, level, weight, half_life_days)
                   values ('job_change', 'Someone we know moved', 'A person we spoke to joined.', 'person', 12, 60)
                   on conflict do nothing""")
    from outbound import signals
    other = db.val(cur, "insert into accounts (name, name_key, primary_domain, fit_tier) values ('Quillfeather Gauge', %s, %s, 'A') "
                        "returning id", signals.normalize_name("Quillfeather Gauge"), f"quillfeather{id(cur)}.example")
    db.run(cur, "insert into account_domains (domain, account_id) values (%s, %s) on conflict do nothing",
           f"quillfeather{id(cur)}.example", other)
    rid = _reply(cur, scene, "I'm no longer with Test Co. I'm now at Quillfeather Gauge.", "left_company",
                 {"new_company": "Quillfeather Gauge"})
    r = db.one(cur, "select * from replies where id = %s", rid)
    replies._moved_signal(cur, r, scene["person"])
    s = db.one(cur, "select type_key, status, account_id, evidence from signals where source = 'replies' and external_id = %s",
               f"reply-{rid}")
    assert s["type_key"] == "job_change" and s["status"] == "matched" and s["account_id"] == other
    assert "Quillfeather Gauge" in s["evidence"]["quote"]


def test_a_new_company_is_only_what_they_wrote():
    assert replies.NEW_CO.search("I'm now at Kestrel Health, happy to stay in touch.").group(1) == "Kestrel Health"
    assert replies.NEW_CO.search("I left last month.") is None


def test_an_emptied_role_is_refilled_from_people_on_record(cur, scene):  # noqa: F811
    db.run(cur, "update enrollments set state = 'stopped', stop_reason = 'left_company' where id = %s", scene["enrollment"])
    db.run(cur, "update people set status = 'left' where id = %s", scene["person"])
    nxt = db.val(cur, """insert into people (account_id, full_name, first_name, title, email, email_status, email_verified_at,
                                             source) values (%s, 'Dana Cole', 'Dana', 'CFO', %s, 'valid', app_now(), 'test')
                         returning id""", scene["account"], f"dana{id(cur)}@x.example")
    outreach.replace_person(cur, {"account_play_id": scene["ap"], "persona_key": "cfo"})
    assert db.val(cur, "select count(*) from enrollments where person_id = %s and account_play_id = %s", nxt, scene["ap"]) == 1
