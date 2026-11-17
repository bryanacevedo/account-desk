"""The docs gate (scripts/docs_check.py): passes on this repository, and each check fails on a fixture that drifted."""
from __future__ import annotations

import importlib.util
import subprocess
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("docs_check", ROOT / "scripts" / "docs_check.py")
docs_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(docs_check)


def _fixture(tmp_path: Path, **over: str) -> Path:
    """A tiny repository whose docs are true; `over` replaces a file's text."""
    files = {
        "README.md": "# X\n\nMigrations (0001 to 0002). Set `FOO_KEY`.\n",
        "PROJECT-STATUS.md": "**Updated:** 2026-11-16. **Decisions:** `docs/DECISIONS.md`, 1 to 2.\n",
        "docs/DECISIONS.md": "1. **One.** Text.\n\n2. **Two.** Text.\n",
        "migrations/0001_a.sql": "select 1;\n",
        "migrations/0002_b.sql": "select 2;\n",
        "src/app.py": 'import os\nKEY = os.environ.get("FOO_KEY")\n',
    }
    files.update(over)
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_this_repository_passes():
    assert docs_check.check(ROOT) == []


def test_fixture_passes(tmp_path):
    assert docs_check.check(_fixture(tmp_path)) == []


def test_test_count_claim_fails(tmp_path):
    root = _fixture(tmp_path, **{"README.md": "Migrations (0001 to 0002). `FOO_KEY`. 325 passed on Postgres.\n"})
    assert any("test-count claim" in p for p in docs_check.check(root))
    root = _fixture(tmp_path, **{"README.md": "![tests](https://img.shields.io/badge/tests-325-blue) Migrations (0001 to 0002) `FOO_KEY`\n"})
    assert any("test-count claim" in p for p in docs_check.check(root))


def test_migration_range_fails(tmp_path):
    root = _fixture(tmp_path, **{"README.md": "Migrations (0001 to 0001). `FOO_KEY`.\n"})
    assert any("ends at 0001" in p for p in docs_check.check(root))
    root = _fixture(tmp_path, **{"README.md": "No range here. `FOO_KEY`.\n"})
    assert any("no 'migrations" in p for p in docs_check.check(root))


def test_env_variable_missing_fails_and_allowlist_passes(tmp_path):
    root = _fixture(tmp_path, **{"src/app.py": 'import os\nA = os.environ.get("FOO_KEY")\nB = os.getenv("NEW_VAR")\nC = _flag("FLAG_X")\n'})
    problems = docs_check.check(root)
    assert any(p.startswith("NEW_VAR") for p in problems) and any(p.startswith("FLAG_X") for p in problems)
    assert not any(p.startswith("FOO_KEY") for p in problems)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "DOCS-CHECK-ALLOW.txt").write_text("NEW_VAR: set by the host\nFLAG_X: set by the host\n")
    assert docs_check.check(root) == []


def test_decision_count_fails(tmp_path):
    root = _fixture(tmp_path, **{"PROJECT-STATUS.md": "**Updated:** 2026-11-16. **Decisions:** `docs/DECISIONS.md`, 1 to 1.\n"})
    assert any("1 to 1" in p and "ends at 2" in p for p in docs_check.check(root))


def test_stale_updated_date_fails_and_skips_without_history(tmp_path):
    root = _fixture(tmp_path)
    assert docs_check.check(root) == []  # not a git repository: skipped
    git = lambda *a: subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "code")
    today = date.today()
    status = root / "PROJECT-STATUS.md"
    status.write_text(f"**Updated:** {today - timedelta(days=3)}. **Decisions:** `docs/DECISIONS.md`, 1 to 2.\n")
    assert any("code last changed" in p for p in docs_check.check(root))
    status.write_text(f"**Updated:** {today - timedelta(days=1)}. **Decisions:** `docs/DECISIONS.md`, 1 to 2.\n")
    assert docs_check.check(root) == []
