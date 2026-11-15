"""Events Desk step 6 part 3, Account Desk half (decision 94): a note before the event. A targeted member starts
`event_pre_event`; a declined person stops the event plays; a moved status stops the pre-event note; the booking link comes only
from Events Desk and only the day-7 email may carry it; Events Desk can read how the plays are going, as counts."""
from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from test_crm_world import Fake, Stub, _event_account, crm, desk, events, member  # noqa: F401
from test_guarantees import scene  # noqa: F401

from outbound import clock, copy_gate, db, event_link, outreach, pipeline, plays, scoring, sim_llm
from outbound.adapters import CrmCampaignMember
from outbound.db import J

LINK = "https://events.example/book/reinvent"
EVENT = {"event": "AWS re:Invent 2026", "starts_on": "2026-11-30", "ends_on": "2026-12-04", "city": "Las Vegas", "booking_url": LINK}


def at(status, email="lee@evt.example", crm_id="con_1", campaign="cmp_1", days=1):
    return CrmCampaignMember(campaign_ref=campaign, campaign_name="AWS re:Invent 2026", campaign_type="event",
                             event_name="AWS re:Invent 2026", status=status, contact_email=email, contact_crm_id=crm_id,
                             account_domain=None, updated_at=clock.now() - timedelta(days=days), change_id=f"{crm_id}_{status}_{days}")


def sync(cur, crm, rows):  # noqa: F811
    c = crm(Fake())
    c.members = rows
    pipeline.crm_sync(cur, {})
    pipeline.crm_members(cur, {})                         # its own job since decision 95
    return c


def live(cur):
    plays.ensure_event_play(cur)
    db.run(cur, "update plays set holdout_pct = 0 where key like 'event_%%'")


def proposed(cur, aid):
    scoring.rescore(cur, aid)
    apid = plays.match(cur, aid)
    return apid, db.val(cur, "select p.key from account_plays ap join plays p on p.id = ap.play_id where ap.id = %s", apid) if apid else None


def enroll(cur, apid, pid):
    return db.val(cur, "insert into enrollments (account_play_id, person_id, persona_key, state) values (%s,%s,'cfo','active') returning id",
                  apid, pid)


@pytest.fixture
def link_off(monkeypatch):
    for k in ("EVENTS_DESK_URL", "EVENTS_DESK_READ_KEY"):
        monkeypatch.delenv(k, raising=False)


def _clear_cache():
    with db.tx() as c:
        db.run(c, "delete from settings where key like 'events_desk_campaign:%%'")


def _age_cache():
    with db.tx() as c:
        db.run(c, "update settings set value = jsonb_set(value, '{day}', '\"2000-01-01\"') where key like 'events_desk_campaign:%%'")


@pytest.fixture
def link_on(monkeypatch, database):
    _clear_cache()
    monkeypatch.setenv("EVENTS_DESK_URL", "https://events.example/")
    monkeypatch.setenv("EVENTS_DESK_READ_KEY", "k-read")
    calls = []

    def get(url, timeout=None, headers=None):
        calls.append((url, headers))
        return httpx.Response(200, json=get.answer, request=httpx.Request("GET", url)) if get.status == 200 else httpx.Response(get.status, json={})
    get.answer, get.status = dict(EVENT), 200
    monkeypatch.setattr(event_link.httpx, "get", get)
    get.calls = calls
    yield get
    _clear_cache()


# ---------------------------------------------------------------- the signal and the play

