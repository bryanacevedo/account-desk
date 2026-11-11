"""Drafting and brief eval: the desk's own writing path over fixed cases, graded by code, with every draft printed
for a person to read.

  ANTHROPIC_LIVE=1 ... python evals/run_writing.py     calls Claude and records every answer
  python evals/run_writing.py                          replays the recordings (what CI does)

Drafts (email and LinkedIn) go through the real path: a first attempt, the copy checks, one redraft with the
failures listed, the checks again. Graded by code only:
  - passes the copy checks on the first try, and after the one redraft the desk allows;
  - never cites a private signal (a website visit, research data, a webinar); the desk never shows them to the
    drafter, and a case whose only facts are private should fail for having nothing to say, not invent;
  - never cites a fact that does not exist.
Briefs are graded on faithfulness: every kept finding cites real facts, every number and every capitalised name in
a finding appears in the facts it cites or is the company, and a thin account gets few findings, not invented ones.

What code cannot judge (is it specific, would a CFO answer) is left to the person reading WRITING.md, which prints
every draft and brief in full. Writes evals/WRITING.md.
"""
from __future__ import annotations

import json
import re
import sys
import zlib
from collections import Counter
from pathlib import Path

from outbound import copy_gate, db, llm, sim_llm  # noqa: F401  (sim_llm registers the stand-in)
from outbound.outreach import OUR_NAMES, PRIVATE_SIGNALS, limits_for

HERE = Path(__file__).resolve().parent
NOTE_LIMIT = 200


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (HERE / name).read_text().splitlines() if line.strip()]


def draft(cur, c: dict) -> dict:
    # As in the desk: private signals are never shown to the drafter (outreach.account_facts leaves them out), so a
    # case whose only facts are private has nothing to say about the company and should fail rather than invent.
    shown = [f for f in c["facts"] if f["kind"].removeprefix("signal:") not in PRIVATE_SIGNALS]
    facts = {f["id"]: f["text"] for f in shown}
    # A stable id, so a replay matches its recordings in any process.
    person = {"id": zlib.crc32(c["id"].encode()) % 10_000, "first_name": copy_gate.clean_first_name(c["person"]["first_name"], None),
              "full_name": c["person"]["first_name"], "title": c["person"]["title"]}
    account = {"name": c["company"]}
    linkedin = c["task"] == "draft_linkedin"
    attempts, failures, out, verdict = [], [], None, None
    for attempt in (1, 2):
        payload = {"company": c["company"], "sender": "Maya Okafor", "angle": "", "play_angle": c["play_angle"], "brief": [],
                   "person": {"id": person["id"], "first_name": person["first_name"], "title": person["title"]},
                   "step": {"index": 0 if c["job"] in ("open", "connect") else 2, "job": c["job"]},
                   "persona_key": c["persona_key"], "facts": shown, "limits": limits_for(c["job"], linkedin, NOTE_LIMIT if c["job"] == "connect" else None), "previous_subject": "billing at " + c["company"]
                   if c["job"] != "open" else None, "attempt": attempt, "failures": [x["message"] for x in failures]}
        if linkedin:
            payload["max_chars"] = NOTE_LIMIT if c["job"] == "connect" else None
        out = llm.run(cur, c["task"], payload)
        verdict = copy_gate.check(out, job=c["job"], person=person, account=account, facts=facts, our_names=OUR_NAMES + ["Maya Okafor"],
                                  other_bodies=[], private_ids=set(c["private_ids"]),
                                  channel="linkedin" if linkedin else "email",
                                  max_chars=NOTE_LIMIT if c["job"] == "connect" else None)
        attempts.append(verdict.passed)
        if attempt == 1:
            first_codes = [f["code"] for f in verdict.failures]
        if verdict.passed:
            break
        failures = verdict.failures
    cited = {i for s in out["sentences"] for i in (s.get("fact_ids") or [])}
    text = " ".join(s["text"] for s in out["sentences"])
    return {"id": c["id"], "task": c["task"], "job": c["job"], "first_pass": attempts[0], "passed": verdict.passed,
            "failures": [f["code"] for f in verdict.failures], "cited_private": sorted(cited & set(c["private_ids"])),
            "cited_unknown": sorted(cited - set(facts)), "subject": out.get("subject"), "text": text, "chars": len(text),
            "note": c.get("note"), "first_codes": first_codes}


NAME = re.compile(r"\b[A-Z][a-zA-Z&'-]+\b")


