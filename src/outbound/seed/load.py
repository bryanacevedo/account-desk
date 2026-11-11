"""Load the catalog into an empty database, then build the simulated world."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .. import db
from ..db import J
from . import catalog as C


def load_catalog(cur, *, start: datetime) -> dict:
    for k, v in C.SETTINGS.items():
        db.run(cur, "insert into settings (key, value) values (%s, %s) on conflict (key) do update set value = excluded.value",
               k, J(v))
    ids = {}
    for name, email, role, tz in C.USERS:
        ids[email] = db.val(cur, "insert into users (name, email, role, timezone, slack_id) values (%s,%s,%s,%s,%s) "
                                 "returning id", name, email, role, tz, "U" + email.split("@")[0].replace(".", "").upper()[:9])
    manager = next(i for e, i in ids.items() if e.startswith("elena"))
    gtm = next(i for e, i in ids.items() if e.startswith("sam"))
    for key, label, patterns, seniority, role, angle in C.PERSONAS:
        db.run(cur, "insert into personas (key, label, title_patterns, seniority, committee_role, angle) "
                    "values (%s,%s,%s,%s,%s,%s)", key, label, patterns, seniority, role, angle)
    for key, label, because, level, weight, hl in C.SIGNAL_TYPES:
        db.run(cur, "insert into signal_types (key, label, because, level, weight, half_life_days) values (%s,%s,%s,%s,%s,%s)",
               key, label, because, level, weight, hl)
    for key, label, adapter, cadence, paid, provider in C.SIGNAL_SOURCES:
        db.run(cur, "insert into signal_sources (key, label, adapter, cadence_minutes, paid, provider) "
                    "values (%s,%s,%s,%s,%s,%s) on conflict (key) do nothing", key, label, adapter, cadence, paid, provider)
    db.run(cur, "insert into icp_versions (rules, note, published_by, published_at) values (%s, %s, %s, %s)",
           J(C.ICP), "Starting ICP", gtm, start - timedelta(days=30))
    for (key, name, hyp, trig, personas, maxp, seq, angle, autonomy, urgent, latency) in C.PLAYS:
        db.run(cur, """insert into plays (key, name, hypothesis, trigger, personas, max_people, sequence, angle, autonomy,
                                          status, holdout_pct, owner_id, created_by, launched_by, launched_at, urgent,
                                          latency_hours, lia_ref, monthly_cap)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'live',20,%s,%s,%s,%s,%s,%s,'LIA-2026-07',%s)""",
               key, name, hyp, J(trig), personas, maxp, J(seq), angle, autonomy, gtm, gtm, manager,
               start - timedelta(days=21), urgent, latency, J(C.PLAY_CAP))
    for country, day, name in C.HOLIDAYS:
        db.run(cur, "insert into holidays (country, day, name) values (%s,%s,%s)", country, date.fromisoformat(day), name)
    for country, rule in C.REGION_RULES:
        db.run(cur, "insert into region_rules (country, rule) values (%s,%s)", country, rule)
    for vendor, cap in C.BUDGETS:
        db.run(cur, "insert into budgets (vendor, monthly_cap_cents) values (%s,%s)", vendor, cap)
    reps = db.all(cur, "select id, name, email from users where role = 'sdr' order by id")
    for d_i, (domain, age_days) in enumerate(C.SENDING_DOMAINS):
        young = age_days < 30
        db.run(cur, """insert into sending_domains (domain, spf, dkim, dmarc, dmarc_policy, dmarc_aligned, registered_at,
                                                    checked_at, spam_rate, spam_rate_at, postmaster_status)
                       values (%s, true, true, true, %s, true, %s, %s, %s, %s, %s)""",
               domain, "quarantine", (start - timedelta(days=age_days)).date(), start,
               None if young else 0.0004, None if young else start - timedelta(days=1), None if young else "compliant")
        # At most 3 mailboxes per domain; each rep gets two mailboxes on the seasoned domains.
        slots = {0: [0, 1, 2], 1: [3, 0, 1], 2: [2, 3], 3: [0, 1]}[d_i]
        for r_i in slots:
            rep = reps[r_i]
            first, last = rep["name"].split()[0].lower(), rep["name"].split()[1].lower()
            addr = f"{first}@{domain}" if d_i % 2 == 0 else f"{first}.{last}@{domain}"
            warm = start - timedelta(days=(age_days - 5) if not young else 9)
            db.run(cur, """insert into mailboxes (address, domain, provider, display_name, user_id, warmup_started, ramp_start)
                           values (%s,%s,%s,%s,%s,%s,%s)""",
                   addr, domain, "google" if d_i < 2 else "microsoft", rep["name"], rep["id"], warm.date(),
                   (warm + timedelta(days=14)).date())
    return {"manager": manager, "gtm": gtm}
