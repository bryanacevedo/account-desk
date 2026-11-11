"""Every system the desk touches, whether it costs money, whether it is connected, and what it cost this month.

The desk meters what it buys per use (credits and AI tokens). Flat subscriptions are entered as monthly fees in
`subscriptions`, flagged as assumptions until a manager enters the figure from a bill; the demo seeds assumed ones.
"""
from __future__ import annotations

import calendar

from . import adapters, db
from .config import CONFIG
from .spend import RATES

# (key, group, name, what it is for, how it is paid, the adapter slot that serves it, the ledger vendor it charges)
CATALOG = [
    ("people_search", "Data", "People search", "Finds the buying group at an account", "metered", "people", "people_search"),
    ("email_finder", "Data", "Email finder", "Finds a work address for a chosen person", "metered", "finder", "email_finder"),
    ("email_verifier", "Data", "Email verification", "Checks an address before anything is sent to it", "metered", "verifier", "email_verifier"),
    ("email_resolver", "Data", "Catch-all resolver", "A second check for companies whose server accepts every address", "metered", "resolver", "email_resolver"),
    ("company_data", "Data", "Company data", "Industry, size, tools, funding, open roles and team growth for each account", "metered", "company", "company_data"),
    ("phone_finder", "Data", "Phone finder", "Finds a direct line when a play has a call step", "metered", "phone", "phone_finder"),
    ("research", "Research", "Website research", "Reads the account's own pages for facts a draft can cite", "free", "research", "research"),
    ("anthropic", "AI", "Claude", "Briefs, drafts, reply labels and suggested answers", "metered", None, "anthropic"),
    ("mail", "Sending", "Mail provider", "Sends from the SDRs' mailboxes and reports bounces", "subscription", "email", None),
    ("telemetry", "Sending", "Inbox placement and spam rate", "Seed tests and the provider's spam rate hold or pause a mailbox", "subscription", "telemetry", None),
    ("dns", "Sending", "DNS checks", "SPF, DKIM and DMARC on every sending domain", "free", "dns", None),
    ("linkedin", "LinkedIn", "HeyReach", "Reports accepted requests and first replies", "subscription", None, None),
    ("crm", "CRM", "CRM", "Deals, owners and the pipeline outreach is credited with", "subscription", "crm", None),
    ("chat", "Team", "Slack", "Alerts and hot replies", "free", "chat", None),
]


# What we would buy for each role. A recommendation, not a claim about the vendor's prices: the prices on this page
# are the desk's own assumptions until a manager enters real ones.
SUGGEST = {
    "people_search": "Apollo", "email_finder": "Findymail, then Prospeo, then LeadMagic",
    "email_verifier": "ZeroBounce", "phone_finder": "Lusha", "email_resolver": "BounceBan or Scrubby",
    "company_data": "Apollo organization enrichment", "research": "No vendor: the account's own website",
    "anthropic": "Claude Opus 5.5", "mail": "Google Workspace or Microsoft 365", "telemetry": "Google Postmaster Tools and GlockApps",
    "dns": "No vendor: public DNS over HTTPS", "linkedin": "HeyReach", "crm": "Salesforce or HubSpot", "chat": "Slack",
}
PROVIDER_NAME = {"findymail": "Findymail", "prospeo": "Prospeo", "leadmagic": "LeadMagic"}


def _waterfall(cur) -> list[dict]:
    """Each finder in order: how often it was asked this month, how often it answered, and what it cost."""
    order = [getattr(f, "provider", "") for f in adapters.get().finders]
    rows = {r["provider"]: r for r in db.all(cur, """
        select split_part(c.adapter, ':', 2) as provider, count(*) as asked, coalesce(sum(l.qty), 0) as found,
               coalesce(sum(l.cost_cents), 0) as cents
        from ledger l join adapter_calls c on c.id = l.adapter_call_id
        where l.vendor = 'email_finder' and c.adapter like 'email_finder:%%' and l.at >= date_trunc('month', app_now())
        group by 1""")}
    return [{"provider": p, "name": PROVIDER_NAME.get(p, p), "step": i + 1, "asked": int(rows.get(p, {}).get("asked", 0)),
             "found": float(rows.get(p, {}).get("found", 0)), "cents": float(rows.get(p, {}).get("cents", 0))}
            for i, p in enumerate(order)]


def _status(slot: str | None, key: str) -> str:
    if key == "anthropic":
        return "connected" if CONFIG.mode == "live" and getattr(CONFIG, "anthropic_live", False) else "simulated"
    if key == "linkedin":
        return "connected" if CONFIG.linkedin_tool_token else ("simulated" if CONFIG.mode == "demo" else "not_connected")
    a = getattr(adapters.get(), slot, None) if slot else None
    if slot in ("company", "resolver") and a is None:
        return "not_connected"
    if CONFIG.mode != "live":
        return "simulated"
    return "not_connected" if a is None or getattr(a, "name", "").startswith("missing:") else "connected"


def _subscriptions(cur) -> dict[str, dict]:
    """Each flat fee as a monthly figure: per mailbox counts active mailboxes, per sender counts active SDRs."""
    boxes = db.val(cur, "select count(*) from mailboxes where status = 'active'")
    sdrs = db.val(cur, "select count(*) from users where role = 'sdr' and active")
    out = {}
    off = {r["key"] for r in db.all(cur, "select key from signal_sources where not enabled")}
    if CONFIG.mode == "live" and not CONFIG.linkedin_tool_token:
        off.add("linkedin")  # no LinkedIn tool connected, so no seats are being paid for
    for r in db.all(cur, "select key, unit_cents, per, assumed, note from subscriptions"):
        if r["key"] in off:
            continue
        n = boxes if r["per"] == "mailbox" else sdrs if r["per"] == "sender" else 1
        out[r["key"]] = {**r, "count": n, "monthly_cents": r["unit_cents"] * n}
    return out


