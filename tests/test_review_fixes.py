"""Regression tests for the second code review's findings (2026-11-11)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from test_guarantees import refused, scene  # noqa: F401

from outbound import db, outreach, pipeline, privacy, replies, sdr_steps, setup_desk, spend


def _erase_hash(cur, email: str) -> None:
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hash', "
                "encode(sha256(convert_to(%s, 'UTF8')), 'hex'), 'Erased on request', 'erasure')", email)


def test_an_erased_person_cannot_be_imported_again(cur, scene):  # noqa: F811
    domain = db.val(cur, "select primary_domain from accounts where id = %s", scene["account"])
    db.run(cur, "insert into account_domains (domain, account_id) values (%s, %s) on conflict do nothing", domain, scene["account"])
    _erase_hash(cur, "gone@" + domain)
    out = setup_desk.import_people(cur, f"full_name,company_domain,email\nGone Person,{domain},gone@{domain}\n")
    assert out["imported"] == 0 and "erased" in out["refused"][0]["why"]


def test_a_referral_address_outside_the_account_is_not_used(cur, scene):  # noqa: F811
    rid = db.val(cur, """insert into replies (person_id, account_id, received_at, from_addr, raw, cleaned, label, extracted)
                         values (%s, %s, now(), 'ana@x.example', 'Talk to Jane', 'Talk to Jane', 'referral', %s) returning id""",
                 scene["person"], scene["account"], db.J({"referral": {"name": "Jane Roe", "email": "jane@othercompany.example"}}))
    outreach.enroll_referral(cur, {"reply_id": rid})
    assert db.val(cur, "select email from people where full_name = 'Jane Roe' and account_id = %s", scene["account"]) is None


def test_erasure_takes_their_name_out_of_signals(cur, scene):  # noqa: F811
    db.run(cur, "update people set full_name = 'Ana Test' where id = %s", scene["person"])
    sid = db.val(cur, """insert into signals (type_key, source, external_id, account_id, person_id, observed_at, strength, evidence, status)
                         values ('t_sig', 't_src', 'erase-sig', %s, %s, now(), 0.5, %s, 'matched') returning id""",
                 scene["account"], scene["person"], db.J({"summary": "Ana Test joined Acme.", "quote": "hi"}))
    privacy.erase(cur, scene["person"], actor_id=None)
    ev = db.val(cur, "select evidence from signals where id = %s", sid)
    assert "Ana Test" not in ev["summary"] and ev["quote"] == "Removed on request"


def test_a_job_change_signal_never_names_the_person(cur, scene):  # noqa: F811
    db.run(cur, """insert into signal_types (key, label, because, level, weight, half_life_days)
                   values ('job_change', 'Someone we know moved', 'A person we spoke to joined this company.', 'person', 12, 60)
                   on conflict do nothing""")
    rid = db.val(cur, """insert into replies (person_id, account_id, received_at, from_addr, raw, cleaned, label, extracted)
                         values (%s, %s, now(), 'ana@x.example', 'I am now at Zed Co', 'I am now at Zed Co', 'left_company', %s)
                         returning id""", scene["person"], scene["account"], db.J({"new_company": "Zed Co"}))
    replies._moved_signal(cur, db.one(cur, "select * from replies where id = %s", rid), scene["person"])
    summary = db.val(cur, "select evidence->>'summary' from signals where external_id = %s", f"reply-{rid}")
    assert summary and db.val(cur, "select full_name from people where id = %s", scene["person"]) not in summary


def test_stopping_a_person_closes_their_open_call(cur, scene):  # noqa: F811
    tid = db.val(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                         values (%s, %s, 'call', 'Call', now(), %s) returning id""", scene["ap"], scene["person"], scene["user"])
    outreach.stop_enrollment(cur, scene["enrollment"], "unsubscribed", close_play=False)
    assert db.val(cur, "select status from tasks where id = %s", tid) == "skipped"


def test_an_opted_out_person_is_not_called(cur, scene):  # noqa: F811
    tid = db.val(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                         values (%s, %s, 'call', 'Call', now(), %s) returning id""", scene["ap"], scene["person"], scene["user"])
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('person', %s, 'Unsubscribed', 'link')",
           str(scene["person"]))
    with pytest.raises(ValueError, match="refused"):
        sdr_steps.complete(cur, tid, user={"id": scene["user"], "role": "sdr"}, outcome="connected")
    assert db.val(cur, "select count(*) from touches where dedup_key = %s", f"task:{tid}") == 0


def test_a_conversation_keeps_the_play_open_for_its_meeting(cur, scene):  # noqa: F811
    sdr_steps.in_conversation(cur, scene["person"], scene["ap"])
    assert db.val(cur, "select state from account_plays where id = %s", scene["ap"]) == "engaged"
    mid = pipeline.book_meeting(cur, account_id=scene["account"], person_id=scene["person"],
                                starts_at=datetime(2026, 12, 1, tzinfo=timezone.utc), source="sdr")
    assert db.val(cur, "select account_play_id from meetings where id = %s", mid) == scene["ap"]


def test_a_departed_sdr_never_gets_accounts_back_from_the_crm(cur, scene):  # noqa: F811
    db.run(cur, "update users set active = false, email = 'gone.sdr@x.example' where id = %s", scene["user"])
    assert pipeline.apply_owner(cur, scene["account"], "gone.sdr@x.example") == "not_on_desk"


def test_owner_changes_sharing_a_timestamp_are_all_read(cur, scene):  # noqa: F811
    from outbound.adapters.sim import SimCrm
    db.run(cur, """insert into sim_crm_owner_changes (account_id, owner_email, updated_at)
                   select %s, 'x@x.example', app_now() - interval '1 hour' from generate_series(1, 5)""", scene["account"])
    crm, since, seen = SimCrm(), None, 0
    while True:
        batch = crm.owners_changed(cur, since, 2)
        seen += len(batch)
        if not batch:
            break
        since = batch[-1].updated_at.isoformat() + "|" + batch[-1].change_id
    assert seen >= 5


def test_a_sequence_cannot_change_under_people_in_it(cur, scene):  # noqa: F811
    db.run(cur, "update enrollments set step_index = 9, next_at = app_now() - interval '1 hour' where id = %s", scene["enrollment"])
    db.run(cur, "update plays set sequence = %s where id = %s",
           db.J([{"day": 0, "channel": "email", "job": "open", "by": "desk"}]), scene["play"])
    outreach.due_steps(cur, {})
    assert db.val(cur, "select state from enrollments where id = %s", scene["enrollment"]) == "done"


def test_the_play_cap_alert_survives_the_job_rolling_back(cur, scene):  # noqa: F811
    db.run(cur, "update plays set monthly_cap = %s where id = %s", db.J({"email_verifier": 0}), scene["play"])
    with spend.for_play(scene["play"]), pytest.raises(spend.PlayOverBudget):
        spend.check_play(cur, "email_verifier", 1)
    with db.tx() as other:
        n = db.val(other, "select count(*) from alerts where dedup_key like %s", f"play_budget:{scene['play']}:%")
        db.run(other, "delete from alerts where dedup_key like %s", f"play_budget:{scene['play']}:%")
    assert n == 1


def test_an_email_to_someone_erased_by_profile_is_refused_by_the_database(cur, scene):  # noqa: F811
    db.run(cur, "update people set linkedin_url = 'https://www.linkedin.com/in/ana-test-x' where id = %s", scene["person"])
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('linkedin_hash', %s, 'Erased', 'erasure')",
           privacy.linkedin_hash("https://www.linkedin.com/in/ana-test-x"))
    refused(cur, scene["message"], "suppressed")