def test_targeted_becomes_a_signal_and_a_pre_event_proposal_for_an_a_account_not_a_c(cur, desk, crm, events, link_off):  # noqa: F811
    aid, pid = _event_account(cur, desk)
    cid, _ = _event_account(cur, desk, domain="c.example", email="cee@c.example")
    db.run(cur, "update accounts set fit_tier = 'C', crm_tier = 'C', crm_fit_score = 10 where id = %s", cid)
    db.run(cur, "update people set crm_id = 'con_2' where account_id = %s", cid)
    sync(cur, crm, [at("targeted"), at("targeted", email="cee@c.example", crm_id="con_2")])
    live(cur)
    sig = db.one(cur, "select * from signals where account_id = %s", aid)
    assert sig["type_key"] == "event_targeted" and sig["campaign_ref"] == "cmp_1" and float(sig["strength"]) == 0.4
    assert sig["external_id"] == "member:cmp_1:con_1:targeted" and sig["person_id"] == pid
    p = db.one(cur, "select * from plays where key = 'event_pre_event'")
    assert p["status"] == "live" and p["trigger"]["any_of"] == ["event_targeted"] and p["autonomy"] == "draft" and not p["urgent"]
    assert [st["job"] for st in p["sequence"]] == ["open", "connect", "follow_up"] and [st["day"] for st in p["sequence"]] == [0, 3, 7]
    assert proposed(cur, aid)[1] == "event_pre_event"
    assert proposed(cur, cid)[0] is None                                   # a C account is not proposed (the play's fit tiers)


def test_a_member_signal_names_its_campaign_and_other_signals_do_not(cur, desk, crm, events, link_off):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    sync(cur, crm, [at("registered")])
    assert db.val(cur, "select campaign_ref from signals where account_id = %s", aid) == "cmp_1"
    assert db.val(cur, "select campaign_ref from signals where id = %s", desk["signal"]) is None


def test_waitlist_is_counted_and_makes_no_signal(cur, desk, crm, events, link_off):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    sync(cur, crm, [at("waitlist"), at("waitlist", email="x@evt.example", crm_id="con_7")])
    assert db.val(cur, "select count(*) from signals where account_id = %s", aid) == 0
    assert db.val(cur, "select value ->> 'waitlist' from settings where key = 'crm_member_counts'") == "2"


# ---------------------------------------------------------------- declined and moved

def _two_plays(cur, desk, crm):  # noqa: F811
    """A person in an open pre-event enrolment and, on a second account, one in an open follow-up enrolment."""
    aid, pid = _event_account(cur, desk)
    sync(cur, crm, [at("targeted", days=3)])
    live(cur)
    apid, key = proposed(cur, aid)
    assert key == "event_pre_event"
    plays.set_state(cur, apid, "accepted")
    plays.set_state(cur, apid, "researching")
    plays.set_state(cur, apid, "active")
    return aid, pid, apid, enroll(cur, apid, pid)


def test_declined_stops_the_persons_event_enrolments_and_closes_the_play(cur, desk, crm, events, link_off):  # noqa: F811
    aid, pid, apid, eid = _two_plays(cur, desk, crm)
    sync(cur, crm, [at("declined", days=1)])
    e = db.one(cur, "select state, stop_reason from enrollments where id = %s", eid)
    assert e == {"state": "stopped", "stop_reason": "declined_event"}
    ap = db.one(cur, "select state, close_reason from account_plays where id = %s", apid)
    assert ap == {"state": "stopped", "close_reason": "declined_event"}
    assert db.val(cur, "select count(*) from audit_log where action = 'event_plays_stopped' and object_id = %s", pid) == 1
    assert db.val(cur, "select count(*) from holds where account_id = %s", aid) == 0     # no cooldown: the account is free
    assert db.val(cur, "select count(*) from signals where account_id = %s and type_key <> 'event_targeted'", aid) == 0


