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


def setup(*, start: datetime, seed: int = 7, n_accounts: int = 3000) -> dict:
    clock.set_sim(start)
    from .. import llm
    llm.SIM_CHARGE = True  # the demo's AI work costs what it would
    with db.tx() as cur:
        load.load_catalog(cur, start=start)
        info = world.build(cur, seed=seed, n_accounts=n_accounts, start=start)
        _sim_placement(cur, random.Random(seed), start)
        db.run(cur, """update sending_domains set dns_detail = jsonb_build_object('seeded', jsonb_build_object('spf', spf,
                       'dkim', dkim, 'dmarc', dmarc, 'aligned', dmarc_aligned, 'policy', dmarc_policy))""")
        first = db.val(cur, "select domain from sending_domains order by domain limit 1")
        db.run(cur, "insert into sim_dns (domain, dkim_broken_from, dkim_broken_until) values (%s, %s, %s)",
               first, start + timedelta(days=36), start + timedelta(days=39))
        pipeline.crm_sync(cur, {})  # the first read of the CRM: its history becomes the desk's
        for r in db.all(cur, "select id from accounts"):
            scoring.rescore(cur, r["id"])
        # Earlier history: a few months of signals already ingested, so scores start warm.
    return info


def _sim_placement(cur, rng: random.Random, start: datetime) -> None:
    """Hidden truth for seed tests and simulated buyers: most mailboxes land well; one starts landing in spam at
    Outlook about four weeks in, so the desk has something real to catch (a 21-day test run never reaches it)."""
    boxes = [r["id"] for r in db.all(cur, "select id from mailboxes order by id")]
    for i, mb in enumerate(boxes):
        worse = i == 2
        db.run(cur, """insert into sim_mailboxes (mailbox_id, gmail, outlook, worsens_from, worse_outlook)
                       values (%s, %s, %s, %s, %s)""", mb, round(rng.uniform(0.9, 0.98), 2), round(rng.uniform(0.86, 0.96), 2),
               start + timedelta(days=27) if worse else None, 0.6 if worse else None)


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
    for ev in db.all(cur, """select * from sim_events where not done and kind not in ('signal', 'opportunity') and at <= %s order by at""", until):
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
        elif ev["kind"] == "li_accept":
            from .. import sdr_steps
            sdr_steps.connection_accepted(cur, p["person_id"], user_id=None, source="linkedin")
        elif ev["kind"] == "li_reply":
            from .. import sdr_steps
            sdr_steps.linkedin_reply(cur, p["person_id"], text=p["text"], received_at=ev["at"], provider_id=f"sim-ev-{ev['id']}")
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


LI_REPLIES = ["Thanks for connecting. What does this look like for a team our size?",
              "Happy to chat. Can you send a couple of times next week?",
              "Appreciate the note. We are not looking at this right now.",
              "Interesting timing, we were just talking about billing. Who should I loop in?"]


def work_task(cur, rng: random.Random, t: dict, u: dict, at: datetime) -> None:
    """One SDR task, done the way people do them: most get done, some skipped, calls mostly reach voicemail."""
    from .. import sdr_steps
    need = t["need"] or 0.3
    user = {"id": u["id"], "role": u["role"]}
    if rng.random() < 0.15:
        outcome = "skipped"
    elif t["kind"] == "linkedin_connect":
        outcome = "sent" if rng.random() < 0.92 else "already_connected"
    elif t["kind"] == "linkedin_message":
        connected = db.val(cur, "select exists (select 1 from touches where person_id = %s and kind = 'linkedin_accepted')",
                           t["person_id"])
        outcome = "sent" if connected else "not_connected"
    elif t["kind"] == "call":
        r = rng.random()
        spoke = 0.08 + 0.14 * need
        outcome = "connected" if r < spoke else "wrong_number" if r < spoke + 0.04 else "voicemail" if r < spoke + 0.5 else "no_answer"
    else:
        outcome = "done"
    try:
        sdr_steps.complete(cur, t["id"], user=user, outcome=outcome)
    except ValueError:
        db.run(cur, "update tasks set status = 'skipped', done_at = %s, note = 'Not sent: refused by the desk' "
                    "where id = %s and status = 'open'", at, t["id"])
        return
    # What the buyer does on LinkedIn, later.
    if t["kind"] == "linkedin_connect" and outcome == "sent":
        if rng.random() < 0.22 + 0.35 * need:
            db.run(cur, "insert into sim_events (at, kind, payload) values (%s, 'li_accept', %s)",
                   at + timedelta(hours=rng.randint(3, 96)), J({"person_id": t["person_id"]}))
    if t["kind"] == "linkedin_message" and outcome == "sent" and rng.random() < 0.06 + 0.2 * need:
        db.run(cur, "insert into sim_events (at, kind, payload) values (%s, 'li_reply', %s)",
               at + timedelta(hours=rng.randint(2, 72)), J({"person_id": t["person_id"], "text": rng.choice(LI_REPLIES)}))


