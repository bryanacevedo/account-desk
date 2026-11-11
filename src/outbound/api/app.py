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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import (audit, db, gate, jobs, monitors, outreach, pipeline, plays, replies, scheduler, scoring, sending,  # noqa: F401
                signals, views)
from ..config import CONFIG

log = logging.getLogger("outbound.api")
WEB = Path(__file__).resolve().parents[3] / "web" / "dist"
app = FastAPI(title="Outbound Desk", docs_url="/api/docs", openapi_url="/api/openapi.json")


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


def current_user(request: Request) -> dict:
    with db.tx() as cur:
        if CONFIG.auth_mode == "header":
            email = request.headers.get(CONFIG.auth_header, "").strip().lower()
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
                                        where m.status in ('awaiting_approval','failed_gate') and (ap.owner_id = %s or %s)""",
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


@app.get("/api/accounts")
def accounts(view: Literal["priority", "in_play", "rising", "all"] = "priority", q: str | None = None,
             owner: int | None = None, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return {"accounts": views.accounts(cur, q=(q or "")[:80] or None, view=view, owner=owner)}


@app.get("/api/accounts/{account_id}")
def account(account_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        a = views.account(cur, account_id, money=money(u))
    if a is None:
        raise HTTPException(404, "No such account.")
    return a


@app.get("/api/signals")
def signals_page(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return views.signals_page(cur)


@app.get("/api/plays")
def plays_page(u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return {"plays": views.plays_page(cur, money=money(u))}


@app.get("/api/messages/{message_id}")
def message(message_id: int, u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        m = views.message(cur, message_id)
    if m is None:
        raise HTTPException(404, "No such message.")
    return m


@app.get("/api/replies")
def replies_page(view: Literal["all", "hot", "needs_person"] = "all", u: dict = Depends(current_user)) -> dict:
    with db.tx() as cur:
        return {"replies": views.replies_page(cur, view=view)}


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
            raise bad_request(exc)
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
            outreach.approve(cur, message_id, user_id=u["id"], subject=body.subject, body=body.body)
        except ValueError as exc:
            raise bad_request(exc)
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
        if body.outcome == "meeting_booked":
            if not r["account_id"]:
                raise HTTPException(422, "This reply is not tied to an account.")
            at = body.meeting_at or (db.val(cur, "select app_now()") + timedelta(days=3))
            pipeline.book_meeting(cur, account_id=r["account_id"], person_id=r["person_id"], starts_at=at,
                                  source="sdr", owner_id=u["id"])
        replies.handle(cur, reply_id, user_id=u["id"], outcome=body.outcome, label=body.label)
        return views.reply(cur, reply_id)


@app.post("/api/tasks/{task_id}/done")
def task_done(task_id: int, skipped: bool = False, u: dict = Depends(writer)) -> dict:
    with db.tx() as cur:
        n = db.run(cur, "update tasks set status = %s, done_at = app_now() where id = %s and status = 'open' "
                        "and (owner_id = %s or %s)", "skipped" if skipped else "done", task_id, u["id"], u["role"] != "sdr")
    if not n:
        raise HTTPException(404, "No open task with that id for you.")
    return {"ok": True}


class MeetingStatus(BaseModel):
    status: Literal["held", "no_show", "cancelled"]
    notes: str | None = Field(None, max_length=8000)
    learn: bool = False


@app.post("/api/meetings/{meeting_id}/status")
def meeting_status(meeting_id: int, body: MeetingStatus, u: dict = Depends(writer)) -> dict:
    with db.tx() as cur:
        pipeline.set_meeting_status(cur, meeting_id, body.status, user_id=u["id"])
        kept = 0
        if body.notes:
            nid = pipeline.record_call_notes(cur, meeting_id, body.notes, u["id"])
            if body.learn:
                kept = pipeline.learn_from(cur, nid, u["id"])
    return {"ok": True, "learnings": kept}


class PlayChange(BaseModel):
    status: Literal["live", "paused"] | None = None
    autonomy: Literal["research", "draft", "supervised", "autonomous"] | None = None
    reason: str = Field(min_length=3, max_length=300)


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
            db.run(cur, "update plays set status = %s where id = %s", body.status, play_id)
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
    if not hmac.compare_digest(outreach.unsubscribe_token(person_id), token):
        raise HTTPException(404, "This link is not valid.")


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

@app.on_event("startup")
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
