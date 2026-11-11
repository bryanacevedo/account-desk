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