def _working(at: datetime, tzname: str) -> bool:
    local = at.astimezone(timeutil.tz(tzname))
    return local.weekday() < 5 and 9 <= local.hour < 18


# How often SDRs approve a draft without touching it, below the 0.92 of drafts they approve at all: the rest of those
# they approve after an edit (a draft with no ask to rewrite, a break-up note, goes as it was).
UNEDITED = 0.72


def sdr_edit(body: str) -> str:
    """An SDR's edit: their own ask in place of the drafted one. A draft with no ask (a break-up note) is approved as
    it was."""
    from ..sim_llm import ASK
    for ask in ASK:
        if ask in body:
            return body.replace(ask, "Would 20 minutes next week be useful?", 1)
    return body


def manager_reviews_autonomy(cur, at: datetime) -> None:
    """Monday mornings the manager looks at each live play's checks and approves the next stage when the desk says it
    is earned: the same rule the Plays page applies to a person's click (a manager, one stage, every check passed)."""
    from .. import audit, views
    manager = db.one(cur, "select id from users where role = 'manager' and active order by id limit 1")
    if manager is None:
        return
    # Moving a play off the research stage is the manager's own judgement (DECISIONS 22), not a count, so it is left.
    for p in db.all(cur, "select * from plays where status = 'live' and autonomy <> 'research' order by id"):
        check = views.promotion_check(cur, p)
        if not (check["ready"] and check["next"]):
            continue
        reason = "Met every check: " + "; ".join(f"{c['label']} {c['value']}" for c in check["checks"])
        db.run(cur, "update plays set autonomy = %s where id = %s", check["next"], p["id"])
        db.run(cur, "insert into play_stage_changes (play_id, from_stage, to_stage, reason, decided_by) values (%s,%s,%s,%s,%s)",
               p["id"], p["autonomy"], check["next"], reason, manager["id"])
        audit.log(cur, "person", "play_changed", "play", p["id"], {"autonomy": check["next"], "reason": reason},
                  actor_id=manager["id"])


# What the manager and GTM do with play suggestions, in the order they are opened, once one has waited two weeks: GTM
# makes the first a draft play, the manager sets the next aside for now, and says no to the one after. One that comes
# back after a "not now" waits for a person, as the desk asks. A planted routine (README).
SUGGESTION_ROUTINE = ["draft", "not_now", "dismissed"]


def review_suggestions(at: datetime) -> None:
    """Tuesdays, on its own transactions through the same code the web app calls (the API's own functions)."""
    from pydantic import ValidationError

    from .. import play_editor, suggestions
    from ..api import app as api
    from ..seed import catalog
    with db.tx() as cur:
        gtm = db.one(cur, "select id, role from users where role = 'gtm' and active order by id limit 1")
        manager = db.one(cur, "select id, role from users where role = 'manager' and active order by id limit 1")
        decided = db.val(cur, "select count(*) from play_suggestions where status in ('drafted', 'not_now', 'dismissed')")
        waiting = db.all(cur, """select id, theme_id from play_suggestions where status = 'open'
                                 and created_at < %s - interval '14 days' and not exists (select 1 from play_suggestions
                                   x where x.theme_id = play_suggestions.theme_id and x.status = 'not_now')
                                 order by created_at, id""", at)
    for s in waiting:
        if decided >= len(SUGGESTION_ROUTINE):
            return
        step = SUGGESTION_ROUTINE[decided]
        if step == "draft" and gtm:
            with db.tx() as cur:
                full = suggestions.one(cur, s["id"])
            d = full["draft"]
            body = play_editor.PlayIn(
                name=d["name"], hypothesis=d["hypothesis"],
                trigger={"any_of": d["trigger"]["any_of"], "fit_tiers": ["A", "B"], "min_priority": 40, "within_days": 30},
                personas=d["personas"], max_people=3, sequence=catalog.STANDARD, angle=d["angle"], holdout_pct=20,
                latency_hours=48, suggested_from=s["theme_id"])
            try:
                api.create_play(body, gtm)
            except (ValidationError, api.HTTPException) as exc:
                log.info("suggestion %s not drafted: %s", s["id"], exc)
                continue
        elif step in ("not_now", "dismissed") and manager:
            with db.tx() as cur:
                suggestions.decide(cur, s["id"], decision=step, user_id=manager["id"],
                                   reason="Revisit after Q1 planning" if step == "not_now" else "An existing play already covers it")
        decided += 1