def test_declined_stops_the_follow_up_enrolment_too_and_leaves_other_people_alone(cur, desk, crm, events, link_off):  # noqa: F811
    aid, pid = _event_account(cur, desk)
    other = db.val(cur, "insert into people (account_id, full_name, first_name, email, source, crm_id) values (%s,'Kim','Kim','kim@evt.example','import','con_5') returning id", aid)
    sync(cur, crm, [at("attended", days=3)])
    live(cur)
    apid, key = proposed(cur, aid)
    assert key == "event_follow_up"
    plays.set_state(cur, apid, "accepted")
    plays.set_state(cur, apid, "researching")
    plays.set_state(cur, apid, "active")
    mine, theirs = enroll(cur, apid, pid), enroll(cur, apid, other)
    sync(cur, crm, [at("declined", days=1)])
    assert db.val(cur, "select stop_reason from enrollments where id = %s", mine) == "declined_event"
    assert db.val(cur, "select state from enrollments where id = %s", theirs) == "active"
    assert db.val(cur, "select state from account_plays where id = %s", apid) == "active"     # someone else is still in it


def test_a_declined_person_gets_no_signal_from_older_rows_in_the_feed(cur, desk, crm, events, link_off):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    sync(cur, crm, [at("targeted", days=5), at("registered", days=4), at("declined", days=2)])
    assert db.val(cur, "select count(*) from signals where account_id = %s", aid) == 0
    sync(cur, crm, [at("targeted", days=3, crm_id="con_1")])                    # an older row arriving later, in another read
    assert db.val(cur, "select count(*) from signals where account_id = %s", aid) == 0
    sync(cur, crm, [at("registered", days=0)])                                  # they come back: a new signal, nothing started
    assert db.val(cur, "select type_key from signals where account_id = %s", aid) == "event_registered"
    assert db.val(cur, "select count(*) from account_plays where account_id = %s", aid) == 0


@pytest.mark.parametrize("moved", ["registered", "attended", "met", "no_show"])
def test_a_moved_status_stops_pre_event_only_and_the_follow_up_can_be_proposed(cur, desk, crm, events, link_off, moved):  # noqa: F811
    aid, pid, apid, eid = _two_plays(cur, desk, crm)
    sync(cur, crm, [at(moved, days=1)])
    assert db.one(cur, "select state, stop_reason from enrollments where id = %s", eid) == {"state": "stopped", "stop_reason": "event_status_moved"}
    assert db.one(cur, "select state, close_reason from account_plays where id = %s", apid) == {"state": "stopped", "close_reason": "event_status_moved"}
    assert proposed(cur, aid)[1] == "event_follow_up"


def test_a_pre_event_play_in_flight_blocks_the_follow_up_until_it_closes(cur, desk, crm, events, link_off):  # noqa: F811
    aid, pid, apid, eid = _two_plays(cur, desk, crm)
    db.run(cur, "insert into signals (type_key, source, external_id, account_id, person_id, observed_at, strength, evidence, status, campaign_ref) "
                "values ('event_registered', 'crm', 'member:cmp_1:con_1:registered', %s, %s, app_now(), 0.5, %s, 'matched', 'cmp_1')",
           aid, pid, J({"summary": "x", "quote": "y"}))
    scoring.rescore(cur, aid)
    assert plays.match(cur, aid) is None                                        # one open play per account
    assert db.val(cur, "select state from account_plays where id = %s", apid) == "active"


def test_a_status_moved_when_nobody_else_is_open_does_not_touch_an_engaged_play(cur, desk, crm, events, link_off):  # noqa: F811
    aid, pid, apid, eid = _two_plays(cur, desk, crm)
    plays.set_state(cur, apid, "engaged")
    sync(cur, crm, [at("registered", days=1)])
    assert db.val(cur, "select state from account_plays where id = %s", apid) == "engaged"


# ---------------------------------------------------------------- alone, and an old install

def test_alone_a_targeted_member_changes_nothing(cur, desk, crm, monkeypatch):  # noqa: F811
    monkeypatch.delenv("INTEGRATED_WITH", raising=False)
    aid, _ = _event_account(cur, desk)
    sync(cur, crm, [at("targeted"), at("declined", crm_id="con_2", email="z@evt.example")])
    assert db.val(cur, "select count(*) from signals where account_id = %s", aid) == 0
    assert db.val(cur, "select count(*) from plays where key like 'event_%%'") == 0
    assert db.val(cur, "select count(*) from signal_types where key = 'event_targeted'") == 0
    assert db.val(cur, "select count(*) from settings where key = 'crm_member_counts'") == 0


