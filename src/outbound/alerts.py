"""Alerts are rows first and Slack messages second, so an alert survives a dead Slack and the health check can see it.

An alert is open until a person acks it or the code that ends its condition resolves it (SPEC 23.2, decision 86). The
Inboxes and Health tabs read the open ones, grouped by condition, so a daily dedup key that raised a row every day
shows once."""
from __future__ import annotations

from . import db

# Which tab an alert belongs on. Mailbox and domain kinds are Inboxes; everything else is Health, and so is any kind
# not listed here (an alert is never hidden for lack of a scope). A test reads every raise_alert kind in the source and
# fails on one missing from this table.
KIND_SCOPE: dict[str, str] = {
    "complaint": "inboxes", "mailbox_paused": "inboxes", "mailbox_warn": "inboxes", "placement_hold": "inboxes",
    "placement_pause": "inboxes", "spam_rate": "inboxes", "spam_rate_warn": "inboxes", "dns_broken": "inboxes",
    "dns_fixed": "inboxes", "no_mailbox": "inboxes", "reply_drop": "inboxes", "watch_paused": "inboxes",
    "send_unknown": "inboxes",
    "hot_reply": "health", "early_reply": "health", "sla_missed": "health", "monitor": "health",
    "monitors_stale": "health", "theme_failed": "health", "suggestion_dropped": "health", "budget": "health",
    "budget_wait": "health", "play_budget": "health", "job_dead": "health", "crm_dead": "health",
    "crm_check_waiting": "health", "owner_not_on_desk": "health", "owner_changed": "health",
    "research_failed": "health", "demoted": "health",
}

# A condition that lasts until something ends it: the code that ends it resolves the alert, so it needs no age cutoff.
# Every other warn or info alert is an event, and drops from the open view after EVENT_DAYS if nobody acked it.
# Urgent alerts never age out.
STATE_KINDS = ("mailbox_paused", "mailbox_warn", "placement_hold", "placement_pause", "spam_rate", "spam_rate_warn",
               "dns_broken", "no_mailbox", "sla_missed", "hot_reply", "watch_paused", "send_unknown")
EVENT_DAYS = 14

SEVERITY_ORDER = {"urgent": 0, "warn": 1, "info": 2}

OPEN = f"""a.acked_at is null and a.resolved_at is null and (a.severity = 'urgent' or a.kind = any(%s)
           or a.at > app_now() - interval '{EVENT_DAYS} days')"""


def scope_of(kind: str) -> str:
    return KIND_SCOPE.get(kind, "health")


def raise_alert(cur, *, kind: str, severity: str, channel: str, title: str, body: str,
                target_user: int | None = None, object_kind: str | None = None, object_id: int | None = None,
                object_key: str | None = None, dedup_key: str | None = None) -> int | None:
    row = db.one(cur, """
        insert into alerts (kind, severity, channel, target_user, object_kind, object_id, object_key, title, body,
                            dedup_key, scope)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (dedup_key) do update set resolved_at = null where alerts.resolved_at is not null
        returning id, (xmax = 0) as fresh""",
        kind, severity, channel, target_user, object_kind, object_id, object_key, title, body, dedup_key, scope_of(kind))
    # A condition that came back the day it was resolved opens its row again, without a second Slack post.
    if row and row["fresh"]:
        from . import jobs
        jobs.enqueue(cur, "deliver_alert", {"alert_id": row["id"]})
        return row["id"]
    return None


def resolve(cur, kinds: list[str] | tuple[str, ...], *, object_kind: str | None = None, object_id: int | None = None,
            object_key: str | None = None, target_user: int | None = None) -> int:
    """The condition behind these alerts has ended: close every open row of those kinds about that object, whatever
    day raised it. Rows are kept for the audit trail and drawn nowhere."""
    return db.run(cur, """
        update alerts set resolved_at = app_now()
        where resolved_at is null and kind = any(%s)
          and (%s::text is null or object_kind = %s) and (%s::bigint is null or object_id = %s)
          and (%s::text is null or object_key = %s) and (%s::bigint is null or target_user = %s)""",
        list(kinds), object_kind, object_kind, object_id, object_id, object_key, object_key, target_user, target_user)


def ack(cur, alert_id: int) -> int | None:
    """A person has seen it. Every open row of the same condition closes with it. Returns how many rows closed, or
    None when there is no such alert."""
    a = db.one(cur, "select gkey from alerts where id = %s", alert_id)
    if a is None:
        return None
    return db.run(cur, "update alerts set acked_at = app_now() where gkey = %s and acked_at is null and resolved_at is null",
                  a["gkey"]) or 0


def open_view(cur, scope: str) -> dict:
    """The open alerts for one tab ('inboxes' or 'health'; an alert scoped 'both' shows on each), one row per
    condition (the newest row of it, with how many rows it has), ordered urgent, warn, info, then newest."""
    rows = db.all(cur, f"""
        select * from (
          select distinct on (a.gkey) a.id, a.at, a.kind, a.severity, a.title, a.body, a.object_kind, a.object_id,
                 a.object_key, a.scope as area, a.channel, a.delivered_at, a.delivery_error,
                 count(*) over (partition by a.gkey) as repeats
          from alerts a where a.scope in (%s, 'both') and {OPEN}
          order by a.gkey, a.at desc, a.id desc) g""", scope, list(STATE_KINDS))
    rows.sort(key=lambda r: (SEVERITY_ORDER[r["severity"]], -r["at"].timestamp(), -r["id"]))
    counts = {s: sum(1 for r in rows if r["severity"] == s) for s in SEVERITY_ORDER}
    return {"alerts": rows, "counts": counts}
