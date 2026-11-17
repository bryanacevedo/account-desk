"""The docs gate: fails when the README, PROJECT-STATUS and docs drift from the code. Run by `make docs-check` and by
tests/test_docs_check.py. Standard library only, and fast (no database, no suite run).

`check(root)` returns a list of problems, empty when the docs are true. Checks:
  1. The README carries no test-count claim ("325 passed", a "tests-325" badge). A count that is not derived from the
     collected suite goes stale, so none is kept.
  2. Every "migrations (0001 to NNNN)" range (also "0001-NNNN", "0001 through NNNN") in the README and docs (not the decision log, which is history) ends at the
     highest file in migrations/, and the README states a range at all.
  3. Every environment variable the code reads (src, evals, scripts, tests; os.environ, getenv, _flag, tuple loops,
     shell ${VAR}, Dockerfile ENV) appears in the README or .env.example, or is
     listed with a reason in docs/DOCS-CHECK-ALLOW.txt.
  4. The highest decision number in docs/DECISIONS.md equals "1 to N" in PROJECT-STATUS.
  5. PROJECT-STATUS "Updated" is not in the future, and no more than one day older than the last commit that touched code. Skipped when there is
     no git history to read (no git, no repository, a shallow clone)."""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

CODE_PATHS = ["src", "migrations", "tests", "scripts", "evals", "web/src", "world", "Makefile", "Dockerfile", "render.yaml",
              "pyproject.toml"]
SCAN_DIRS = ["src", "evals", "scripts", "tests"]
SCAN_FILES = ["Dockerfile"]
ENV_READ = re.compile(
    r"""(?:environ(?:\.get)?\s*[\(\[]|getenv\s*\(|_flag\s*\()\s*["']([A-Z][A-Z0-9_]*)["']""")
SHELL_VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)[:}\-=]")
TUPLE_LOOP = re.compile(r"environ[^\n]*\bfor\s+\w+\s+in\s+\(([^)]*)\)")
DOCKER_ENV = re.compile(r"^ENV\s+((?:[^\n]*\\\n)*[^\n]*)", re.MULTILINE)
TEST_CLAIM = re.compile(
    r"\b\d[\d,]*(?:\s|%20)+(?:tests?|passed|passing)\b|\b\d[\d,]*\s+pass\b(?!\s+(?:every|the|all)\b)"
    r"|\btests?-\d|badge/\d[\d,]*(?:%20|-)tests|\b(?:passed|tests?):\s*\d", re.IGNORECASE)
MIGRATION_RANGE = re.compile(r"migrations?\s*\(?\s*0001\s*(?:to|-|\u2013|through)\s*(\d{4})", re.IGNORECASE)
ALLOW_FILE = "docs/DOCS-CHECK-ALLOW.txt"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _test_claims(root: Path) -> list[str]:
    return [f"README.md: test-count claim {m.group(0)!r}; keep no number (it goes stale), or derive it from the collected suite"
            for m in TEST_CLAIM.finditer(_read(root / "README.md"))]


def _migrations(root: Path) -> list[str]:
    files = sorted(p.name for p in (root / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        return ["migrations/: no migration files found"]
    last = int(files[-1][:4])
    out = []
    docs = [root / "README.md", root / "PROJECT-STATUS.md", *sorted((root / "docs").glob("*.md"))]
    docs = [p for p in docs if p.name != "DECISIONS.md"]
    readme_ranges = MIGRATION_RANGE.findall(_read(root / "README.md"))
    if not readme_ranges:
        out.append("README.md: no 'migrations (0001 to NNNN)' range")
    for p in docs:
        for end in MIGRATION_RANGE.findall(_read(p)):
            if int(end) != last:
                out.append(f"{p.relative_to(root)}: migrations range ends at {end}, the folder ends at {last:04d}")
    return out


def env_vars(root: Path) -> set[str]:
    found: set[str] = set()
    for d in SCAN_DIRS:
        for p in (root / d).rglob("*"):
            if p.suffix in (".py", ".mjs", ".js", ".sh") and p.is_file() and "node_modules" not in p.parts \
                    and p.name not in ("docs_check.py", "test_docs_check.py"):
                text = _read(p)
                found.update(ENV_READ.findall(text))
                for group in TUPLE_LOOP.findall(text):
                    found.update(re.findall(r"""["']([A-Z][A-Z0-9_]*)["']""", group))
                if p.suffix == ".sh":
                    found.update(SHELL_VAR.findall(text))
    for name in SCAN_FILES:
        for block in DOCKER_ENV.findall(_read(root / name)):
            found.update(re.findall(r"(?:^|\s)([A-Z][A-Z0-9_]*)=", block.replace("\\\n", " ")))
    return found


def _allowed(root: Path) -> set[str]:
    names = set()
    for line in _read(root / ALLOW_FILE).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line.split(":", 1)[0].strip())
    return names


def _env(root: Path) -> list[str]:
    documented = _read(root / "README.md") + "\n" + _read(root / ".env.example")
    allowed = _allowed(root)
    return [f"{name}: read by the code, missing from README.md and .env.example (add it, or list it with a reason in {ALLOW_FILE})"
            for name in sorted(env_vars(root))
            if name not in allowed and not re.search(rf"(?<![A-Z0-9_]){name}(?![A-Z0-9_])", documented)]


def _decisions(root: Path) -> list[str]:
    nums = [int(m) for m in re.findall(r"^(\d+)\. \*\*", _read(root / "docs" / "DECISIONS.md"), re.MULTILINE)]
    if not nums:
        return ["docs/DECISIONS.md: no decisions found"]
    if sorted(nums) != list(range(1, max(nums) + 1)):
        return ["docs/DECISIONS.md: decision numbers are not exactly 1 to N (a duplicate or a gap)"]
    m = re.search(r"\*\*Decisions:\*\*[^\n]*?\b1 to (\d+)", _read(root / "PROJECT-STATUS.md"))
    if not m:
        return ["PROJECT-STATUS.md: no 'Decisions: ... 1 to N' count"]
    if int(m.group(1)) != max(nums):
        return [f"PROJECT-STATUS.md: says decisions 1 to {m.group(1)}, docs/DECISIONS.md ends at {max(nums)}"]
    return []


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _updated(root: Path) -> list[str]:
    m = re.search(r"\*\*Updated:\*\*\s*(\d{4}-\d{2}-\d{2})", _read(root / "PROJECT-STATUS.md"))
    if not m:
        return ["PROJECT-STATUS.md: no 'Updated: YYYY-MM-DD' date"]
    if date.fromisoformat(m.group(1)) > date.today() + timedelta(days=1):
        return [f"PROJECT-STATUS.md: Updated {m.group(1)} is in the future"]
    if _git(root, "rev-parse", "--is-shallow-repository") != "false":
        return []  # no git, not a repository or a shallow clone: no history to compare with
    paths = [p for p in CODE_PATHS if (root / p).exists()]
    last = _git(root, "log", "-1", "--format=%cs", "--", *paths)
    if not last:
        return []
    updated, code = date.fromisoformat(m.group(1)), date.fromisoformat(last)
    if updated < code - timedelta(days=1):
        return [f"PROJECT-STATUS.md: Updated {updated}, but code last changed {code}"]
    return []


def check(root: Path | str) -> list[str]:
    root = Path(root)
    return [*_test_claims(root), *_migrations(root), *_env(root), *_decisions(root), *_updated(root)]


if __name__ == "__main__":
    problems = check(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
    for line in problems:
        print(line)
    print("docs-check: " + (f"{len(problems)} problem(s)" if problems else "ok"))
    sys.exit(1 if problems else 0)
