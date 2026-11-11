"""How simulated people react to an email: reply, ignore, bounce, complain, or send an out-of-office.

Reactions come from the company's hidden need, the person's fit to the message, how fresh the reason for writing
is, and whether the message cites real facts. Reply texts are written like real replies, with quoted history,
signatures, other languages and the occasional trap (an "unsubscribe" inside a quoted footer)."""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from .. import db
from ..adapters.sim import sim_inbox_rate
from ..db import J

POSITIVE = [
    "Hi {sender}, good timing actually. We're feeling this at month end. Can you send a couple of times next week?",
    "{sender}, we're two weeks from quarter close and this is exactly the mess. Thursday or Friday afternoon?",
    "Fair point on the invoicing. Our controller has been asking the same thing. Open to 30 minutes.",
    "We moved two products to usage pricing this year and billing hasn't caught up. Let's find a time.",
    "Not sure we need a new tool, but I'm curious how you handle credits. Can you walk me through it?",
    "Appreciate the specific note. Can we do something early next week? Mornings are best.",
    "Yes. Add Priya from finance systems to the invite, she owns {stack}.",
    "How long does a rollout usually take for a team our size? If it's under a quarter, let's talk.",
    "Send me something I can forward to our CFO first, then we can set up a call.",
    "Thanks for reaching out. This is on our list for Q1. Happy to take a call, does Thursday work?",
    "Interesting. How does this work with {stack}? If it does, I'd like to see it.",
    "We're evaluating options right now. What does pricing look like for a team our size?",
    "Yes, let's talk. Loop in my colleague too, she runs billing ops.",
    "Can you share a case study from a company like ours first? Then happy to meet.",
]
NOT_NOW = [
    "Not a priority this quarter. Try me again in {month}.",
    "We just signed a renewal with our current vendor, reach back out in {month}.",
    "Busy with our audit until {month}. Ping me after that.",
]
NOT_INTERESTED = ["No thanks, we're all set.", "Not interested, please don't follow up.",
                  "We built this in house and we're happy with it. Thanks though."]
REFERRAL = ["I'm not the right person, {ref_name} runs our billing. You can reach them at {ref_email}.",
            "{ref_name} owns this area, I'd talk to them.",
            "Please speak with {ref_name} ({ref_title}) instead."]
WRONG = ["I don't handle this, sorry.", "Wrong person, I'm in a different team now."]
UNSUB = ["Please remove me from your list.", "Unsubscribe", "Stop emailing me.",
         "Bitte keine weiteren E-Mails.", "Por favor, no me envíen más correos.", "Merci de ne plus me contacter."]
OOO = ["I'm out of the office until {date} with limited access to email. For urgent matters contact finance@{domain}.",
       "Automatic reply: I am on leave and will return on {date}.",
       "Abwesenheitsnotiz: Ich bin bis {date} nicht im Büro."]
ES_POS = ["Hola {sender}, nos interesa. ¿Podemos hablar la semana que viene?"]
DE_POS = ["Hallo {sender}, klingt interessant. Haben Sie nächste Woche Zeit für einen Termin?"]
SIGS = ["\n\n--\n{name}\n{title}\n{company}", "\n\nBest,\n{first}\n\nSent from my iPhone", "\n\nThanks,\n{first}",
        "\n\n{name} | {title}\nThis email and any attachments are confidential. If you received it in error, please "
        "unsubscribe the sender and delete it."]


def _quote(original: str, sender: str, at: datetime) -> str:
    quoted = "\n".join("> " + line for line in original.splitlines())
    return f"\n\nOn {at:%a, %d %b %Y at %H:%M}, {sender} wrote:\n{quoted}"


