"""Alerts are rows first and Slack messages second, so an alert survives a dead Slack and the health check can see it."""
from __future__ import annotations

from . import db


def raise_alert(cur, *, kind: str, severity: str, channel: str, title: str, body: str,
                target_user: int | None = None, object_kind: str | None = None, object_id: int | None = None,
                dedup_key: str | None = None) -> int | None:
    row = db.one(cur, """
        insert into alerts (kind, severity, channel, target_user, object_kind, object_id, title, body, dedup_key)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (dedup_key) do nothing returning id""",
        kind, severity, channel, target_user, object_kind, object_id, title, body, dedup_key)
    if row:
        from . import jobs
        jobs.enqueue(cur, "deliver_alert", {"alert_id": row["id"]})
    return row["id"] if row else None
