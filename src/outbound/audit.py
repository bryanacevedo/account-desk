from __future__ import annotations

from . import db
from .db import J


def log(cur, actor: str, action: str, object_kind: str, object_id: int | None, detail: dict | None = None,
        actor_id: int | None = None) -> None:
    db.run(cur, "insert into audit_log (actor_id, actor, action, object_kind, object_id, detail) "
                "values (%s, %s, %s, %s, %s, %s)", actor_id, actor, action, object_kind, object_id, J(detail or {}))
