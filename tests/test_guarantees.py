"""The promises the database enforces, tried directly against Postgres. Each test tries the bad write and expects
Postgres to refuse it, whatever the application code would have done."""
from __future__ import annotations

import psycopg
import pytest

from outbound import db
from outbound.db import J


@pytest.fixture
def scene(cur):
    """One account, one person, a treated account play, an active enrollment and an approved message."""
    db.run(cur, "insert into settings (key, value) values ('kill_switch', 'false'), ('account_max_active', '3') "
                "on conflict (key) do update set value = excluded.value")
    u = db.val(cur, "insert into users (name, email, role) values ('T', %s, 'sdr') returning id", f"t{id(cur)}@x.example")
    a = db.val(cur, "insert into accounts (name, primary_domain, fit_tier) values ('Test Co', %s, 'A') returning id",
               f"test{id(cur)}.example")
    p = db.val(cur, """insert into people (account_id, full_name, first_name, email, email_status, email_verified_at, source)
                       values (%s, 'Ana Test', 'Ana', %s, 'valid', now(), 'test') returning id""", a, f"ana{id(cur)}@x.example")
    db.run(cur, "insert into signal_types (key, label, because, level, weight, half_life_days) values "
                "('t_sig', 'Test', 'Because of a test signal', 'account', 10, 10) on conflict do nothing")
    db.run(cur, "insert into signal_sources (key, label, adapter, cadence_minutes) values ('t_src', 'T', 'sim', 60) "
                "on conflict do nothing")
    s = db.val(cur, """insert into signals (type_key, source, external_id, account_id, observed_at, strength, evidence, status)
                       values ('t_sig', 't_src', %s, %s, now(), 0.5, %s, 'matched') returning id""",
               f"x{id(cur)}", a, J({"summary": "x", "url": "https://x"}))
    pl = db.val(cur, """insert into plays (key, name, hypothesis, trigger, personas, sequence, angle) values
                        (%s, 'P', 'h', '{}', '{cfo}', '[]', 'a') returning id""", f"p{id(cur)}")
    ap = db.val(cur, """insert into account_plays (account_id, play_id, trigger_signal_id, arm, state, why_now, owner_id)
                        values (%s, %s, %s, 'treated', 'active', '{}', %s) returning id""", a, pl, s, u)
    db.run(cur, "insert into personas (key, label, title_patterns, committee_role, angle) values ('cfo', 'F', '{cfo}', "
                "'economic_buyer', 'a') on conflict do nothing")
    e = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state) values (%s, %s, 'cfo', 'active')
                       returning id""", ap, p)
    m = db.val(cur, """insert into messages (enrollment_id, step_index, channel, subject, body, status, body_hash)
                       values (%s, 0, 'email', 'hi', 'Ana, hello.', 'awaiting_approval', '') returning id""", e)
    db.run(cur, "update messages set approved_hash = body_hash, approved_at = now(), approval_mode = 'person', "
                "status = 'scheduled' where id = %s", m)
    return {"account": a, "person": p, "ap": ap, "enrollment": e, "message": m, "play": pl, "signal": s, "user": u}


def send(cur, m):
    with cur.connection.transaction():
        db.run(cur, "update messages set status = 'sending', sent_at = now(), mailbox_id = null where id = %s", m)


def refused(cur, m, match: str):
    with pytest.raises(psycopg.errors.RaiseException, match=match):
        send(cur, m)


def test_an_approved_message_can_be_sent(cur, scene):
    send(cur, scene["message"])


def test_body_changed_after_approval_is_refused(cur, scene):
    db.run(cur, "update messages set body = 'Ana, something else.' where id = %s", scene["message"])
    refused(cur, scene["message"], "body changed after approval")


def test_kill_switch_refuses_every_send(cur, scene):
    db.run(cur, "update settings set value = 'true' where key = 'kill_switch'")
    refused(cur, scene["message"], "kill switch")


def test_holdout_account_is_never_sent_to(cur, scene):
    with pytest.raises(psycopg.errors.CheckViolation):
        with cur.connection.transaction():
            db.run(cur, "update account_plays set arm = 'holdout' where id = %s", scene["ap"])


def test_suppressed_address_domain_and_erased_hash_are_refused(cur, scene):
    email = db.val(cur, "select email from people where id = %s", scene["person"])
    for kind, value in (("email", email), ("domain", email.split("@")[1]), ("person", str(scene["person"]))):
        with cur.connection.transaction():
            sid = db.val(cur, "insert into suppressions (kind, value, reason, source) values (%s,%s,'t','t') returning id",
                         kind, value)
            refused(cur, scene["message"], "suppressed")
            db.run(cur, "delete from suppressions where id = %s", sid)
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hash', "
                "encode(sha256(convert_to(%s, 'UTF8')), 'hex'), 'erased', 't')", email)
    refused(cur, scene["message"], "suppressed")


def test_paused_enrollment_cannot_send(cur, scene):
    db.run(cur, "update enrollments set state = 'paused', pause_reason = 'reply_received' where id = %s", scene["enrollment"])
    refused(cur, scene["message"], "enrollment")


def test_customer_and_parent_customer_are_refused(cur, scene):
    with cur.connection.transaction():
        db.run(cur, "update accounts set lifecycle = 'customer' where id = %s", scene["account"])
        refused(cur, scene["message"], "account is customer")
        db.run(cur, "update accounts set lifecycle = 'prospect' where id = %s", scene["account"])
    parent = db.val(cur, "insert into accounts (name, primary_domain, lifecycle) values ('Parent', %s, 'customer') returning id",
                    f"parent{id(cur)}.example")
    db.run(cur, "update accounts set parent_id = %s where id = %s", parent, scene["account"])
    refused(cur, scene["message"], "account is")


def test_unverified_email_and_consent_countries_are_refused(cur, scene):
    with cur.connection.transaction():
        db.run(cur, "update people set email_status = 'risky' where id = %s", scene["person"])
        refused(cur, scene["message"], "email not valid")
        db.run(cur, "update people set email_status = 'valid' where id = %s", scene["person"])
    db.run(cur, "insert into region_rules (country, rule) values ('ZZ', 'consent_required') on conflict do nothing")
    db.run(cur, "update people set country = 'ZZ' where id = %s", scene["person"])
    refused(cur, scene["message"], "basis")
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'consent')", scene["person"])
    send(cur, scene["message"])


def test_one_live_enrollment_per_person(cur, scene):
    with pytest.raises(psycopg.errors.UniqueViolation):
        with cur.connection.transaction():
            db.run(cur, "insert into enrollments (account_play_id, person_id, persona_key, state) values (%s,%s,'cfo','pending')",
                   scene["ap"], scene["person"])


def test_one_open_play_per_account(cur, scene):
    with pytest.raises(psycopg.errors.UniqueViolation):
        with cur.connection.transaction():
            db.run(cur, """insert into account_plays (account_id, play_id, trigger_signal_id, arm, state, why_now)
                           values (%s,%s,%s,'treated','proposed','{}')""", scene["account"], scene["play"], scene["signal"])


def test_account_cap_on_active_people(cur, scene):
    for i in range(2):
        p = db.val(cur, "insert into people (account_id, full_name, source) values (%s, %s, 't') returning id",
                   scene["account"], f"P{i}")
        db.run(cur, "insert into enrollments (account_play_id, person_id, persona_key, state) values (%s,%s,'cfo','active')",
               scene["ap"], p)
    p = db.val(cur, "insert into people (account_id, full_name, source) values (%s, 'Fourth', 't') returning id", scene["account"])
    with pytest.raises(psycopg.errors.RaiseException, match="already has 3 people active"):
        with cur.connection.transaction():
            db.run(cur, "insert into enrollments (account_play_id, person_id, persona_key, state) values (%s,%s,'cfo','active')",
                   scene["ap"], p)


def test_stops_drops_and_rejections_need_a_reason(cur, scene):
    for sql in ("update enrollments set state = 'stopped' where id = %s",
                "update account_plays set state = 'lost' where id = %s",
                "update messages set status = 'rejected' where id = %s"):
        with pytest.raises(psycopg.errors.CheckViolation):
            with cur.connection.transaction():
                obj = scene["enrollment"] if "enrollments" in sql else scene["ap"] if "account_plays" in sql else scene["message"]
                db.run(cur, sql, obj)


def test_signals_need_evidence_and_matched_needs_an_account(cur, scene):
    with pytest.raises(psycopg.errors.CheckViolation):
        with cur.connection.transaction():
            db.run(cur, """insert into signals (type_key, source, external_id, observed_at, strength, evidence, status)
                           values ('t_sig', 't_src', 'noev', now(), 0.5, '{"summary": "x"}', 'unmatched')""")
    with pytest.raises(psycopg.errors.CheckViolation):
        with cur.connection.transaction():
            db.run(cur, """insert into signals (type_key, source, external_id, observed_at, strength, evidence, status)
                           values ('t_sig', 't_src', 'noacct', now(), 0.5, '{"summary": "x", "url": "https://x"}', 'matched')""")


def test_a_live_play_needs_a_launcher_who_did_not_write_it(cur, scene):
    with pytest.raises(psycopg.errors.CheckViolation):
        with cur.connection.transaction():
            db.run(cur, "update plays set status = 'live', created_by = %s, launched_by = %s, launched_at = now() where id = %s",
                   scene["user"], scene["user"], scene["play"])


# ---------------------------------------------------------------- regressions from the first code review

def give_mailbox(cur, scene) -> int:
    db.run(cur, "insert into sending_domains (domain, registered_at) values ('t-send.example', '2026-01-01') on conflict do nothing")
    mb = db.val(cur, """insert into mailboxes (address, domain, provider, display_name, user_id, warmup_started, ramp_start)
                        values (%s, 't-send.example', 'google', 'T', %s, '2026-01-01', '2026-01-15') returning id""",
                f"t{id(cur)}@t-send.example", scene["user"])
    db.run(cur, "update messages set mailbox_id = %s where id = %s", mb, scene["message"])
    return mb


def test_recording_a_send_already_under_way_is_not_refused(cur, scene):
    """A kill switch flipped while an email is in flight must not erase the record that it left."""
    db.run(cur, "insert into sending_domains (domain, registered_at) values ('t-send.example', '2026-01-01') on conflict do nothing")
    mb = db.val(cur, """insert into mailboxes (address, domain, provider, display_name, user_id, warmup_started, ramp_start)
                        values (%s, 't-send.example', 'google', 'T', %s, '2026-01-01', '2026-01-15') returning id""",
                f"t{id(cur)}@t-send.example", scene["user"])
    send(cur, scene["message"])
    db.run(cur, "update messages set mailbox_id = %s where id = %s", mb, scene["message"])
    db.run(cur, "update settings set value = 'true' where key = 'kill_switch'")
    with cur.connection.transaction():
        db.run(cur, "update messages set status = 'sent' where id = %s", scene["message"])
    assert db.val(cur, "select status from messages where id = %s", scene["message"]) == "sent"


def test_a_job_left_running_by_a_dead_worker_is_reclaimed(cur, scene):
    from outbound import jobs
    jid = db.val(cur, """insert into jobs (kind, status, attempts, locked_at, locked_by, dedupe_key)
                         values ('send_one', 'running', 1, now() - interval '1 hour', 'dead-worker', 'reap-test') returning id""")
    assert jobs.reap(cur) >= 1
    assert db.val(cur, "select status from jobs where id = %s", jid) == "queued"


def test_an_unknown_send_resolved_as_not_sent_on_a_stopped_person_is_cancelled(cur, scene):
    from outbound import sending
    send(cur, scene["message"])
    give_mailbox(cur, scene)
    db.run(cur, "update messages set status = 'send_unknown' where id = %s", scene["message"])
    db.run(cur, "update enrollments set state = 'stopped', stop_reason = 'replied_positive' where id = %s", scene["enrollment"])
    sending.resolve_unknown(cur, scene["message"], sent=False)
    assert db.val(cur, "select status from messages where id = %s", scene["message"]) == "cancelled"


def test_a_first_email_nobody_approves_lapses(cur, scene):
    from outbound import outreach
    db.run(cur, "update settings set value = '5' where key = 'approval_lapse_business_days'")
    db.run(cur, "insert into settings (key, value) values ('approval_lapse_business_days', '5') on conflict do nothing")
    db.run(cur, "update messages set status = 'cancelled' where id = %s", scene["message"])
    p = db.val(cur, "insert into people (account_id, full_name, source) values (%s, 'Late One', 't') returning id", scene["account"])
    e = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, next_at)
                       values (%s, %s, 'cfo', 'pending', app_now() - interval '20 days') returning id""", scene["ap"], p)
    db.run(cur, """insert into messages (enrollment_id, step_index, channel, subject, body, status, body_hash)
                   values (%s, 0, 'email', 's', 'b', 'awaiting_approval', '')""", e)
    db.run(cur, "insert into settings (key, value) values ('send_window', '[[\"08:30\",\"11:30\"]]') on conflict do nothing")
    outreach.due_steps(cur, {})
    assert db.val(cur, "select state from enrollments where id = %s", e) == "done"