def skip_reasons(employees: int | None) -> list[str]:
    """Why an SDR passes on a proposal, in words that fit the account: nobody calls a 300-person company too small."""
    out = ["Already talking to them through a partner", "Wrong timing for this account"]
    if employees is not None and employees < 150:
        out.append("Too small for us right now")
    if employees is not None and employees >= 2000:
        out.append("The enterprise team works this account")
    return out


def act_as_reps(cur, rng: random.Random, at: datetime, eagerness: float) -> None:
    reps = db.all(cur, "select * from users where role in ('sdr', 'manager')")
    for u in reps:
        if not _working(at, u["timezone"]) or rng.random() > eagerness:
            continue
        # Proposals: accept most, skip some with a reason.
        for ap in db.all(cur, """select ap.id, a.employees from account_plays ap join accounts a on a.id = ap.account_id
                                 where ap.owner_id = %s and ap.state = 'proposed' order by ap.proposed_at limit 3""",
                         u["id"]):
            if rng.random() < 0.82:
                plays.decide(cur, ap["id"], accept=True, user_id=u["id"])
            elif rng.random() < 0.5:
                plays.decide(cur, ap["id"], accept=False, user_id=u["id"], reason=rng.choice(skip_reasons(ap["employees"])))
        # Drafts: approve most, edit a few, reject a few.
        for m in db.all(cur, """select m.id, m.body, m.status, pl.key as play from messages m
                                join enrollments e on e.id = m.enrollment_id
                                join account_plays ap on ap.id = e.account_play_id join plays pl on pl.id = ap.play_id
                                where ap.owner_id = %s and m.status in ('awaiting_approval', 'failed_gate') and m.channel = 'email'
                                order by m.created_at limit 6""", u["id"]):
            roll = rng.random()
            try:
                if m["status"] == "failed_gate":
                    if roll < 0.5:
                        outreach.reject(cur, m["id"], user_id=u["id"], reason="Did not pass the checks; skipping")
                    continue
                if roll < UNEDITED:
                    outreach.approve(cur, m["id"], user_id=u["id"])
                elif roll < 0.92:
                    outreach.approve(cur, m["id"], user_id=u["id"], body=sdr_edit(m["body"]))
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
                     "ooo": "out_of_office", "auto": "auto_reply"}.get(truth, "other")
            replies.handle(cur, r["id"], user_id=u["id"], outcome="labelled", label=label)
        # Hot replies: answer, and book a meeting when the buyer wants one.
        for r in db.all(cur, """select r.* from replies r join tasks t on t.reply_id = r.id and t.kind = 'reply'
                                where t.owner_id = %s and t.status = 'open' order by r.received_at limit 4""", u["id"]):
            if rng.random() < 0.85:
                if r["label"] in ("meeting_request", "interested") and rng.random() < 0.85 or rng.random() < 0.45:
                    starts = timeutil.add_business_days(at, rng.randint(2, 7))
                    pipeline.book_meeting(cur, account_id=r["account_id"], person_id=r["person_id"], starts_at=starts,
                                          source="sdr", owner_id=u["id"])
                    replies.handle(cur, r["id"], user_id=u["id"], outcome="meeting_booked")
                else:
                    replies.handle(cur, r["id"], user_id=u["id"], outcome="answered")
        # Tasks: calls and LinkedIn steps, worked the way an SDR would, with outcomes the desk records.
        for t in db.all(cur, """select t.id, t.kind, t.person_id, sa.need::float as need from tasks t
                                left join people p on p.id = t.person_id left join sim_accounts sa on sa.account_id = p.account_id
                                where t.owner_id = %s and t.status = 'open' and t.kind in
                                ('call','linkedin_connect','linkedin_message','research','referral') and t.due_at <= %s
                                order by t.due_at limit 6""", u["id"], at):
            work_task(cur, rng, t, u, at)


