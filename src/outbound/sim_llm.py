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
    "Following up on my last note, since {clause}. Teams that moved early kept month-end close from growing.",
    "One more thought: since {clause}, this is usually where the manual invoice work starts.",
]
BREAKUP = [
    "I'll stop here. If billing comes up later this year, I'm easy to find.",
    "Last note from me. If the timing changes, reply and I'll pick it up.",
]


VERBS = ("Posted", "Raised", "Appointed", "Started", "Stopped", "Created", "Announced", "Left", "Signed", "Adopted")


def clause(company: str, text: str) -> str:
    """A fact as a clause with the company as its subject, proper nouns kept as written.
    'Posted a job for an Accounts Receivable Lead.' -> 'Brightwave Apps posted a job for an Accounts Receivable Lead'
    'Pilar Vasquez joined Brightwave Apps.'         -> 'Pilar Vasquez joined Brightwave Apps'"""
    t = text.strip().rstrip(".")
    first, _, rest = t.partition(" ")
    if first in VERBS:
        return f"{company} {first.lower()} {rest}".strip()
    return t  # it already names its subject (the company, or a person); keep it whole


def _claim(company: str, f: dict) -> str | None:
    """Turn a stored fact into a sentence that keeps its proper nouns as written."""
    t = f["text"].rstrip(".")
    kind = f["kind"]
    if kind.startswith("signal:"):
        return f"Saw that {clause(company, t)}."
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
    referral = next((f for f in facts if f["kind"] == "referral"), None)
    signal_facts = [f for f in facts if f["kind"].startswith("signal:")]
    page_facts = [f for f in facts if f["kind"] in ("page:billing", "page:careers")]
    lead = signal_facts[0] if signal_facts else (page_facts[0] if page_facts else None)
    support = next((f for f in page_facts if f is not lead), None)
    persona = (p.get("persona_key") or "cfo")
    job = p["step"]["job"]
    s: list[dict] = [{"text": f"{first},", "kind": "courtesy", "fact_ids": []}]
    if job == "open" and referral:
        who = referral["text"].split(" suggested ")[0]
        s.append({"text": f"{who} suggested I get in touch with you.", "kind": "claim", "fact_ids": [referral["id"]]})
        c2 = _claim(company, lead) if lead else None
        if c2:
            s.append({"text": c2, "kind": "claim", "fact_ids": [lead["id"]]})
        s.append({"text": r.choice(WHY.get(persona, WHY["cfo"])), "kind": "courtesy", "fact_ids": []})
        s.append({"text": r.choice(ASK), "kind": "ask", "fact_ids": []})
    elif job == "open":
        c = _claim(company, lead) if lead else None
        if c:
            s.append({"text": c, "kind": "claim", "fact_ids": [lead["id"]]})
        c2 = _claim(company, support) if support else None
        if c2 and r.random() < 0.75:
            s.append({"text": c2, "kind": "claim", "fact_ids": [support["id"]]})
        s.append({"text": r.choice(WHY.get(persona, WHY["cfo"])), "kind": "courtesy", "fact_ids": []})
        s.append({"text": r.choice(ASK), "kind": "ask", "fact_ids": []})
    elif job == "follow_up":
        if lead:
            s.append({"text": r.choice(FOLLOW).format(clause=clause(company, lead["text"])), "kind": "claim",
                      "fact_ids": [lead["id"]]})
        else:
            s.append({"text": "Following up on my last note about billing.", "kind": "courtesy", "fact_ids": []})
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


CONNECT_WHY = ["I work with finance teams on usage billing and would be glad to connect.",
               "I spend my days on billing and close for finance teams, so this caught my eye.",
               "Billing is what I work on, so it seemed worth connecting."]
LI_ASK = ["Open to comparing notes on how you invoice usage?", "Would a short call on your billing setup be useful?",
          "Worth a few minutes to compare notes?"]


@sim("draft_linkedin")
def draft_linkedin(p: dict) -> dict:
    r = _rng("li", p["person"]["id"], p["step"]["index"], p.get("attempt", 1))
    first, company = p["person"]["first_name"], p["company"]
    facts = p["facts"]
    public = [f for f in facts if f["kind"].startswith("signal:")] + [f for f in facts if f["kind"] in ("page:billing", "page:careers")]
    lead = public[0] if public else None
    s: list[dict] = [{"text": f"{first},", "kind": "courtesy", "fact_ids": []}]
    c = _claim(company, lead) if lead else None
    if c:
        s.append({"text": c, "kind": "claim", "fact_ids": [lead["id"]]})
    if p["step"]["job"] == "connect":
        # A redraft after a length failure drops the courtesy line, the way a person would trim it.
        if p.get("attempt", 1) == 1:
            s.append({"text": r.choice(CONNECT_WHY), "kind": "courtesy", "fact_ids": []})
    else:
        s.append({"text": r.choice(WHY.get(p.get("persona_key") or "cfo", WHY["cfo"])), "kind": "courtesy", "fact_ids": []})
        s.append({"text": r.choice(LI_ASK), "kind": "ask", "fact_ids": []})
    return {"sentences": s}


