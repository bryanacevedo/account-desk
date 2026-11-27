# ruff: noqa: F811
"""BL-111: Account Desk carries the play, the signal and the SDR's own note to the deal in the CRM, so the account executive has
them at the handoff. It writes what it knows and never makes up the rest; the CRM refuses a handoff that still lacks one."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
from test_guarantees import scene  # noqa: F401  (fixture)

from outbound import db, pipeline
from outbound.adapters import crmdesk
from outbound.adapters.recorded import RecordedCrm


def _outbox(cur, crm_id):
    return db.all(cur, "select kind, payload, idempotency_key from crm_outbox where kind = 'deal_context' and payload->>'crm_id' = %s order by id", crm_id)


def _touch(cur, scene, days_ago=20):
    db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source, dedup_key)
                   values (%s, %s, %s, 'email', 'out', 'email_sent', app_now() - (%s || ' days')::interval, 'desk', %s)""",
           scene["account"], scene["person"], scene["ap"], days_ago, f"hc-{days_ago}-{scene['ap']}")


def _meeting(cur, scene, source="sdr", note="Warm. Her CFO asked for a demo before budget closes.", days_ago=10):
    return db.val(cur, """insert into meetings (account_play_id, account_id, person_id, booked_at, starts_at, status, source, sdr_note, sdr_note_by)
                          values (%s, %s, %s, app_now() - (%s || ' days')::interval, app_now(), 'booked', %s, %s, %s) returning id""",
                  scene["ap"], scene["account"], scene["person"], days_ago, source, note, scene["user"] if note else None)


def _deal(cur, scene, crm_id):
    return pipeline.opportunity_created(cur, account_id=scene["account"], crm_id=crm_id, name="x", amount_cents=1, stage="Discovery",
                                        created_at=db.val(cur, "select app_now()"))


def test_a_sourced_deal_queues_the_play_the_signal_and_the_sdrs_note(cur, scene):
    _touch(cur, scene)
    _meeting(cur, scene)
    _deal(cur, scene, "opp_1")
    rows = _outbox(cur, "opp_1")
    assert len(rows) == 1
    p = rows[0]["payload"]
    assert p["handoff_play"] == "P: h"
    assert p["handoff_signal"].startswith("Test, seen ") and p["handoff_signal"].endswith(": x")
    assert p["handoff_note"] == "Warm. Her CFO asked for a demo before budget closes."


def test_what_the_desk_does_not_know_is_left_out_never_invented(cur, scene):
    _touch(cur, scene)
    _meeting(cur, scene, source="inbound", note=None)          # a website demo request: no SDR wrote anything
    _deal(cur, scene, "opp_2")
    p = _outbox(cur, "opp_2")[0]["payload"]
    assert "handoff_note" not in p and p["handoff_play"] and p["handoff_signal"]


def test_a_deal_outbound_never_touched_carries_nothing(cur, scene):
    _deal(cur, scene, "opp_3")                                 # attribution none: no play reached the account
    assert _outbox(cur, "opp_3") == []


def test_the_same_words_are_queued_once_and_a_new_note_is_queued_again(cur, scene):
    _touch(cur, scene)
    mid = _meeting(cur, scene)
    oid = _deal(cur, scene, "opp_4")
    pipeline.attribute(cur, oid)
    pipeline.attribute(cur, oid)
    assert len(_outbox(cur, "opp_4")) == 1
    pipeline.set_sdr_note(cur, mid, "  Changed my mind: she is the buyer.  ", scene["user"])
    rows = _outbox(cur, "opp_4")
    assert len(rows) == 2 and rows[1]["payload"]["handoff_note"] == "Changed my mind: she is the buyer."
    assert db.val(cur, "select sdr_note_by from meetings where id = %s", mid) == scene["user"]
    pipeline.set_sdr_note(cur, mid, "   ", scene["user"])      # clearing removes the note; nothing is sent for the blank
    assert db.val(cur, "select sdr_note from meetings where id = %s", mid) is None
    rows = _outbox(cur, "opp_4")
    assert len(rows) == 3 and rows[2]["payload"]["handoff_note"] is None      # cleared: the CRM is told to drop this desk's copy
    # Back to the first words: that is a change from the last write, so it is sent again.
    pipeline.set_sdr_note(cur, mid, "Warm. Her CFO asked for a demo before budget closes.", scene["user"])
    rows = _outbox(cur, "opp_4")
    assert len(rows) == 4 and rows[3]["payload"]["handoff_note"].startswith("Warm.")
    assert len({r["idempotency_key"] for r in rows}) == 4


