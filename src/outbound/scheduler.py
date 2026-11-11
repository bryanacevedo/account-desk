"""Periodic work. Each tick enqueues what is due, with a dedupe key so a double tick enqueues once."""
from __future__ import annotations

from datetime import timedelta

from . import db, jobs
from .db import J

PERIODIC = {  # kind: minutes
    "send_due": 10, "due_steps": 15, "expire_proposals": 60, "close_stale_plays": 360, "rescore_all": 1440,
    "sla_check": 30, "crm_push": 10, "mailbox_health": 360, "telemetry": 1440, "monitors": 360, "crm_sync": 360,
    "watch_reset": 1440, "sweep_sending": 15, "autonomy_watch": 360, "placement_tests": 10080, "dns_check": 1440,
}


def tick(cur) -> int:
    jobs.reap(cur)
    # Guarantee 21: the monitors run every 6 hours. If none ran in 12, the tick itself says so.
    last = db.val(cur, "select max(at) from monitor_runs")
    if last is not None and db.val(cur, "select %s < app_now() - interval '12 hours'", last):
        from . import alerts
        alerts.raise_alert(cur, kind="monitors_stale", severity="urgent", channel="#outbound-ops",
                           title="The checks have not run for 12 hours",
                           body="Nothing is watching sends, caps or replies. Check the worker.",
                           dedup_key=f"monitors_stale:{db.val(cur, "select to_char(app_now(), 'YYYY-MM-DD')")}")
    now = db.val(cur, "select app_now()")
    queued = 0
    state = {r["key"]: r["value"] for r in db.all(cur, "select key, value from settings where key like 'sched:%%'")}
    due = dict(PERIODIC)
    for s in db.all(cur, "select key, cadence_minutes from signal_sources where enabled and adapter <> 'webhook'"):
        due["ingest:" + s["key"]] = s["cadence_minutes"]
    for kind, minutes in due.items():
        last = state.get("sched:" + kind)
        if last is not None and db.val(cur, "select %s::timestamptz + %s > app_now()", last, timedelta(minutes=minutes)):
            continue
        if kind.startswith("ingest:"):
            jobs.enqueue(cur, "ingest_source", {"source": kind.split(":", 1)[1]}, dedupe_key="periodic:" + kind)
        else:
            jobs.enqueue(cur, kind, {}, dedupe_key="periodic:" + kind)
        db.run(cur, "insert into settings (key, value) values (%s, %s) on conflict (key) do update set value = excluded.value",
               "sched:" + kind, J(now.isoformat()))
        queued += 1
    return queued


@jobs.handler("ingest_source")
def ingest_source(cur, payload: dict) -> None:
    from . import signals
    from .adapters import sources
    raws = sources.fetch(cur, payload["source"])
    signals.ingest(cur, payload["source"], raws)


@jobs.handler("watch_reset")
def watch_reset(cur, payload: dict) -> None:
    """Nothing to reset: watched batches stay paused until GTM resumes them. Kept as a heartbeat."""
    return None