def test_an_install_that_has_follow_up_gets_the_pre_event_play_added(cur, desk):  # noqa: F811
    plays.ensure_event_play(cur)
    db.run(cur, "delete from plays where key = 'event_pre_event'")
    follow = db.val(cur, "select id from plays where key = 'event_follow_up'")
    assert plays.ensure_event_play(cur) == follow
    row = db.one(cur, "select status, created_by, launched_by from plays where key = 'event_pre_event'")
    assert row["status"] == "live" and row["created_by"] != row["launched_by"]
    assert db.val(cur, "select count(*) from plays where key = 'event_follow_up'") == 1
    plays.ensure_event_play(cur)
    assert db.val(cur, "select count(*) from plays where key = 'event_pre_event'") == 1


# ---------------------------------------------------------------- the booking link

def _evidence(cur, aid):
    return db.val(cur, "select evidence from signals where account_id = %s and type_key = 'event_targeted'", aid)


def test_the_booking_link_present_is_stored_in_the_signal_and_asked_once_a_day(cur, desk, crm, events, link_on):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    sync(cur, crm, [at("targeted"), at("targeted", crm_id="con_2", email="b@evt.example")])
    ev = _evidence(cur, aid)
    assert ev["event"] == {"name": "AWS re:Invent 2026", "starts_on": "2026-11-30", "ends_on": "2026-12-04", "city": "Las Vegas", "booking_url": LINK}
    assert "AWS re:Invent 2026 in Las Vegas, 30 November to 4 December 2026" in ev["summary"]
    url, headers = link_on.calls[0]
    assert url == "https://events.example/api/desk/campaigns/cmp_1" and headers == {"authorization": "Bearer k-read"}
    sync(cur, crm, [at("targeted", crm_id="con_3", email="c@evt.example")])
    assert len(link_on.calls) == 1                                              # once per campaign per day
    _age_cache()
    sync(cur, crm, [at("targeted", crm_id="con_4", email="d@evt.example")])
    assert len(link_on.calls) == 2


@pytest.mark.parametrize("how", ["no_settings", "unreachable", "refused", "no_link", "bad_link"])
def test_no_link_is_written_when_it_is_absent_unreachable_or_refused(cur, desk, crm, events, link_on, monkeypatch, how):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    if how == "no_settings":
        monkeypatch.delenv("EVENTS_DESK_URL")
    elif how == "unreachable":
        def boom(*a, **k):
            raise httpx.ConnectError("down")
        monkeypatch.setattr(event_link.httpx, "get", boom)
    elif how == "refused":
        link_on.status = 401
    elif how == "no_link":
        link_on.answer = {**EVENT, "booking_url": None}
    else:
        link_on.answer = {**EVENT, "booking_url": "javascript:alert(1)"}
    sync(cur, crm, [at("targeted")])
    ev = _evidence(cur, aid)
    assert "events.example/book" not in str(ev) and not (ev.get("event") or {}).get("booking_url")
    assert db.val(cur, "select count(*) from signals where account_id = %s", aid) == 1     # the signal itself still lands
    if how in ("no_settings", "unreachable", "refused"):
        assert "event" not in ev and "Someone at the company is a person we want to meet at AWS re:Invent 2026." == ev["summary"]


def test_a_link_added_later_reaches_the_waiting_signal(cur, desk, crm, events, link_on):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    link_on.answer = {**EVENT, "booking_url": None}
    sync(cur, crm, [at("targeted")])
    assert _evidence(cur, aid)["event"]["booking_url"] is None
    _age_cache()
    link_on.answer = dict(EVENT)
    sync(cur, crm, [at("targeted", crm_id="con_3", email="c@evt.example")])
    assert _evidence(cur, aid)["event"]["booking_url"] == LINK


