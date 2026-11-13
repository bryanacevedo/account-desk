"""The built demo shows every scenario the app can show: every play state, reply label, signal type, autonomy stage,
region outcome, committee gap, task kind and deal outcome, except those coverage.BY_CHANCE names. It reads the demo exactly as `python -m outbound demo`
builds it (the `built_demo` fixture, shared with the other whole-demo test). A scenario at zero fails here; the fix
belongs in the simulation, never in the data."""
from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from outbound import coverage


def test_the_demo_shows_every_scenario(built_demo):
    with psycopg.connect(built_demo, row_factory=dict_row) as conn, conn.cursor() as cur:
        rows = coverage.scenarios(cur)
    zero = [f"{r['group']}: {r['scenario']}" for r in coverage.missing(rows)]
    assert zero == [], "\n" + coverage.table(rows)


def test_the_image_build_fails_on_a_missing_scenario():
    """The hosted demo is built once, into the image: coverage runs right after the simulation, so a build that cannot
    show every scenario stops there instead of going live (and `set -e` makes its exit code stop the build)."""
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "scripts" / "docker-build-demo.sh").read_text()
    assert "set -e" in script
    assert script.index("-m outbound demo") < script.index("-m outbound coverage") < script.index("pg_ctl -D /data -m fast")