def costs(cur) -> dict:
    now = db.val(cur, "select app_now()")
    subs = _subscriptions(cur)
    spend = {r["vendor"]: r for r in db.all(cur, """select vendor, sum(qty) as qty, sum(cost_cents) as cents, count(*) as calls
                                                   from ledger where at >= date_trunc('month', app_now()) group by vendor""")}
    caps = {r["vendor"]: r["monthly_cap_cents"] for r in db.all(cur, "select vendor, monthly_cap_cents from budgets")}
    ai_calls = db.val(cur, "select count(*) from llm_calls where cost_cents > 0 and at >= date_trunc('month', app_now())")
    rows = []
    for key, group, name, purpose, paid, slot, vendor in CATALOG:
        s = spend.get(vendor or "", {})
        row = {"key": key, "group": group, "name": name, "purpose": purpose, "paid": paid, "status": _status(slot, key),
               "unit": "tokens" if key == "anthropic" else ("credits" if paid == "metered" else None),
               "rate_cents": RATES.get(vendor) if vendor and key != "anthropic" else None,
               "used": float(s.get("qty") or 0), "cents": float(s.get("cents") or 0), "calls": int(s.get("calls") or 0),
               # The AI cap is kept in cents; every other cap is in the vendor's own credits (spend.py).
               "cap": caps.get(vendor) if vendor else None, "cap_unit": "cents" if key == "anthropic" else "credits"}
        if key == "anthropic":
            row["calls"] = ai_calls
        if key in subs:
            row["subscription"] = subs[key]
        row["suggest"] = SUGGEST.get(key)
        if key == "email_finder":
            row["waterfall"] = _waterfall(cur)
        rows.append(row)
    sources = db.all(cur, """select s.key, s.label, s.adapter, s.enabled, s.paid,
                                    (select max(started_at) from source_runs r where r.source_key = s.key) as last_run,
                                    (select count(*) from signals g where g.source = s.key
                                      and g.observed_at >= date_trunc('month', app_now())) as signals
                             from signal_sources s order by s.paid desc, s.label""")
    for s in sources:
        s["subscription"] = subs.get(s["key"])
        s["status"] = ("webhook" if s["adapter"] == "webhook" else "simulated" if CONFIG.mode != "live" or s["adapter"] == "sim"
                       else "connected")
        if CONFIG.mode == "live" and s["adapter"] == "sim":
            s["status"] = "not_connected"
    by_play = db.all(cur, """select p.id, p.name, sum(l.cost_cents) as cents, count(distinct l.account_id) as accounts
                             from ledger l join plays p on p.id = l.play_id
                             where l.at >= date_trunc('month', app_now()) group by p.id, p.name order by 3 desc""")
    untagged = db.val(cur, """select coalesce(sum(cost_cents), 0) from ledger where play_id is null
                              and at >= date_trunc('month', app_now())""")
    metered = sum(r["cents"] for r in rows)
    flat = sum(x["monthly_cents"] for x in subs.values())
    last = db.one(cur, """select coalesce(sum(cost_cents), 0) as cents, coalesce(sum(qty) filter (where unit = 'credits'), 0) as credits
                          from ledger where at >= date_trunc('month', app_now()) - interval '1 month'
                          and at < date_trunc('month', app_now())""")
    credits = sum(r["used"] for r in rows if r["unit"] == "credits")
    meetings = db.val(cur, """select count(*) from meetings where account_play_id is not null and source <> 'inbound'
                              and status <> 'cancelled' and booked_at >= date_trunc('month', app_now())""")
    days = calendar.monthrange(now.year, now.month)[1]
    elapsed = max(now.day - 1 + now.hour / 24, 1)
    projected = (metered / elapsed * days if metered else 0) + flat
    # Flat fees accrue by the day: on day 11 of 30, a month's seats have cost 11/30 of their price so far.
    flat_so_far = flat * min(elapsed / days, 1)
    last_meetings = db.val(cur, """select count(*) from meetings where account_play_id is not null and source <> 'inbound'
                                   and status <> 'cancelled' and booked_at >= date_trunc('month', app_now()) - interval '1 month'
                                   and booked_at < date_trunc('month', app_now())""")
    last_total = float(last["cents"]) + flat
    return {"vendors": rows, "sources": sources, "by_play": by_play, "untagged_cents": float(untagged),
            "metered_cents": metered, "flat_cents": flat, "flat_so_far_cents": flat_so_far,
            "total_cents": metered + flat_so_far, "projected_cents": projected,
            "credits": credits, "meetings": meetings,
            "cost_per_meeting_cents": (metered + flat_so_far) / meetings if meetings else None,
            # Flat fees are not kept by month, so last month uses this month's: say so on the page.
            "last_month": {"cents": last_total, "metered_cents": float(last["cents"]), "credits": float(last["credits"]),
                           "meetings": last_meetings, "per_meeting_cents": last_total / last_meetings if last_meetings else None},
            "assumed": any(x["assumed"] for x in subs.values()),
            "day": now.day, "days": days, "mode": CONFIG.mode}
