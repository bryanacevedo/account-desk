"""Deterministic stand-ins for each model task, used by the demo and tests when there is no key and no recording.

They are deliberately imperfect in the ways real drafts are (a stray dash, a number with no source, a claim with
no citation) a small share of the time, so the copy checks have something real to catch."""
from __future__ import annotations

import hashlib
import random
import re

from .llm import sim


def _rng(*parts) -> random.Random:
    return random.Random(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest())


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


@sim("brief")
def brief(p: dict) -> dict:
    facts = p["facts"]
    signal = [f for f in facts if f["kind"].startswith("signal:")]
    other = [f for f in facts if not f["kind"].startswith("signal:")]
    chosen = (signal[:3] + other[:3])[:5] or facts[:1]
    findings = [{"text": f["text"], "fact_ids": [f["id"]]} for f in chosen]
    lead = signal[0]["text"] if signal else (chosen[0]["text"] if chosen else "")
    return {"findings": findings, "angle": f"{p['company']}: {_lower_first(lead).rstrip('.')}." if lead else p["company"]}


WHY = {
    "cfo": ["New leaders usually find the gap between what was sold and what was invoiced in their first close.",
            "That tends to show up first as a longer month-end close."],
    "controller": ["That is usually when revenue recognition moves back into spreadsheets.",
                   "It tends to land on the controller's team before anyone plans for it."],
    "revops": ["That is usually where billing and the CRM stop agreeing on what was sold.",
               "It tends to mean more manual invoice fixes each month."],
    "data": ["That usually means finance and product start reporting two different usage numbers.",
             "It tends to put a new pipeline between the product data and the ledger."],
}
ASK = [
    "Worth 20 minutes to compare how other finance teams handled it?",
    "Open to a short call next week?",
    "Is this on your list for this quarter?",
    "Would it help to see how a team your size set this up?",
]
FOLLOW = [
    "Following up on {fact}. Teams that moved early kept month-end close from growing.",
    "One more note on {fact}: this is usually where the manual invoice work starts.",
]
BREAKUP = [
    "I'll stop here. If billing comes up later this year, I'm easy to find.",
    "Last note from me. If the timing changes, reply and I'll pick it up.",
]


def _claim(company: str, f: dict) -> str | None:
    """Turn a stored fact into a sentence that keeps its proper nouns as written."""
    t = f["text"].rstrip(".")
    kind = f["kind"]
    if kind.startswith("signal:"):
        verb = t.split(" ", 1)
        if verb[0] in ("Posted", "Raised", "Appointed", "Started", "Stopped", "Created", "Announced", "Left"):
            return f"Saw that {company} {verb[0].lower()} {verb[1]}." if len(verb) > 1 else None
        if t.startswith(company):
            return f"Saw that {t}."
        return f"Noticed this about {company}: {t[0].lower() + t[1:]}."
    if kind == "page:billing":
        return f"Your docs say {t[0].lower() + t[1:]}."
    if kind == "page:careers":
        return f"Your careers page lists {t[len('Open roles include '):] if t.startswith('Open roles include') else t}."
    return None


