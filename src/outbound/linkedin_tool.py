"""A LinkedIn tool's webhooks (HeyReach-shaped): a connection request was accepted, or someone wrote back.

HeyReach sends one event per action and retries a failed delivery, so every event is safe to receive twice. It only
fires on the first reply in a conversation; later messages are still pasted on the person's sheet.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from . import audit, db, sdr_steps

ACCEPTED = {"connection_request_accepted", "connection_accepted"}
REPLIED = {"message_reply_received", "every_message_reply_received", "inmail_reply_received"}

# The same normalisation as privacy.linkedin_hash and the send trigger: no scheme, no www, no trailing slash.
_NORM = "rtrim(regexp_replace(regexp_replace(lower(trim(%s)), '^[a-z]+://', ''), '^www\\.', ''), '/')"


def _profile(payload: dict) -> str | None:
    lead = payload.get("lead") or payload.get("contact") or {}
    for k in ("profile_url", "profileUrl", "linkedin_url", "linkedinUrl"):
        if lead.get(k):
            return str(lead[k])
    return payload.get("profile_url") or payload.get("linkedin_url")


def find_person(cur, url: str) -> int | None:
    return db.val(cur, f"""select id from people where linkedin_url is not null
                           and {_NORM % 'linkedin_url'} = {_NORM % '%s'} order by id limit 1""", url)


def _when(s: str | None, fallback: datetime) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else fallback
    except ValueError:
        return fallback


def handle(cur, payload: dict) -> dict:
    """Apply one event. Unknown events and people are acknowledged and noted, so the tool does not retry them."""
    event = str(payload.get("event_type") or payload.get("eventType") or payload.get("type") or "").strip().lower()
    url = _profile(payload)
    if event not in ACCEPTED | REPLIED:
        return {"ok": True, "applied": False, "why": "event not used"}
    person = find_person(cur, url) if url else None
    if person is None:
        audit.log(cur, "desk", "linkedin_event_unmatched", "person", None, {"event": event, "profile": url})
        return {"ok": True, "applied": False, "why": "no person on the desk with that profile"}
    if event in ACCEPTED:
        sdr_steps.connection_accepted(cur, person, user_id=None, source="heyreach")
        return {"ok": True, "applied": True, "person_id": person}
    theirs = [m for m in payload.get("recent_messages") or [] if m.get("is_reply") and (m.get("message") or "").strip()]
    if not theirs:
        return {"ok": True, "applied": False, "why": "no message from them in the event"}
    last = theirs[-1]
    now = db.val(cur, "select app_now()")
    key = last.get("timestamp") or hashlib.sha256(last["message"].encode()).hexdigest()[:16]
    conv = payload.get("conversation_id") or payload.get("conversationId") or "none"
    rid = sdr_steps.linkedin_reply(cur, person, text=last["message"], received_at=_when(last.get("timestamp"), now),
                                   provider_id=f"heyreach:{conv}:{key}")
    return {"ok": True, "applied": rid is not None, "person_id": person, "reply_id": rid, "duplicate": rid is None}
