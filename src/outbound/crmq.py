"""The one way a CRM write is queued: a row in `crm_outbox`, with the traceparent of the span that queued it (NULL when
tracing is off or nothing traced it), so the call that later delivers it can be linked to the action that caused it
(decision 107)."""
from __future__ import annotations

from . import db, telemetry
from .db import J


def enqueue(cur, kind: str, payload: dict, idempotency_key: str, *, done: str | None = None) -> bool:
    """Queue one CRM write. A second row with the same idempotency key is ignored. `done` writes the row as finished with
    that reference (a contact the adapter already wrote). Returns whether a row was added."""
    if done is not None:
        row = db.one(cur, """insert into crm_outbox (kind, payload, idempotency_key, status, done_at, trace_parent)
                             values (%s, %s, %s, 'done', app_now(), %s) on conflict do nothing returning id""",
                     kind, J({**payload, "crm_ref": done}), idempotency_key, telemetry.current_traceparent())
    else:
        row = db.one(cur, """insert into crm_outbox (kind, payload, idempotency_key, trace_parent)
                             values (%s, %s, %s, %s) on conflict do nothing returning id""",
                     kind, J(payload), idempotency_key, telemetry.current_traceparent())
    return row is not None
