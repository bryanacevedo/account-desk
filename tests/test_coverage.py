"""The built demo shows every scenario the app can show: every play state, reply label, signal type, autonomy stage,
region outcome, committee gap, task kind and deal outcome. It reads the demo exactly as `python -m outbound demo`
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