# ---------------------------------------------------------------- the drafts

def _drafting(cur, desk, link):  # noqa: F811
    """The scene's enrollment becomes a pre-event one, triggered by a targeted signal that carries (or lacks) a link."""
    plays.ensure_event_play(cur)
    pre = db.val(cur, "select id from plays where key = 'event_pre_event'")
    ev = {"summary": "Someone at the company is a person we want to meet at AWS re:Invent 2026 in Las Vegas, 30 November to 4 December 2026.",
          "quote": "x", "event": {"name": "AWS re:Invent 2026", "city": "Las Vegas", "starts_on": "2026-11-30", "ends_on": "2026-12-04", "booking_url": link}}
    sid = db.val(cur, """insert into signals (type_key, source, external_id, account_id, person_id, observed_at, strength, evidence, status, campaign_ref)
                         values ('event_targeted', 'crm', 'member:cmp_1:con_1:targeted', %s, %s, app_now(), 0.4, %s, 'matched', 'cmp_1') returning id""",
                 desk["account"], desk["person"], J(ev))
    db.run(cur, "insert into facts (account_id, person_id, kind, text, source, observed_at) values (%s,%s,'signal:event_targeted',%s,'crm',app_now())",
           desk["account"], desk["person"], ev["summary"])
    db.run(cur, "update account_plays set play_id = %s, trigger_signal_id = %s where id = %s", pre, sid, desk["ap"])
    db.run(cur, "update enrollments set state = 'active' where id = %s", desk["enrollment"])
    db.run(cur, "delete from messages where enrollment_id = %s", desk["enrollment"])
    db.run(cur, "update account_plays set brief = '{\"findings\": []}' where id = %s", desk["ap"])
    return pre


def _draft(cur, desk, step):  # noqa: F811
    m = outreach.draft_step(cur, desk["enrollment"], step)
    return m


def test_the_day_zero_email_says_a_reply_will_find_a_time_and_carries_no_link(cur, desk, link_off):  # noqa: F811
    _drafting(cur, desk, LINK)
    m = _draft(cur, desk, 0)
    assert m["status"] == "awaiting_approval", m["gate"]
    assert "I'll be at AWS re:Invent 2026 in Las Vegas, 30 November to 4 December 2026." in m["body"]
    assert "reply" in m["body"] and LINK not in m["body"] and "book" not in m["body"].split("\n\n--\n")[0].lower()


def test_the_day_seven_email_carries_the_link_events_desk_gave(cur, desk, link_off):  # noqa: F811
    _drafting(cur, desk, LINK)
    m = _draft(cur, desk, 2)
    assert m["status"] == "awaiting_approval", m["gate"]
    assert m["body"].count(LINK) == 1


def test_the_day_seven_email_without_a_link_writes_none(cur, desk, link_off):  # noqa: F811
    _drafting(cur, desk, None)
    m = _draft(cur, desk, 2)
    assert m["status"] == "awaiting_approval", m["gate"]
    assert "http" not in m["body"].split("\n\n--\n")[0] and "reply" in m["body"]


def test_the_draft_inputs_carry_the_link_only_for_the_follow_up(cur, desk, link_off):  # noqa: F811
    pre = _drafting(cur, desk, LINK)
    ap = db.one(cur, "select * from account_plays where id = %s", desk["ap"])
    play = db.one(cur, "select * from plays where id = %s", pre)
    got = {i: outreach.event_context(cur, ap, play, st) for i, st in enumerate(play["sequence"])}
    assert got[0]["booking_url"] is None and got[1]["booking_url"] is None and got[2]["booking_url"] == LINK
    assert got[2]["name"] == "AWS re:Invent 2026" and got[2]["city"] == "Las Vegas"
    other = db.one(cur, "select * from plays where key = 'event_follow_up'")
    assert outreach.event_context(cur, ap, other, play["sequence"][2]) is None


