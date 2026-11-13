"""The truth-visibility check each desk runs in its own tests (DESIGN.md section 4.2, "Visibility").

Only the simulated vendors and the simulator may read a release's `truth/` folder. `violations(repo, allowed)` scans
a desk's source for any mention of the truth folder, as a path (`truth/`) or as a quoted name joined into one
(`"truth"`), and returns the files that mention it but are not in `allowed` (glob patterns relative to the repository).

Every slice carries a copy of this file (`guard.py`) and a JavaScript twin (`guard.mjs`), so a desk calls the copy in
its own vendored slice and never needs this repository, the network or Python to check itself (DESIGN.md 2a). It is a
text check: a path assembled from variables gets past it, which is why the allowed list stays short and the desks'
reviews read the simulator modules.

    python guard.py REPO "src/app/sim_*.py" ...   exits 1 and lists the files when any are found
"""
from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

SOURCE = (".py", ".ts", ".tsx", ".js", ".mjs", ".sql")
SKIP = ("node_modules", ".venv", ".git", "dist", "build", "__pycache__", "tests", "samples", "world")
MENTION = re.compile(r"""truth/|["']truth["']""")


def violations(repo: str | Path, allowed: list[str]) -> list[str]:
    repo = Path(repo)
    bad = []
    for p in sorted(repo.rglob("*")):
        if not p.is_file() or p.suffix not in SOURCE:
            continue
        rel = p.relative_to(repo).as_posix()
        if any(part in SKIP or part.startswith(".") for part in p.relative_to(repo).parts[:-1]):  # hidden: worktrees, tools
            continue
        if not MENTION.search(p.read_text(encoding="utf-8", errors="ignore")):
            continue
        if not any(fnmatch.fnmatch(rel, a) for a in allowed):
            bad.append(rel)
    return bad


if __name__ == "__main__":
    found = violations(sys.argv[1], sys.argv[2:])
    print("\n".join(found) or "No module outside the allowed list reads the truth.")
    sys.exit(1 if found else 0)
