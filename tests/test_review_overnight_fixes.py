"""Fixes from the standalone-day review: a date is not an invented number, the call sheet knows their clock, a
signal two sources saw is listed once, and the call note reaches the task."""
from __future__ import annotations

from datetime import datetime, timezone

from test_guarantees import scene  # noqa: F401  (the scene fixture)

from outbound import db, gate, sdr_steps, views
from outbound.copy_gate import check_suggestion
from outbound.db import J


def test_a_date_in_a_meeting_time_is_not_an_invented_number():
    theirs = "Does Thursday work for a call?"
    assert check_suggestion("Thursday 19 November at 10:00 works for me.", theirs) == []
    assert check_suggestion("Thursday, November 19th at 10:00 works for me.", theirs) == []
    # Real invented numbers are still caught.
    assert check_suggestion("We can save 19% for you.", theirs)[0]["code"] == "invented_number"
    assert check_suggestion("Pricing starts at $19 a month.", theirs)[0]["code"] == "invented_number"
    assert check_suggestion("We have 120 customers like you.", theirs)[0]["code"] == "invented_number"


def _call_task(cur, sc) -> int:
    db.run(cur, "update people set phone = '+1 215 555 0100', phone_status = 'valid' where id = %s", sc["person"])
    return db.val(cur, """insert into tasks (account_play_id, person_id, kind, title, due_at, owner_id)
                          values (%s, %s, 'call', 'Call', now(), %s) returning id""", sc["ap"], sc["person"], sc["user"])


def test_the_call_sheet_says_what_time_it_is_for_them(cur, scene, monkeypatch):  # noqa: F811
    db.run(cur, "update people set timezone = 'America/Los_Angeles' where id = %s", scene["person"])
    tid = _call_task(cur, scene)
    monkeypatch.setattr(gate, "now", lambda c: datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc))  # Monday 7:00 in LA
    t = views.task(cur, tid)
    assert t["local_now"] == "07:00" and t["in_call_hours"] is False
    monkeypatch.setattr(gate, "now", lambda c: datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc))  # 10:00 in LA
    t = views.task(cur, tid)
    assert t["local_now"] == "10:00" and t["in_call_hours"] is True


def test_the_call_sheet_with_no_known_zone_gives_no_verdict(cur, scene):  # noqa: F811
    db.run(cur, "update people set timezone = null, country = null where id = %s", scene["person"])
    t = views.task(cur, _call_task(cur, scene))
    assert t["local_now"] is None and t["in_call_hours"] is None


def test_a_call_note_is_kept_on_the_task(cur, scene):  # noqa: F811
    tid = _call_task(cur, scene)
    sdr_steps.complete(cur, tid, user={"id": scene["user"], "role": "sdr"}, outcome="no_answer", note="Voicemail, call back Thursday.")
    assert db.val(cur, "select note from tasks where id = %s", tid) == "Voicemail, call back Thursday."


def test_a_signal_two_sources_saw_is_listed_once_with_both_sources(cur, scene):  # noqa: F811
    db.run(cur, "insert into signal_sources (key, label, adapter, cadence_minutes) values ('t_src2', 'T2', 'sim', 60) "
                "on conflict do nothing")
    seen = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    for src, ext in (("t_src", "dup-a"), ("t_src2", "dup-b")):
        db.run(cur, """insert into signals (type_key, source, external_id, account_id, observed_at, strength, evidence, status)
                       values ('t_sig', %s, %s, %s, %s, 0.5, %s, 'matched')""",
               src, f"{ext}{id(cur)}", scene["account"], seen, J({"summary": "Oscar Alvarez became CFO", "url": "https://x"}))
    a = views.account(cur, scene["account"], money=False)
    same = [s for s in a["signals"] if s["evidence"].get("summary") == "Oscar Alvarez became CFO"]
    assert len(same) == 1 and sorted(same[0]["sources"]) == ["t_src", "t_src2"]
    assert any(s["evidence"].get("summary") == "x" for s in a["signals"])  # an unrelated signal stays


def test_the_web_screens_carry_the_review_fixes():
    """The web app has no browser test harness; this pins the strings and structure the review fixes added."""
    from pathlib import Path
    web = Path(__file__).resolve().parent.parent / "web" / "src"
    sheets = (web / "sheets.tsx").read_text()
    assert '<Status kind="stop">{""}</Status><span className="bad">{p}</span>' in sheets  # warning is two children, so it has width
    assert "I answered elsewhere" in sheets and '"Queued"' in sheets and "failed its own checks" in sheets
    assert "Their time now" in sheets and "What was said" in sheets and "sources" in sheets
    assert "Accepting..." in sheets and "Accepting..." in (web / "pages" / "Work.tsx").read_text()
    assert '["mine", "Mine"]' in (web / "pages" / "Work.tsx").read_text()
    assert "cap(r.outcome)" in (web / "pages" / "Flow.tsx").read_text()
    assert "dashed" in (web / "styles.css").read_text()
