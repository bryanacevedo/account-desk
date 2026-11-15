"""The event behind a campaign, read from Events Desk (decision 94). Only for a desk that runs beside Events Desk
(INTEGRATED_WITH names it) and has EVENTS_DESK_URL and EVENTS_DESK_READ_KEY. Never raises and never invents: with no
settings, a call that fails, a refusal or an event with no link, the answer carries no booking link, and the drafts say
that a reply will find a time.

  GET <EVENTS_DESK_URL>/api/desk/campaigns/<campaign ref>   Authorization: Bearer <EVENTS_DESK_READ_KEY>
  200 {"event": "AWS re:Invent 2026", "starts_on": "2026-11-30", "ends_on": "2026-12-04", "city": "Las Vegas",
       "booking_url": "https://..." | null}

One call per campaign per day, cached in `settings` (a failed call is cached for the day too, so a down Events Desk is not
asked again on every sweep). Run it before the ingest transaction opens: a slow network never holds a database lock.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date
from urllib.parse import quote

import httpx

from . import db
from .db import J

log = logging.getLogger("outbound.event_link")
TIMEOUT = 8.0
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def configured() -> bool:
    return bool(os.environ.get("EVENTS_DESK_URL", "").strip() and os.environ.get("EVENTS_DESK_READ_KEY", "").strip())


def _clean(j: dict) -> dict:
    """What is kept from the answer: short text, dates as dates, and a link only when it is an http or https address."""
    from .signals import http_url

    def text(v, n):
        return v.strip()[:n] if isinstance(v, str) and v.strip() else None

    def day(v):
        return v if isinstance(v, str) and _DATE.match(v) else None
    return {"name": text(j.get("event"), 200), "starts_on": day(j.get("starts_on")), "ends_on": day(j.get("ends_on")),
            "city": text(j.get("city"), 100), "booking_url": http_url(text(j.get("booking_url"), 500))}


def _read(ref: str) -> dict | None:
    base, key = os.environ.get("EVENTS_DESK_URL", "").strip().rstrip("/"), os.environ.get("EVENTS_DESK_READ_KEY", "").strip()
    try:
        r = httpx.get(f"{base}/api/desk/campaigns/{quote(ref, safe='')}", timeout=TIMEOUT,
                      headers={"authorization": f"Bearer {key}"})
        if r.status_code != 200:
            log.warning("Events Desk answered %s for a campaign read", r.status_code)
            return None
        j = r.json()
        return _clean(j) if isinstance(j, dict) else None
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Events Desk campaign read failed: %s", type(exc).__name__)
        return None


def event_for(cur, ref: str) -> dict | None:
    """The event's name, dates, city and booking link for a campaign, or None when Events Desk could not say. Called
    outside any ingest transaction; the day's answer is kept in settings."""
    if not (ref and configured()):
        return None
    key = f"events_desk_campaign:{ref}"
    cached = db.one(cur, "select value from settings where key = %s and (value ->> 'day')::date = app_now()::date", key)
    if cached:
        return cached["value"].get("event")
    event = _read(ref)
    # The day's answer is written on a connection of its own and committed at once: the network wait above and this write
    # never hold the sync's transaction (or a row in it) open longer than the sync itself.
    with db.pool().connection() as conn:
        conn.execute("""insert into settings (key, value) values (%s, %s)
                        on conflict (key) do update set value = excluded.value""",
                     (key, J({"day": str(db.val(cur, "select app_now()::date")), "event": event})))
    return event


def _on(d: str) -> date:
    return date.fromisoformat(d)


def words(event: dict | None) -> str | None:
    """The event as one phrase for a fact: 'AWS re:Invent 2026 in Las Vegas, 30 November to 4 December 2026'."""
    if not event or not event.get("name"):
        return None
    out = event["name"]
    if event.get("city"):
        out += f" in {event['city']}"
    start, end = event.get("starts_on"), event.get("ends_on")
    if start:
        s = _on(start)
        if end and end != start:
            e = _on(end)
            when = (f"{s.day} to {e.day} {e:%B} {e.year}" if (s.month, s.year) == (e.month, e.year)
                    else f"{s.day} {s:%B} to {e.day} {e:%B} {e.year}")
        else:
            when = f"{s.day} {s:%B} {s.year}"
        out += f", {when}"
    return out
