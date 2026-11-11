"""Suggested-reply eval: the reply an SDR is offered after a positive answer, over cases written independently.

  ANTHROPIC_LIVE=1 ... python evals/run_suggest.py     calls Claude (and the judge) and records every answer
  python evals/run_suggest.py                          replays the recordings (what CI does)

The suggestion is written without product facts, so the bar is safety first: it never invents a price, an
integration, a customer, a number, a date or a promise. Graded by code where code can see it (length, dashes,
exclamation marks, invented numbers, two concrete times when they asked to meet, their language) and by the judge
for the rest (answers what they asked, invents nothing, does nothing the case forbids, sounds like a person).
Writes evals/SUGGEST.md; exits non-zero when a score falls below evals/thresholds.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # judge.py and thresholds.py sit here
from judge import judge, rate  # noqa: E402

from outbound import db, llm, replies, sim_llm  # noqa: F401

HERE = Path(__file__).resolve().parent
NUMBERISH = re.compile(r"[$€£]\s?\d|\d+\s?%|\d{2,}")
TIME = re.compile(r"\b(\d{1,2}(:\d{2})?\s?(am|pm|h)|\d{1,2}:\d{2}|monday|tuesday|wednesday|thursday|friday|lunes|martes|miércoles|"
                  r"jueves|viernes|lundi|mardi|mercredi|jeudi|vendredi|montag|dienstag|mittwoch|donnerstag|freitag|"
                  r"segunda|terça|quarta|quinta|sexta)\b", re.I)

CRITERIA = [
    ("answers", "It responds to what the prospect actually asked or said; if they asked a question it addresses it "
                "honestly, even if only to say the SDR will confirm the detail."),
    ("no_invention", "It does not state any price, discount, integration, customer name, security certification, "
                     "number, launch date or other product fact; the SDR has none to give."),
    ("respects_case", "It does none of the things listed in the case's must_not."),
    ("meeting", "If the prospect wants to meet, it proposes two concrete times or accepts the time they offered; "
                "otherwise it does not push for a meeting harder than one light offer."),
    ("tone", "It reads like a person: plain, warm, short, no hype, no flattery, does not repeat their words back."),
]


def load(name: str) -> list[dict]:
    path = HERE / name
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def run_case(cur, c: dict) -> dict:
    out = llm.run(cur, "suggest_reply", {"label": c["label"], "cleaned": c["cleaned"], "first_name": c.get("first_name")})
    body = out["body"]
    e = c.get("expect", {})
    words = len(body.split())
    times = len({m.group(0).lower() for m in TIME.finditer(body)})
    reply_lang, their_lang = replies.detect_language(body), replies.detect_language(c["cleaned"])
    code = {
        "under_80_words": words <= 80,
        "no_dashes_or_exclamations": "—" not in body and "–" not in body and "!" not in body,
        "no_invented_numbers": not NUMBERISH.search(TIME.sub("", body)) or bool(NUMBERISH.search(c["cleaned"])),
        "two_times_when_asked": (not e.get("wants_meeting")) or times >= 2 or bool(TIME.search(c["cleaned"])),
        "their_language": reply_lang == their_lang or their_lang == "en",
    }
    j = judge({"label": c["label"], "prospect_reply": c["cleaned"], "first_name": c.get("first_name"),
               "wants_meeting": e.get("wants_meeting"), "question": e.get("question"), "must_not": e.get("must_not", [])},
              {"suggested_reply": body}, CRITERIA)
    judged = {k: v["passed"] for k, v in j.items() if not k.startswith("_")} if j else None
    passed = all(code.values()) and (judged is None or all(judged.values()))
    return {"id": c["id"], "tags": c.get("tags", []), "body": body, "words": words, "code": code, "judge": judged,
            "why": {k: v["why"] for k, v in j.items() if not k.startswith("_") and not v["passed"]} if j else {},
            "passed": passed}


def report(rows: list[dict]) -> tuple[str, dict]:
    n = len(rows)
    judged = [r for r in rows if r["judge"] is not None]
    scores = {"suggest_pass": sum(r["passed"] for r in rows) / n if n else 0,
              "suggest_no_invention": sum(r["judge"]["no_invention"] for r in judged) / len(judged) if judged else 1.0}
    lines = ["# Suggested-reply eval", "",
             f"{n} cases written independently of the code. Graded by code and by a {('Claude Sonnet 5.5')} judge "
             f"({len(judged)} judged).", "",
             "| Check | Result |", "|---|---|",
             f"| Passes every check | {rate(sum(r['passed'] for r in rows), n)} |"]
    for k in rows[0]["code"] if rows else []:
        lines.append(f"| Code: {k.replace('_', ' ')} | {rate(sum(r['code'][k] for r in rows), n)} |")
    for cid, _ in CRITERIA:
        lines.append(f"| Judge: {cid.replace('_', ' ')} | {rate(sum(r['judge'][cid] for r in judged), len(judged))} |")
    lines += ["", "## Every suggestion", ""]
    for r in rows:
        fails = [k for k, v in r["code"].items() if not v] + [k for k, v in (r["judge"] or {}).items() if not v]
        lines += [f"**{r['id']}** {', '.join(r['tags'])}: {'passes' if r['passed'] else 'fails ' + ', '.join(fails)}", "",
                  "> " + r["body"].replace("\n", " "), ""]
        for k, why in r["why"].items():
            lines.append(f"- {k}: {why}")
        if r["why"]:
            lines.append("")
    return "\n".join(lines), scores


def main() -> int:
    cases = load("suggest_v2.jsonl")
    with db.tx() as cur:
        rows = [run_case(cur, c) for c in cases]
        db.run(cur, "rollback")
    text, scores = report(rows)
    (HERE / "SUGGEST.md").write_text(text)
    print(text.split("## Every suggestion")[0])
    from thresholds import check
    return check(scores)


if __name__ == "__main__":
    sys.exit(main())
