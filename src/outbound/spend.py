"""Every paid call goes through here: it is logged, charged to the ledger in the vendor's own unit, and held to
the vendor's monthly cap. Credits and dollars are never added together."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from . import alerts, db
from .db import J

# Configured rates, cents per unit. Credits are still reported as credits; cents are for leadership's cost view only.
RATES = {"people_search": 1.0, "email_finder": 4.0, "email_verifier": 0.8, "phone_finder": 10.0, "research": 0.0}
UNITS = {"people_search": "credits", "email_finder": "credits", "email_verifier": "credits", "phone_finder": "credits",
         "anthropic": "tokens"}


class OverBudget(Exception):
    pass


def month_used(cur, vendor: str) -> float:
    col = "cost_cents" if vendor == "anthropic" else "qty"
    return float(db.val(cur, f"select coalesce(sum({col}), 0) from ledger where vendor = %s "
                             "and at >= date_trunc('month', app_now())", vendor))


def check_budget(cur, vendor: str, qty: float) -> None:
    cap = db.val(cur, "select monthly_cap_cents from budgets where vendor = %s", vendor)
    if cap is None:
        return
    if month_used(cur, vendor) + qty > cap:
        alerts.raise_alert(cur, kind="budget", severity="warn", channel="#outbound-ops",
                           title=f"{vendor} reached its monthly cap", body=f"Cap {cap}. Paid work for {vendor} waits.",
                           dedup_key=f"budget:{vendor}:{db.val(cur, "select to_char(app_now(), 'YYYY-MM')")}")
        raise OverBudget(vendor)


@contextmanager
def paid_call(cur, adapter: str, operation: str, *, vendor: str, qty: float, purpose: str,
              account_id: int | None = None) -> Iterator[dict]:
    """Wraps one paid adapter call. Charges only when the call returns; a failed call is logged unpaid."""
    check_budget(cur, vendor, qty)
    started = time.perf_counter()
    info: dict = {}
    ok = False
    try:
        yield info
        ok = True
    finally:
        # The vendor charged us whether or not the surrounding job later rolls back, so the record of the call is
        # written on its own connection and committed at once. A retry shows as a second charge, which it was.
        ms = int((time.perf_counter() - started) * 1000)
        with db.pool().connection() as own:
            with own.transaction(), own.cursor() as c:
                call_id = db.val(c, "insert into adapter_calls (adapter, operation, paid, ok, ms, detail) "
                                    "values (%s,%s,%s,%s,%s,%s) returning id", adapter, operation, ok, ok, ms, J(info))
                if ok:
                    charged = info.get("charged_qty", qty)
                    db.run(c, "insert into ledger (vendor, unit, qty, cost_cents, purpose, account_id, adapter_call_id) "
                              "values (%s,%s,%s,%s,%s,%s,%s)", vendor, UNITS.get(vendor, "credits"), charged,
                           round(charged * RATES.get(vendor, 0), 4), purpose, account_id, call_id)


def charge_llm(cur, *, model: str, input_tokens: int, output_tokens: int, cost_cents: float, purpose: str,
               account_id: int | None = None) -> None:
    db.run(cur, "insert into ledger (vendor, unit, qty, cost_cents, purpose, account_id) values "
                "('anthropic', 'tokens', %s, %s, %s, %s)", input_tokens + output_tokens, cost_cents, purpose, account_id)