POS_WORDS = ("good timing", "happy to", "let's talk", "lets talk", "does thursday", "send a couple", "case study",
             "pricing look", "evaluating", "nos interesa", "klingt interessant", "how does this work",
             "find a time", "30 minutes", "walk me through", "early next week", "add priya", "rollout",
             "forward to our cfo", "fair point", "exactly the mess", "thursday or friday")


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
        label = "meeting_request" if any(w in t for w in ("times", "thursday", "call", "termin", "hablar", "find a time",
                                                            "30 minutes", "early next week", "invite")) else (
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
        ln = line.strip()
        low = ln.lower()
        if not ln:
            continue
        tool = next((name for key, name in (("chargewise", "Chargewise"), ("meterline", "Meterline"),
                                            ("spreadsheet", "Spreadsheets"), ("in-house", "An in-house system"))
                     if key in low), None)
        if tool:
            items.append({"kind": "competitor", "text": tool, "quote": ln})
        elif any(w in low for w in ("worried", "concern", "too expensive", "timing", "not sure")):
            items.append({"kind": "objection", "text": ln[:120], "quote": ln})
        elif any(w in low for w in ("need", "want", "close", "audit", "board")):
            items.append({"kind": "reason_to_buy", "text": ln[:120], "quote": ln})
    return {"items": items[:8]}


@sim("check_claims")
def check_claims(p: dict) -> dict:
    """The stand-in trusts its own drafts, which only restate facts."""
    return {"sentences": [{"index": i, "supported": True, "why": ""} for i, _ in enumerate(p["sentences"])]}


# The theme stand-in groups by meaning the cheap way: content words, a few synonyms, and how much two wordings share.
_STOP = set("a an the and or of on in to for by with it its is are was were be been they their them we our us as at "
            "from that this these those than then so but not no all any one more most very up out also still just "
            "want wants need needs said says say".split())
_SYN = {"auditors": "audit", "audited": "audit", "auditor": "audit", "rev": "revenue", "rec": "recognition",
        "revrec": "revenue recognition", "recognised": "recognition", "recognized": "recognition",
        "reconcile": "reconciling", "reconciliation": "reconciling", "reconciled": "reconciling", "reconciles": "reconciling", "manually": "hand",
        "manual": "hand", "books": "close", "closing": "close", "contract": "contracts", "invoice": "invoices",
        "boards": "board", "consumption": "usage", "metered": "usage"}


def _words(text: str) -> set[str]:
    out: set[str] = set()
    for w in re.findall(r"[a-z]+", text.lower()):
        for part in _SYN.get(w, w).split():
            if part not in _STOP and len(part) > 2:
                out.add(part.rstrip("s") if len(part) > 4 else part)
    return out


@sim("theme")
def theme(p: dict) -> dict:
    mine = _words(p["text"])
    best, score = None, 0.0
    for t in p["themes"]:
        theirs = _words(t["label"])
        if mine and theirs:
            s = len(mine & theirs) / min(len(mine), len(theirs))
            if s > score:
                best, score = t, s
    if best is not None and score >= 0.6:
        return {"theme_id": best["id"], "new_label": None}
    label = p["text"].strip().rstrip(".")
    return {"theme_id": None, "new_label": label[:1].upper() + label[1:80]}


def _short(text: str, n: int) -> str:
    """Cut at a word, never inside one."""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(" ,:;")


@sim("draft_play")
def draft_play(p: dict) -> dict:
    seg, idea = p["segment"], _lower_first(p["theme"]["label"]).rstrip(".")
    return {
        "name": _short(f"{seg['label']}: {idea}", 60),
        "hypothesis": (f"Accounts that come in on {_lower_first(seg['label'])} keep raising the same need on first calls: "
                       f"{idea}. {seg['because']}")[:400],
        "trigger": {"any_of": [seg["key"]]},
        "personas": [x["key"] for x in p["catalog"]["personas"]][:2],
        "angle": (f"Teams in that position often find this: {idea}. Lead with how other finance teams handled it, "
                  "and ask whether it is on their list" + (", without naming what we saw." if any("without naming" in f for f in p.get("failures", [])) else "."))[:400],
    }
