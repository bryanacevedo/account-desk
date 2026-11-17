"""The simulation database guard (workday simulation, Revision 5). Off unless SIM_DB_GUARD=1, which the simulation runner sets.

With it on, a desk refuses to start against any database that is not a simulation one: the host must be this laptop or one
of SIM_ALLOWED_HOSTS (the four Neon simulation projects), and the database must be `neondb` or start with SIM_DB_PREFIX
(`sim_`), or `p3` for a local rehearsal. So an exported production URL can never be wiped by a simulation command.
With it off nothing changes: the public demos and every local run behave as before."""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

LOCAL = {"127.0.0.1", "localhost", "::1"}


def check(url: str) -> None:
    if os.environ.get("SIM_DB_GUARD") != "1":
        return
    parts = urlsplit(url)
    host, name = parts.hostname or "", parts.path.lstrip("/")
    allowed = {h for h in os.environ.get("SIM_ALLOWED_HOSTS", "").split(",") if h}
    prefix = os.environ.get("SIM_DB_PREFIX", "sim_")
    if host not in LOCAL and host not in allowed:
        raise SystemExit(f"Simulation guard: refusing host {host}; it is not a simulation database.")
    if host in allowed and name != "neondb" and not name.startswith(prefix):
        raise SystemExit(f"Simulation guard: refusing database {name}; simulation databases start with {prefix}.")
    if host in LOCAL and not re.match(r"^(p3|sim_|test|pytest)", name) and name not in {"postgres", "crm", "market", "outbound"}:
        raise SystemExit(f"Simulation guard: refusing local database {name}.")
