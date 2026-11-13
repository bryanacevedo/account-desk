"""Signal source adapters. In the demo each source returns the simulated signals that have 'arrived' by now,
so sources have real latency and cadence. Live sources (job boards, funding feeds, intent providers) plug in here
behind env keys; the webhook source is pushed to through the API instead."""
from __future__ import annotations

from datetime import datetime

from .. import db
from ..config import CONFIG


def fetch(cur, source: str) -> list[dict]:
    if CONFIG.mode == "live":
        from . import live
        return live.fetch_source(cur, source)
    rows = db.all(cur, """select id, payload from sim_events where kind = 'signal' and not done and at <= app_now()
                          and payload->>'source' = %s order by at, id for update skip locked""", source)
    out = []
    for r in rows:
        raw = dict(r["payload"]["raw"])
        raw["observed_at"] = datetime.fromisoformat(raw["observed_at"])
        out.append(raw)
    if rows:
        db.run(cur, "update sim_events set done = true where id = any(%s)", [r["id"] for r in rows])
    return out
