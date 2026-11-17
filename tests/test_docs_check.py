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


def test_more_test_count_spellings_fail(tmp_path):
    for claim in ("badge/tests-325%20passing", "badge/325%20tests", "passed: 325", "Tests: 325", "325 pass", "325%20passing"):
        root = _fixture(tmp_path, **{"README.md": f"Migrations (0001 to 0002). `FOO_KEY`. {claim}\n"})
        assert any("test-count claim" in p for p in docs_check.check(root)), claim
    root = _fixture(tmp_path, **{"README.md": "Migrations (0001 to 0002). `FOO_KEY`. 11 of 15 pass every check.\n"})
    assert docs_check.check(root) == []


def test_other_migration_range_spellings_fail(tmp_path):
    for text in ("migrations 0001-0001", "migrations (0001 through 0001)"):
        root = _fixture(tmp_path, **{"README.md": f"{text} `FOO_KEY`\n"})
        assert any("ends at 0001" in p for p in docs_check.check(root)), text


def test_missing_migrations_folder_fails(tmp_path):
    root = _fixture(tmp_path)
    for f in (root / "migrations").glob("*.sql"):
        f.unlink()
    assert any("no migration files" in p for p in docs_check.check(root))


def test_env_in_shell_tuple_loop_and_dockerfile_fail(tmp_path):
    root = _fixture(tmp_path, **{
        "scripts/run.sh": 'PORT="${SHELL_VAR:-1}"\n',
        "src/guard.py": 'import os\nany(os.environ.get(v) for v in ("LOOP_VAR", "LOOP_TWO"))\n',
        "Dockerfile": "FROM x\nENV DOCKER_VAR=1 \\\n    DOCKER_TWO=2\n",
    })
    names = {p.split(":")[0] for p in docs_check.check(root)}
    assert {"SHELL_VAR", "LOOP_VAR", "LOOP_TWO", "DOCKER_VAR", "DOCKER_TWO"} <= names


def test_future_updated_date_fails(tmp_path):
    future = date.today() + timedelta(days=10)
    root = _fixture(tmp_path, **{"PROJECT-STATUS.md": f"**Updated:** {future}. **Decisions:** `docs/DECISIONS.md`, 1 to 2.\n"})
    assert any("in the future" in p for p in docs_check.check(root))


def test_duplicate_or_missing_decision_numbers_fail(tmp_path):
    root = _fixture(tmp_path, **{"docs/DECISIONS.md": "1. **One.** x\n\n2. **Two.** x\n\n2. **Again.** x\n"})
    assert any("duplicate or a gap" in p for p in docs_check.check(root))
    root = _fixture(tmp_path, **{"docs/DECISIONS.md": "1. **One.** x\n\n3. **Three.** x\n"})
    assert any("duplicate or a gap" in p for p in docs_check.check(root))