def test_the_copy_check_refuses_a_link_in_the_open_email_and_an_invented_one_in_the_follow_up():
    person = {"first_name": "Lee", "full_name": "Lee Evt", "last_name": "Evt"}
    account = {"name": "Evt"}
    facts = {1: "Someone at the company is a person we want to meet at AWS re:Invent 2026 in Las Vegas, 30 November to 4 December 2026."}

    def check(job, url, allowed):
        d = {"subject": "re invent", "sentences": [
            {"text": "Hi Lee,", "kind": "courtesy", "fact_ids": []},
            {"text": "I'll be at AWS re:Invent 2026 in Las Vegas, 30 November to 4 December 2026.", "kind": "claim", "fact_ids": [1]},
            {"text": "I'm Priya at Lumen Ledger and we do usage billing for finance teams, so a short word there may help.", "kind": "courtesy", "fact_ids": []},
            {"text": f"You can book a time at {url}", "kind": "courtesy", "fact_ids": []}]}
        return copy_gate.check(d, job=job, person=person, account=account, facts=facts, our_names=["Priya", "Lumen", "Ledger"],
                               other_bodies=[], allowed_links=allowed)
    assert any(f["code"] == "link" and "First emails" in f["message"] for f in check("open", LINK, {LINK}).failures)
    assert check("follow_up", LINK, {LINK}).passed
    assert any(f["code"] == "link" for f in check("follow_up", "https://invented.example/x", {LINK}).failures)
    assert any(f["code"] == "link" for f in check("follow_up", LINK, set()).failures)


def test_the_stand_in_draft_names_the_event_from_its_input_only():
    p = {"person": {"id": 1, "first_name": "Lee"}, "company": "Evt", "step": {"index": 2, "job": "follow_up"}, "sender": "Priya Natarajan",
         "our_company": "Lumen Ledger", "attempt": 2, "facts": [{"id": 9, "kind": "signal:event_targeted",
         "text": "Someone at the company is a person we want to meet at AWS re:Invent 2026 in Las Vegas, 30 November to 4 December 2026."}],
         "event": {"name": "AWS re:Invent 2026", "city": "Las Vegas", "starts_on": "2026-11-30", "ends_on": "2026-12-04", "booking_url": None}}
    text = " ".join(s["text"] for s in sim_llm.draft(p)["sentences"])
    assert "AWS re:Invent 2026" in text and "http" not in text and "—" not in text


# ---------------------------------------------------------------- the read Events Desk makes

