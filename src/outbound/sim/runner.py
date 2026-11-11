"""Runs the simulated world forward in time: signals arrive, the desk works, simulated buyers react, and simulated
reps do what reps do (accept most proposals, approve most drafts, answer hot replies, book meetings).

The reps are deliberately imperfect and slower near the end of the run, so the demo opens with work waiting."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

from .. import clock, db, jobs, outreach, pipeline, plays, replies, scheduler, scoring, timeutil
from ..db import J
from ..seed import load
from . import signals_gen, world

log = logging.getLogger("outbound.sim")


def reset(url: str | None = None) -> None:
    with db.tx() as cur:
        db.run(cur, "drop schema public cascade; create schema public;")
    db.migrate(url)


def setup(*, start: datetime, seed: int = 7, n_accounts: int = 460) -> dict:
    clock.set_sim(start)
    with db.tx() as cur:
        load.load_catalog(cur, start=start)
        info = world.build(cur, seed=seed, n_accounts=n_accounts, start=start)
        for r in db.all(cur, "select id from accounts"):
            scoring.rescore(cur, r["id"])
        # Earlier history: a few months of signals already ingested, so scores start warm.
    return info


def _queue_day_signals(cur, rng: random.Random, day: datetime) -> int:
    raw = signals_gen.day_signals(cur, rng, day)
    n = 0
    for source, items in raw.items():
        for it in items:
            lag = timedelta(minutes=rng.randint(20, 6 * 60))
            payload = {"source": source, "raw": {**it, "observed_at": it["observed_at"].isoformat()}}
            db.run(cur, "insert into sim_events (at, kind, payload) values (%s, 'signal', %s)", it["observed_at"] + lag,
                   J(payload))
            n += 1
    return n


def _process_events(cur, until: datetime) -> int:
    n = 0
    for ev in db.all(cur, """select * from sim_events where not done and kind <> 'signal' and at <= %s order by at""", until):
        db.run(cur, "update sim_clock set at = greatest(at, %s)", ev["at"])
        p = ev["payload"]
        if ev["kind"] in ("reply", "bounce"):
            m = db.one(cur, "select * from messages where id = %s", p["message_id"])
            person = db.one(cur, "select * from people where id = %s", p["person_id"])
            mb = db.one(cur, "select * from mailboxes where id = %s", m["mailbox_id"])
            if ev["kind"] == "bounce":
                replies.ingest(cur, from_addr=f"mailer-daemon@{mb['domain']}", subject="Delivery Status Notification (Failure)",
                               raw=f"Address not found. Your message to {person['email']} could not be delivered.",
                               received_at=ev["at"], thread_key=m["thread_key"], provider_id=f"sim-ev-{ev['id']}")
            else:
                replies.ingest(cur, from_addr=person["email"] or "unknown@example.com", subject="Re: " + (m["subject"] or ""),
                               raw=p["text"], received_at=ev["at"], thread_key=m["thread_key"],
                               provider_id=f"sim-ev-{ev['id']}")
                db.run(cur, "update replies set extracted = extracted || %s where provider_id = %s",
                       J({"_sim_kind": p.get("kind")}), f"sim-ev-{ev['id']}")
        elif ev["kind"] == "complaint":
            from .. import sending
            sending.record_delivery_event(cur, p["message_id"], "complaint", {"source": "feedback loop"})
        elif ev["kind"] == "second_move_source":
            from .. import signals
            raw = dict(p)
            raw["observed_at"] = datetime.fromisoformat(raw["observed_at"])
            signals.ingest(cur, "social_feed", [raw])
        db.run(cur, "update sim_events set done = true where id = %s", ev["id"])
        n += 1
    return n


def _working(at: datetime, tzname: str) -> bool:
    local = at.astimezone(timeutil.tz(tzname))
    return local.weekday() < 5 and 9 <= local.hour < 18


def act_as_reps(cur, rng: random.Random, at: datetime, eagerness: float) -> None:
    reps = db.all(cur, "select * from users where role in ('sdr', 'manager')")
    for u in reps:
        if not _working(at, u["timezone"]) or rng.random() > eagerness:
            continue
        # Proposals: accept most, skip some with a reason.
        for ap in db.all(cur, "select id from account_plays where owner_id = %s and state = 'proposed' order by proposed_at limit 3",
                         u["id"]):
            if rng.random() < 0.82:
                plays.decide(cur, ap["id"], accept=True, user_id=u["id"])
            elif rng.random() < 0.5:
                plays.decide(cur, ap["id"], accept=False, user_id=u["id"],
                             reason=rng.choice(["Already talking to them through a partner", "Wrong timing for this account",
                                                "Too small for us right now"]))
        # Drafts: approve most, edit a few, reject a few.
        for m in db.all(cur, """select m.id, m.body, m.status from messages m join enrollments e on e.id = m.enrollment_id
                                join account_plays ap on ap.id = e.account_play_id
                                where ap.owner_id = %s and m.status in ('awaiting_approval', 'failed_gate')
                                order by m.created_at limit 6""", u["id"]):
            roll = rng.random()
            try:
                if m["status"] == "failed_gate":
                    if roll < 0.5:
                        outreach.reject(cur, m["id"], user_id=u["id"], reason="Did not pass the checks; skipping")
                    continue
                if roll < 0.80:
                    outreach.approve(cur, m["id"], user_id=u["id"])
                elif roll < 0.92:
                    outreach.approve(cur, m["id"], user_id=u["id"],
                                     body=m["body"].replace("Would a short call next week be useful?",
                                                            "Would 20 minutes next week be useful?"))
                else:
                    outreach.reject(cur, m["id"], user_id=u["id"], reason=rng.choice(
                        ["Tone is off for this person", "I know them, I'll write myself", "Wrong person for this"]))
            except ValueError:
                pass
        # Replies a person must label.
        for r in db.all(cur, """select r.* from replies r join tasks t on t.reply_id = r.id
                                where t.owner_id = %s and t.kind = 'review_reply' and t.status = 'open' limit 4""", u["id"]):
            truth = (r["extracted"] or {}).get("_sim_kind")
            label = {"positive": "interested", "not_now": "not_now", "not_interested": "not_interested",
                     "referral": "referral", "wrong_person": "wrong_person", "unsubscribe": "unsubscribe",
                     "ooo": "out_of_office"}.get(truth, "other")
            replies.handle(cur, r["id"], user_id=u["id"], outcome="labelled", label=label)
        # Hot replies: answer, and book a meeting when the buyer wants one.
        for r in db.all(cur, """select r.* from replies r join tasks t on t.reply_id = r.id and t.kind = 'reply'
                                where t.owner_id = %s and t.status = 'open' order by r.received_at limit 4""", u["id"]):
            if rng.random() < 0.85:
                if r["label"] in ("meeting_request", "interested") and rng.random() < 0.72 or rng.random() < 0.3:
                    starts = timeutil.add_business_days(at, rng.randint(2, 7))
                    pipeline.book_meeting(cur, account_id=r["account_id"], person_id=r["person_id"], starts_at=starts,
                                          source="sdr", owner_id=u["id"])
                    replies.handle(cur, r["id"], user_id=u["id"], outcome="meeting_booked")
                else:
                    replies.handle(cur, r["id"], user_id=u["id"], outcome="answered")
        # Tasks: calls and LinkedIn steps, done or skipped.
        for t in db.all(cur, """select id from tasks where owner_id = %s and status = 'open' and kind in
                                ('call','linkedin_connect','linkedin_message','research','referral') and due_at <= %s
                                order by due_at limit 6""", u["id"], at):
            db.run(cur, "update tasks set status = %s, done_at = %s where id = %s",
                   "done" if rng.random() < 0.75 else "skipped", at, t["id"])


def meetings_and_deals(cur, rng: random.Random, at: datetime) -> None:
    for m in db.all(cur, """select m.*, sa.need::float as need from meetings m join sim_accounts sa on sa.account_id = m.account_id
                            where m.status = 'booked' and m.starts_at < %s""", at):
        status = "held" if rng.random() < 0.84 else "no_show"
        pipeline.set_meeting_status(cur, m["id"], status)
        if status == "held":
            notes = rng.choice([
                "They close the books in 9 days and want it under 5.\nWorried about migration effort from Chargewise.\n"
                "Board wants clean usage revenue by next quarter.",
                "Billing runs on spreadsheets and Stripe invoices.\nNot sure about timing, audit in progress.\n"
                "Need finance and product to agree on one usage number.",
                "Evaluating Meterline as well.\nToo expensive was the first reaction, then asked about phased rollout.\n"
                "Want a sandbox with last month's usage data."])
            nid = pipeline.record_call_notes(cur, m["id"], notes, m["owner_id"])
            if rng.random() < 0.6:
                pipeline.learn_from(cur, nid, m["owner_id"])
            if rng.random() < 0.22 + 0.5 * m["need"]:
                db.run(cur, "insert into sim_events (at, kind, payload) values (%s, 'opportunity', %s)",
                       at + timedelta(days=rng.randint(2, 15)),
                       J({"account_id": m["account_id"], "amount": rng.randint(30, 180) * 100000}))
    for ev in db.all(cur, "select * from sim_events where kind = 'opportunity' and not done and at <= %s", at):
        p = ev["payload"]
        name = db.val(cur, "select name from accounts where id = %s", p["account_id"])
        pipeline.opportunity_created(cur, account_id=p["account_id"], crm_id=f"CRM-OPP-{ev['id']}", name=f"{name} new business",
                                     amount_cents=p["amount"], stage="Discovery", created_at=ev["at"])
        db.run(cur, "update sim_events set done = true where id = %s", ev["id"])


def _hour(cur_rng: random.Random, at: datetime, eagerness: float, totals: dict) -> None:
    with db.tx() as cur:
        db.run(cur, "update sim_clock set at = %s", at)
        totals["events"] += _process_events(cur, at)
        db.run(cur, "update sim_clock set at = %s", at)
        scheduler.tick(cur)
    totals["jobs"] += jobs.run_ready(limit=2000)
    with db.tx() as cur:
        act_as_reps(cur, cur_rng, at, eagerness)
        meetings_and_deals(cur, cur_rng, at)
    totals["jobs"] += jobs.run_ready(limit=2000)


def run(days: int, *, seed: int = 11, slow_last_days: int = 2, idle_hours: int = 40) -> dict:
    rng = random.Random(seed)
    with db.tx() as cur:
        start = clock.now(cur)
    totals = {"signals": 0, "events": 0, "jobs": 0}
    for d in range(days):
        day = start + timedelta(days=d)
        with db.tx() as cur:
            totals["signals"] += _queue_day_signals(cur, rng, day.replace(hour=0, minute=0, second=0, microsecond=0))
        eagerness = 0.55 if d < days - slow_last_days else 0.12
        for h in range(24):
            # The reps stop a day before the demo opens, so it opens on a morning with work waiting.
            idle = (days - d) * 24 - h <= idle_hours
            _hour(rng, day + timedelta(hours=h), 0.0 if idle else eagerness, totals)
        log.info("simulated day %s: %s", d + 1, totals)
    with db.tx() as cur:
        db.run(cur, "update sim_clock set at = %s", start + timedelta(days=days))
    return totals


def run_hours(hours: int, *, seed: int | None = None) -> dict:
    """Move the demo forward from the web app. New days get their signals when the clock crosses midnight."""
    with db.tx() as cur:
        start = clock.now(cur)
    rng = random.Random(seed if seed is not None else int(start.timestamp()))
    totals = {"signals": 0, "events": 0, "jobs": 0}
    for h in range(1, hours + 1):
        at = start + timedelta(hours=h)
        if at.date() != (at - timedelta(hours=1)).date():
            with db.tx() as cur:
                totals["signals"] += _queue_day_signals(cur, rng, at.replace(hour=0, minute=0, second=0, microsecond=0))
        _hour(rng, at, 0.5, totals)
    return totals
