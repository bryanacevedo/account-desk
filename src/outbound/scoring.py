"""Account scoring: fit from the published ICP, intent from decayed signals, engagement from our own outcomes.

The formulas are in docs/SPEC.md section 22.7. `compute` is pure: given the stored inputs it returns the same
score every time, which is what the reproduction monitor checks.
"""
from __future__ import annotations

import math
from datetime import datetime

from . import db, jobs
from .db import J

CONVERGENCE_STEP = 0.15
CONVERGENCE_MAX_EXTRA_TYPES = 3
INTENT_SCALE = 40.0


# ---------------------------------------------------------------- fit

def _matches(rule: dict, account: dict) -> bool:
    value = account.get(rule["field"])
    op, target = rule["op"], rule["value"]
    if value is None:
        return False
    if op == "in":
        return value in target
    if op == "between":
        return target[0] <= value <= target[1]
    if op == "has_any":
        return bool(set(value or []) & set(target))
    if op == "has_none":
        return not (set(value or []) & set(target))
    raise ValueError(f"unknown ICP operator {op}")


def fit(rules: dict, account: dict) -> dict:
    """Returns {score, tier, factors: [{key, matched, weight, contribution}], excluded: reason|None}."""
    if account.get("lifecycle") in ("customer", "open_opp", "competitor"):
        return {"score": 0, "tier": "X", "factors": [], "excluded": f"Account is a {account['lifecycle'].replace('_', ' ')}"}
    for ex in rules.get("excludes", []):
        if _matches(ex, account):
            return {"score": 0, "tier": "X", "factors": [], "excluded": ex["reason"]}
    total = sum(f["weight"] for f in rules["factors"] if f["weight"] > 0) or 1
    factors, got = [], 0.0
    for f in rules["factors"]:
        m = _matches(f, account)
        contribution = 100.0 * f["weight"] / total if m else 0.0
        got += contribution
        factors.append({"key": f["key"], "matched": m, "weight": f["weight"], "contribution": round(contribution, 1)})
    for p in rules.get("penalties", []):
        if _matches(p, account):
            got -= p["weight"]
            factors.append({"key": p["key"], "matched": True, "weight": -p["weight"], "contribution": -p["weight"]})
    score = int(round(max(0.0, min(100.0, got))))
    tiers = rules.get("tiers", {"A": 70, "B": 50})
    tier = "A" if score >= tiers["A"] else "B" if score >= tiers["B"] else "C"
    return {"score": score, "tier": tier, "factors": factors, "excluded": None}


# ---------------------------------------------------------------- intent and priority

def compute(inputs: dict) -> dict:
    """inputs = {fit, fit_tier, now, signals: [{id, type, weight, half_life, strength, age_days}],
                 positive_replies_90d, meetings_held_90d}"""
    contributions = []
    pos = 0.0
    neg = 0.0
    types: set[str] = set()
    for s in inputs["signals"]:
        c = s["weight"] * s["strength"] * 0.5 ** (s["age_days"] / s["half_life"])
        contributions.append({"signal_id": s["id"], "type": s["type"], "value": round(c, 3)})
        if s["weight"] >= 0:
            pos += c
            if c >= 1:
                types.add(s["type"])
        else:
            neg += abs(c)
    mult = 1 + CONVERGENCE_STEP * min(max(len(types) - 1, 0), CONVERGENCE_MAX_EXTRA_TYPES) if types else 1.0
    intent_raw = 100 * (1 - math.exp(-pos * mult / INTENT_SCALE)) - neg
    intent = int(round(max(0.0, min(100.0, intent_raw))))
    engagement = int(min(100, 35 * inputs.get("positive_replies_90d", 0) + 50 * inputs.get("meetings_held_90d", 0)))
    f = inputs["fit"]
    if inputs["fit_tier"] in ("A", "B"):
        blended = 0.85 * intent + 0.15 * engagement
        priority = int(round((f ** 0.4) * (blended ** 0.6))) if blended > 0 else 0
    else:
        priority = 0
    contributions.sort(key=lambda c: -c["value"])
    reason = next((c["signal_id"] for c in contributions if c["value"] > 0), None)
    return {"fit": f, "intent": intent, "engagement": engagement, "priority": priority,
            "convergence": round(mult, 2), "distinct_types": sorted(types), "contributions": contributions[:12],
            "negative": round(neg, 2), "reason_signal_id": reason}


