"""The HTTP API and the web app's host.

Identity: in demo mode the browser says who it is acting as (X-Acting-As); in header mode a trusted proxy
(Cloudflare Access) sets the user's email. Every write checks the role. Webhooks are HMAC-signed."""
from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import (  # noqa: F401
    audit,
    db,
    gate,
    jobs,
    monitors,
    outreach,
    pipeline,
    play_editor,
    plays,
    replies,
    scheduler,
    scoring,
    sdr_steps,
    sending,
    signals,
    views,
)
from ..config import CONFIG

log = logging.getLogger("outbound.api")
WEB = Path(__file__).resolve().parents[3] / "web" / "dist"
@asynccontextmanager
async def lifespan(_app):
    start_worker()
    yield


app = FastAPI(title="Outbound Desk", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


# ---------------------------------------------------------------- cross-cutting

@app.middleware("http")
async def headers_and_errors(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request %s %s failed (%s)", request.method, request.url.path, rid)
        response = JSONResponse({"error": "Something went wrong on our side.", "request_id": rid}, status_code=500)
    response.headers["X-Request-Id"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: https://randomuser.me https://media.licdn.com; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    ms = (time.perf_counter() - started) * 1000
    if request.url.path.startswith("/api/"):
        log.info('{"rid":"%s","method":"%s","path":"%s","status":%s,"ms":%.0f}', rid, request.method,
                 request.url.path, response.status_code, ms)
    return response


_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def rate_limit(request: Request, limit: int = 120, window: float = 60.0) -> None:
    """Writes per client per minute. In memory: enough for one instance; a shared deployment uses the proxy's."""
    key = request.client.host if request.client else "?"
    now = time.monotonic()
    with _hits_lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many changes in a minute. Try again shortly.")
        q.append(now)


_jwks = None


def _access_email(request: Request) -> str | None:
    """Cloudflare Access signs every request it lets through. Verify the token; never trust a plain header."""
    global _jwks
    import jwt
    token = request.headers.get("Cf-Access-Jwt-Assertion") or request.cookies.get("CF_Authorization")
    if not token:
        return None
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"https://{CONFIG.access_team_domain}/cdn-cgi/access/certs", cache_keys=True)
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=CONFIG.access_aud,
                            issuer=f"https://{CONFIG.access_team_domain}")
    except Exception:
        return None
    return (claims.get("email") or "").strip().lower() or None


def current_user(request: Request) -> dict:
    with db.tx() as cur:
        if CONFIG.auth_mode == "header":
            email = _access_email(request)
            u = db.one(cur, "select * from users where email = %s and active", email) if email else None
        else:
            raw = request.headers.get("X-Acting-As") or request.query_params.get("as")
            u = db.one(cur, "select * from users where id = %s and active", int(raw)) if raw and raw.isdigit() else None
            if u is None:
                u = db.one(cur, "select * from users where role = 'sdr' and active order by id limit 1")
    if u is None:
        raise HTTPException(401, "Sign in to use the desk.")
    return u


def money(u: dict) -> bool:
    return u["role"] in ("manager", "gtm")


def need(u: dict, *roles: str) -> None:
    if u["role"] not in roles:
        raise HTTPException(403, "Your role cannot do this.")


def writer(request: Request, u: dict = Depends(current_user)) -> dict:
    rate_limit(request)
    if CONFIG.write_key and request.headers.get("X-Write-Key") != CONFIG.write_key and CONFIG.auth_mode == "demo" \
            and not CONFIG.public_demo:
        raise HTTPException(403, "This desk needs its write key for changes.")
    return u


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(422, str(exc))


# ---------------------------------------------------------------- reads

@app.get("/api/health")
def health() -> dict:
    with db.tx() as cur:
        backlog = db.val(cur, "select count(*) from jobs where status = 'queued' and run_at < app_now() - interval '15 minutes'")
        dead = db.val(cur, "select count(*) from jobs where status = 'dead' and finished_at > app_now() - interval '1 day'")
        undelivered = db.val(cur, "select count(*) from alerts where delivered_at is null and at < app_now() - interval '30 minutes'")
        failing = db.val(cur, """select count(*) from (select distinct on (monitor) ok from monitor_runs
                                 order by monitor, at desc) m where not ok""")
        now = db.val(cur, "select app_now()")
    ok = backlog < 50 and dead == 0 and undelivered == 0
    return {"ok": ok, "now": now, "job_backlog": backlog, "dead_jobs_today": dead, "undelivered_alerts": undelivered,
            "monitors_failing": failing, "mode": CONFIG.mode, "public_demo": CONFIG.public_demo}


@app.get("/api/me")
def me(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        users = db.all(cur, "select id, name, role, timezone from users where active order by role desc, name") \
            if CONFIG.auth_mode == "demo" else []
        counts = {
            "today": db.val(cur, """select (select count(*) from account_plays where state = 'proposed' and (owner_id = %s or %s))
                                         + (select count(*) from tasks where status = 'open' and owner_id = %s and kind in ('reply','review_reply'))""",
                            u["id"], u["role"] != "sdr", u["id"]),
            "approvals": db.val(cur, """select count(*) from messages m join enrollments e on e.id = m.enrollment_id
                                        join account_plays ap on ap.id = e.account_play_id
                                        where m.status in ('awaiting_approval','failed_gate') and m.channel = 'email' and (ap.owner_id = %s or %s)""",
                                u["id"], u["role"] != "sdr"),
            "replies": db.val(cur, "select count(*) from replies where needs_review and handled_at is null"),
        }
        now = db.val(cur, "select app_now()")
        sim = db.val(cur, "select enabled from sim_clock")
    return {"user": {k: u[k] for k in ("id", "name", "role", "timezone")}, "users": users, "counts": counts,
            "money": money(u), "now": now, "simulated": sim, "public_demo": CONFIG.public_demo,
            "company": CONFIG.sender_company}


@app.get("/api/today")
def today(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return views.today(cur, u)


@app.get("/api/in-flight")
def in_flight(mine: bool | None = None, u: dict = Depends(current_user)) -> dict:
    """What is moving: every open play and each person's sequence. SDRs see their own by default."""
    with db.tx() as cur:
        return views.in_flight(cur, u, mine=(u["role"] == "sdr") if mine is None else mine)


@app.get("/api/accounts")
def accounts(view: Literal["priority", "in_play", "rising", "all"] = "priority", q: str | None = None,
             owner: int | None = None, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        rows = views.accounts(cur, q=(q or "")[:80] or None, view=view, owner=owner)
        total = db.val(cur, "select count(*) from accounts" + ("" if view == "all" else " where fit_tier in ('A','B')"))
        return {"accounts": rows, "total": total if not q and view in ("all", "priority") else len(rows)}


@app.get("/api/accounts/{account_id}")
def account(account_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        a = views.account(cur, account_id, money=money(u))
    if a is None:
        raise HTTPException(404, "No such account.")
    return a


@app.get("/api/people/{person_id}")
def person(person_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        p = views.person(cur, person_id)
    if p is None:
        raise HTTPException(404, "No such person.")
    return p


@app.get("/api/signals")
def signals_page(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return views.signals_page(cur)


@app.get("/api/plays")
def plays_page(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return {"plays": views.plays_page(cur, money=money(u))}


@app.get("/api/plays/{play_id}/accounts")
def play_accounts(play_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return {"accounts": db.all(cur, """select ap.id, ap.state, ap.arm, ap.proposed_at, a.id as account_id, a.name,
                                           a.primary_domain, u.name as owner
                                    from account_plays ap join accounts a on a.id = ap.account_id
                                    left join users u on u.id = ap.owner_id
                                    where ap.play_id = %s order by ap.proposed_at desc limit 100""", play_id)}


@app.get("/api/messages/{message_id}")
def message(message_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        m = views.message(cur, message_id)
    if m is None:
        raise HTTPException(404, "No such message.")
    return m


@app.get("/api/replies")
def replies_page(view: Literal["mine", "all", "hot", "needs_person"] = "mine", u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return {"replies": views.replies_page(cur, view=view, user_id=u["id"])}


@app.get("/api/replies/{reply_id}")
def reply(reply_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        r = views.reply(cur, reply_id)
    if r is None:
        raise HTTPException(404, "No such reply.")
    return r


@app.get("/api/deliverability")
def deliverability(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return views.deliverability(cur)


@app.get("/api/results")
def results(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return views.results(cur, money=money(u))


@app.get("/api/ops")
def ops(u: dict = Depends(current_user)) -> dict:
    need(u, "gtm", "manager")
    with db.tx() as cur:
        return views.health(cur)


@app.get("/api/settings")
def settings_page(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return views.settings(cur)


# ---------------------------------------------------------------- writes

class Decide(BaseModel):
    accept: bool
    reason: str | None = Field(None, max_length=300)


@app.post("/api/account-plays/{ap_id}/decide")
def decide(ap_id: int, body: Decide, u: dict = Depends(writer)) -> dict:
    with db.tx() as cur:
        ap = db.one(cur, "select owner_id, state from account_plays where id = %s", ap_id)
        if ap is None:
            raise HTTPException(404, "No such proposal.")
        if u["role"] == "sdr" and ap["owner_id"] != u["id"]:
            raise HTTPException(403, "This account belongs to someone else.")
        try:
            plays.decide(cur, ap_id, accept=body.accept, user_id=u["id"], reason=body.reason)
        except (ValueError, plays.BadTransition) as exc:
            raise bad_request(exc) from exc
    if CONFIG.worker_inline:
        jobs.run_ready(limit=50)
    return {"ok": True}


class Approve(BaseModel):
    subject: str | None = Field(None, max_length=200)
    body: str | None = Field(None, max_length=6000)


def _own_message(cur, message_id: int, u: dict) -> None:
    owner = db.val(cur, """select ap.owner_id from messages m join enrollments e on e.id = m.enrollment_id
                           join account_plays ap on ap.id = e.account_play_id where m.id = %s""", message_id)
    if owner is None:
        raise HTTPException(404, "No such message.")
    if u["role"] == "sdr" and owner != u["id"]:
        raise HTTPException(403, "This email belongs to another SDR's account.")


@app.post("/api/messages/{message_id}/approve")
def approve(message_id: int, body: Approve, u: dict = Depends(writer)) -> dict:
    with db.tx() as cur:
        _own_message(cur, message_id, u)
        try:
            with cur.connection.transaction():
                outreach.approve(cur, message_id, user_id=u["id"], subject=body.subject, body=body.body)
        except ValueError as exc:
            raise bad_request(exc) from exc
        except psycopg.errors.RaiseException as exc:
            raise HTTPException(422, str(exc).split("\n")[0]) from exc
        return views.message(cur, message_id)


class Reject(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
    skip_person: bool = False


@app.post("/api/messages/{message_id}/reject")
def reject(message_id: int, body: Reject, u: dict = Depends(writer)) -> dict:
    with db.tx() as cur:
        _own_message(cur, message_id, u)
        outreach.reject(cur, message_id, user_id=u["id"], reason=body.reason, skip_person=body.skip_person)
    return {"ok": True}


class Handle(BaseModel):
    outcome: Literal["answered", "meeting_booked", "labelled", "no_action"]
    label: str | None = None
    meeting_at: datetime | None = None


@app.post("/api/replies/{reply_id}/handle")
def handle_reply(reply_id: int, body: Handle, u: dict = Depends(writer)) -> dict:
    from ..llm import LABELS
    if body.label and body.label not in LABELS:
        raise HTTPException(422, "Unknown label.")
    with db.tx() as cur:
        r = db.one(cur, "select * from replies where id = %s", reply_id)
        if r is None:
            raise HTTPException(404, "No such reply.")
        if u["role"] == "sdr" and r["account_id"]:
            owner = db.val(cur, """select coalesce((select ap.owner_id from account_plays ap where ap.account_id = %s
                                   order by ap.proposed_at desc limit 1), (select owner_id from accounts where id = %s))""",
                           r["account_id"], r["account_id"])
            if owner not in (None, u["id"]):
                raise HTTPException(403, "This reply belongs to another SDR's account.")
        if body.outcome == "meeting_booked":
            if not r["account_id"]:
                raise HTTPException(422, "This reply is not tied to an account.")
            at = body.meeting_at or (db.val(cur, "select app_now()") + timedelta(days=3))
            pipeline.book_meeting(cur, account_id=r["account_id"], person_id=r["person_id"], starts_at=at,
                                  source="sdr", owner_id=u["id"])
        replies.handle(cur, reply_id, user_id=u["id"], outcome=body.outcome, label=body.label)
        return views.reply(cur, reply_id)


@app.get("/api/tasks/{task_id}")
def task(task_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        t = views.task(cur, task_id)
    if t is None:
        raise HTTPException(404, "No such task.")
    return t


class TaskOutcome(BaseModel):
    outcome: str = Field("done", max_length=40)
    text: str | None = Field(None, max_length=3000)  # the LinkedIn note as sent, when the SDR edited it
    note: str | None = Field(None, max_length=2000)


@app.post("/api/tasks/{task_id}/done")
def task_done(task_id: int, body: TaskOutcome | None = None, skipped: bool = False, u: dict = Depends(writer)) -> dict:
    """What happened with a call or LinkedIn task. LinkedIn 'sent' goes through the send guard."""
    body = body or TaskOutcome(outcome="skipped" if skipped else "done")
    try:
        with db.tx() as cur:
            return sdr_steps.complete(cur, task_id, user=u, outcome=body.outcome, text=body.text, note=body.note)
    except ValueError as exc:
        # A refusal by the send guard closes the task in its own transaction, so it stays closed.
        if "The task is closed" in str(exc):
            with db.tx() as cur:
                db.run(cur, "update tasks set status = 'skipped', done_at = app_now(), note = %s where id = %s "
                            "and status = 'open'", str(exc)[:500], task_id)
        raise HTTPException(409 if "refused" in str(exc) else 400, str(exc)) from None


class LinkedInEvent(BaseModel):
    event: Literal["accepted", "reply"]
    text: str | None = Field(None, max_length=20_000)


@app.post("/api/people/{person_id}/linkedin")
def linkedin_event(person_id: int, body: LinkedInEvent, u: dict = Depends(writer)) -> dict:
    """The SDR records what happened on LinkedIn: they accepted the request, or they wrote back (pasted here)."""
    with db.tx() as cur:
        acct = db.val(cur, "select account_id from people where id = %s", person_id)
        if acct is None and not db.val(cur, "select exists (select 1 from people where id = %s)", person_id):
            raise HTTPException(404, "No such person.")
        _sdr_owns(cur, u, acct)
        if body.event == "accepted":
            sdr_steps.connection_accepted(cur, person_id, user_id=u["id"])
            return {"ok": True}
        if not (body.text or "").strip():
            raise HTTPException(400, "Paste what they wrote.")
        now = db.val(cur, "select app_now()")
        rid = sdr_steps.linkedin_reply(cur, person_id, text=body.text, received_at=now,
                                       provider_id=f"li-manual:{person_id}:{now.isoformat()}")
        return {"ok": True, "reply_id": rid}


class MeetingStatus(BaseModel):
    status: Literal["held", "no_show", "cancelled"]
    notes: str | None = Field(None, max_length=8000)
    learn: bool = False


@app.post("/api/meetings/{meeting_id}/status")
def meeting_status(meeting_id: int, body: MeetingStatus, u: dict = Depends(writer)) -> dict:
    with db.tx() as cur:
        owner = db.val(cur, "select owner_id from meetings where id = %s", meeting_id)
        if u["role"] == "sdr" and owner not in (None, u["id"]):
            raise HTTPException(403, "This meeting belongs to another SDR.")
        pipeline.set_meeting_status(cur, meeting_id, body.status, user_id=u["id"])
        kept = 0
        if body.notes:
            nid = pipeline.record_call_notes(cur, meeting_id, body.notes, u["id"])
            if body.learn:
                kept = pipeline.learn_from(cur, nid, u["id"])
    return {"ok": True, "learnings": kept}


@app.get("/api/meetings/{meeting_id}")
def meeting(meeting_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        m = views.meeting(cur, meeting_id, money=money(u))
    if m is None:
        raise HTTPException(404, "No such meeting.")
    return m


class CalendarBooking(BaseModel):
    """A booking tool's webhook (Calendly-shaped): an invitee booked, rescheduled or cancelled."""
    event: Literal["booked", "rescheduled", "cancelled"]
    external_id: str = Field(min_length=1, max_length=300)
    invitee_email: str = Field(min_length=3, max_length=320)
    starts_at: datetime | None = None
    inbound: bool = False  # booked from the website rather than a link an SDR sent


@app.post("/api/webhooks/meeting")
async def webhook_meeting(request: Request) -> dict:
    raw = await request.body()
    verify_signature(request, raw)
    b = CalendarBooking.model_validate_json(raw)
    with db.tx() as cur:
        existing = db.one(cur, "select id from meetings where external_id = %s", b.external_id)
        if b.event == "cancelled":
            if existing:
                pipeline.set_meeting_status(cur, existing["id"], "cancelled")
            return {"ok": True, "meeting_id": existing["id"] if existing else None}
        if b.starts_at is None:
            raise HTTPException(422, "A booking needs starts_at.")
        if existing:
            # A reschedule moves a booked meeting; one that happened or was cancelled stays as it is.
            db.run(cur, "update meetings set starts_at = %s where id = %s and status = 'booked'", b.starts_at, existing["id"])
            return {"ok": True, "meeting_id": existing["id"]}
        p = db.one(cur, "select id, account_id from people where email = %s", b.invitee_email.strip().lower())
        account_id = p["account_id"] if p else signals.resolve_account(cur, b.invitee_email.split("@")[-1], None)[0]
        if account_id is None:
            return {"ok": True, "meeting_id": None, "unmatched": True}
        mid = pipeline.book_meeting(cur, account_id=account_id, person_id=p["id"] if p else None, starts_at=b.starts_at,
                                    source="inbound" if b.inbound else "calendar", external_id=b.external_id)
    return {"ok": True, "meeting_id": mid}


class ImportFile(BaseModel):
    csv: str = Field(min_length=1, max_length=5_000_000)


@app.post("/api/import/{kind}")
def import_rows(kind: Literal["accounts", "people"], body: ImportFile, u: dict = Depends(writer)) -> dict:
    """Bring your own accounts and people. Rows the desk refuses come back with the reason."""
    need(u, "manager", "gtm")
    from .. import setup_desk
    with db.tx() as cur:
        out = (setup_desk.import_accounts if kind == "accounts" else setup_desk.import_people)(cur, body.csv)
        audit.log(cur, "person", f"imported_{kind}", "desk", None, {"imported": out["imported"],
                                                                     "refused": len(out["refused"])}, actor_id=u["id"])
    return out


class Suppression(BaseModel):
    kind: Literal["email", "domain", "person", "account", "phone"]
    value: str = Field(min_length=1, max_length=320)
    reason: str = Field(min_length=3, max_length=300)


@app.post("/api/suppressions")
def add_suppression(body: Suppression, u: dict = Depends(writer)) -> dict:
    """Do not contact, added by a person: takes effect on the next send check, and the send trigger enforces it."""
    if u["role"] == "sdr" and body.kind in ("domain", "account"):
        raise HTTPException(403, "Blocking a whole company is for a manager or GTM.")
    with db.tx() as cur:
        value = body.value.strip().lower()
        db.run(cur, "insert into suppressions (kind, value, reason, source) values (%s,%s,%s,%s)",
               body.kind, value, body.reason, f"person:{u['id']}")
        if body.kind in ("person", "email", "domain", "account"):
            people = db.all(cur, """select id from people where (%s = 'person' and id::text = %s) or (%s = 'email' and email = %s)
                                    or (%s = 'domain' and split_part(email, '@', 2) = %s)
                                    or (%s = 'account' and account_id::text = %s)""",
                            body.kind, value, body.kind, value, body.kind, value, body.kind, value)
            for p in people:
                for e in db.all(cur, "select id from enrollments where person_id = %s and state in ('pending','active','paused')", p["id"]):
                    outreach.stop_enrollment(cur, e["id"], "suppressed")
                db.run(cur, """update tasks set status = 'skipped', done_at = app_now(), note = 'Closed: do not contact'
                               where person_id = %s and status = 'open'""", p["id"])
        audit.log(cur, "person", "suppressed", body.kind, None, {"value": value, "reason": body.reason}, actor_id=u["id"])
    return {"ok": True}


@app.delete("/api/suppressions/{sup_id}")
def remove_suppression(sup_id: int, u: dict = Depends(writer)) -> dict:
    """Only a manager lifts a do-not-contact, and only one a person added by hand."""
    need(u, "manager")
    with db.tx() as cur:
        sup = db.one(cur, "select * from suppressions where id = %s", sup_id)
        if sup is None:
            raise HTTPException(404, "No such entry.")
        if not sup["source"].startswith("person:"):
            raise HTTPException(409, "Only an entry a person added by hand can be lifted. Opt-outs, replies and "
                                     "erasures stay.")
        db.run(cur, "update suppressions set expires_at = app_now() where id = %s", sup_id)
        audit.log(cur, "person", "suppression_lifted", sup["kind"], None, {"value": sup["value"]}, actor_id=u["id"])
    return {"ok": True}


def _sdr_owns(cur, u: dict, account_id: int | None) -> None:
    """An SDR acts on accounts they own or work in an open play; managers and GTM act on any."""
    if u["role"] != "sdr" or account_id is None:
        return
    owner = db.val(cur, """select coalesce((select ap.owner_id from account_plays ap where ap.account_id = %s and ap.state in
                           ('proposed','accepted','researching','approving','active','engaged','meeting') order by ap.proposed_at desc
                           limit 1), (select owner_id from accounts where id = %s))""", account_id, account_id)
    if owner not in (None, u["id"]):
        raise HTTPException(403, "This account belongs to another SDR.")


class LogMeeting(BaseModel):
    person_id: int | None = None
    starts_at: datetime


@app.post("/api/accounts/{account_id}/meetings")
def log_meeting(account_id: int, body: LogMeeting, u: dict = Depends(writer)) -> dict:
    """A meeting the SDR booked another way (a call, LinkedIn, a conference): recorded like any other."""
    with db.tx() as cur:
        _sdr_owns(cur, u, account_id)
        if body.person_id and db.val(cur, "select account_id from people where id = %s", body.person_id) != account_id:
            raise HTTPException(422, "That person is not at this account.")
        mid = pipeline.book_meeting(cur, account_id=account_id, person_id=body.person_id, starts_at=body.starts_at,
                                    source="sdr", owner_id=u["id"])
    return {"ok": True, "meeting_id": mid}


class Activity(BaseModel):
    kind: Literal["they_called", "they_emailed", "i_emailed"]
    note: str | None = Field(None, max_length=2000)


@app.post("/api/people/{person_id}/activity")
def log_activity(person_id: int, body: Activity, u: dict = Depends(writer)) -> dict:
    """Contact that happened outside the desk. Any of it means the SDR is in the conversation, so the desk's own
    steps for this person stop (docs/SPEC.md 22.19)."""
    with db.tx() as cur:
        p = db.one(cur, "select id, account_id from people where id = %s", person_id)
        if p is None:
            raise HTTPException(404, "No such person.")
        _sdr_owns(cur, u, p["account_id"])
        ap = db.val(cur, "select account_play_id from enrollments where person_id = %s order by created_at desc limit 1", person_id)
        channel, direction = {"they_called": ("call", "in"), "they_emailed": ("email", "in"), "i_emailed": ("email", "out")}[body.kind]
        db.run(cur, """insert into touches (account_id, person_id, account_play_id, channel, direction, kind, at, source, dedup_key)
                       values (%s,%s,%s,%s,%s,%s,app_now(),'sdr',%s)""", p["account_id"], person_id, ap, channel, direction,
               body.kind, f"activity:{person_id}:{db.val(cur, 'select extract(epoch from app_now())')}")
        sdr_steps.in_conversation(cur, person_id, ap)
        audit.log(cur, "person", "activity_logged", "person", person_id, {"kind": body.kind, "note": body.note}, actor_id=u["id"])
    return {"ok": True}


class Colleagues(BaseModel):
    action: Literal["stop", "resume_now"]


@app.post("/api/replies/{reply_id}/colleagues")
def colleagues(reply_id: int, body: Colleagues, u: dict = Depends(writer)) -> dict:
    """After a positive reply the desk resumes the person's colleagues in 3 business days unless the SDR decides
    otherwise: stop them (this one conversation is enough) or resume them now."""
    with db.tx() as cur:
        r = db.one(cur, "select id, account_id, person_id from replies where id = %s", reply_id)
        if r is None or not r["account_id"]:
            raise HTTPException(404, "No such reply.")
        _sdr_owns(cur, u, r["account_id"])
        paused = db.all(cur, """select e.id from enrollments e join account_plays ap on ap.id = e.account_play_id
                                where ap.account_id = %s and e.state = 'paused' and e.pause_reason = 'account_reply'
                                and e.person_id is distinct from %s""", r["account_id"], r["person_id"])
        for e in paused:
            if body.action == "stop":
                outreach.stop_enrollment(cur, e["id"], "colleague_engaged", close_play=False)
            else:
                replies.resume(cur, e["id"])
        db.run(cur, "update jobs set status = 'done', finished_at = app_now(), last_error = 'decided by the SDR' "
                    "where dedupe_key = %s and status = 'queued'", f"rap:{reply_id}")
        audit.log(cur, "person", f"colleagues_{body.action}", "reply", reply_id, {"count": len(paused)}, actor_id=u["id"])
    return {"ok": True, "colleagues": len(paused)}


class Hold(BaseModel):
    until: datetime
    reason: str = Field(min_length=3, max_length=300)


@app.post("/api/accounts/{account_id}/hold")
def hold_account(account_id: int, body: Hold, u: dict = Depends(writer)) -> dict:
    """Put an account on hold (a partner is talking to them, legal asked): nothing sends until the date."""
    with db.tx() as cur:
        _sdr_owns(cur, u, account_id)
        db.run(cur, "insert into holds (account_id, reason, until, set_by) values (%s,%s,%s,%s)",
               account_id, body.reason, body.until, f"person:{u['id']}")
        audit.log(cur, "person", "held", "account", account_id, {"until": body.until.isoformat()}, actor_id=u["id"])
    return {"ok": True}


class Resolve(BaseModel):
    action: Literal["create", "link", "ignore"]
    account_id: int | None = None
    name: str | None = Field(None, max_length=200)
    domain: str | None = Field(None, max_length=300)


@app.post("/api/signals/{signal_id}/resolve")
def resolve_signal(signal_id: int, body: Resolve, u: dict = Depends(writer)) -> dict:
    """A person decides what an unmatched signal is about: a new account, one we have, or nothing."""
    with db.tx() as cur:
        s = db.one(cur, "select * from signals where id = %s and status = 'unmatched' for update", signal_id)
        if s is None:
            raise HTTPException(404, "No unmatched signal with that id.")
        if body.action == "ignore":
            db.run(cur, "update signals set status = 'ignored', status_reason = %s where id = %s",
                   f"ignored by {u['name']}", signal_id)
            return {"ok": True}
        if body.action == "create":
            dom = signals.normalize_domain(body.domain or s["raw_domain"])
            name = (body.name or s["raw_company"] or (dom or "").split(".")[0].title()).strip()
            if not dom:
                raise HTTPException(422, "A new account needs its company domain.")
            if db.val(cur, "select account_id from account_domains where domain = %s", dom):
                raise HTTPException(409, "An account with that domain exists. Link to it instead.")
            aid = db.val(cur, """insert into accounts (name, name_key, primary_domain, source) values (%s,%s,%s,'signal')
                                 returning id""", name, signals.normalize_name(name), dom)
            db.run(cur, "insert into account_domains (domain, account_id) values (%s,%s)", dom, aid)
            jobs.enqueue(cur, "crm_retry_held", {}, dedupe_key="crm_retry_held")
        else:
            aid = body.account_id
            if not aid or not db.val(cur, "select exists (select 1 from accounts where id = %s)", aid):
                raise HTTPException(422, "Pick the account it belongs to.")
            if s["raw_domain"] and not db.val(cur, "select exists (select 1 from account_domains where domain = %s)", s["raw_domain"]):
                db.run(cur, "insert into account_domains (domain, account_id) values (%s,%s)", s["raw_domain"], aid)
        db.run(cur, "update signals set status = 'matched', status_reason = null, account_id = %s where id = %s", aid, signal_id)
        db.run(cur, """insert into facts (account_id, person_id, kind, text, source, source_url, observed_at)
                       values (%s,%s,%s,%s,%s,%s,%s)""", aid, s["person_id"], "signal:" + s["type_key"],
               s["evidence"]["summary"], s["source"], s["evidence"].get("url"), s["observed_at"])
        jobs.enqueue(cur, "rescore", {"account_id": aid, "reason": "signal"}, dedupe_key=f"rescore:{aid}")
        audit.log(cur, "person", "signal_resolved", "signal", signal_id, {"action": body.action, "account_id": aid},
                  actor_id=u["id"])
    return {"ok": True, "account_id": aid}


class IcpFactor(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    field: Literal["industry", "employees", "region", "revenue_band", "tech", "hq_country"]
    op: Literal["in", "between", "has_any", "has_none"]
    value: list[str] | list[int]
    weight: int = Field(ge=0, le=100)


class IcpExclude(BaseModel):
    field: Literal["industry", "employees", "region", "revenue_band", "tech", "hq_country"]
    op: Literal["in", "between", "has_any", "has_none"]
    value: list[str] | list[int]
    reason: str = Field(min_length=3, max_length=200)


class IcpRules(BaseModel):
    factors: list[IcpFactor] = Field(min_length=1)
    penalties: list[IcpFactor] = []
    excludes: list[IcpExclude] = []
    tiers: dict[Literal["A", "B"], int]
    note: str = Field(min_length=3, max_length=300)


@app.put("/api/icp")
def publish_icp(body: IcpRules, u: dict = Depends(writer)) -> dict:
    """GTM publishes a new version of the ideal customer profile. Every account is rescored against it; the old
    version stays, so a score can always be traced to the rules it was computed with."""
    need(u, "gtm")
    if not (0 < body.tiers["B"] < body.tiers["A"] <= 100):
        raise HTTPException(422, "Tier A needs a higher score than tier B, both between 1 and 100.")
    for f in body.factors + body.penalties:
        if f.op == "between" and (len(f.value) != 2 or not all(isinstance(x, int) for x in f.value)):
            raise HTTPException(422, f"{f.key}: a range is two whole numbers.")
    rules = body.model_dump(exclude={"note"})
    with db.tx() as cur:
        vid = db.val(cur, "insert into icp_versions (rules, note, published_by, published_at) values (%s,%s,%s,app_now()) returning id",
                     db.J(rules), body.note, u["id"])
        jobs.enqueue(cur, "rescore_all", {"reason": "icp"}, dedupe_key=f"rescore_all:icp:{vid}")
        audit.log(cur, "person", "icp_published", "icp", vid, {"note": body.note}, actor_id=u["id"])
    return {"ok": True, "version": vid}


# ---------------------------------------------------------------- administration (managers)

def _admin(fn, *args, **kwargs):
    from .. import admin
    try:
        with db.tx() as cur:
            return fn(cur, *args, **kwargs)
    except admin.AdminError as exc:
        raise HTTPException(422, str(exc)) from None


@app.get("/api/admin")
def admin_view(u: dict = Depends(current_user)) -> dict:
    need(u, "manager", "gtm")
    with db.tx() as cur:
        return {"users": db.all(cur, """select u.id, u.name, u.email, u.role, u.timezone, u.slack_id, u.active,
                                          (select count(*) from accounts a where a.owner_id = u.id) as accounts,
                                          (select count(*) from mailboxes m where m.user_id = u.id and m.status <> 'retired') as mailboxes
                                   from users u order by u.active desc, u.role, u.name""")}


class NewUser(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    role: Literal["sdr", "manager", "gtm"]
    timezone: str = Field("America/New_York", max_length=60)
    slack_id: str | None = Field(None, max_length=40)


@app.post("/api/users")
def add_user(body: NewUser, u: dict = Depends(writer)) -> dict:
    need(u, "manager")
    from .. import admin
    return {"ok": True, "id": _admin(admin.add_user, **body.model_dump(), by=u["id"])}


class UserChange(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    role: Literal["sdr", "manager", "gtm"] | None = None
    timezone: str | None = Field(None, max_length=60)
    slack_id: str | None = Field(None, max_length=40)
    deactivate: bool = False
    successor: int | None = None


@app.patch("/api/users/{uid}")
def change_user(uid: int, body: UserChange, u: dict = Depends(writer)) -> dict:
    need(u, "manager")
    from .. import admin
    if body.deactivate:
        return {"ok": True, "moved": _admin(admin.deactivate, uid, successor=body.successor, by=u["id"])}
    _admin(admin.change_user, uid, by=u["id"], name=body.name, role=body.role, timezone=body.timezone, slack_id=body.slack_id)
    return {"ok": True}


class NewDomain(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    registered: date
    dkim_selector: str | None = Field(None, max_length=63)


@app.post("/api/sending-domains")
def add_domain(body: NewDomain, u: dict = Depends(writer)) -> dict:
    need(u, "manager")
    from .. import admin
    return {"ok": True, "domain": _admin(admin.add_domain, **body.model_dump(), by=u["id"])}


class NewMailbox(BaseModel):
    address: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    user_id: int
    provider: Literal["google", "microsoft"]
    warmup_started: date


@app.post("/api/mailboxes")
def add_mailbox(body: NewMailbox, u: dict = Depends(writer)) -> dict:
    need(u, "manager")
    from .. import admin
    return {"ok": True, "id": _admin(admin.add_mailbox, **body.model_dump(), by=u["id"])}


class MailboxChange(BaseModel):
    status: Literal["active", "paused", "retired"]
    reason: str | None = Field(None, max_length=300)


@app.patch("/api/mailboxes/{mid}")
def change_mailbox(mid: int, body: MailboxChange, u: dict = Depends(writer)) -> dict:
    need(u, "manager")
    from .. import admin
    _admin(admin.set_mailbox, mid, status=body.status, reason=body.reason, by=u["id"])
    return {"ok": True}


class PlayChange(BaseModel):
    status: Literal["live", "paused"] | None = None
    autonomy: Literal["research", "draft", "supervised", "autonomous"] | None = None
    reason: str = Field(min_length=3, max_length=300)
    # The monthly cap the manager sets at launch (SPEC 22.16): credits per vendor, and AI in cents.
    monthly_cap: dict[Literal["people_search", "email_finder", "email_verifier", "phone_finder", "anthropic_cents"],
                      int] | None = None


@app.post("/api/plays/{play_id}")
def change_play(play_id: int, body: PlayChange, u: dict = Depends(writer)) -> dict:
    need(u, "manager", "gtm")
    with db.tx() as cur:
        p = db.one(cur, "select * from plays where id = %s for update", play_id)
        if p is None:
            raise HTTPException(404, "No such play.")
        if body.status:
            if body.status == "live" and u["role"] != "manager":
                raise HTTPException(403, "A manager launches plays.")
            if body.status == "live" and p["created_by"] == u["id"]:
                raise HTTPException(422, "The person who wrote a play cannot launch it.")
            if body.status == "live" and p["status"] == "draft" and not (body.monthly_cap or p["monthly_cap"]):
                raise HTTPException(422, "Set the play's monthly cap from its cost card before launching it.")
            db.run(cur, """update plays set status = %s,
                           launched_by = case when %s = 'live' then coalesce(launched_by, %s) else launched_by end,
                           launched_at = case when %s = 'live' then coalesce(launched_at, app_now()) else launched_at end
                           where id = %s""", body.status, body.status, u["id"], body.status, play_id)
        if body.monthly_cap is not None:
            if u["role"] != "manager":
                raise HTTPException(403, "A manager sets a play's monthly cap.")
            if any(v < 0 for v in body.monthly_cap.values()):
                raise HTTPException(422, "A cap cannot be negative.")
            db.run(cur, "update plays set monthly_cap = %s where id = %s", db.J(body.monthly_cap), play_id)
        if body.autonomy and body.autonomy != p["autonomy"]:
            order = views.STAGES
            if order.index(body.autonomy) > order.index(p["autonomy"]):
                if u["role"] != "manager":
                    raise HTTPException(403, "A manager approves a promotion.")
                check = views.promotion_check(cur, p)
                if order.index(body.autonomy) != order.index(p["autonomy"]) + 1 or not check["ready"]:
                    raise HTTPException(422, "This play has not met the checks for the next stage.")
            db.run(cur, "update plays set autonomy = %s where id = %s", body.autonomy, play_id)
            db.run(cur, "insert into play_stage_changes (play_id, from_stage, to_stage, reason, decided_by) "
                        "values (%s,%s,%s,%s,%s)", play_id, p["autonomy"], body.autonomy, body.reason, u["id"])
        audit.log(cur, "person", "play_changed", "play", play_id, body.model_dump(), actor_id=u["id"])
    return {"ok": True}


def _play_in(cur, body: play_editor.PlayIn) -> None:
    try:
        play_editor.check_names(cur, body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/play-preview")
def play_preview(body: play_editor.PlayIn, u: dict = Depends(current_user)) -> dict:
    """What a play, saved or not, would match today and cost a month."""
    with db.tx() as cur:
        _play_in(cur, body)
        pv = play_editor.preview(cur, body)
        out = {"preview": pv}
        if money(u):
            out["cost"] = play_editor.cost(cur, body, pv["per_month_contacted"])
        return out


@app.post("/api/plays")
def create_play(body: play_editor.PlayIn, u: dict = Depends(writer)) -> dict:
    need(u, "gtm")
    with db.tx() as cur:
        _play_in(cur, body)
        key = play_editor.slug(body.name)
        while db.val(cur, "select exists (select 1 from plays where key = %s)", key):
            key = f"{key}_2" if not key[-1].isdigit() else key[:-1] + str(int(key[-1]) + 1)
        # The desk's own legitimate-interest reference, recorded at init; the most recent play's otherwise.
        lia = db.val(cur, "select value #>> '{}' from settings where key = 'lia_ref'") or db.val(
            cur, "select lia_ref from plays where lia_ref is not null order by id desc limit 1")
        if not lia:
            raise HTTPException(422, "The desk has no legitimate-interest reference yet. Set it at init.")
        pid = db.val(cur, """insert into plays (key, name, hypothesis, trigger, personas, max_people, sequence, angle, autonomy,
                                                status, holdout_pct, owner_id, created_by, urgent, latency_hours, lia_ref)
                             values (%s,%s,%s,%s,%s,%s,%s,%s,'draft','draft',%s,%s,%s,%s,%s,%s) returning id""",
                     key, body.name, body.hypothesis, db.J(body.trigger.model_dump()), body.personas, body.max_people,
                     db.J([s.model_dump() for s in body.sequence]), body.angle, body.holdout_pct, u["id"], u["id"],
                     body.urgent, body.latency_hours, lia)
        audit.log(cur, "person", "play_created", "play", pid, {"name": body.name}, actor_id=u["id"])
    return {"ok": True, "id": pid}


@app.put("/api/plays/{play_id}")
def edit_play(play_id: int, body: play_editor.PlayIn, u: dict = Depends(writer)) -> dict:
    need(u, "gtm")
    with db.tx() as cur:
        p = db.one(cur, "select * from plays where id = %s for update", play_id)
        if p is None:
            raise HTTPException(404, "No such play.")
        _play_in(cur, body)
        # A live play's words can change; who it reaches, when, and how many are held back change only after a
        # manager pauses it, so the comparison group is not reshuffled mid-measurement without anyone deciding to.
        in_flight = db.val(cur, """select count(*) from enrollments e join account_plays ap on ap.id = e.account_play_id
                                   where ap.play_id = %s and e.state in ('pending','active','paused')""", play_id)
        if in_flight and p["sequence"] != [x.model_dump() for x in body.sequence]:
            raise HTTPException(409, f"{in_flight} people are part-way through this sequence. Write a new play for the new "
                                     "steps, or wait until they finish.")
        if p["status"] == "live":
            moved = [k for k, new in (("trigger", body.trigger.model_dump()), ("sequence", [x.model_dump() for x in body.sequence]),
                                      ("personas", body.personas), ("max_people", body.max_people),
                                      ("holdout_pct", body.holdout_pct)) if p[k] != new]
            if moved:
                raise HTTPException(409, "This play is live. A manager pauses it before its "
                                         + ", ".join(m.replace("_", " ") for m in moved) + " can change.")
        db.run(cur, """update plays set name = %s, hypothesis = %s, trigger = %s, personas = %s, max_people = %s,
                       sequence = %s, angle = %s, holdout_pct = %s, urgent = %s, latency_hours = %s, version = version + 1
                       where id = %s""", body.name, body.hypothesis, db.J(body.trigger.model_dump()), body.personas,
                   body.max_people, db.J([s.model_dump() for s in body.sequence]), body.angle, body.holdout_pct,
                   body.urgent, body.latency_hours, play_id)
        audit.log(cur, "person", "play_edited", "play", play_id, {"version": p["version"] + 1, "before": {
            k: p[k] for k in ("name", "trigger", "personas", "max_people", "sequence", "holdout_pct")}}, actor_id=u["id"])
    return {"ok": True}


class Outcome(BaseModel):
    sent: bool


@app.post("/api/messages/{message_id}/outcome")
def message_outcome(message_id: int, body: Outcome, u: dict = Depends(writer)) -> dict:
    """A person checked the mailbox's sent folder for a send whose outcome the provider could not report."""
    need(u, "gtm", "manager")
    with db.tx() as cur:
        sending.resolve_unknown(cur, message_id, sent=body.sent)
        audit.log(cur, "person", "send_outcome", "message", message_id, {"sent": body.sent}, actor_id=u["id"])
    return {"ok": True}


@app.post("/api/watch/{template_key}/resume")
def resume_watch(template_key: str, u: dict = Depends(writer)) -> dict:
    need(u, "gtm")
    with db.tx() as cur:
        db.run(cur, "update play_step_watch set paused = false, paused_reason = null, sends = 0, hard_bounces = 0, "
                    "complaints = 0 where template_key = %s", template_key)
        audit.log(cur, "person", "watch_resumed", "play_step", None, {"key": template_key}, actor_id=u["id"])
    return {"ok": True}


class KillSwitch(BaseModel):
    on: bool
    reason: str = Field(min_length=3, max_length=300)


@app.post("/api/kill-switch")
def kill_switch(body: KillSwitch, u: dict = Depends(writer)) -> dict:
    need(u, "gtm", "manager")
    with db.tx() as cur:
        db.run(cur, "insert into settings (key, value, updated_by) values ('kill_switch', %s, %s) "
                    "on conflict (key) do update set value = excluded.value, updated_by = excluded.updated_by, updated_at = now()",
               db.J(body.on), u["id"])
        audit.log(cur, "person", "kill_switch_on" if body.on else "kill_switch_off", "settings", None,
                  {"reason": body.reason}, actor_id=u["id"])
    return {"ok": True}


class SignalWeight(BaseModel):
    weight: float = Field(ge=-50, le=50)
    half_life_days: float = Field(gt=0, le=365)
    enabled: bool = True


@app.post("/api/signal-types/{key}")
def set_signal_type(key: str, body: SignalWeight, u: dict = Depends(writer)) -> dict:
    need(u, "gtm")
    with db.tx() as cur:
        n = db.run(cur, "update signal_types set weight = %s, half_life_days = %s, enabled = %s where key = %s",
                   body.weight, body.half_life_days, body.enabled, key)
        if not n:
            raise HTTPException(404, "No such signal type.")
        audit.log(cur, "person", "signal_weight", "signal_type", None, {"key": key, **body.model_dump()}, actor_id=u["id"])
        jobs.enqueue(cur, "rescore_all", {}, dedupe_key="rescore_all:manual")
    return {"ok": True}


@app.post("/api/people/{person_id}/erase")
def erase(person_id: int, u: dict = Depends(writer)) -> dict:
    need(u, "gtm")
    from .. import privacy
    with db.tx() as cur:
        result = privacy.erase(cur, person_id, actor_id=u["id"])
    return result


class Advance(BaseModel):
    hours: int = Field(ge=1, le=24 * 14)


@app.post("/api/sim/advance")
def sim_advance(body: Advance, u: dict = Depends(writer)) -> dict:
    """Demo only: move the simulated clock forward and let the world and the desk work."""
    with db.tx() as cur:
        if not db.val(cur, "select enabled from sim_clock"):
            raise HTTPException(404, "Not a simulated desk.")
    from ..sim import runner
    totals = runner.run_hours(body.hours)
    return {"ok": True, **totals}


# ---------------------------------------------------------------- webhooks (signed)

def verify_signature(request: Request, raw: bytes) -> None:
    ts = request.headers.get("X-Signature-Timestamp", "")
    sig = request.headers.get("X-Signature", "")
    if not ts.isdigit() or abs(time.time() - int(ts)) > 300:
        raise HTTPException(401, "Stale or missing timestamp.")
    expected = hmac.new(CONFIG.webhook_secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "Bad signature.")


class InboundReply(BaseModel):
    provider_id: str = Field(min_length=1, max_length=300)
    from_addr: str = Field(min_length=3, max_length=320)
    subject: str | None = Field(None, max_length=500)
    body: str = Field(max_length=100_000)
    received_at: datetime
    thread_key: str | None = Field(None, max_length=300)
    channel: Literal["email", "linkedin"] = "email"


@app.post("/api/webhooks/reply")
async def webhook_reply(request: Request) -> dict:
    raw = await request.body()
    verify_signature(request, raw)
    body = InboundReply.model_validate_json(raw)
    with db.tx() as cur:
        rid = replies.ingest(cur, from_addr=body.from_addr, subject=body.subject, raw=body.body,
                             received_at=body.received_at, thread_key=body.thread_key, channel=body.channel,
                             provider_id=body.provider_id)
    return {"ok": True, "reply_id": rid, "duplicate": rid is None}


class InboundSignal(BaseModel):
    type: str = Field(max_length=60)
    external_id: str = Field(max_length=300)
    observed_at: datetime
    domain: str | None = Field(None, max_length=300)
    company: str | None = Field(None, max_length=300)
    strength: float = Field(0.6, ge=0, le=1)
    evidence: dict
    person: dict | None = None


@app.post("/api/webhooks/signal")
async def webhook_signal(request: Request) -> dict:
    raw = await request.body()
    verify_signature(request, raw)
    body = InboundSignal.model_validate_json(raw)
    if not isinstance(body.evidence.get("summary"), str) or not (body.evidence.get("url") or body.evidence.get("quote")):
        raise HTTPException(422, "Evidence needs a summary and a url or quote.")
    with db.tx() as cur:
        counts = signals.ingest(cur, "webhook", [body.model_dump()])
    return {"ok": True, **counts}


# ---------------------------------------------------------------- one-click unsubscribe (RFC 8058)

def _check_token(person_id: int, token: str) -> None:
    """The short form (12 characters) is in today's footers; the long one (24) in emails already sent, which must
    keep working for as long as they sit in an inbox."""
    full = outreach.unsubscribe_token(person_id)
    if len(token) not in (12, 24) or not hmac.compare_digest(full[:len(token)], token):
        raise HTTPException(404, "This link is not valid.")


def _split(slug: str) -> tuple[int, str]:
    pid, _, token = slug.partition("-")
    if not pid.isdigit():
        raise HTTPException(404, "This link is not valid.")
    return int(pid), token


@app.get("/u/{slug}", response_class=HTMLResponse)
def unsubscribe_page_short(slug: str) -> str:
    return unsubscribe_page(*_split(slug))


@app.post("/u/{slug}", response_class=HTMLResponse)
def unsubscribe_short(slug: str) -> str:
    return unsubscribe(*_split(slug))


@app.get("/u/{person_id}/{token}", response_class=HTMLResponse)
def unsubscribe_page(person_id: int, token: str) -> str:
    _check_token(person_id, token)
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>Stop these emails</title><body style='font:16px system-ui;max-width:420px;margin:15vh auto;padding:0 16px'>"
            f"<h1 style='font-size:22px'>Stop emails from {CONFIG.sender_company}?</h1>"
            f"<form method=post><button style='font:inherit;padding:12px 20px;border-radius:22px;border:0;background:#1d3b34;color:#fff'>"
            f"Stop all emails</button></form></body>")


@app.post("/u/{person_id}/{token}", response_class=HTMLResponse)
def unsubscribe(person_id: int, token: str) -> str:
    _check_token(person_id, token)
    with db.tx() as cur:
        email = db.val(cur, "select email from people where id = %s", person_id)
        if email:
            db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email', %s, 'One-click unsubscribe', 'link')",
                   email)
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('person', %s, 'One-click unsubscribe', 'link')",
               str(person_id))
        for e in db.all(cur, "select id from enrollments where person_id = %s and state in ('pending','active','paused')", person_id):
            outreach.stop_enrollment(cur, e["id"], "unsubscribed")
        audit.log(cur, "recipient", "unsubscribed", "person", person_id, {"via": "one_click"})
    return "<!doctype html><meta charset=utf-8><body style='font:16px system-ui;max-width:420px;margin:15vh auto'>Done. You won't hear from us again.</body>"


# ---------------------------------------------------------------- the web app

if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "No such endpoint.")
    index = WEB / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<p>Build the web app: <code>make web</code></p>")


# ---------------------------------------------------------------- the worker

def start_worker() -> None:
    db.pool()
    if not CONFIG.worker_inline:
        return

    def loop() -> None:
        while True:
            try:
                with db.tx() as cur:
                    simulated = db.val(cur, "select enabled from sim_clock")
                    if not simulated:
                        scheduler.tick(cur)
                if not simulated:
                    jobs.run_ready()
            except Exception:
                log.exception("worker tick failed")
            time.sleep(5)

    threading.Thread(target=loop, daemon=True, name="worker").start()