def test_a_lost_expansion_deal_leaves_a_customer_a_customer(cur, scene):
    from outbound import pipeline
    db.run(cur, "update accounts set lifecycle = 'customer' where id = %s", scene["account"])
    db.run(cur, """insert into opportunities (account_id, crm_id, name, amount_cents, stage, created_at, closed_at, won)
                   values (%s, 'won-1', 'First deal', 100, 'Closed Won', now() - interval '300 days', now() - interval '200 days', true)""",
           scene["account"])
    db.run(cur, """insert into opportunities (account_id, crm_id, name, amount_cents, stage, created_at)
                   values (%s, 'exp-1', 'Expansion', 100, 'Evaluation', now() - interval '20 days')""", scene["account"])
    pipeline.opportunity_closed(cur, "exp-1", False, db.val(cur, "select app_now()"))
    assert db.val(cur, "select lifecycle from accounts where id = %s", scene["account"]) == "customer"


def test_influenced_counts_a_play_that_is_still_open(cur, scene):
    from outbound import pipeline
    db.run(cur, "update account_plays set proposed_at = app_now() - interval '110 days', state = 'meeting' where id = %s",
           scene["ap"])
    oid = pipeline.opportunity_created(cur, account_id=scene["account"], crm_id="infl-1", name="x", amount_cents=1,
                                       stage="Discovery", created_at=db.val(cur, "select app_now()"))
    assert db.val(cur, "select attribution from opportunities where id = %s", oid) == "influenced"


