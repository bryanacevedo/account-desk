"""A React hook called after an early return crashes the whole page when the data arrives ("Rendered more hooks than
during the previous render", the account sheet on 2026-11-17). The web app has no browser test runner, so this reads the
source: in a component, no hook may come after a top-level `if (...) return`."""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web" / "src"
NOT_HOOKS = {"useNowIso"}   # named like a hook, only returns a module variable


def late_hooks(text: str) -> list[tuple[int, str]]:
    out, early = [], False
    for n, line in enumerate(text.split("\n"), 1):
        if re.match(r"^(export )?(default )?function \w+|^(export )?const \w+ = \(.*\) => \{$", line):
            early = False
        if re.match(r"^  if \(.*\) return\b", line):
            early = True
        m = re.match(r"^  (?:const .*= )?(use[A-Z]\w*)[(<]", line)
        if early and m and m.group(1) not in NOT_HOOKS:
            out.append((n, line.strip()))
    return out


def test_no_hook_comes_after_an_early_return():
    bad = {str(f.relative_to(WEB)): late_hooks(f.read_text()) for f in sorted(WEB.rglob("*.tsx"))}
    assert {k: v for k, v in bad.items() if v} == {}


def test_the_check_finds_the_bug_it_was_written_for():
    src = "export function Sheet() {\n  const a = useData(1);\n  if (!a) return null;\n  const [x, setX] = useState(0);\n  return x;\n}\n"
    assert late_hooks(src) == [(4, "const [x, setX] = useState(0);")]
