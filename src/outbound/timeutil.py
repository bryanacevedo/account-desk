"""Business time: send windows in the recipient's timezone, weekends and public holidays."""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import db

UTC = ZoneInfo("UTC")


def tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "America/New_York")
    except Exception:
        return ZoneInfo("America/New_York")


_holiday_cache: dict[str, set[date]] = {}


def load_holidays(cur) -> None:
    _holiday_cache.clear()
    for r in db.all(cur, "select country, day from holidays"):
        _holiday_cache.setdefault(r["country"], set()).add(r["day"])


def is_business_day(d: date, country: str | None) -> bool:
    return d.weekday() < 5 and d not in _holiday_cache.get(country or "", set())


def windows(setting: list[list[str]]) -> list[tuple[time, time]]:
    return [(time.fromisoformat(a), time.fromisoformat(b)) for a, b in setting]


def next_slot(after: datetime, *, timezone: str | None, country: str | None, window: list[tuple[time, time]],
              jitter_key: str | None = None, max_days: int = 30) -> datetime:
    """The first moment at or after `after` that is inside a send window on a business day for the recipient.

    A deterministic jitter (from jitter_key) of up to 25 minutes spreads sends so they do not land on the minute.
    """
    zone = tz(timezone)
    local = after.astimezone(zone)
    jitter = timedelta(minutes=(random.Random(jitter_key).randint(0, 25) if jitter_key else 0))
    for day_offset in range(max_days):
        d = (local + timedelta(days=day_offset)).date()
        if not is_business_day(d, country):
            continue
        for start, end in window:
            begin = datetime.combine(d, start, zone)
            finish = datetime.combine(d, end, zone)
            candidate = max(begin, local) + (jitter if local <= begin else timedelta(0))
            if candidate < finish:
                return candidate.astimezone(UTC)
    return (local + timedelta(days=max_days)).astimezone(UTC)


def in_window(at: datetime, *, timezone: str | None, country: str | None, window: list[tuple[time, time]]) -> bool:
    local = at.astimezone(tz(timezone))
    if not is_business_day(local.date(), country):
        return False
    return any(s <= local.time() < e for s, e in window)


def add_business_days(start: datetime, days: int, *, country: str | None = None, timezone: str | None = None) -> datetime:
    zone = tz(timezone)
    local = start.astimezone(zone)
    added = 0
    while added < days:
        local += timedelta(days=1)
        if is_business_day(local.date(), country):
            added += 1
    return local.astimezone(UTC)


def add_business_hours(start: datetime, hours: float, *, timezone: str | None, country: str | None = None,
                       open_at: time = time(9), close_at: time = time(18)) -> datetime:
    """Business hours in someone's own timezone (used for reply SLAs)."""
    zone = tz(timezone)
    t = start.astimezone(zone)
    remaining = timedelta(hours=hours)
    for _ in range(60):
        if not is_business_day(t.date(), country) or t.time() >= close_at:
            t = datetime.combine(t.date() + timedelta(days=1), open_at, zone)
            continue
        if t.time() < open_at:
            t = datetime.combine(t.date(), open_at, zone)
        end_of_day = datetime.combine(t.date(), close_at, zone)
        if t + remaining <= end_of_day:
            return (t + remaining).astimezone(UTC)
        remaining -= end_of_day - t
        t = datetime.combine(t.date() + timedelta(days=1), open_at, zone)
    return t.astimezone(UTC)


def business_days_between(a: datetime, b: datetime, country: str | None = None) -> int:
    if b <= a:
        return 0
    n, d = 0, a.date()
    while d < b.date():
        d += timedelta(days=1)
        if is_business_day(d, country):
            n += 1
    return n

