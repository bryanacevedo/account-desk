"""Live adapters, chosen by which env keys are present. Filled in vendor by vendor; until a vendor's key is set,
its simulated adapter stays in place and /api/health says so."""
from __future__ import annotations

from . import Adapters


def adapters(sim: Adapters) -> Adapters:
    sim.notes.append("Live mode: no live vendor keys configured yet; simulated adapters in place")
    return sim


def fetch_source(cur, source: str) -> list[dict]:
    return []