def gather_inputs(cur, account_id: int, at: datetime) -> dict | None:
    a = db.one(cur, "select * from accounts where id = %s", account_id)
    if a is None:
        return None
    icp = db.one(cur, "select id, rules from icp_versions order by published_at desc, id desc limit 1")
    f = fit(icp["rules"], a)
    sigs = db.all(cur, """
        select s.id, s.type_key as type, t.weight::float as weight, t.half_life_days::float as half_life,
               s.strength::float as strength,
               greatest(0, extract(epoch from (%s - s.observed_at)) / 86400.0)::float as age_days
        from signals s join signal_types t on t.key = s.type_key
        where s.account_id = %s and s.status = 'matched' and t.enabled
          and s.observed_at > %s - (t.half_life_days * 3 || ' days')::interval
          and s.observed_at <= %s
        order by s.observed_at desc""", at, account_id, at, at)
    eng = db.one(cur, """
        select (select count(*) from replies r where r.account_id = %s and r.hot
                  and r.received_at > %s - interval '90 days') as pr,
               (select count(*) from meetings m where m.account_id = %s and m.status = 'held'
                  and m.starts_at > %s - interval '90 days') as mh""", account_id, at, account_id, at)
    for s in sigs:
        s["age_days"] = round(s["age_days"], 4)
    return {"account_id": account_id, "icp_version": icp["id"], "fit": f["score"], "fit_tier": f["tier"],
            "fit_factors": f["factors"], "excluded": f["excluded"], "now": at.isoformat(), "signals": sigs,
            "positive_replies_90d": eng["pr"], "meetings_held_90d": eng["mh"]}


def rescore(cur, account_id: int) -> dict | None:
    at = db.val(cur, "select app_now()")
    inputs = gather_inputs(cur, account_id, at)
    if inputs is None:
        return None
    result = compute(inputs)
    prev = db.one(cur, "select priority from account_scores where account_id = %s", account_id)
    db.run(cur, """update accounts set fit_score = %s, fit_tier = %s, fit_breakdown = %s, fit_icp_version = %s
                   where id = %s""", inputs["fit"], inputs["fit_tier"],
           J({"factors": inputs["fit_factors"], "excluded": inputs["excluded"]}), inputs["icp_version"], account_id)
    db.run(cur, """
        insert into account_scores (account_id, computed_at, fit, intent, engagement, priority, inputs, breakdown,
                                    reason_signal_id)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (account_id) do update set computed_at = excluded.computed_at, fit = excluded.fit,
          intent = excluded.intent, engagement = excluded.engagement, priority = excluded.priority,
          inputs = excluded.inputs, breakdown = excluded.breakdown, reason_signal_id = excluded.reason_signal_id""",
        account_id, at, result["fit"], result["intent"], result["engagement"], result["priority"], J(inputs),
        J({k: result[k] for k in ("contributions", "convergence", "distinct_types", "negative")}),
        result["reason_signal_id"])
    before = prev["priority"] if prev else 0
    if abs(result["priority"] - before) >= 5:
        db.run(cur, "insert into score_history (account_id, at, priority, previous, reason_signal_id) "
                    "values (%s,%s,%s,%s,%s)", account_id, at, result["priority"], before, result["reason_signal_id"])
    return result


@jobs.handler("rescore")
def _rescore_job(cur, payload: dict) -> None:
    result = rescore(cur, payload["account_id"])
    if result and result["priority"] > 0:
        from . import plays
        plays.match(cur, payload["account_id"])


@jobs.handler("rescore_all")
def _rescore_all(cur, payload: dict) -> None:
    """Nightly decay: every account with a recent signal or a stored score."""
    ids = [r["id"] for r in db.all(cur, """
        select distinct a.id from accounts a
        where exists (select 1 from signals s where s.account_id = a.id and s.observed_at > app_now() - interval '180 days')
           or exists (select 1 from account_scores sc where sc.account_id = a.id and sc.priority > 0)""")]
    for aid in ids:
        rescore(cur, aid)
