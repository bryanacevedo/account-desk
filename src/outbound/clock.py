"""One clock for the whole app. In demo mode it is the simulated clock stored in the database."""
from __future__ import annotations

from datetime import datetime, timedelta

from . import db


def now(cur=None) -> datetime:
    if cur is not None:
        return db.val(cur, "select app_now()")
    with db.tx() as c:
        return db.val(c, "select app_now()")


def set_sim(at: datetime) -> None:
    with db.tx() as cur:
        db.run(cur, "update sim_clock set enabled = true, at = %s", at)


def advance(cur, delta: timedelta) -> datetime:
    return db.val(cur, "update sim_clock set at = at + %s where enabled returning at", delta)


def sim_enabled(cur) -> bool:
    return bool(db.val(cur, "select enabled from sim_clock"))