@pytest.fixture
def seeded(database):
    """Committed rows for one campaign: a play with accounts, two people stopped (one declined), one waiting."""
    with db.tx() as cur:
        db.run(cur, "insert into signal_types (key, label, because, level, weight, half_life_days) values "
                    "('evx_sig', 'Read test', 'Because of a read test signal', 'person', 10, 21) on conflict do nothing")
        db.run(cur, "insert into signal_sources (key, label, adapter, cadence_minutes) values ('crm','CRM','sim',360) on conflict do nothing")
        pl = db.val(cur, """insert into plays (key, name, hypothesis, trigger, personas, sequence, angle)
                            values ('evx_pre', 'Before the event', 'h', '{}', '{cfo}', '[]', 'a') returning id""")
        db.run(cur, "insert into personas (key, label, title_patterns, committee_role, angle) values ('cfo','F','{cfo}','economic_buyer','a') on conflict do nothing")
        made = {"plays": [pl], "accounts": [], "people": [], "signals": []}
        for i, why in enumerate(["declined_event", "event_status_moved", None]):
            a = db.val(cur, "insert into accounts (name, primary_domain, fit_tier) values (%s, %s, 'A') returning id", f"Secret Co {i}", f"secret{i}.example")
            p = db.val(cur, "insert into people (account_id, full_name, first_name, email, source) values (%s, %s, 'Zed', %s, 'test') returning id",
                       a, f"Zed Personname{i}", f"zed{i}@secret{i}.example")
            s = db.val(cur, """insert into signals (type_key, source, external_id, account_id, person_id, observed_at, strength, evidence, status, campaign_ref)
                               values ('evx_sig','crm',%s,%s,%s,app_now(),0.4,%s,'matched','cmp_read') returning id""",
                       f"member:cmp_read:{i}:targeted", a, p, J({"summary": "x", "quote": "y"}))
            ap = db.val(cur, """insert into account_plays (account_id, play_id, trigger_signal_id, arm, state, why_now, close_reason, closed_at)
                                values (%s,%s,%s,'treated',%s,'{}',%s,%s) returning id""",
                        a, pl, s, "stopped" if why else "active", why, clock.now() if why else None)
            db.run(cur, """insert into enrollments (account_play_id, person_id, persona_key, state, stop_reason, pause_reason)
                           values (%s,%s,'cfo',%s,%s,%s)""", ap, p, "stopped" if why else "paused", why, None if why else "reply_received")
            made["accounts"].append(a)
            made["people"].append(p)
            made["signals"].append(s)
        # the same play from another campaign, and from a signal with no campaign: neither is counted
        s2 = db.val(cur, """insert into signals (type_key, source, external_id, account_id, observed_at, strength, evidence, status)
                            values ('evx_sig','crm','member:old:1:targeted',%s,app_now(),0.4,%s,'matched') returning id""",
                    made["accounts"][0], J({"summary": "x", "quote": "y"}))
        made["signals"].append(s2)
    yield made
    with db.tx() as cur:
        db.run(cur, "delete from enrollments where account_play_id in (select id from account_plays where play_id = any(%s))", made["plays"])
        db.run(cur, "delete from account_plays where play_id = any(%s)", made["plays"])
        db.run(cur, "delete from signals where id = any(%s)", made["signals"])
        db.run(cur, "delete from plays where id = any(%s)", made["plays"])
        db.run(cur, "delete from people where id = any(%s)", made["people"])
        db.run(cur, "delete from accounts where id = any(%s)", made["accounts"])
        db.run(cur, "delete from signal_types where key = 'evx_sig'")


@pytest.fixture(scope="module")
def client(database):
    from fastapi.testclient import TestClient

    from outbound.api.app import app
    return TestClient(app)


def test_the_campaign_read_is_404_without_a_key_401_with_a_wrong_one_and_200_with_the_right_one(client, seeded, monkeypatch):
    path = "/api/desk/campaigns/cmp_read/plays"
    monkeypatch.delenv("DESK_READ_KEY", raising=False)
    assert client.get(path, headers={"Authorization": "Bearer anything"}).status_code == 404
    monkeypatch.setenv("DESK_READ_KEY", "right-key")
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get(path, headers={"Authorization": "right-key"}).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer right-key"}).status_code == 200


def test_the_campaign_read_gives_counts_only(client, seeded, monkeypatch):
    monkeypatch.setenv("DESK_READ_KEY", "right-key")
    r = client.get("/api/desk/campaigns/cmp_read/plays", headers={"Authorization": "Bearer right-key"})
    j = r.json()
    assert j["campaign_ref"] == "cmp_read" and set(j) == {"campaign_ref", "plays", "as_of"}
    (play,) = j["plays"]
    assert play["key"] == "evx_pre" and play["states"] == {"stopped": 2, "active": 1}
    assert play["people"] == {"stopped_declined_event": 1, "stopped_event_status_moved": 1, "replied": 1}
    for needle in ("Secret Co", "Personname", "@secret", "Zed", ".example"):
        assert needle not in r.text
    empty = client.get("/api/desk/campaigns/none/plays", headers={"Authorization": "Bearer right-key"}).json()
    assert empty["plays"] == []