@sim("draft")
def draft(p: dict) -> dict:
    r = _rng(p["person"]["id"], p["step"]["index"], p.get("attempt", 1))
    first = p["person"]["first_name"]
    company = p["company"]
    facts = p["facts"]
    signal_facts = [f for f in facts if f["kind"].startswith("signal:")]
    page_facts = [f for f in facts if f["kind"] in ("page:billing", "page:careers")]
    lead = signal_facts[0] if signal_facts else (page_facts[0] if page_facts else None)
    support = next((f for f in page_facts if f is not lead), None)
    persona = (p.get("persona_key") or "cfo")
    job = p["step"]["job"]
    s: list[dict] = [{"text": f"{first},", "kind": "courtesy", "fact_ids": []}]
    if job == "open":
        c = _claim(company, lead) if lead else None
        if c:
            s.append({"text": c, "kind": "claim", "fact_ids": [lead["id"]]})
        c2 = _claim(company, support) if support else None
        if c2 and r.random() < 0.75:
            s.append({"text": c2, "kind": "claim", "fact_ids": [support["id"]]})
        s.append({"text": r.choice(WHY.get(persona, WHY["cfo"])), "kind": "courtesy", "fact_ids": []})
        s.append({"text": r.choice(ASK), "kind": "ask", "fact_ids": []})
    elif job == "follow_up":
        short = lead["text"].rstrip(".") if lead else "your billing setup"
        short = short[0].lower() + short[1:] if not short.startswith(company) else short
        s.append({"text": r.choice(FOLLOW).format(fact=short), "kind": "claim", "fact_ids": [lead["id"]] if lead else []})
        s.append({"text": r.choice(ASK), "kind": "ask", "fact_ids": []})
    else:
        s.append({"text": r.choice(BREAKUP), "kind": "courtesy", "fact_ids": []})
    # Real drafts go wrong sometimes. Only on a first attempt, so a redraft with the failures listed comes back clean.
    if p.get("attempt", 1) == 1 and not p.get("failures"):
        roll = r.random()
        if roll < 0.04:
            s.insert(2, {"text": "Most teams cut close time by 43% in the first quarter.", "kind": "claim", "fact_ids": []})
        elif roll < 0.07:
            s[-1]["text"] = s[-1]["text"].rstrip("?.") + " \u2014 no pressure?"
        elif roll < 0.09:
            s.insert(1, {"text": "I hope this email finds you well.", "kind": "courtesy", "fact_ids": []})
    subjects = {"open": ["billing at {company}", "{company} and month-end", "question on invoicing", "your close process"],
                "follow_up": ["re: {prev}"], "bump": ["re: {prev}"], "break_up": ["closing the loop"]}
    subj = r.choice(subjects.get(job, ["note"])).format(company=company, prev=p.get("previous_subject") or "billing")
    return {"subject": subj, "sentences": s}


POS_WORDS = ("good timing", "happy to", "let's talk", "lets talk", "does thursday", "send a couple", "case study",
             "pricing look", "evaluating", "nos interesa", "klingt interessant", "how does this work")


@sim("classify")
def classify(p: dict) -> dict:
    t = p["cleaned"].lower()
    out = {"label": "other", "confidence": 0.55, "same_person": True, "return_date": None, "referral": None,
           "new_company": None, "instructs_system": bool(re.search(r"ignore (all|previous|your) instructions|mark (this|me) as",
                                                                   t)), "language": p.get("language_hint") or "en"}
    m = re.search(r"(?:speak with|reach them at|talk to|runs our billing|owns this area)", t)
    if m:
        name = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+)", p["cleaned"])
        email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", p["cleaned"])
        out.update(label="referral", confidence=0.86,
                   referral={"name": name.group(1) if name else "a colleague", "title": None,
                             "email": email.group(0) if email else None, "relationship": "colleague"})
        return out
    if any(w in t for w in ("try me again", "reach back out", "ping me after", "not a priority this quarter")):
        mon = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)", t)
        out.update(label="not_now", confidence=0.84, return_date=mon.group(1) if mon else None)
    elif any(w in t for w in POS_WORDS):
        label = "meeting_request" if any(w in t for w in ("times", "thursday", "call", "termin", "hablar")) else (
            "question" if "?" in t else "interested")
        out.update(label=label, confidence=0.82)
    elif any(w in t for w in ("not interested", "all set", "built this in house", "don't follow up")):
        out.update(label="not_interested", confidence=0.88)
    elif any(w in t for w in ("wrong person", "don't handle", "different team")):
        out.update(label="wrong_person", confidence=0.8)
    elif any(w in t for w in ("left the company", "no longer with", "moved on")):
        out.update(label="left_company", confidence=0.8)
    return out


@sim("suggest_reply")
def suggest_reply(p: dict) -> dict:
    first = p.get("first_name") or "there"
    if p["label"] in ("meeting_request", "interested"):
        body = (f"{first}, thanks. Tuesday at 10:00 or Wednesday at 14:00 your time both work on my side. "
                "I'll bring a short walkthrough of how invoicing and the ledger stay in step.")
    else:
        body = f"{first}, good question. Short answer: yes, and I can show you how in 20 minutes. Want me to send two times?"
    return {"body": body}


@sim("extract")
def extract(p: dict) -> dict:
    items = []
    for line in p["notes"].splitlines():
        l = line.strip()
        low = l.lower()
        if not l:
            continue
        if "chargewise" in low or "meterline" in low:
            items.append({"kind": "competitor", "text": "Compared us with an incumbent billing tool", "quote": l})
        elif any(w in low for w in ("worried", "concern", "too expensive", "timing", "not sure")):
            items.append({"kind": "objection", "text": l[:120], "quote": l})
        elif any(w in low for w in ("need", "want", "close", "audit", "board")):
            items.append({"kind": "reason_to_buy", "text": l[:120], "quote": l})
    return {"items": items[:8]}