def test_a_failed_draft_cannot_be_approved_unchanged(cur, scene):
    from outbound import outreach
    db.run(cur, "update messages set status = 'cancelled' where id = %s", scene["message"])
    p = db.val(cur, "insert into people (account_id, full_name, source) values (%s, 'Failed Draft', 't') returning id",
               scene["account"])
    e = db.val(cur, "insert into enrollments (account_play_id, person_id, persona_key, state) values (%s,%s,'cfo','pending') "
                    "returning id", scene["ap"], p)
    m = db.val(cur, """insert into messages (enrollment_id, step_index, channel, subject, body, status, body_hash)
                       values (%s, 0, 'email', 's', 'b', 'failed_gate', '') returning id""", e)
    with pytest.raises(ValueError, match="Rewrite"):
        outreach.approve(cur, m, user_id=scene["user"])


def test_production_settings_refuse_unsafe_defaults(monkeypatch):
    from outbound.config import Config
    for k in ("WEBHOOK_SECRET", "CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD", "LIVE_SEND", "PUBLIC_DEMO"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MODE", "live")
    with pytest.raises(SystemExit, match="WEBHOOK_SECRET"):
        Config().validate()
    monkeypatch.setenv("MODE", "demo")
    monkeypatch.setenv("AUTH_MODE", "header")
    with pytest.raises(SystemExit, match="CF_ACCESS"):
        Config().validate()
