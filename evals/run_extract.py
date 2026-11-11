"""Call-note eval: learnings pulled from an SDR's notes, over cases written independently of the code.

  ANTHROPIC_LIVE=1 ... python evals/run_extract.py     calls Claude and records every answer
  python evals/run_extract.py                          replays the recordings (what CI does)

Graded by code only, the way the desk itself keeps learnings: an item counts only if its quote is copied verbatim
from the notes (anything else is thrown away, so a paraphrased quote is a lost learning). Then recall (each expected
learning found, of the right kind), no invention (nothing the case lists as absent), and silence when the notes
hold nothing worth learning. Writes evals/EXTRACT.md; exits non-zero below evals/thresholds.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # judge.py and thresholds.py sit here
from judge import rate  # noqa: E402

from outbound import db, llm, sim_llm  # noqa: F401

HERE = Path(__file__).resolve().parent


def load(name: str) -> list[dict]:
    path = HERE / name
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def run_case(cur, c: dict) -> dict:
    out = llm.run(cur, "extract", {"notes": c["notes"]})
    items = out["items"]
    kept = [i for i in items if i["quote"] and i["quote"] in c["notes"]]
    e = c.get("expect", {})
    blob = lambda i: (i["text"] + " " + i["quote"]).lower()  # noqa: E731
    found, missing = 0, []
    for want in e.get("items", []):
        hit = any(want["must_contain"].lower() in blob(i) and i["kind"] == want["kind"] for i in kept) or \
            any(want["must_contain"].lower() in blob(i) for i in kept if want["kind"] == "quote")
        found += hit
        if not hit:
            missing.append(f"{want['kind']}: {want['must_contain']}")
    invented = [m for m in e.get("must_not", []) if any(m.lower() in blob(i) for i in items)]
    silent_ok = (not e.get("allow_empty")) or e.get("items") or not kept
    return {"id": c["id"], "tags": c.get("tags", []), "items": len(items), "kept": len(kept),
            "verbatim": len(kept) == len(items), "expected": len(e.get("items", [])), "found": found, "missing": missing,
            "invented": invented, "silent_ok": bool(silent_ok),
            "passed": found == len(e.get("items", [])) and not invented and bool(silent_ok),
            "out": [f"{i['kind']}: {i['text']} (\"{i['quote']}\")" for i in items]}


def report(rows: list[dict]) -> tuple[str, dict]:
    n = len(rows)
    expected = sum(r["expected"] for r in rows)
    found = sum(r["found"] for r in rows)
    items = sum(r["items"] for r in rows)
    kept = sum(r["kept"] for r in rows)
    scores = {"extract_recall": found / expected if expected else 1.0,
              "extract_verbatim": kept / items if items else 1.0,
              "extract_no_invention": sum(not r["invented"] for r in rows) / n if n else 1.0}
    lines = ["# Call-note eval", "",
             f"{n} sets of notes written independently of the code. Graded by code, the way the desk keeps learnings.", "",
             "| Check | Result |", "|---|---|",
             f"| Expected learnings found | {rate(found, expected)} |",
             f"| Items whose quote is verbatim (kept by the desk) | {rate(kept, items)} |",
             f"| Cases with nothing invented | {rate(sum(not r['invented'] for r in rows), n)} |",
             f"| Silent when there is nothing to learn | {rate(sum(r['silent_ok'] for r in rows), n)} |",
             f"| Cases passing every check | {rate(sum(r['passed'] for r in rows), n)} |", "",
             "## Every case", ""]
    for r in rows:
        lines += [f"**{r['id']}** {', '.join(r['tags'])}: {'passes' if r['passed'] else 'fails'}"
                  + (f"; missing {', '.join(r['missing'])}" if r["missing"] else "")
                  + (f"; invented {', '.join(r['invented'])}" if r["invented"] else ""), ""]
        lines += [f"- {x}" for x in r["out"]] or ["- nothing extracted"]
        lines.append("")
    return "\n".join(lines), scores


def main() -> int:
    cases = load("extract_v2.jsonl")
    with db.tx() as cur:
        rows = [run_case(cur, c) for c in cases]
        db.run(cur, "rollback")
    text, scores = report(rows)
    (HERE / "EXTRACT.md").write_text(text)
    print(text.split("## Every case")[0])
    from thresholds import check
    return check(scores)


if __name__ == "__main__":
    sys.exit(main())