# What buyers say on first calls, weighted so some themes recur across calls the way they do in real life. Each is
# written a few ways, so filing them under themes has real work to do.
REASONS = [(("Board wants clean usage revenue by next quarter.", "Their board wants usage revenue reported cleanly by next quarter.",
             "Board is pushing for clean usage revenue numbers next quarter."), 5),
           (("They close the books in 9 days and want it under 5.", "Close takes 9 days today; they want it under 5.",
             "Want to get the monthly close from 9 days to under 5."), 4),
           (("Need finance and product to agree on one usage number.", "Finance and product report different usage numbers; they need one.",
             "Want one usage number that finance and product both trust."), 4),
           (("Want invoices to match contracts without manual fixes.", "Want invoices to match what the contract says, with no manual fixes."), 3),
           (("Audit flagged revenue recognition on usage contracts.", "Auditors flagged rev rec on the usage contracts.",
             "Last audit raised revenue recognition issues on usage contracts."), 1),
           (("Need to launch usage pricing for the API product in Q1.", "Launching usage pricing for the API product in Q1 and need billing ready.",
             "Want usage-based pricing live for the API product by Q1."), 1),
           (("Want one place for contract terms and invoices.",), 1),
           (("Close team spends a week reconciling usage by hand.", "Their close team reconciles usage by hand for a week every month.",
             "A week of every close goes to reconciling usage manually."), 1)]
OBJECTIONS = [("Worried about migration effort and losing invoice history.", 5), ("Not sure about timing, a renewal is due in March.", 3),
              ("Too expensive was the first reaction; asked about a phased rollout.", 3),
              ("Concern about adding another tool for a small finance team.", 2),
              ("Worried the ERP sync will need engineering time.", 3), ("Not sure who owns billing after the reorg.", 1)]
TOOLS = [(("Currently on Chargewise, contract ends in June.",), 4),
         (("Evaluating Meterline as well.", "Also looking at Meterline.", "Meterline is on their shortlist too."), 1),
         (("Billing runs on spreadsheets and Stripe invoices.",), 3), (("Built an in-house billing script that one engineer maintains.",), 2)]
CONTEXT = ["On the call: the CFO and the controller.", "Next step: a sandbox with last month's usage data.",
           "Follow up with pricing for 40,000 invoices a month.", "They will bring the data team to the next call."]
# A planted relationship, so the demo has a true pattern for play suggestions to find (README, "What is real and what
# is simulated"): accounts that came in on these four signals raise this reason (or name this competitor) on 90% of
# first calls. To keep the contrast clear, these four were also made rarer everywhere else: their weight in the
# general pool above is 1 (it was 2, 2, 2 and 3 before the plant). Nothing else in the notes depends on the signal.
PLANTED = {"new_exec": REASONS[4][0], "hiring_function": REASONS[7][0], "pricing_change": REASONS[5][0],
           "competitor_review": TOOLS[1][0]}
PLANTED_SHARE = 0.9
# Who said it and how, so the same reason from ten companies reads like ten people, not one line pasted ten times.
SAID = ["{}", "Controller: {}", "CFO said it twice: {}", "{} Came up before we asked.", "Their VP Finance brought it up: {}",
        "{} It was the first thing they raised.", "Head of billing, unprompted: {}"]


# Reasons a buyer gives for not buying, and lines worth keeping word for word.
NOT_BUYING = ["No budget until the new fiscal year.", "They just renewed their billing tool and signed for two years."]
SAID_ON_CALLS = ["Month-end is three people and a spreadsheet.", "Every usage invoice gets touched by hand twice.",
                 "Our auditors ask the same question every quarter.", "Sales and finance never agree on the number."]

