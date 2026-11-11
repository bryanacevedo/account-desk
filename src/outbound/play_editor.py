"""Writing, previewing, pricing and launching plays (docs/SPEC.md section 7 and 22.16).

GTM engineering writes a play as a draft. The editor shows which accounts it would match today, how many a month
from the last 30 days of signals, and a cost card in each vendor's own unit with AI spend in dollars beside it,
never added together. A manager launches it; the database refuses a launch by the play's own author."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from . import db

CHANNEL_JOBS = {"email": {"open", "follow_up", "bump", "break_up"}, "linkedin_connect": {"connect"},
                "linkedin_message": {"message"}, "call": {"call"}}


class Step(BaseModel):
    day: int = Field(ge=0, le=45)
    channel: Literal["email", "linkedin_connect", "linkedin_message", "call"]
    job: Literal["open", "follow_up", "bump", "break_up", "connect", "message", "call"]
    by: Literal["desk", "sdr"]

    @model_validator(mode="after")
    def fits(self):
        if self.job not in CHANNEL_JOBS[self.channel]:
            raise ValueError(f"A {self.channel.replace('_', ' ')} step cannot be a {self.job.replace('_', ' ')}")
        if self.channel != "email" and self.by == "desk":
            raise ValueError("Calls and LinkedIn steps are the SDR's; only emails are sent by the desk")
        return self


class Trigger(BaseModel):
    any_of: list[str] = Field(min_length=1, max_length=8)
    fit_tiers: list[Literal["A", "B"]] = Field(min_length=1)
    min_priority: int = Field(ge=0, le=100)
    within_days: int = Field(ge=1, le=120)


class PlayIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    hypothesis: str = Field(min_length=10, max_length=400)
    trigger: Trigger
    personas: list[str] = Field(min_length=1, max_length=4)
    max_people: int = Field(ge=1, le=5)
    sequence: list[Step] = Field(min_length=1, max_length=10)
    angle: str = Field(min_length=10, max_length=400)
    holdout_pct: int = Field(ge=0, le=50)
    urgent: bool = False
    latency_hours: int = Field(ge=4, le=168)

    @field_validator("sequence")
    @classmethod
    def ordered(cls, steps: list[Step]) -> list[Step]:
        if steps[0].day != 0:
            raise ValueError("The first step is on day 0")
        if any(b.day < a.day for a, b in zip(steps, steps[1:])):
            raise ValueError("Steps must be in day order")
        emails = [s for s in steps if s.channel == "email"]
        if emails and emails[0].job != "open":
            raise ValueError("The first email opens the conversation")
        return steps


def check_names(cur, p: PlayIn) -> None:
    types = {r["key"] for r in db.all(cur, "select key from signal_types where enabled")}
    unknown = [t for t in p.trigger.any_of if t not in types]
    if unknown:
        raise ValueError(f"Unknown signals: {', '.join(unknown)}")
    personas = {r["key"] for r in db.all(cur, "select key from personas")}
    if any(x not in personas for x in p.personas):
        raise ValueError("Unknown buyer role")
    if p.max_people > int(db.val(cur, "select value from settings where key = 'account_max_active_wide'") or 5):
        raise ValueError("More people than an account may have in sequence at once")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "play"


def preview(cur, p: PlayIn) -> dict:
    """Accounts this play would match today, and how many a month it would have proposed over the last 30 days."""
    t = p.trigger
    rows = db.all(cur, """
        select a.id, a.name, a.primary_domain, a.fit_tier, sc.priority,
               (select st.label from signals s join signal_types st on st.key = s.type_key
                 where s.account_id = a.id and s.status = 'matched' and s.type_key = any(%s)
                   and s.observed_at > app_now() - (%s || ' days')::interval order by s.observed_at desc limit 1) as signal,
               exists (select 1 from account_plays ap where ap.account_id = a.id and ap.state in
                       ('proposed','accepted','researching','approving','active','engaged','meeting')) as in_play,
               exists (select 1 from holds h where h.account_id = a.id and h.person_id is null and h.until > app_now()) as resting
        from accounts a join account_scores sc on sc.account_id = a.id
        where a.fit_tier = any(%s) and sc.priority >= %s
          and a.lifecycle not in ('customer', 'open_opp', 'competitor')
          and exists (select 1 from signals s where s.account_id = a.id and s.status = 'matched'
                      and s.type_key = any(%s) and s.observed_at > app_now() - (%s || ' days')::interval)
        order by sc.priority desc""", t.any_of, t.within_days, list(t.fit_tiers), t.min_priority, t.any_of, t.within_days)
    free = [r for r in rows if not r["in_play"] and not r["resting"]]
    month = db.val(cur, """
        select count(distinct s.account_id) from signals s join accounts a on a.id = s.account_id
        join account_scores sc on sc.account_id = a.id
        where s.status = 'matched' and s.type_key = any(%s) and s.ingested_at > app_now() - interval '30 days'
          and a.fit_tier = any(%s) and sc.priority >= %s and a.lifecycle not in ('customer', 'open_opp', 'competitor')""",
        t.any_of, list(t.fit_tiers), t.min_priority)
    treated = round(month * (100 - p.holdout_pct) / 100)
    return {"matching": len(rows), "free_now": len(free), "in_another_play": sum(r["in_play"] for r in rows),
            "resting": sum(1 for r in rows if r["resting"] and not r["in_play"]), "per_month": month,
            "per_month_contacted": treated, "per_month_held_back": month - treated, "sample": free[:12]}


# Worst-case token sizes per call, measured on the stand-in prompts; live calls are logged with their real counts.
TOKENS = {"brief": (3200, 700), "draft": (2600, 450), "classify": (1330, 70), "suggest_reply": (900, 160)}
OPUS = (4.0, 20.0)  # dollars per million tokens, input and output


def cost(cur, p: PlayIn, per_month: int) -> dict:
    """Worst case per account, then per month at the preview's rate. Credits stay in credits; AI is in dollars."""
    desk_emails = sum(1 for s in p.sequence if s.channel == "email" and s.by == "desk")
    has_call = any(s.channel == "call" for s in p.sequence)
    credits = {"people_search": len(p.personas), "email_finder": p.max_people, "email_verifier": p.max_people * 2,
               "phone_finder": p.max_people if has_call else 0}
    calls = {"brief": 1, "draft": desk_emails * p.max_people * 2, "classify": desk_emails * p.max_people,
             "suggest_reply": p.max_people}
    usd = sum(n * (TOKENS[k][0] * OPUS[0] + TOKENS[k][1] * OPUS[1]) / 1_000_000 for k, n in calls.items())
    return {"per_account": {"credits": credits, "ai_calls": sum(calls.values()), "ai_dollars": round(usd, 2)},
            "per_month": {"credits": {k: v * per_month for k, v in credits.items()},
                          "ai_calls": sum(calls.values()) * per_month, "ai_dollars": round(usd * per_month, 2)},
            "note_ai": "Worst case: every email drafted twice and every reply read by the model."}
