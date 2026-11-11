"""The copy checks. Pure functions: a draft in, a verdict out. Nothing here calls a model.

What code can check is listed in docs/SPEC.md 22.11. The approval screen covers what it cannot: a claim the
model labelled as courtesy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

BANNED = [
    "i hope this email finds you well", "i hope this finds you well", "hope you're well", "hope you are well",
    "quick question", "just checking in", "just following up", "touching base", "circling back", "per my last email",
    "i wanted to reach out", "i'm reaching out", "game-changer", "game changer", "revolutionary", "cutting-edge",
    "best-in-class", "synergy", "leverage our", "unlock", "supercharge", "in today's fast-paced", "as a valued",
    "i came across your profile", "no pressure", "would love to", "pick your brain", "low-hanging fruit",
]
SPAM_HARD = ["click here", "act now", "limited time", "risk free", "risk-free", "buy now", "order now", "no cost",
             "free trial", "winner", "cash bonus", "make money", "100% free", "this is not spam", "guarantee"]
SPAM_SOFT = ["free", "discount", "special offer", "promotion", "best price", "cheap", "urgent", "congratulations"]
MERGE = re.compile(r"\{\{|\}\}|\[first|\[name|\[company|<name>|<first|\{first|\{company|%first%", re.I)
URL = re.compile(r"https?://\S+|www\.\S+", re.I)
NUMBER = re.compile(r"(?<![\w.])\$?\d[\d,.]*%?")
DASHES = ("—", "–")
TIME_UNIT = re.compile(r"^[- ]?(minutes?|mins?|hours?|am|pm)\b")
STOPWORDS_CAPS = {"I", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January",
                  "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
                  "December", "Q1", "Q2", "Q3", "Q4", "CFO", "VP", "OK", "API", "ERP", "If", "When", "Worth", "Open",
                  "Would", "Is", "Last", "One", "Following", "Teams", "That", "Most", "Saw", "Noticed", "Also",
                  "Reply", "The", "Thanks", "Short",
                  # Ordinary business terms, not names: a draft may use them without a source.
                  "CRM", "SaaS", "B2B", "B2C", "ARR", "MRR", "ROI", "KPI", "SOC", "GTM", "CEO", "COO", "CTO", "CRO",
                  "RevOps", "FinOps", "ASC", "GAAP", "IFRS", "SLA", "SQL", "AI", "US", "UK", "EU"}
LIMITS = {"open": (40, 120), "follow_up": (15, 90), "bump": (10, 60), "break_up": (8, 60),
          # LinkedIn: a connect note is a line or two; a message reads like a short email without the frame.
          "connect": (6, 45), "message": (15, 90)}
PREFIXES = re.compile(r"^(dr|mr|mrs|ms|mx|prof)\.?\s+", re.I)


@dataclass
class Verdict:
    passed: bool
    failures: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    words: int = 0

    def as_dict(self) -> dict:
        return {"passed": self.passed, "failures": self.failures, "warnings": self.warnings, "words": self.words}


def clean_first_name(first: str | None, full: str | None) -> str:
    if first:
        return PREFIXES.sub("", first).strip()
    return PREFIXES.sub("", (full or "").strip()).split(" ")[0]


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9À-ɏ'$%]+", text))


def shingles(text: str, n: int = 5) -> set[str]:
    toks = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def similarity(a: str, b: str) -> float:
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def check(draft: dict, *, job: str, person: dict, account: dict, facts: dict[int, str], our_names: list[str],
          other_bodies: list[str], private_ids: set[int] | None = None, channel: str = "email",
          max_chars: int | None = None) -> Verdict:
    """The same checks for every channel. LinkedIn text has no subject and no footer, a connect note has a
    character cap (the setting), and LinkedIn carries no links at all."""
    f: list[dict] = []
    w: list[dict] = []
    sentences = draft["sentences"]
    text = " ".join(s["text"] for s in sentences)
    subject = (draft.get("subject") or "").strip()
    linkedin = channel == "linkedin"

    def fail(code: str, msg: str) -> None:
        f.append({"code": code, "message": msg})

    if MERGE.search(text) or MERGE.search(subject):
        fail("merge_field", "Has a merge field that was not filled in")
    lo, hi = LIMITS.get(job, (10, 120))
    n = words(" ".join(s["text"] for s in sentences[1:]))  # greeting excluded
    if not lo <= n <= hi:
        fail("length", f"{n} words; this step needs {lo} to {hi}")
    if linkedin:
        if max_chars and len(text) > max_chars:
            fail("too_long", f"{len(text)} characters; a connect note fits in {max_chars}")
    else:
        sw = len(subject.split())
        if not 1 <= sw <= 6:
            fail("subject_length", f"Subject has {sw} words; 1 to 6")
        if subject.isupper() and len(subject) > 3:
            fail("subject_caps", "Subject is all capitals")
    first = clean_first_name(person.get("first_name"), person.get("full_name"))
    if not sentences or not sentences[0]["text"].strip().startswith(first):
        fail("opening", f"Does not open with {first}")
    if PREFIXES.match(sentences[0]["text"] if sentences else ""):
        fail("opening", "Opens with a title instead of the first name")
    cited_claims = 0
    cited_text = []
    for s in sentences:
        ids = s.get("fact_ids") or []
        bad = [i for i in ids if i not in facts]
        if bad:
            fail("unknown_fact", f"Cites facts that do not exist for this account: {bad}")
        if private_ids and any(i in private_ids for i in ids):
            fail("private_signal", "Cites something we only know from tracking (a visit or research data)")
        if s["kind"] == "claim":
            if not ids:
                fail("uncited_claim", f"A claim with no source: \"{s['text'][:80]}\"")
            elif not bad:
                cited_claims += 1
        cited_text += [facts[i] for i in ids if i in facts]
    if job in ("open", "follow_up", "connect", "message") and cited_claims == 0:
        fail("not_about_them", "Says nothing sourced about their company")
    source = " ".join(cited_text)
    for s in sentences:
        for mt in NUMBER.finditer(s["text"]):
            num = mt.group(0)
            core = num.strip("$%.,")
            if not core or core in source.replace(",", ""):
                continue
            after = s["text"][mt.end():mt.end() + 12].lower()
            # An ask may name a meeting length or a time ("20 minutes", "10:00"); that is not a claim about them.
            if s["kind"] == "ask" and (TIME_UNIT.match(after) or ":" in num):
                continue
            fail("unsourced_number", f"The number {num} is not in a cited fact")
    allowed = set(first.split()) | set((person.get("last_name") or "").split()) | set(account["name"].split())
    for nm in our_names:
        allowed |= set(nm.split())
    for s in sentences:
        toks = re.findall(r"\b[A-Z][A-Za-z0-9&'-]+\b", s["text"])
        for tok in toks[1:]:  # the first word of a sentence is capitalised anyway
            if tok in allowed or tok in STOPWORDS_CAPS or tok in source or tok.startswith("I'"):
                continue
            fail("unsourced_name", f"\"{tok}\" is not the person, their company, or in a cited fact")
    low = (subject + " " + text).lower()
    for b in BANNED:
        if b in low:
            fail("banned_phrase", f"Uses \"{b}\"")
    if any(d in text or d in subject for d in DASHES):
        fail("dash", "Uses a long dash")
    if text.count("!") > 1:
        fail("exclamation", "More than one exclamation mark")
    links = URL.findall(text)
    if links and linkedin:
        fail("link", "LinkedIn notes and messages carry no links")
    elif links and job == "open":
        fail("link", "First emails carry no links")
    elif len(links) > 1:
        fail("link", "More than one link")
    for sp in SPAM_HARD:
        if re.search(r"\b" + re.escape(sp) + r"\b", low):
            fail("spam_word", f"Spam-filter word \"{sp}\"")
    soft = [sp for sp in SPAM_SOFT if re.search(r"\b" + re.escape(sp) + r"\b", low)]
    if soft:
        w.append({"code": "spam_soft", "message": "Softer spam words: " + ", ".join(soft)})
    for other in other_bodies:
        if similarity(text, other) > 0.6:
            fail("near_duplicate", "Nearly the same as another note to this company")
            break
    # Keep each failure once.
    seen, uniq = set(), []
    for x in f:
        k = (x["code"], x["message"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return Verdict(passed=not uniq, failures=uniq, warnings=w, words=n)


def assemble(draft: dict, *, sender_name: str, footer: str) -> str:
    """Greeting on its own line, then the body, the rep's name, and the required footer."""
    s = draft["sentences"]
    greeting = s[0]["text"] if s else ""
    middle = " ".join(x["text"] for x in s[1:])
    body = greeting + "\n\n" + middle
    return body.strip() + f"\n\n{sender_name.split()[0]}\n\n{footer}"


def footer(*, company: str, address: str, unsubscribe_url: str, privacy_url: str | None) -> str:
    lines = ["--", address,
             f"If this isn't relevant, reply \"no thanks\" or use {unsubscribe_url} and I won't write again."]
    if privacy_url:
        lines.append(f"How we found your details and your rights: {privacy_url}")
    return "\n".join(lines)
