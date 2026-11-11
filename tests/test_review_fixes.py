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


def test_a_deal_on_an_unknown_account_is_held_and_read_once_the_account_exists(cur, scene):  # noqa: F811
    from outbound.adapters import CrmDeal
    now = db.val(cur, "select app_now()")
    d = CrmDeal("held-1", "notyet.example", "New deal", 5000, "Discovery", now, now)
    assert pipeline.upsert_deal(cur, d) is None
    pipeline.hold_deal(cur, d)
    assert pipeline.retry_held_deals(cur) == 0  # still unknown: stays held
    aid = db.val(cur, "insert into accounts (name, primary_domain) values ('Not Yet', 'notyet.example') returning id")
    db.run(cur, "insert into account_domains (domain, account_id) values ('notyet.example', %s)", aid)
    assert pipeline.retry_held_deals(cur) == 1
    assert db.val(cur, "select account_id from opportunities where crm_id = 'held-1'") == aid
    assert db.val(cur, "select count(*) from crm_held_deals where crm_id = 'held-1'") == 0


def test_in_flight_shows_each_persons_sequence_and_what_comes_next(cur, scene):  # noqa: F811
    from outbound import views
    seq = [{"day": 0, "channel": "email", "job": "open", "by": "desk"}, {"day": 3, "channel": "call", "job": "call", "by": "sdr"}]
    db.run(cur, "update plays set sequence = %s where id = %s", db.J(seq), scene["play"])
    db.run(cur, "update messages set status = 'sent', sent_at = now() where id = %s", scene["message"])
    db.run(cur, "update enrollments set step_index = 1, next_at = app_now() + interval '1 day' where id = %s", scene["enrollment"])
    out = views.in_flight(cur, {"id": scene["user"]}, mine=True)
    play = next(p for p in out["plays"] if p["id"] == scene["ap"])
    assert play["people"][0]["sent"] == [0]
    assert play["next"]["step"]["channel"] == "call"
    assert out["counts"]["active"] >= 1


def test_heyreach_events_reach_the_right_person_once(cur, scene):  # noqa: F811
    from outbound import linkedin_tool
    db.run(cur, "update people set linkedin_url = 'https://www.linkedin.com/in/ana-test-hr/' where id = %s", scene["person"])
    acc = {"event_type": "CONNECTION_REQUEST_ACCEPTED", "lead": {"profile_url": "http://linkedin.com/in/Ana-Test-HR"}}
    assert linkedin_tool.handle(cur, acc)["person_id"] == scene["person"]
    linkedin_tool.handle(cur, acc)
    assert db.val(cur, "select count(*) from touches where person_id = %s and kind = 'linkedin_accepted'", scene["person"]) == 1
    rep = {"event_type": "message_reply_received", "conversation_id": "c1",
           "lead": {"profile_url": "https://linkedin.com/in/ana-test-hr"},
           "recent_messages": [{"message": "Hi Ana", "is_reply": False, "timestamp": "2026-11-10T10:00:00Z"},
                               {"message": "Not right now, thanks.", "is_reply": True, "timestamp": "2026-11-10T12:00:00Z"}]}
    first = linkedin_tool.handle(cur, rep)
    assert first["applied"] and linkedin_tool.handle(cur, rep)["duplicate"]
    assert db.val(cur, "select state from enrollments where id = %s", scene["enrollment"]) == "paused"
    assert not linkedin_tool.handle(cur, {**rep, "lead": {"profile_url": "https://linkedin.com/in/nobody"}})["applied"]


def test_a_message_written_already_sent_meets_the_same_rules(cur, scene):  # noqa: F811
    db.run(cur, "update settings set value = 'true' where key = 'kill_switch'")
    with pytest.raises(Exception, match="kill switch"):
        db.run(cur, r"""insert into messages (enrollment_id, step_index, channel, subject, body, status, body_hash, approved_hash,
                        approved_at, approval_mode, sent_at, mailbox_id)
                        values (%s, 7, 'email', 's', 'b', 'sent', 'h', encode(sha256(convert_to('s' || E'\n' || 'b', 'UTF8')), 'hex'),
                                now(), 'person', app_now(), %s)""", scene["enrollment"], scene["mailbox"])


