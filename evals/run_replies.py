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
# Only for the original set, which has no per-case list. "Not interested" and "unsubscribe" are never the same: one
# ends this conversation, the other ends all contact.
EQUIVALENT = {frozenset({"interested", "meeting_request"}), frozenset({"interested", "question"})}


def classify(cur, item: dict) -> dict:
    cleaned = replies.clean(item["text"])
    ruled = replies.rules_label(item.get("from", "buyer@example.com"), item.get("subject", "Re: billing"), cleaned)
    if ruled:
        return {"label": ruled[0], "by": "rules", "rules_label": ruled[0], "same_person": True, "instructs_system": False}
    out = llm.run(cur, "classify", {"cleaned": cleaned, "subject": item.get("subject", "Re: billing"),
                                    "language_hint": replies.detect_language(cleaned), "today": "2026-11-11"})
    ref = out.get("referral") or {}
    email_ok = not ref.get("email") or ref["email"].lower() in item["text"].lower()
    return {"label": out["label"], "by": "model", "rules_label": None, "confidence": out["confidence"],
            "same_person": out["same_person"], "instructs_system": out["instructs_system"], "referral": ref,
            "referral_email_in_text": email_ok, "out": out}


def _expect(it: dict) -> dict:
    """The original set keeps side facts at the top level; the independent set keeps them under expect."""
    e = dict(it.get("expect") or {})
    for k in ("same_person", "instructs_system", "return_date", "new_company"):
        if k in it and k not in e:
            e[k] = it[k]
    return e


def main() -> int:
    sys.path.insert(0, str(HERE))
    from judge import rate
    from thresholds import check
    items = []
    for name in ("replies.jsonl", "replies_v2.jsonl"):
        path = HERE / name
        if path.exists():
            items += [{**json.loads(line), "_set": name} for line in path.read_text().splitlines() if line.strip()]
    results = []
    with db.tx() as cur:
        for it in items:
            got = classify(cur, it)  # one model call per case; the full answer comes back with it
            results.append({**it, "got_label": got["label"], "by": got["by"], "rules_label": got["rules_label"],
                            "out": got.get("out") or {},
                            "referral_email_in_text": got.get("referral_email_in_text", True)})
        db.run(cur, "rollback")
    n = len(results)
    ok = lambda r: r["got_label"] == r["label"]  # noqa: E731
    accept = lambda r: ok(r) or r["got_label"] in (_expect(r).get("acceptable") or []) or (  # noqa: E731
        r["_set"] == "replies.jsonl" and frozenset({r["got_label"], r["label"]}) in EQUIVALENT)
    exact, soft = sum(map(ok, results)), sum(map(accept, results))
    rules_only = sum((r["rules_label"] or "other") == r["label"] for r in results)
    # Dangerous confusions, counted on their own: a stop request read as anything else keeps emailing someone who
    # asked us to stop; a positive reply read as negative drops a buyer.
    stop_missed = [r["id"] for r in results if r["label"] == "unsubscribe" and r["got_label"] != "unsubscribe"
                   and "unsubscribe" not in (_expect(r).get("acceptable") or [])]
    hot = {"interested", "meeting_request", "question", "referral"}
    hot_lost = [r["id"] for r in results if r["label"] in hot and r["got_label"] not in hot]
    side = {"same_person": [], "instructs_system": [], "return_date": [], "referral_name": [], "new_company": [], "language": []}
    for r in results:
        e, o = _expect(r), r["out"]
        if r["by"] != "model" or not o:
            continue
        if "same_person" in e:
            side["same_person"].append(o.get("same_person") == e["same_person"])
        if e.get("instructs_system"):
            side["instructs_system"].append(bool(o.get("instructs_system")))
        if e.get("return_date"):
            side["return_date"].append((o.get("return_date") or "")[:10] == str(e["return_date"])[:10])
        if e.get("referral_name"):
            got = ((o.get("referral") or {}).get("name") or "").lower()
            side["referral_name"].append(e["referral_name"].split()[0].lower() in got)
        if e.get("new_company"):
            side["new_company"].append(e["new_company"].split()[0].lower() in (o.get("new_company") or "").lower())
        if e.get("language"):
            side["language"].append((o.get("language") or "")[:2] == e["language"][:2])
    invented_emails = [r["id"] for r in results if r.get("referral_email_in_text") is False]
    by_tag: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        for t in r.get("tags") or ["original set"]:
            by_tag[t].append(accept(r))
    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        confusion[r["label"]][r["got_label"]] += 1
    labels = sorted({r["label"] for r in results} | {r["got_label"] for r in results})
    scores = {"replies_accept": soft / n, "replies_exact": exact / n,
              "replies_stop_respected": 1 - len(stop_missed) / max(1, sum(r["label"] == "unsubscribe" for r in results)),
              "replies_no_invented_email": 1.0 if not invented_emails else 0.0}
    lines = [
        "# Reply classification eval", "",
        f"{n} labelled replies ({sum(r['_set'] == 'replies.jsonl' for r in results)} original, "
        f"{sum(r['_set'] == 'replies_v2.jsonl' for r in results)} written independently of the code), through the real "
        f"pipeline: cleaning, rules, then the model. Answers from {'live calls' if llm.CONFIG.anthropic_live else 'recordings'} "
        f"({llm.TASKS['classify']['model']}, effort {llm.TASKS['classify']['effort']}).", "",
        "| Measure | Result |", "|---|---|",
        f"| Label a careful person would accept | {rate(soft, n)} |",
        f"| Exact label | {rate(exact, n)} |",
        f"| Stop requests read as stop requests | {rate(sum(r['label'] == 'unsubscribe' for r in results) - len(stop_missed), sum(r['label'] == 'unsubscribe' for r in results))} |",
        f"| Positive replies kept positive | {rate(sum(r['label'] in hot for r in results) - len(hot_lost), sum(r['label'] in hot for r in results))} |",
        f"| Rules alone, everything else read as unclear | {rate(rules_only, n)} |",
        f"| Settled by rules, no model call | {sum(r['by'] == 'rules' for r in results)} of {n} |",
        *[f"| Side fact: {k.replace('_', ' ')} right | {rate(sum(v), len(v))} |" for k, v in side.items() if v],
        f"| Referral emails the model invented | {len(invented_emails)}{' (' + ', '.join(invented_emails) + ')' if invented_emails else ''} |", "",
        "## By category", "", "| Category | Accepted |", "|---|---|",
        *[f"| {t} | {rate(sum(v), len(v))} |" for t, v in sorted(by_tag.items(), key=lambda x: sum(x[1]) / len(x[1]))], "",
        "## Misses", "",
    ]
    for r in results:
        if not accept(r):
            lines.append(f"- {r['id']}: expected {r['label']}, got {r['got_label']} ({r['by']}). \"{r['text'][:110].replace(chr(10), ' ')}\"")
    lines += ["", "## Confusion matrix (rows: expected, columns: got)", "",
              "| expected \\ got | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for exp in labels:
        if exp in confusion:
            lines.append(f"| {exp} | " + " | ".join(str(confusion[exp][g] or "") for g in labels) + " |")
    (HERE / "REPLIES.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:20]))
    return check(scores)


if __name__ == "__main__":
    sys.exit(main())