# ---------------------------------------------------------------- review fixes

def test_a_decline_before_the_proposal_leaves_nothing_to_propose(cur, desk, crm, events, link_off):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    sync(cur, crm, [at("targeted", days=3), at("registered", days=2, crm_id="con_1")])
    sync(cur, crm, [at("declined", days=0)])
    live(cur)
    assert proposed(cur, aid)[0] is None


def test_a_moved_status_before_the_proposal_sets_the_targeted_signal_aside(cur, desk, crm, events, link_off):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    sync(cur, crm, [at("targeted", days=3)])
    sync(cur, crm, [at("attended", days=1)])
    live(cur)
    assert [(r["type_key"], r["status"]) for r in db.all(cur, "select type_key, status from signals where account_id = %s order by id", aid)] == [
        ("event_targeted", "ignored"), ("event_campaign_member", "matched")]
    assert proposed(cur, aid)[1] == "event_follow_up"


def test_a_failed_read_still_names_the_event_from_the_campaign(cur, desk, link_off):  # noqa: F811
    _drafting(cur, desk, None)
    db.run(cur, "update signals set evidence = %s where id = (select trigger_signal_id from account_plays where id = %s)",
           J({"summary": "Someone at the company is a person we want to meet at AWS re:Invent 2026.", "quote": "x", "campaign_name": "AWS re:Invent 2026"}), desk["ap"])
    db.run(cur, "update facts set text = 'Someone at the company is a person we want to meet at AWS re:Invent 2026.' where kind = 'signal:event_targeted'")
    m = _draft(cur, desk, 0)
    assert m["status"] == "awaiting_approval", m["gate"]
    assert "None" not in m["body"] and "I'll be at AWS re:Invent 2026." in m["body"]
    ap = db.one(cur, "select * from account_plays where id = %s", desk["ap"])
    play = db.one(cur, "select * from plays where key = 'event_pre_event'")
    db.run(cur, "update signals set evidence = '{\"summary\": \"x\", \"quote\": \"y\"}' where id = %s", ap["trigger_signal_id"])
    assert outreach.event_context(cur, ap, play, play["sequence"][0]) is None          # no name anywhere: no event input


def test_a_link_added_later_reaches_a_signal_whose_first_read_failed(cur, desk, crm, events, link_on):  # noqa: F811
    aid, _ = _event_account(cur, desk)
    link_on.status = 503
    sync(cur, crm, [at("targeted")])
    assert "event" not in _evidence(cur, aid)
    _age_cache()
    link_on.status, link_on.answer = 200, dict(EVENT)
    sync(cur, crm, [at("targeted", crm_id="con_3", email="c@evt.example")])
    ev = _evidence(cur, aid)
    assert ev["event"]["booking_url"] == LINK and "Las Vegas" in ev["summary"]
    assert db.val(cur, "select text from facts where account_id = %s and kind = 'signal:event_targeted'", aid) == ev["summary"]


# ---------------------------------------------------------------- the Events Desk call is not in the CRM sync (decision 95)

def test_crm_sync_does_not_call_events_desk_and_its_own_job_does(cur, desk, crm, events, link_on):  # noqa: F811
    _event_account(cur, desk)
    c = crm(Fake())
    c.members = [at("targeted")]
    pipeline.crm_sync(cur, {})
    assert link_on.calls == []                                             # the sync's transaction made no network call
    assert db.val(cur, "select count(*) from jobs where kind = 'crm_members' and status = 'queued'") == 1
    pipeline.crm_sync(cur, {})
    assert db.val(cur, "select count(*) from jobs where kind = 'crm_members' and status = 'queued'") == 1   # one at a time
    pipeline.crm_members(cur, {})
    assert len(link_on.calls) == 1 and link_on.calls[0][0].endswith("/api/desk/campaigns/cmp_1")
    assert db.val(cur, "select count(*) from signals where type_key = 'event_targeted'") == 1
