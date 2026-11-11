"""The reply eval, replayed from recorded Claude answers. No key needed. A prompt change without a new recording
fails here, so CI never grades a prompt it did not see."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from outbound import db, llm

ROOT = Path(__file__).resolve().parents[1]


def _runner():
    spec = importlib.util.spec_from_file_location("run_replies", ROOT / "evals" / "run_replies.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_recordings_match_the_current_prompt():
    rows = [json.loads(line) for line in (ROOT / "evals/recordings/classify.jsonl").read_text().splitlines() if line.strip()]
    assert rows, "no recordings: run evals/run_replies.py with ANTHROPIC_LIVE=1"
    assert {r["prompt_hash"] for r in rows} == {llm.prompt_hash("classify")}, "prompt changed: re-record the evals"


def test_reply_classifier_holds_its_recorded_accuracy(database):
    run = _runner()
    items = [json.loads(line) for line in (ROOT / "evals/replies.jsonl").read_text().splitlines() if line.strip()]
    with db.tx() as cur:
        got = [run.classify(cur, it) for it in items]
    exact = sum(g["label"] == it["label"] for g, it in zip(got, items))
    assert exact / len(items) >= 0.90
    assert all(g.get("referral_email_in_text", True) for g in got)
    flagged = {it["id"] for g, it in zip(got, items) if g.get("instructs_system")}
    assert "r37" in flagged
    assert all(g["by"] == "rules" or "confidence" in g for g in got)