def test_a_finished_call_counts_as_a_done_step_in_flight(cur, scene):  # noqa: F811
    from outbound import views
    seq = [{"day": 0, "channel": "email", "job": "open", "by": "desk"}, {"day": 2, "channel": "call", "job": "call", "by": "sdr"},
           {"day": 5, "channel": "email", "job": "bump", "by": "desk"}]
    db.run(cur, "update plays set sequence = %s where id = %s", db.J(seq), scene["play"])
    db.run(cur, "update messages set status = 'sent', sent_at = now() where id = %s", scene["message"])
    db.run(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id, status, done_at)
                   values (%s, %s, 'call', 'Call', now(), %s, 'done', now())""", scene["ap"], scene["person"], scene["user"])
    db.run(cur, "update enrollments set step_index = 2 where id = %s", scene["enrollment"])
    out = views.in_flight(cur, {"id": scene["user"]}, mine=True)
    person = next(p for p in out["plays"] if p["id"] == scene["ap"])["people"][0]
    assert person["sent"] == [0, 1]


def test_the_email_waterfall_asks_the_next_finder_and_pays_only_for_answers(cur, scene, monkeypatch):  # noqa: F811
    from outbound import adapters

    class Step:
        def __init__(self, provider, answer):
            self.provider, self.answer, self.name, self.asked = provider, answer, provider, 0

        def find(self, cur, person, domain):
            self.asked += 1
            return self.answer

    class Valid:
        name = "test_verifier"

        def verify(self, cur, email):
            return "valid"

    from contextlib import contextmanager
    charged = []

    @contextmanager
    def record(cur, adapter, operation, **kw):
        info = {}
        yield info
        charged.append((adapter, info.get("charged_qty", kw["qty"])))

    monkeypatch.setattr(outreach.spend, "paid_call", record)
    first, second, third = Step("first", None), Step("second", "ana.found@x.example"), Step("third", "never@x.example")
    ad = adapters.get()
    monkeypatch.setattr(ad, "finders", [first, second, third])
    monkeypatch.setattr(ad, "verifier", Valid())
    db.run(cur, "update people set email = null, email_status = 'unknown', email_verified_at = null where id = %s", scene["person"])
    person = db.one(cur, "select * from people where id = %s", scene["person"])
    account = db.one(cur, "select * from accounts where id = %s", scene["account"])
    assert outreach._ensure_email(cur, person, account) == "valid"
    assert (first.asked, second.asked, third.asked) == (1, 1, 0)
    assert db.val(cur, "select email from people where id = %s", scene["person"]) == "ana.found@x.example"
    assert charged == [("email_finder:first", 0), ("email_finder:second", 1), ("email_verifier", 1)]


def _fresh_draft(cur, scene, step: int) -> int:  # noqa: F811
    return db.val(cur, """insert into messages (enrollment_id, step_index, channel, subject, body, status, body_hash)
                          values (%s, %s, 'email', 's', 'b', 'awaiting_approval', '') returning id""", scene["enrollment"], step)


def test_an_autonomous_play_sends_tier_b_on_its_own_and_tier_a_still_waits(cur, scene):  # noqa: F811
    db.run(cur, "update plays set autonomy = 'autonomous' where id = %s", scene["play"])
    db.run(cur, "update accounts set fit_tier = 'B' where id = %s", scene["account"])
    b = _fresh_draft(cur, scene, 3)
    assert outreach.maybe_auto_approve(cur, b)
    assert db.val(cur, "select approval_mode from messages where id = %s", b) == "auto_autonomous"
    db.run(cur, "update accounts set fit_tier = 'A' where id = %s", scene["account"])
    a = _fresh_draft(cur, scene, 4)
    assert not outreach.maybe_auto_approve(cur, a)
    assert db.val(cur, "select status from messages where id = %s", a) == "awaiting_approval"


def test_a_complaint_moves_an_autonomous_play_back_a_stage(cur, scene):  # noqa: F811
    from outbound import plays
    db.run(cur, "update plays set autonomy = 'autonomous', status = 'live', launched_by = %s, launched_at = now() where id = %s", scene["user"], scene["play"])
    db.run(cur, "insert into deliveries (message_id, event, at) values (%s, 'complaint', app_now())", scene["message"])
    plays.autonomy_watch(cur, {})
    assert db.val(cur, "select autonomy from plays where id = %s", scene["play"]) == "supervised"
    assert db.val(cur, "select reason from play_stage_changes where play_id = %s", scene["play"]) == "A spam complaint"


def test_heavy_editing_moves_a_supervised_play_back_to_drafts(cur, scene):  # noqa: F811
    from outbound import plays
    db.run(cur, "update plays set autonomy = 'supervised', status = 'live', launched_by = %s, launched_at = now() where id = %s", scene["user"], scene["play"])
    for i in range(20):
        m = _fresh_draft(cur, scene, 20 + i)
        db.run(cur, """update messages set status = 'approved', approved_hash = body_hash, approval_mode = 'person',
                       approved_at = app_now() - (%s || ' minutes')::interval, edited = %s where id = %s""", str(i), i < 7, m)
    plays.autonomy_watch(cur, {})
    assert db.val(cur, "select autonomy from plays where id = %s", scene["play"]) == "draft"
