"""The simulation database guard (workday simulation, Revision 5). Off unless SIM_DB_GUARD=1, which the simulation runner sets.

With it on, a desk refuses to start against any database that is not a simulation one: the host must be this laptop or one
of SIM_ALLOWED_HOSTS (the four Neon simulation projects), and the database must be `neondb` or start with SIM_DB_PREFIX
(`sim_`), or be a local rehearsal or test database (p3, s3, sim_, test_, pytest_, or `postgres`). The URL is read the way libpq reads it, and a
URL that carries host, hostaddr, dbname, service or options in its query, or an environment that sets PGHOST, PGHOSTADDR, PGDATABASE
or PGSERVICE, is refused because those would override what the guard checked. With it off nothing changes."""
from __future__ import annotations

import os
import re

from psycopg.conninfo import conninfo_to_dict

LOCAL = {"127.0.0.1", "localhost", "::1"}
OVERRIDES = ("host", "hostaddr", "dbname", "service", "options", "port")
LOCAL_DB = re.compile(r"^(p3t?_|s3b?_|sim_|test_|pytest_)[a-z0-9_]*$|^postgres$")


def check(url: str) -> None:
    if os.environ.get("SIM_DB_GUARD") != "1":
        return
    try:
        parts = conninfo_to_dict(url)
    except Exception:
        raise SystemExit("Simulation guard: the database URL could not be read.") from None
    query = url.split("?", 1)[1] if "?" in url else ""
    keys = {q.split("=", 1)[0].lower() for q in query.split("&") if q}
    if keys & set(OVERRIDES) or "@" in url.split("//", 1)[-1].split("/", 1)[0].split("@", 1)[-1]:
        raise SystemExit("Simulation guard: the URL carries a host, database or option override.")
    if any(os.environ.get(v) for v in ("PGHOST", "PGHOSTADDR", "PGDATABASE", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")):
        raise SystemExit("Simulation guard: a PG* environment variable would override the URL.")
    host, name = parts.get("host", ""), parts.get("dbname", "")
    if "," in host:
        raise SystemExit("Simulation guard: one host only.")
    allowed = {h for h in os.environ.get("SIM_ALLOWED_HOSTS", "").split(",") if h}
    prefix = os.environ.get("SIM_DB_PREFIX", "sim_")
    if host not in LOCAL and host not in allowed:
        raise SystemExit(f"Simulation guard: refusing host {host}; it is not a simulation database.")
    if host in allowed and name != "neondb" and not name.startswith(prefix):
        raise SystemExit(f"Simulation guard: refusing database {name}; simulation databases start with {prefix}.")
    if host in LOCAL and not LOCAL_DB.match(name):
        raise SystemExit(f"Simulation guard: refusing local database {name}.")
