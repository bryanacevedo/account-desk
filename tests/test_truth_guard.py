"""Only the simulator and the simulated vendors may read the shared world's `truth/` folder (shared-world DESIGN.md 4.2,
"Visibility"). The check is the release's own guard.py, vendored under world/ with the slice, so it needs nothing outside
this repository."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The modules that may mention the folder: the loader that reads it, and the world generator that has always kept a
# "truth" column of its own (what a verifier would find). A module that reads the slice for a new reason is added here
# on purpose, in the same change.
ALLOWED = ["src/outbound/sim/world.py", "src/outbound/sim/world_load.py"]


def _guard():
    spec = importlib.util.spec_from_file_location("world_guard", ROOT / "world" / "guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_module_outside_the_allowed_list_mentions_the_truth_folder():
    assert _guard().violations(ROOT, ALLOWED) == []


def test_the_allowed_list_is_no_longer_than_it_needs_to_be():
    """Every module on the list does mention the folder; a name that stopped needing the exemption comes off."""
    mentions = set(_guard().violations(ROOT, []))
    assert mentions == set(ALLOWED), sorted(mentions ^ set(ALLOWED))


def test_the_guard_does_catch_a_new_reader(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "reader.py").write_text('PATH = "world/truth/people.csv"\n', encoding="utf-8")
    (tmp_path / "src" / "clean.py").write_text("X = 1\n", encoding="utf-8")
    assert _guard().violations(tmp_path, []) == ["src/reader.py"]
