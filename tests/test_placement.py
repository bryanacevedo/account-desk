"""Inbox placement: seed tests hold or pause a mailbox, an old or missing test counts as unknown, and a mailbox that
goes quiet next to its peers raises an alert and asks for a seed test."""
from __future__ import annotations

import pytest

from outbound import db, outreach, sending
from outbound.db import J


@pytest.fixture
def box(cur):
    """A seasoned domain with a known, low spam rate and one mailbox ramped long ago, so only placement can hold it."""
    db.run(cur, "insert into settings (key, value) values ('mailbox_max_daily', '30') "
                "on conflict (key) do update set value = excluded.value")
    u = db.val(cur, "insert into users (name, email, role) values ('Pat Test', %s, 'sdr') returning id", f"p{id(cur)}@x.example")
    dom = f"send{id(cur)}.example"
    db.run(cur, """insert into sending_domains (domain, spf, dkim, dmarc, dmarc_policy, dmarc_aligned, registered_at,
                                                checked_at, spam_rate, spam_rate_at, postmaster_status)
                   values (%s, true, true, true, 'quarantine', true, app_now()::date - 200, app_now(), 0.0004, app_now(), 'compliant')""",
           dom)
    mb = db.val(cur, """insert into mailboxes (address, domain, provider, display_name, user_id, warmup_started, ramp_start)
                        values (%s, %s, 'google', 'Pat Test', %s, app_now()::date - 120, app_now()::date - 100) returning id""",
                f"pat@{dom}", dom, u)
    return {"id": mb, "user": u, "domain": dom}


def truth(cur, mailbox_id: int, gmail: float, outlook: float) -> None:
    db.run(cur, """insert into sim_mailboxes (mailbox_id, gmail, outlook) values (%s, %s, %s)
                   on conflict (mailbox_id) do update set gmail = excluded.gmail, outlook = excluded.outlook""",
           mailbox_id, gmail, outlook)


def mailbox(cur, mailbox_id: int) -> dict:
    return db.one(cur, "select * from mailboxes where id = %s", mailbox_id)


def alerts_for(cur, mailbox_id: int) -> list[str]:
    return [r["kind"] for r in db.all(cur, "select kind from alerts where object_kind = 'mailbox' and object_id = %s",
                                      mailbox_id)]


def test_spam_at_one_provider_pauses_the_mailbox(cur, box):
    truth(cur, box["id"], gmail=0.97, outlook=0.1)
    sending.placement_tests(cur, {"mailbox_id": box["id"]})
    m = mailbox(cur, box["id"])
    assert m["status"] == "paused" and "Outlook" in m["pause_reason"]
    assert "placement_pause" in alerts_for(cur, box["id"])
    assert db.val(cur, "select count(*) from placement_tests where mailbox_id = %s", box["id"]) == 2


def test_middling_placement_holds_capacity_without_pausing(cur, box):
    truth(cur, box["id"], gmail=0.97, outlook=0.65)
    sending.placement_tests(cur, {"mailbox_id": box["id"]})
    m = mailbox(cur, box["id"])
    assert m["status"] == "active"
    assert outreach.mailbox_capacity(cur, m) == 10
    assert "placement_hold" in alerts_for(cur, box["id"])


def test_unknown_placement_cannot_gain_capacity(cur, box):
    m = mailbox(cur, box["id"])
    assert outreach.mailbox_capacity(cur, m) == 10  # never tested
    truth(cur, box["id"], gmail=1.0, outlook=1.0)
    sending.placement_tests(cur, {"mailbox_id": box["id"]})
    assert outreach.mailbox_capacity(cur, m) == 30
    db.run(cur, "update placement_tests set at = app_now() - interval '11 days' where mailbox_id = %s", box["id"])
    assert outreach.mailbox_capacity(cur, m) == 10  # too old to go on


def test_a_mailbox_gone_quiet_next_to_its_peers_raises_an_alert(cur, box):
    peer = db.val(cur, """insert into mailboxes (address, domain, provider, display_name, user_id, warmup_started, ramp_start)
                          values (%s, %s, 'google', 'Pat Test', %s, app_now()::date - 120, app_now()::date - 100) returning id""",
                  f"pat.test@{box['domain']}", box["domain"], box["user"])
    db.run(cur, "insert into signal_types (key, label, because, level, weight, half_life_days) values "
                "('t_sig', 'Test', 'Because of a test signal', 'account', 10, 10) on conflict do nothing")
    db.run(cur, "insert into signal_sources (key, label, adapter, cadence_minutes) values ('t_src', 'T', 'sim', 60) "
                "on conflict do nothing")
    db.run(cur, "insert into personas (key, label, title_patterns, committee_role, angle) values ('cfo', 'F', '{cfo}', "
                "'economic_buyer', 'a') on conflict do nothing")
    play = db.val(cur, """insert into plays (key, name, hypothesis, trigger, personas, sequence, angle) values
                          (%s, 'P', 'h', '{}', '{cfo}', '[]', 'a') returning id""", f"pl{id(cur)}")
    # 70 sends from each mailbox for the same play: the peer gets 14 replies, ours gets 1 (its peers predict 14).
    for mb, replied in ((peer, 14), (box["id"], 1)):
        for i in range(70):
            a = db.val(cur, "insert into accounts (name, primary_domain, fit_tier) values (%s, %s, 'A') returning id",
                       f"Co {mb}-{i}", f"co{mb}x{i}x{id(cur)}.example")
            p = db.val(cur, """insert into people (account_id, full_name, first_name, email, email_status, email_verified_at, source)
                               values (%s, 'Ana Test', 'Ana', %s, 'valid', app_now(), 'test') returning id""", a, f"ana{mb}x{i}@co.example")
            s = db.val(cur, """insert into signals (type_key, source, external_id, account_id, observed_at, strength, evidence, status)
                               values ('t_sig', 't_src', %s, %s, app_now(), 0.5, %s, 'matched') returning id""",
                       f"s{mb}x{i}x{id(cur)}", a, J({"summary": "x", "url": "https://x"}))
            ap = db.val(cur, """insert into account_plays (account_id, play_id, trigger_signal_id, arm, state, why_now, owner_id)
                                values (%s, %s, %s, 'treated', 'active', '{}', %s) returning id""", a, play, s, box["user"])
            e = db.val(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, mailbox_id)
                               values (%s, %s, 'cfo', 'active', %s) returning id""", ap, p, mb)
            m = db.val(cur, """insert into messages (enrollment_id, step_index, channel, subject, body, status, body_hash,
                                                     approved_hash, approved_at, approval_mode, sent_at, mailbox_id)
                               values (%s, 0, 'email', 'hi', 'Ana, hello.', 'sent', 'h', 'h', app_now(), 'person',
                                       app_now() - interval '5 days', %s) returning id""", e, mb)
            if i < replied:
                db.run(cur, """insert into replies (message_id, person_id, account_id, received_at, from_addr, raw, cleaned, label)
                               values (%s, %s, %s, app_now(), 'ana@co.example', 'ok', 'ok', 'question')""", m, p, a)
    flagged = sending.reply_rate_drops(cur)
    assert [d["id"] for d in flagged] == [box["id"]]
    sending.mailbox_health(cur, {})
    assert "reply_drop" in alerts_for(cur, box["id"])
    assert db.val(cur, "select count(*) from jobs where kind = 'placement_tests' and payload->>'mailbox_id' = %s",
                  str(box["id"])) == 1