# What a buyer says about the billing they run today: always the account's own tool (sim_accounts.billing).
ON_TODAY = {"Chargewise": "Currently on Chargewise, contract ends in June.",
            "Meterline": "Currently on Meterline; the renewal comes up in the spring.",
            "Stripe Billing": "Billing runs on Stripe Billing today.",
            "an in-house billing system": "Built an in-house billing script that one engineer maintains.",
            "spreadsheets and Stripe invoices": "Billing runs on spreadsheets and Stripe invoices."}


def call_notes(rng: random.Random, signal_type: str | None = None, billing: str | None = None) -> str:
    def pick(pool, k):
        return [rng.choice(x) if isinstance(x, tuple) else x
                for x in rng.choices([x for x, _ in pool], weights=[w for _, w in pool], k=k)]
    lines = [rng.choice(CONTEXT)] + pick(REASONS, rng.randint(1, 2))
    if signal_type in PLANTED and rng.random() < PLANTED_SHARE:
        said = rng.choice(PLANTED[signal_type])
        lines.append(rng.choice(SAID).format(said))
    tools = pick(TOOLS, rng.randint(0, 1))
    if billing in ON_TODAY:
        # A line about the tool they run is about their own tool; a Meterline user is not "also looking at Meterline".
        tools = [t if t in TOOLS[1][0] and billing != "Meterline" else ON_TODAY[billing] for t in tools]
    lines += pick(OBJECTIONS, rng.randint(0, 2)) + tools
    # Drawn last, so the lines above are what they were before these were added.
    if rng.random() < 0.15:
        lines.append(rng.choice(NOT_BUYING))
    if rng.random() < 0.2:
        lines.append(f'In their words: "{rng.choice(SAID_ON_CALLS)}"')
    return "\n".join(dict.fromkeys(lines))


STAGES = ["Discovery", "Evaluation", "Proposal", "Negotiation"]
LOSS = [("timing", 4), ("budget", 3), ("competitor", 2), ("no decision", 3)]


def _crm_deal(cur, rng: random.Random, at: datetime, account_id: int, need: float, contact_email: str | None) -> None:
    """A deal appears in the CRM, the way a sales team would open one; the desk only learns of it by reading."""
    name = db.val(cur, "select name from accounts where id = %s", account_id)
    n = db.val(cur, "select count(*) from sim_crm_deals") + 1
    db.run(cur, """insert into sim_crm_deals (crm_id, account_id, name, amount_cents, stage, created_at, updated_at,
                                             contact_email, close_on, will_win)
                   values (%s,%s,%s,%s,'Discovery',%s,%s,%s,%s,%s)""",
           f"006SIM{n:06d}", account_id, f"{name} new business", rng.randint(30, 180) * 100000, at, at, contact_email,
           at + timedelta(days=rng.randint(20, 70)), rng.random() < 0.2 + 0.45 * need)


def _open_deal(cur, account_id: int) -> bool:
    return db.val(cur, "select exists (select 1 from sim_crm_deals where account_id = %s and closed_at is null)", account_id)


