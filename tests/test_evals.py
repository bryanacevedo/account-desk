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


def _writing():
    spec = importlib.util.spec_from_file_location("run_writing", ROOT / "evals" / "run_writing.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_writing_recordings_match_the_current_prompts():
    for task in ("draft", "draft_linkedin", "brief"):
        rows = [json.loads(line) for line in (ROOT / f"evals/recordings/{task}.jsonl").read_text().splitlines() if line.strip()]
        assert rows, f"no recordings for {task}: run evals/run_writing.py with ANTHROPIC_LIVE=1"
        assert {r["prompt_hash"] for r in rows} == {llm.prompt_hash(task)}, f"{task} prompt changed: re-record the evals"


def test_drafts_and_briefs_hold_their_recorded_quality(database):
    run = _writing()
    with db.tx() as cur:
        drafts, briefs = run.run(cur)
        db.run(cur, "rollback")
    n = len(drafts)
    # The claim checker sends more first drafts back on purpose; what matters is what passes after the rewrite.
    assert sum(d["first_pass"] for d in drafts) / n >= 0.5
    assert sum(d["passed"] for d in drafts) / n >= 0.85
    assert not any(d["cited_private"] or d["cited_unknown"] for d in drafts)
    # The one case with only private facts must fail rather than say something unsourced.
    assert not next(d for d in drafts if d["id"] == "d05")["passed"]
    # The original six are held to the strict code check; the independent set, whose facts include job titles the
    # capitalised-name check cannot tell from invented names, is held to the judge's floor instead.
    assert all(b["kept"] >= 1 for b in briefs)
    assert all(not b["unfaithful"] for b in briefs if not b["id"].startswith("b2_"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "evals" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_ai_task_has_recordings_for_its_current_prompt():
    for task in ("classify", "draft", "draft_linkedin", "brief", "suggest_reply", "extract", "check_claims", "theme",
                 "draft_play"):
        rows = [json.loads(line) for line in (ROOT / f"evals/recordings/{task}.jsonl").read_text().splitlines() if line.strip()]
        assert rows, f"no recordings for {task}: run make evals-live"
        assert {r["prompt_hash"] for r in rows} == {llm.prompt_hash(task)}, f"{task} prompt changed: re-record the evals"


def _floors() -> dict:
    return json.loads((ROOT / "evals/thresholds.json").read_text())


def test_suggested_replies_hold_their_floors(database):
    run = _load("run_suggest")
    with db.tx() as cur:
        rows = [run.run_case(cur, c) for c in run.load("suggest_v2.jsonl")]
        db.run(cur, "rollback")
    _, scores = run.report(rows)
    floors = _floors()
    assert all(r["judge"] is not None for r in rows), "a suggestion was never judged: run make evals-live"
    for k in ("suggest_pass", "suggest_no_invention"):
        assert scores[k] >= floors[k], (k, scores[k])


def test_call_notes_hold_their_floors(database):
    run = _load("run_extract")
    with db.tx() as cur:
        rows = [run.run_case(cur, c) for c in run.load("extract_v2.jsonl")]
        db.run(cur, "rollback")
    _, scores = run.report(rows)
    floors = _floors()
    for k in ("extract_recall", "extract_verbatim", "extract_no_invention"):
        assert scores[k] >= floors[k], (k, scores[k])


# Recorded live while a competitor review could still be cited. Since 2026-11-11 competitor reviews are private (the
# desk acts on them and never names them), so these cases now give the model an input it never answered and replay
# the stand-in instead. They stay out of the floors until `make evals-live` re-records them; then empty these.
STALE_WRITING = {"d2_16"}


def _stale_draft_play(c: dict) -> bool:
    """A case whose catalog offered competitor reviews outside their own segment: the desk now leaves them out."""
    return c["segment"]["key"] != "competitor_review" and any(
        t["key"] == "competitor_review" for t in c["catalog"]["signal_types"])


def test_drafts_and_briefs_hold_their_floors(database):
    run = _writing()
    with db.tx() as cur:
        drafts, briefs = run.run(cur)
        db.run(cur, "rollback")
    assert STALE_WRITING <= {d["id"] for d in drafts}
    every = len(drafts)
    drafts = [d for d in drafts if d["id"] not in STALE_WRITING]
    scores = run.scores_of(drafts, briefs)
    floors = _floors()
    for k, v in scores.items():
        if k == "drafts_faithful" and STALE_WRITING:
            # A rate over fewer cases moves when a stale one is dropped, so while any are stale the floor is held as a
            # count: no more unfaithful drafts among the cases still measured than the floor allowed over all of them.
            assert round((1 - v) * len(drafts)) <= round((1 - floors[k]) * every), (k, v)
        elif k in floors:
            assert v >= floors[k], (k, v)


def test_theming_holds_its_floors(database):
    run = _load("run_themes")
    with db.tx() as cur:
        rows = run.run(cur, run.load())
        db.run(cur, "rollback")
    _, scores = run.report(rows)
    floors = _floors()
    for k in ("themes_agreement", "themes_filed", "themes_no_names", "themes_kept_together"):
        assert scores[k] >= floors[k], (k, scores[k])


def test_suggested_plays_hold_their_floors(database):
    run = _load("run_draft_play")
    with db.tx() as cur:
        rows = [run.run_case(cur, c) for c in run.load() if not _stale_draft_play(c)]
        db.run(cur, "rollback")
    assert rows, "every suggested-play case is stale: run make evals-live"
    _, scores = run.report(rows)
    floors = _floors()
    assert all(r["judge"] is not None for r in rows if r["draft"]), "a play was never judged: run it live"
    for k in ("draft_play_pass", "draft_play_not_as_fact", "draft_play_catalog_only", "draft_play_no_names",
              "draft_play_follows", "draft_play_triggers_allowed"):
        assert scores[k] >= floors[k], (k, scores[k])
