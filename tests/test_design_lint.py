"""The design-lint gate: banned UI patterns ("the AI tells") fail the suite.
Rules and rulings: BRYAN-DESIGN-INSTRUMENT.md, "Banned: the AI tells". Existing violations are listed in
docs/DESIGN-LINT-BASELINE.txt for Bryan to review; only violations not in that file fail here."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MESSAGE = (
    "Banned UI pattern (see BRYAN-DESIGN-INSTRUMENT.md, Banned: the AI tells). "
    "Fix it, or add `design-lint: allow <reason>` if Bryan approved it."
)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_no_new_banned_ui_pattern():
    run = subprocess.run(["node", str(ROOT / "scripts" / "design-lint.mjs")], capture_output=True, text=True, cwd=ROOT)
    assert run.returncode == 0, f"{MESSAGE}\n{run.stdout}{run.stderr}"