def on_send(cur, message: dict, person_id: int, mailbox: dict, at: datetime) -> None:
    sp = db.one(cur, "select * from sim_people where person_id = %s", person_id)
    if sp is None:
        return
    p = db.one(cur, "select p.*, a.name as company, a.primary_domain, a.tech, sa.need::float as need from people p "
                    "join accounts a on a.id = p.account_id join sim_accounts sa on sa.account_id = a.id "
                    "where p.id = %s", person_id)
    rng = random.Random(f"{message['id']}:{person_id}")
    email_sent_to = (p["email"] or "").lower()
    if sp["email_truth"] == "invalid" or (sp["true_email"] or "").lower() != email_sent_to:
        _event(cur, at + timedelta(minutes=rng.randint(1, 20)), "bounce", message, person_id)
        return
    if sp["email_truth"] == "catch_all" and rng.random() < 0.3:
        _event(cur, at + timedelta(minutes=rng.randint(1, 30)), "bounce", message, person_id)
        return
    # Mail that lands in spam is never read: no reply, no complaint. The buyer's provider follows their company domain.
    provider = "outlook" if int(hashlib.md5(p["primary_domain"].encode()).hexdigest(), 16) % 5 < 2 else "gmail"
    if mailbox and rng.random() >= sim_inbox_rate(cur, mailbox["id"], provider):
        return
    if rng.random() < 0.0015:
        _event(cur, at + timedelta(hours=rng.randint(1, 30)), "complaint", message, person_id)
        return
    if rng.random() < 0.045:
        back = (at + timedelta(days=rng.randint(3, 14))).date()
        _event(cur, at + timedelta(minutes=rng.randint(1, 5)), "reply", message, person_id,
               kind="ooo", text=rng.choice(OOO).format(date=f"{back:%d %B}", domain=p["primary_domain"]))
        return
    need = p["need"]
    persona_fit = 1.0 if p["persona_key"] else 0.5
    cited = len(message.get("citations") or [])
    step_factor = {0: 1.0}.get(message["step_index"], 0.65)
    freshness = 1.0
    sig_age = db.val(cur, """select extract(epoch from (%s - s.observed_at)) / 86400 from enrollments e
                             join account_plays ap on ap.id = e.account_play_id join signals s on s.id = ap.trigger_signal_id
                             where e.id = %s""", at, message["enrollment_id"])
    if sig_age is not None and sig_age < 10:
        freshness = 1.35
    elif sig_age is not None and sig_age > 30:
        freshness = 0.8
    champion = 1.8 if p["is_champion"] else 1.0
    p_reply = (0.02 + 0.24 * need * persona_fit * sp["responsiveness"]) * step_factor * freshness * champion
    p_reply *= 1.0 + 0.08 * min(cited, 3)
    if rng.random() >= p_reply:
        return
    # What kind of reply
    r = rng.random()
    pos_share = 0.25 + 0.55 * need * (1.2 if p["is_champion"] else 1.0)
    if r < pos_share:
        kind = "positive"
    elif r < pos_share + 0.16:
        kind = "not_now"
    elif r < pos_share + 0.30:
        kind = "not_interested"
    elif r < pos_share + 0.37:
        kind = "referral"
    elif r < pos_share + 0.42:
        kind = "wrong_person"
    else:
        kind = "unsubscribe"
    sender_first = mailbox["display_name"].split()[0]
    if kind == "positive":
        pool = POSITIVE + (ES_POS if p["country"] == "ES" else []) + (DE_POS if p["country"] == "DE" else [])
        text = rng.choice(pool).format(sender=sender_first, stack=(p["tech"] or ["our stack"])[0])
    elif kind == "not_now":
        month = (at + timedelta(days=rng.randint(45, 120))).strftime("%B")
        text = rng.choice(NOT_NOW).format(month=month)
    elif kind == "not_interested":
        text = rng.choice(NOT_INTERESTED)
    elif kind == "referral":
        pool = db.all(cur, "select full_name, title, true_email from sim_hidden_people where account_id = %s "
                           "and found_person_id is null order by id", p["account_id"])
        colleague = rng.choice(pool) if pool else None  # the sim's own seeded choice, so a world can be replayed
        if colleague is None:
            kind, text = "wrong_person", rng.choice(WRONG)
        else:
            text = rng.choice(REFERRAL).format(ref_name=colleague["full_name"], ref_email=colleague["true_email"],
                                               ref_title=colleague["title"])
    elif kind == "wrong_person":
        text = rng.choice(WRONG)
    else:
        text = rng.choice(UNSUB)
    sig = rng.choice(SIGS).format(name=p["full_name"], first=p["first_name"], title=p["title"], company=p["company"])
    body = text + sig + _quote(message["body"], mailbox["display_name"], at)
    delay = timedelta(hours=rng.uniform(1.5, 52))
    _event(cur, at + delay, "reply", message, person_id, kind=kind, text=body)


def _event(cur, at: datetime, event: str, message: dict, person_id: int, **extra) -> None:
    db.run(cur, "insert into sim_events (at, kind, payload) values (%s, %s, %s)", at, event,
           J({"message_id": message["id"], "person_id": person_id, **extra}))
