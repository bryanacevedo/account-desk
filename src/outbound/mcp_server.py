"""The desk for an assistant: read-only questions over MCP (docs/SPEC.md 20). "Why is this account hot", "what is
waiting on me", "how did this play do". It reads no money, writes nothing, and every query runs in a read-only
transaction, so a tool cannot change the desk even by mistake.

    python -m outbound mcp            # stdio, for Claude Desktop, Claude Code or any MCP client
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import db, views

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

server = MCPServer(
    name="account-desk",
    title="Account Desk",
    instructions="Read-only questions about a signal-based account desk: which accounts are hot and why, what is "
                 "waiting on an SDR, and how plays perform against their held-back comparison group. No money figures.",
)


def _plain(x: Any) -> Any:
    """Dates as ISO strings and numerics as floats, so every answer is plain JSON."""
    return json.loads(json.dumps(x, default=lambda v: v.isoformat() if isinstance(v, (datetime, date))
                                 else float(v) if isinstance(v, Decimal) else str(v)))


def _read(fn):
    with db.tx() as cur:
        cur.execute("set transaction read only")
        return _plain(fn(cur))


def _account_id(cur, account: str) -> int | None:
    a = account.strip()
    if a.isdigit():
        return int(a)
    return db.val(cur, """select a.id from accounts a left join account_domains d on d.account_id = a.id
                          where d.domain = lower(%s) or a.primary_domain = lower(%s) or lower(a.name) = lower(%s)
                          order by a.id limit 1""", a, a, a)


@server.tool(annotations=READ_ONLY)
def find_accounts(query: str, limit: int = 10) -> list[dict]:
    """Accounts whose name or domain contains the query, highest priority first."""
    return _read(lambda cur: db.all(cur, """
        select a.id, a.name, a.primary_domain, a.fit_tier, a.lifecycle, s.priority, s.intent
        from accounts a left join account_scores s on s.account_id = a.id
        where a.name ilike %s or a.primary_domain ilike %s
        order by s.priority desc nulls last limit %s""", f"%{query}%", f"%{query}%", max(1, min(limit, 50))))


@server.tool(annotations=READ_ONLY)
def why_hot(account: str) -> dict:
    """Why an account is where it is: its scores, what each signal adds, the evidence behind the latest signals,
    and the play it is in. `account` is a name, a domain or an id."""
    def run(cur):
        aid = _account_id(cur, account)
        if aid is None:
            return {"error": f"No account matches '{account}'."}
        d = views.account(cur, aid, money=False)
        cur_play = d["current"]
        return {"account": {k: d["account"][k] for k in ("id", "name", "primary_domain", "industry", "employees",
                                                         "hq_country", "lifecycle", "fit_tier")},
                "scores": {k: (d["score"] or {}).get(k) for k in ("priority", "fit", "intent")},
                "what_adds_up": [{"signal": c["label"], "adds": c["value"]} for c in d["contributions"]],
                "latest_signals": [{"what": s["label"], "when": s["observed_at"], "evidence": s["evidence"].get("summary"),
                                    "source_url": s["evidence"].get("url")} for s in d["signals"][:8]],
                "current_play": {"play": cur_play["play"], "state": cur_play["state"], "owner": cur_play["owner"],
                                 "why_now": cur_play["why_now"]} if cur_play else None,
                "on_hold_until": d["holds"][0]["until"] if d["holds"] else None}
    return _read(run)


@server.tool(annotations=READ_ONLY)
def waiting_on(email: str) -> dict:
    """What is waiting on one person right now: replies to answer, accounts to decide, emails to approve, calls and
    LinkedIn steps, meetings this week. `email` is the person's work email on the desk."""
    def run(cur):
        u = db.one(cur, "select id, name, role from users where email = lower(%s)", email.strip())
        if u is None:
            return {"error": f"Nobody on the desk has the email {email}."}
        t = views.today(cur, u)
        return {"for": u["name"], "role": u["role"],
                "replies_to_answer": [{"from": r["full_name"], "company": r["company"], "said": r["cleaned"][:200],
                                       "due": r["sla_due_at"]} for r in t["replies"]],
                "accounts_to_decide": [{"account": p["name"], "play": p["play"], "priority": p["priority"]}
                                       for p in t["proposals"]],
                "emails_to_approve": len(t["approvals"]),
                "calls_and_linkedin": [{"task": x["title"], "company": x["company"]} for x in t["tasks"]],
                "meetings_this_week": [{"with": m["full_name"], "company": m["company"], "at": m["starts_at"]}
                                       for m in t["meetings"]]}
    return _read(run)


@server.tool(annotations=READ_ONLY)
def play_report(play: str) -> dict:
    """How one play is doing: its funnel, meetings and deals against the held-back comparison group (with the
    sample still needed when it is too early to say), approvals and autonomy. `play` is its name or key."""
    def run(cur):
        rows = views.plays_page(cur, money=False)
        p = next((r for r in rows if play.lower() in (r["name"].lower(), r["key"].lower())), None) or \
            next((r for r in rows if play.lower() in r["name"].lower()), None)
        if p is None:
            return {"error": f"No play matches '{play}'.", "plays": [r["name"] for r in rows]}
        return {k: p[k] for k in ("name", "key", "status", "autonomy", "hypothesis", "funnel", "lift", "deal_lift",
                                  "approvals", "median_hours_to_first_touch", "promotion") if k in p}
    return _read(run)


@server.tool(annotations=READ_ONLY)
def results_summary() -> dict:
    """The desk as a whole: the funnel, meetings and deals against the held-back group, results by channel, and how
    fast hot replies are answered. Deal counts only, never amounts."""
    def run(cur):
        r = views.results(cur, money=False)
        return {k: r[k] for k in ("funnel", "lift", "deal_lift", "channels", "sla", "opportunities") if k in r}
    return _read(run)


def main() -> None:
    server.run("stdio")