def brief(cur, b: dict) -> dict:
    out = llm.run(cur, "brief", {"company": b["company"], "facts": b["facts"], "why_now": b["why_now"]})
    facts = {f["id"]: f["text"] for f in b["facts"]}
    kept = [x for x in out["findings"] if x["fact_ids"] and all(i in facts for i in x["fact_ids"])]
    unfaithful = []
    for x in kept:
        source = " ".join(facts[i] for i in x["fact_ids"]) + " " + b["company"]
        for num in copy_gate.NUMBER.findall(x["text"]):
            core = num.strip("$%.,")
            if core and core not in source.replace(",", ""):
                unfaithful.append(f"number {num}")
        # A capitalised word that starts a sentence is not a name; the rest must be in the cited facts.
        for sentence in re.split(r"(?<=[.!?:;])\s+", x["text"]):
            for tok in NAME.findall(sentence)[1:]:
                if tok not in source and tok not in copy_gate.STOPWORDS_CAPS:
                    unfaithful.append(f"name {tok}")
    return {"id": b["id"], "findings": len(out["findings"]), "kept": len(kept), "unfaithful": unfaithful,
            "texts": [x["text"] for x in kept], "angle": out["angle"], "facts": len(b["facts"]), "note": b.get("note")}


def run(cur) -> tuple[list[dict], list[dict]]:
    return [draft(cur, c) for c in load("drafts.jsonl")], [brief(cur, b) for b in load("briefs.jsonl")]


def report(drafts: list[dict], briefs: list[dict]) -> str:
    n = len(drafts)
    first = sum(d["first_pass"] for d in drafts)
    final = sum(d["passed"] for d in drafts)
    private = [d["id"] for d in drafts if d["cited_private"]]
    unknown = [d["id"] for d in drafts if d["cited_unknown"]]
    codes = Counter(code for d in drafts for code in d["failures"])
    source = "recorded Claude answers" if llm.CONFIG.anthropic_live or all(
        (HERE / "recordings" / f"{t}.jsonl").exists() for t in ("draft", "draft_linkedin", "brief")) else "the stand-in"
    lines = [
        "# Drafting and brief eval", "",
        f"{n} draft cases (email first touches, follow-ups, a last email, LinkedIn connect notes and messages) and "
        f"{len(briefs)} brief cases, invented companies. Answers from {source}. Graded by code; read the drafts below "
        "for what code cannot judge.", "",
        "## Drafts", "",
        "| Check | Result |", "|---|---|",
        f"| Passes the copy checks first time | {first} of {n} |",
        f"| Passes after the one redraft the desk allows | {final} of {n} |",
        f"| Cites a private signal | {len(private)} {'(' + ', '.join(private) + ')' if private else ''} |",
        f"| Cites a fact that does not exist | {len(unknown)} {'(' + ', '.join(unknown) + ')' if unknown else ''} |",
        "", "Why first attempts failed: " + (", ".join(f"{k} {v}" for k, v in Counter(c for d in drafts for c in d["first_codes"]).most_common()) or "none") + ".",
        "", "Checks still failing after the redraft: " + (", ".join(f"{k} {v}" for k, v in codes.most_common()) or "none") + ".", "",
        "Read by a person (2026-11-11): the drafts are specific and cite their facts. One problem code does not catch: "
        "d06 credits our product to the prospect (\"Quillon Payments runs usage-based billing so finance does not end "
        "up rebuilding invoices\"). Watch for it in the approval queue.", "",
        "## Briefs", "",
        "| Case | Findings | Kept (cite real facts) | Unfaithful numbers or names |", "|---|---|---|---|",
        *[f"| {b['id']} | {b['findings']} | {b['kept']} | {', '.join(b['unfaithful']) or 'none'} |" for b in briefs], "",
        "## Every draft", "",
    ]
    for d in drafts:
        status = "passes" if d["passed"] else "fails: " + ", ".join(d["failures"])
        lines += [f"**{d['id']}** {d['task'].replace('_', ' ')}, {d['job'].replace('_', ' ')}, {status}"
                  + (f" ({d['note']})" if d.get("note") else ""), ""]
        if d.get("subject"):
            lines += [f"Subject: {d['subject']}", ""]
        lines += ["> " + d["text"], ""]
    lines += ["## Every brief", ""]
    for b in briefs:
        lines += [f"**{b['id']}**" + (f" ({b['note']})" if b.get("note") else ""), ""] + [f"- {t}" for t in b["texts"]] + \
                 ["", f"Angle: {b['angle']}", ""]
    return "\n".join(lines)


def main() -> int:
    with db.tx() as cur:
        drafts, briefs = run(cur)
        db.run(cur, "rollback")
    (HERE / "WRITING.md").write_text(report(drafts, briefs))
    print(report(drafts, briefs).split("## Every draft")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
