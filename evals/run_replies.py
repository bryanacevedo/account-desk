"""Reply classification eval: the real pipeline (cleaning, rules, then the model) over a labelled set.

  ANTHROPIC_LIVE=1 ... python evals/run_replies.py     calls Claude and records every answer
  python evals/run_replies.py                          replays the recordings (what CI does)

Writes evals/REPLIES.md with accuracy, the rules-only baseline, a confusion matrix and the side-fact checks.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from outbound import db, llm, replies, sim_llm  # noqa: F401

HERE = Path(__file__).resolve().parent
# Pairs a person would accept either way; scored as a soft match and reported separately.
EQUIVALENT = {frozenset({"interested", "meeting_request"}), frozenset({"interested", "question"}),
              frozenset({"not_interested", "unsubscribe"})}


def classify(cur, item: dict) -> dict:
    cleaned = replies.clean(item["text"])
    ruled = replies.rules_label(item.get("from", "buyer@example.com"), item.get("subject", "Re: billing"), cleaned)
    if ruled:
        return {"label": ruled[0], "by": "rules", "rules_label": ruled[0], "same_person": True, "instructs_system": False}
    out = llm.run(cur, "classify", {"cleaned": cleaned, "subject": item.get("subject", "Re: billing"),
                                    "language_hint": replies.detect_language(cleaned)})
    ref = out.get("referral") or {}
    email_ok = not ref.get("email") or ref["email"].lower() in item["text"].lower()
    return {"label": out["label"], "by": "model", "rules_label": None, "confidence": out["confidence"],
            "same_person": out["same_person"], "instructs_system": out["instructs_system"], "referral": ref,
            "referral_email_in_text": email_ok}


def main() -> int:
    items = [json.loads(line) for line in (HERE / "replies.jsonl").read_text().splitlines() if line.strip()]
    results = []
    with db.tx() as cur:
        for it in items:
            results.append({**it, **{f"got_{k}" if k in ("label",) else k: v for k, v in classify(cur, it).items()}})
    exact = sum(r["got_label"] == r["label"] for r in results)
    soft = sum(r["got_label"] == r["label"] or frozenset({r["got_label"], r["label"]}) in EQUIVALENT for r in results)
    rules_only = sum((r["rules_label"] or "other") == r["label"] for r in results)
    by_rules = sum(r["by"] == "rules" for r in results)
    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        confusion[r["label"]][r["got_label"]] += 1
    side = {
        "assistant or forward spotted": [(r["id"], r["same_person"]) for r in results if r.get("same_person") is not None
                                         and "same_person" in r and r["by"] == "model" and r.get("same_person") is False],
        "instruction attempt flagged": [r["id"] for r in results if r.get("instructs_system") and r["by"] == "model"],
        "referral emails not in the text": [r["id"] for r in results if r.get("referral_email_in_text") is False],
    }
    expected_not_same = [r["id"] for r in items if r.get("same_person") is False]
    got_not_same = [r["id"] for r in results if r["by"] == "model" and r.get("same_person") is False]
    labels = sorted({r["label"] for r in results} | {r["got_label"] for r in results})
    n = len(results)
    lines = [
        "# Reply classification eval", "",
        f"{n} labelled replies, run through the real pipeline: cleaning, rules, then the model. "
        f"Source of the model's answers: {'live calls' if llm.CONFIG.anthropic_live else 'recordings'} "
        f"({llm.TASKS['classify']['model']}, effort {llm.TASKS['classify']['effort']}).", "",
        "| Measure | Result |", "|---|---|",
        f"| Exact label | {exact} of {n} ({exact / n:.0%}) |",
        f"| Label a person would accept (interested and meeting request, not interested and unsubscribe, treated as one) | {soft} of {n} ({soft / n:.0%}) |",
        f"| Rules alone, everything else read as unclear | {rules_only} of {n} ({rules_only / n:.0%}) |",
        f"| Settled by rules, no model call | {by_rules} of {n} |",
        f"| Written by someone else (assistant, colleague) spotted | {len(set(got_not_same) & set(expected_not_same))} of {len(expected_not_same)} |",
        f"| Attempt to instruct the system flagged | {'yes' if 'r37' in side['instruction attempt flagged'] else 'no'} (r37) |",
        f"| Referral emails the model invented | {len(side['referral emails not in the text'])} |", "",
        "## Misses", "",
    ]
    for r in results:
        if r["got_label"] != r["label"]:
            lines.append(f"- {r['id']}: expected {r['label']}, got {r['got_label']} ({r['by']}). \"{r['text'][:90]}\"")
    lines += ["", "## Confusion matrix (rows: expected, columns: got)", "",
              "| expected \\ got | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for exp in labels:
        if exp in confusion:
            lines.append(f"| {exp} | " + " | ".join(str(confusion[exp][g] or "") for g in labels) + " |")
    (HERE / "REPLIES.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:14]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
