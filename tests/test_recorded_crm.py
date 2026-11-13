"""The recorded CRM: a journal produced by recording CrmDeskCrm against a fake, then replayed. No database."""
import dataclasses
import json

import httpx
import pytest

from outbound import adapters
from outbound.__main__ import demo_crm
from outbound.adapters import choose_crm
from outbound.adapters.crmdesk import CrmDeskCrm
from outbound.adapters.recorded import JournalMismatch, RecordedCrm, RecordingCrm
from outbound.config import CONFIG


def fake(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p.endswith("/activities"):
        return httpx.Response(201, json={"id": "act_1"})
    if p.endswith("/changes/opportunities"):
        return httpx.Response(200, json={"data": [], "next": None, "has_more": False})
    if p.endswith("/changes/owners"):
        return httpx.Response(200, json={"data": [{"account_domain": "a.com", "owner_email": "o@x.com",
                                                   "updated_at": "2026-01-01T00:00:00+00:00", "change_id": "c1"}],
                                         "next": None, "has_more": False})
    if p.endswith("/contacts/contactability"):
        refs = json.loads(request.content)["contacts"]
        return httpx.Response(200, json={"results": [{"ref": r["ref"], "can_email": True, "can_call": True} for r in refs]})
    return httpx.Response(404, json={})


def record(path, optional=True):
    inner = CrmDeskCrm("http://crm", "k", client=httpx.Client(base_url="http://crm", transport=httpx.MockTransport(fake)))
    crm = RecordingCrm(inner, path)
    drive(crm, optional)
    return path


def drive(crm, optional=True):
    crm.push(None, "activity", {"type": "email_sent", "email": "p@a.com", "subject": "Hi", "message_id": 7}, "message:7")
    crm.deals_changed(None, None, 10)
    crm.owners_changed(None, "t|1", 10)
    if optional:
        crm.contactability(None, [{"ref": 1, "email": "p@a.com"}])


@pytest.fixture
def journal(tmp_path):
    p = tmp_path / "journal.jsonl"
    p.write_text(json.dumps({"actor": "market_desk", "at": "x", "method": "POST", "path": "/accounts/batch", "body": {}, "status": 200, "answer": {}}) + "\n")
    with p.open() as f:
        pass
    record_to = tmp_path / "mine.jsonl"
    record(record_to)
    with p.open("a") as f:
        f.write(record_to.read_text())
    return p


def steps(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def write(p, ss):
    p.write_text("".join(json.dumps(s) + "\n" for s in ss))


def test_exact_replay_passes_and_ignores_other_actors(journal):
    crm = RecordedCrm.from_journal(journal)
    drive(crm)
    crm.finish()


def test_extra_call_fails(journal):
    crm = RecordedCrm.from_journal(journal)
    drive(crm)
    with pytest.raises(JournalMismatch):
        crm.owners_changed(None, "t|1", 10)
    with pytest.raises(JournalMismatch):
        crm.finish()


def test_changed_body_fails(journal):
    crm = RecordedCrm.from_journal(journal)
    with pytest.raises(JournalMismatch, match="body"):
        crm.push(None, "activity", {"type": "email_sent", "email": "p@a.com", "subject": "Other", "message_id": 7}, "message:7")


def test_changed_idempotency_key_fails(journal):
    crm = RecordedCrm.from_journal(journal)
    with pytest.raises(JournalMismatch, match="idempotency_key"):
        crm.push(None, "activity", {"type": "email_sent", "email": "p@a.com", "subject": "Hi", "message_id": 7}, "message:8")


def test_timestamps_are_not_compared(journal, tmp_path):
    ss = steps(journal)
    for s in ss:
        s["at"] = "1999-01-01T00:00:00+00:00"
    write(journal, ss)
    crm = RecordedCrm.from_journal(journal)
    drive(crm)
    crm.finish()


def test_missing_call_at_end_fails(journal):
    crm = RecordedCrm.from_journal(journal)
    crm.push(None, "activity", {"type": "email_sent", "email": "p@a.com", "subject": "Hi", "message_id": 7}, "message:7")
    crm.deals_changed(None, None, 10)
    with pytest.raises(JournalMismatch, match="not used"):
        crm.finish()


def test_wrong_order_fails(journal):
    crm = RecordedCrm.from_journal(journal)
    with pytest.raises(JournalMismatch):
        crm.deals_changed(None, None, 10)


def test_a_mismatch_the_desk_swallowed_still_fails_the_build(journal):
    crm = RecordedCrm.from_journal(journal)
    try:
        crm.deals_changed(None, None, 10)
    except (Exception, JournalMismatch):
        pass
    with pytest.raises(JournalMismatch):
        crm.finish()


def test_optional_methods_follow_the_journal(tmp_path):
    p = record(tmp_path / "j.jsonl", optional=False)
    crm = RecordedCrm.from_journal(p)
    assert getattr(crm, "contactability", None) is None
    assert getattr(crm, "accounts_changed", None) is None
    assert getattr(crm, "campaign_members_changed", None) is None
    assert callable(crm.push) and callable(crm.deals_changed) and callable(crm.owners_changed)
    drive(crm, optional=False)
    crm.finish()
    full = RecordedCrm.from_journal(record(tmp_path / "k.jsonl"))
    assert callable(getattr(full, "contactability", None))
    assert getattr(full, "accounts_changed", None) is None


def test_recorded_refused_in_live_mode_and_public_demo(journal, monkeypatch):
    monkeypatch.setenv("CRM", "recorded")
    monkeypatch.setenv("JOURNAL_PATH", str(journal))
    assert isinstance(choose_crm(None), RecordedCrm)
    monkeypatch.setattr(adapters, "CONFIG", dataclasses.replace(CONFIG, mode="live"))
    with pytest.raises(SystemExit):
        choose_crm(None)
    monkeypatch.setattr(adapters, "CONFIG", dataclasses.replace(CONFIG, public_demo=True))
    with pytest.raises(SystemExit):
        choose_crm(None)


def test_demo_uses_the_simulated_crm_without_account_desk_steps(tmp_path, journal):
    assert demo_crm(tmp_path / "missing.jsonl") is None
    other = tmp_path / "other.jsonl"
    write(other, [s for s in steps(journal) if s["actor"] != "account_desk"])
    assert demo_crm(other) is None
    assert isinstance(demo_crm(journal), RecordedCrm)