def meetings_and_deals(cur, rng: random.Random, at: datetime) -> None:
    for m in db.all(cur, """select m.*, sa.need::float as need, sa.billing, p.email, s.type_key,
                                   coalesce(m.owner_id, a.owner_id) as writer
                            from meetings m join sim_accounts sa on sa.account_id = m.account_id
                            join accounts a on a.id = m.account_id left join people p on p.id = m.person_id
                            left join account_plays ap on ap.id = m.account_play_id left join signals s on s.id = ap.trigger_signal_id
                            where m.status = 'booked' and m.starts_at < %s""", at):
        status = "held" if rng.random() < 0.84 else "no_show"
        pipeline.set_meeting_status(cur, m["id"], status)
        if status == "held":
            # What was said on the call has its own random stream, so the notes never shift the rest of the world.
            notes = call_notes(random.Random(f"notes:{m['id']}"), m["type_key"], m["billing"])
            nid = pipeline.record_call_notes(cur, m["id"], notes, m["writer"])
            if rng.random() < 0.9:
                pipeline.learn_from(cur, nid, m["writer"])
            if rng.random() < 0.22 + 0.5 * m["need"]:
                db.run(cur, "insert into sim_events (at, kind, payload) values (%s, 'opportunity', %s)",
                       at + timedelta(days=rng.randint(2, 8)), J({"account_id": m["account_id"], "email": m["email"]}))
    for ev in db.all(cur, "select * from sim_events where kind = 'opportunity' and not done and at <= %s", at):
        p = ev["payload"]
        need = db.val(cur, "select need::float from sim_accounts where account_id = %s", p["account_id"]) or 0.3
        # One open new-business deal per company: a second good meeting moves the open deal along, it does not open
        # another (found 2026-11-11: two deals from one meeting at one account).
        if not _open_deal(cur, p["account_id"]):
            _crm_deal(cur, rng, ev["at"], p["account_id"], need, p.get("email"))
        db.run(cur, "update sim_events set done = true where id = %s", ev["id"])
    # Deals move: a stage every week or two, then they close on their hidden date.
    for d in db.all(cur, "select * from sim_crm_deals where closed_at is null and updated_at < %s - interval '9 days'", at):
        if at >= d["close_on"]:
            reason = None if d["will_win"] else rng.choices([r for r, _ in LOSS], weights=[w for _, w in LOSS])[0]
            db.run(cur, """update sim_crm_deals set closed_at = %s, won = %s, loss_reason = %s, updated_at = %s,
                           stage = %s where id = %s""", at, d["will_win"], reason, at,
                   "Closed Won" if d["will_win"] else "Closed Lost", d["id"])
        elif d["stage"] in STAGES and STAGES.index(d["stage"]) < len(STAGES) - 1:
            db.run(cur, "update sim_crm_deals set stage = %s, updated_at = %s where id = %s",
                   STAGES[STAGES.index(d["stage"]) + 1], at, d["id"])
    if at.hour == 15:
        _organic(cur, rng, at)
    if at.hour == 14 and at.weekday() == 0:
        manager_reviews_autonomy(cur, at)
    if at.hour == 16 and at.weekday() == 0 and rng.random() < 0.5:
        _rebalance(cur, rng, at)


def _rebalance(cur, rng: random.Random, at: datetime) -> None:
    """Sales ops moves a few accounts between SDRs in the CRM, and once in a while to an AE who is not on the desk."""
    sdrs = [r["email"] for r in db.all(cur, "select email from users where role = 'sdr' order by id")]
    for a in db.all(cur, """select a.id, u.email from accounts a left join users u on u.id = a.owner_id
                            where a.lifecycle = 'prospect' order by a.id offset %s limit 3""", rng.randint(0, 400)):
        to = "ae.team@lumenledger.example" if rng.random() < 0.15 else rng.choice([e for e in sdrs if e != a["email"]] or sdrs)
        db.run(cur, "insert into sim_crm_owner_changes (account_id, owner_email, updated_at) values (%s,%s,%s)", a["id"], to, at)


def _organic(cur, rng: random.Random, at: datetime) -> None:
    """What happens without outbound, once a day: some companies ask for a demo, and sales opens some deals on its
    own. Held-back accounts get these too, so the comparison group measures what outbound adds, not zero."""
    for a in db.all(cur, """select a.id, sa.need::float as need from accounts a join sim_accounts sa on sa.account_id = a.id
                            where a.lifecycle = 'prospect'"""):
        if rng.random() < 0.0012 * a["need"]:
            person = db.one(cur, "select id, email from people where account_id = %s and status = 'active' order by id limit 1", a["id"])
            if person:
                pipeline.book_meeting(cur, account_id=a["id"], person_id=person["id"],
                                      starts_at=at + timedelta(days=rng.randint(2, 6)), source="inbound",
                                      external_id=f"sim-inbound-{a['id']}-{at:%Y%m%d}")
        elif rng.random() < 0.0004 * a["need"] and not _open_deal(cur, a["id"]):
            _crm_deal(cur, rng, at, a["id"], a["need"], None)


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
    if at.hour == 15 and at.weekday() == 1 and eagerness > 0:
        review_suggestions(at)
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
