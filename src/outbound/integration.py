"""Which other desks are present, and which world the demo is built from. Read from the environment each time it is
asked, so a test or a restart changes it without an import. Unset means alone: every feature on, nothing linked
(shared-world DESIGN.md 2a and 2b).

  INTEGRATED_WITH  the other desks present, comma separated: `market_desk` (its accounts and profile are the book and
                   the fit: this desk hides publishing its own profile and its accounts import), `events_desk` (event
                   follow-up runs here as a play started from campaign members read from the CRM).
  DESK_LINKS       `crm_desk=https://...,market_desk=https://...`: adds "Open in" links and wakes the linked services.
                   Links only. It never hides a feature.
  WORLD            `legacy` (default: the desk's own generator) or `world` (the demo is built from the shared world's
                   slice in world/).
"""
from __future__ import annotations

import os

KNOWN = ("market_desk", "events_desk", "crm_desk")


def integrated_with() -> frozenset[str]:
    names = {p.strip().lower() for p in os.environ.get("INTEGRATED_WITH", "").split(",") if p.strip()}
    bad = names - set(KNOWN)
    if bad:
        raise SystemExit(f"INTEGRATED_WITH names {', '.join(sorted(bad))}; use {', '.join(KNOWN)}.")
    return frozenset(names)


def has(desk: str) -> bool:
    return desk in integrated_with()


def desk_links() -> dict[str, str]:
    out = {}
    for part in os.environ.get("DESK_LINKS", "").split(","):
        k, _, v = part.partition("=")
        if k.strip() in KNOWN and v.strip().startswith("https://"):
            out[k.strip()] = v.strip().rstrip("/")
    return out


def world_mode() -> str:
    w = os.environ.get("WORLD", "legacy").strip().lower() or "legacy"
    if w not in ("legacy", "world"):
        raise SystemExit(f"WORLD={w}; use legacy or world.")
    return w
