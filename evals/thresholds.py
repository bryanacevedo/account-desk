"""The floors the weekly live run holds the AI to. A score below its floor fails the run, so a drop is loud.

Floors are set from the first live baseline, a few points under it, so normal noise does not fail the run but a real
regression does. They live in thresholds.json; change them there, with a reason in the commit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parent / "thresholds.json"


def check(scores: dict[str, float]) -> int:
    floors = json.loads(PATH.read_text()) if PATH.exists() else {}
    failed = [f"{k} {v:.2f} is below its floor {floors[k]:.2f}" for k, v in scores.items() if k in floors and v < floors[k]]
    for line in failed:
        print("BELOW FLOOR:", line, file=sys.stderr)
    return 1 if failed else 0