def test_the_crm_adapter_sends_only_what_is_known_and_a_missing_deal_is_finished(cur, scene):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"id": "opp_1", "refused": []}) if "gone" not in request.url.path else httpx.Response(404, json={"error": "no"})
    crm = crmdesk.CrmDeskCrm("http://crm.test", "k", client=httpx.Client(base_url="http://crm.test", transport=httpx.MockTransport(handler)))
    assert crm.push(cur, "deal_context", {"crm_id": "opp_1", "handoff_play": "P: h", "handoff_signal": "S"}, "k1") == "opp_1"
    assert calls == [("PATCH", "/api/v1/opportunities/opp_1", {"handoff_play": "P: h", "handoff_signal": "S"})]
    assert crm.push(cur, "deal_context", {"crm_id": "gone", "handoff_play": "P"}, "k2") == "skipped:no_such_deal"
    calls.clear()
    crm.push(cur, "deal_context", {"crm_id": "opp_1", "handoff_play": "P", "handoff_note": None}, "k3")
    assert calls[0][2] == {"handoff_play": "P", "handoff_note": None}


def test_a_crm_that_does_not_take_the_kind_gets_nothing_and_the_row_is_finished(cur):
    class Plain:
        accepts_kinds = {"contact"}

        def push(self, *a):
            raise AssertionError("must not be called")
    assert pipeline._push(cur, Plain(), {"kind": "deal_context", "payload": {}, "idempotency_key": "x"}) == "skipped:unsupported"


def test_the_recorded_crm_takes_the_kind_only_when_its_journal_holds_the_call():
    plain = RecordedCrm([{"method": "GET", "path": "/changes/opportunities", "body": None}])
    assert "deal_context" not in plain.accepts_kinds
    held = RecordedCrm([{"method": "PATCH", "path": "/opportunities/opp_1", "body": {"handoff_play": "P"}}])
    assert "deal_context" in held.accepts_kinds


# ---- the screen's routes

def test_logging_a_meeting_keeps_the_sdrs_note_and_an_sdr_edits_only_their_own(world, monkeypatch):
    import contextlib

    from fastapi.testclient import TestClient

    from outbound.api.app import app
    client = TestClient(app)

    class _Back(Exception):
        pass
    try:
        with db.tx() as cur:
            @contextlib.contextmanager
            def same():
                yield cur
            monkeypatch.setattr(db, "tx", same)
            a = db.one(cur, "select id, owner_id from accounts where owner_id is not null limit 1")
            sdr = db.one(cur, "select id from users where role = 'sdr' and active and id = %s", a["owner_id"]) or db.one(cur, "select id from users where role = 'sdr' and active limit 1")
            other = db.val(cur, "select id from users where role = 'sdr' and active and id <> %s limit 1", sdr["id"])
            when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
            r = client.post(f"/api/accounts/{a['id']}/meetings", headers={"X-Acting-As": str(sdr["id"])}, json={"starts_at": when, "note": "  Knows the CFO.  "})
            assert r.status_code == 200, r.text
            mid = r.json()["meeting_id"]
            assert db.val(cur, "select sdr_note from meetings where id = %s", mid) == "Knows the CFO."
            assert client.put(f"/api/meetings/{mid}/sdr-note", headers={"X-Acting-As": str(other)}, json={"note": "mine"}).status_code == 403
            ok = client.put(f"/api/meetings/{mid}/sdr-note", headers={"X-Acting-As": str(sdr["id"])}, json={"note": "Knows the CFO and the CTO."})
            assert ok.status_code == 200 and db.val(cur, "select sdr_note from meetings where id = %s", mid) == "Knows the CFO and the CTO."
            assert client.get(f"/api/meetings/{mid}", headers={"X-Acting-As": str(sdr["id"])}).json()["sdr_note"] == "Knows the CFO and the CTO."
            assert client.put("/api/meetings/999999999/sdr-note", headers={"X-Acting-As": str(sdr["id"])}, json={"note": "x"}).status_code == 404
            raise _Back
    except _Back:
        pass


def test_the_screens_ask_for_the_note_in_the_sdrs_own_words():
    from pathlib import Path
    sheets = (Path(__file__).resolve().parents[1] / "web" / "src" / "sheets.tsx").read_text()
    assert "Your note for the account executive" in sheets and "/api/meetings/${id}/sdr-note" in sheets
    assert "note: note.trim() || null" in sheets
