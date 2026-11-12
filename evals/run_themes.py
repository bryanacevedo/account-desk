"""Theming eval: learnings worded differently, filed under themes one after another, as the desk files them.

  ANTHROPIC_LIVE=1 ... python evals/run_themes.py     calls Claude and records every answer
  python evals/run_themes.py                          replays the recordings (what CI does)

Cases are in evals/cases/themes_v1.jsonl, written by an agent that never saw the code (DECISIONS 45). Each case has
the group a careful person would put it in. The desk's real path runs: a learning row, `themes.file_learning`, the
code checks and the one re-ask, all inside a transaction that is rolled back. Themes already in the database are set
aside first (inside the same transaction), so every case meets only the themes earlier cases made.

Graded by code: pairwise agreement with the expected grouping (for every two learnings of the same kind, do the desk
and the person agree on same theme or not), how often a group stays together and different groups stay apart, and
whether a label holds a name or address the case says it must not (a safety check, floor 1.0).
Writes evals/THEMES.md; exits non-zero when a score falls below evals/thresholds.json.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import rate  # noqa: E402

from outbound import db, sim_llm, themes  # noqa: E402,F401

HERE = Path(__file__).resolve().parent


def load(name: str = "cases/themes_v1.jsonl") -> list[dict]:
    path = HERE / name
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def run(cur, cases: list[dict]) -> list[dict]:
    """File every case in order. The caller rolls the transaction back."""
    db.run(cur, "delete from play_suggestions")
    db.run(cur, "update plays set suggested_from = null")
    db.run(cur, "update learnings set theme_id = null")
    db.run(cur, "delete from learning_themes")
    a = db.val(cur, "insert into accounts (name, primary_domain) values ('Eval Co', 'eval-themes.example') returning id")
    m = db.val(cur, "insert into meetings (account_id, booked_at, starts_at, status, source) values (%s, now(), now(), 'held', 'sdr') returning id", a)
    note = db.val(cur, "insert into call_notes (meeting_id, text) values (%s, 'eval') returning id", m)
    out = []
    for c in cases:
        lid = db.val(cur, "insert into learnings (call_note_id, kind, text, quote) values (%s, %s, %s, %s) returning id",
                     note, c["kind"], c["text"], c["text"])
        tid = themes.file_learning(cur, lid)
        label = db.val(cur, "select label from learning_themes where id = %s", tid) if tid else None
        banned = [w for w in c.get("label_must_not_contain", []) if label and w.lower() in label.lower()]
        out.append({"id": c["case_id"], "kind": c["kind"], "group": c["group"], "text": c["text"], "theme": tid,
                    "label": label, "named": banned, "trap": c.get("trap")})
    return out


def report(rows: list[dict]) -> tuple[str, dict]:
    pairs = [(x, y) for x, y in itertools.combinations(rows, 2) if x["kind"] == y["kind"]]
    agree = sum((x["group"] == y["group"]) == (x["theme"] is not None and x["theme"] == y["theme"]) for x, y in pairs)
    together = [(x, y) for x, y in pairs if x["group"] == y["group"]]
    apart = [(x, y) for x, y in pairs if x["group"] != y["group"]]
    kept = sum(x["theme"] is not None and x["theme"] == y["theme"] for x, y in together)
    split = sum(x["theme"] != y["theme"] for x, y in apart)
    traps = [r for r in rows if r["trap"]]
    named = [r for r in rows if r["named"]]
    n = len(rows)
    scores = {"themes_agreement": agree / len(pairs) if pairs else 0.0,
              "themes_no_names": 1 - len(named) / len(traps) if traps else 1.0,
              "themes_filed": sum(r["theme"] is not None for r in rows) / n if n else 0.0}
    groups = len({r["group"] for r in rows})
    made = len({r["theme"] for r in rows if r["theme"] is not None})
    lines = ["# Theming eval", "",
             f"{n} learnings in {groups} groups, written independently of the code, filed one after another through "
             "the desk's own path (the model answers, code checks, one re-ask). Graded by code.", "",
             "| Check | Result |", "|---|---|",
             f"| Pairs of the same kind where the desk agrees with the expected grouping | {rate(agree, len(pairs))} |",
             f"| Pairs that belong together and were kept together | {rate(kept, len(together))} |",
             f"| Pairs that belong apart and were kept apart | {rate(split, len(apart))} |",
             f"| Filed under a theme | {rate(sum(r['theme'] is not None for r in rows), n)} |",
             f"| Themes made, against {groups} expected groups | {made} |",
             f"| Labels holding a name or address the case forbids | {len(named)} of {len(traps)} cases with one |",
             "", "## Every learning", "", "| Case | Expected group | Theme | Text |", "|---|---|---|---|"]
    for r in rows:
        flag = f" (names {', '.join(r['named'])})" if r["named"] else ""
        lines.append(f"| {r['id']} | {r['group']} | {r['label'] or '(not filed)'}{flag} | {r['text']} |")
    return "\n".join(lines), scores


def main() -> int:
    with db.tx() as cur:
        rows = run(cur, load())
        db.run(cur, "rollback")
    text, scores = report(rows)
    (HERE / "THEMES.md").write_text(text + "\n")
    print(text.split("## Every learning")[0])
    from thresholds import check
    return check(scores)


if __name__ == "__main__":
    sys.exit(main())
