"""Monitors: the promises the database cannot enforce at write time. Each is a query that returns the rows that
break it. They alert and show on Health; they never fix anything (docs/SPEC.md section 16)."""
from __future__ import annotations

import logging

from . import alerts, db, jobs, scoring
from .db import J

log = logging.getLogger("outbound.monitors")

MONITORS: dict[str, dict] = {
    "sent_outside_window": {
        "title": "Emails sent outside the recipient's send window",
        "sql": """select m.id, m.sent_at, p.timezone, p.country from messages m join enrollments e on e.id = m.enrollment_id
                  join people p on p.id = e.person_id where m.status = 'sent' and m.channel = 'email'
                  and m.sent_at > app_now() - interval '2 days'""",  # a LinkedIn step is done by hand, whenever the SDR does it
        "python": "window"},
    "hot_reply_unalerted": {
        "title": "Positive replies with no alert",
        "sql": """select r.id from replies r where r.hot and r.received_at < app_now() - interval '15 minutes'
                  and not exists (select 1 from alerts a where a.object_kind = 'reply' and a.object_id = r.id)"""},
    "sla_unescalated": {
        "title": "Positive replies past their answer time and not escalated",
        "sql": """select id from replies where hot and handled_at is null and sla_due_at < app_now() - interval '1 hour'
                  and escalated_at is null"""},
    "crm_outbox_stuck": {
        "title": "CRM writes pending for more than a day",
        "sql": "select id from crm_outbox where status = 'pending' and created_at < app_now() - interval '24 hours'"},
    "spend_over_cap": {
        "title": "Vendors over their monthly cap",
        "sql": """select b.vendor from budgets b where (select coalesce(sum(case when b.vendor = 'anthropic' then cost_cents
                  else qty end), 0) from ledger l where l.vendor = b.vendor and l.at >= date_trunc('month', app_now()))
                  > b.monthly_cap_cents"""},
    "paid_call_unledgered": {
        "title": "Paid lookups missing from the spend record",
        "sql": """select c.id from adapter_calls c where c.paid and c.ok and c.at > app_now() - interval '7 days'
                  and not exists (select 1 from ledger l where l.adapter_call_id = c.id)"""},
    "score_not_reproducible": {
        "title": "Scores that do not match their inputs",
        "sql": "select account_id, priority, inputs from account_scores order by computed_at desc limit 200",
        "python": "scores"},
    "source_silent": {
        "title": "Signal sources that stopped checking in",
        "sql": """select s.key from signal_sources s where s.enabled and s.adapter not in ('webhook', 'enrichment') and coalesce(
                  (select max(started_at) from source_runs r where r.source_key = s.key and r.error is null), '-infinity')
                  < app_now() - (s.cadence_minutes * 2 || ' minutes')::interval"""},
    "source_empty": {
        "title": "Paid signal sources that ran for two weeks and returned nothing",
        # Two weeks, because some sources (job changes, funding) are quiet for days at a time and that is normal.
        "sql": """select s.key from signal_sources s where s.enabled and s.paid and s.adapter not in ('webhook', 'enrichment')
                  and (select count(*) from source_runs r where r.source_key = s.key and r.started_at > app_now() - interval '14 days') >= 5
                  and (select min(started_at) from source_runs r where r.source_key = s.key) < app_now() - interval '14 days'
                  and not exists (select 1 from source_runs r where r.source_key = s.key
                                  and r.started_at > app_now() - interval '14 days' and r.fetched > 0)"""},
    "slow_first_touch": {
        "title": "Accepted accounts not contacted within the play's time limit",
        "sql": """select ap.id from account_plays ap join plays p on p.id = ap.play_id join signals s on s.id = ap.trigger_signal_id
                  where ap.arm = 'treated' and ap.state in ('accepted','researching','approving')
                  and s.ingested_at < app_now() - (p.latency_hours * 1.5 || ' hours')::interval
                  and not exists (select 1 from touches t where t.account_play_id = ap.id and t.direction = 'out')"""},
    "alerts_undelivered": {
        "title": "Alerts that never reached Slack",
        "sql": "select id from alerts where delivered_at is null and at < app_now() - interval '30 minutes'"},
    "draft_quality_drift": {
        "title": "SDRs are editing many more drafts than usual",
        # The live signal of drafting quality: the share of emails an SDR approved only after editing, this week
        # against the four weeks before. Twenty approvals at least, so a slow week does not raise it.
        "sql": """with w as (select count(*) filter (where approved_at > app_now() - interval '7 days') as n7,
                                    count(*) filter (where approved_at > app_now() - interval '7 days' and edited) as e7,
                                    count(*) filter (where approved_at <= app_now() - interval '7 days') as n28,
                                    count(*) filter (where approved_at <= app_now() - interval '7 days' and edited) as e28
                             from messages where channel = 'email' and approval_mode = 'person'
                             and approved_at > app_now() - interval '35 days')
                  select 1 as id, e7, n7, e28, n28 from w
                  where n7 >= 20 and n28 >= 20 and e7::float / n7 - e28::float / n28 >= 0.15"""},
    "jobs_dead": {
        "title": "Jobs that stopped after their last retry",
        "sql": "select id from jobs where status = 'dead' and finished_at > app_now() - interval '7 days'"},
    "emailed_after_engaging": {
        "title": "Emails sent after the person engaged on LinkedIn or by phone in the same play",
        "sql": """select m.id from messages m join enrollments e on e.id = m.enrollment_id
                  join touches t on t.person_id = e.person_id and t.account_play_id = e.account_play_id
                  where m.channel = 'email' and m.status = 'sent' and t.channel in ('linkedin', 'call')
                  and (t.direction = 'in' or t.kind = 'call_connected') and t.kind <> 'linkedin_accepted'
                  and m.sent_at > t.at"""},
    "placement_unknown": {
        "title": "Mailboxes with no inbox test in 10 days",
        "sql": """select mb.id from mailboxes mb where mb.status = 'active' and not exists (select 1 from placement_tests t
                  where t.mailbox_id = mb.id and t.at > app_now() - interval '10 days')"""},
    "postmaster_failing": {
        "title": "Domains failing Google Postmaster with mailboxes still active",
        # The telemetry job pauses a domain's mailboxes when its verdict is needs work or its spam rate passes 0.3%;
        # a mailbox active on such a domain was resumed or added since, and sends at a reputation Google calls bad.
        "sql": """select d.domain from sending_domains d where (d.postmaster_status = 'needs_work' or d.spam_rate >= 0.003)
                  and exists (select 1 from mailboxes m where m.domain = d.domain and m.status = 'active')"""},
    "unknown_sends": {
        "title": "Sends whose outcome is unknown for more than a day",
        "sql": "select id from messages where status = 'send_unknown' and sent_at < app_now() - interval '1 day'"},
}


def _window_violations(cur, rows: list[dict]) -> list[dict]:
    from . import timeutil
    timeutil.load_holidays(cur)
    w = timeutil.windows(db.val(cur, "select value from settings where key = 'send_window'"))
    # A send may land up to 30 minutes past the window's end when it was claimed inside it.
    from datetime import timedelta
    return [r for r in rows if not (timeutil.in_window(r["sent_at"], timezone=r["timezone"], country=r["country"], window=w)
                                    or timeutil.in_window(r["sent_at"] - timedelta(minutes=30), timezone=r["timezone"],
                                                          country=r["country"], window=w))]


def _score_violations(cur, rows: list[dict]) -> list[dict]:
    bad = []
    for r in rows:
        if scoring.compute(r["inputs"])["priority"] != r["priority"]:
            bad.append({"account_id": r["account_id"]})
    return bad


def run_one(cur, name: str) -> dict:
    spec = MONITORS[name]
    try:
        with cur.connection.transaction():
            rows = db.all(cur, spec["sql"])
            if spec.get("python") == "window":
                rows = _window_violations(cur, rows)
            elif spec.get("python") == "scores":
                rows = _score_violations(cur, rows)
        found = len(rows)
        sample = [{k: (str(v) if not isinstance(v, (int, float, str, type(None))) else v) for k, v in r.items()
                   if k != "inputs"} for r in rows[:5]]
        db.run(cur, "insert into monitor_runs (monitor, ok, found, sample) values (%s,%s,%s,%s)", name, found == 0, found,
               J(sample))
        return {"monitor": name, "ok": found == 0, "found": found, "sample": sample}
    except Exception as exc:
        db.run(cur, "insert into monitor_runs (monitor, ok, found, error) values (%s,false,0,%s)", name, str(exc)[:500])
        return {"monitor": name, "ok": False, "found": 0, "error": str(exc)}


@jobs.handler("monitors")
def run_all(cur, payload: dict | None = None) -> list[dict]:
    results = [run_one(cur, n) for n in MONITORS]
    for r in results:
        if not r["ok"]:
            alerts.raise_alert(cur, kind="monitor", severity="warn", channel="#outbound-ops",
                               title=MONITORS[r["monitor"]]["title"], body=f"{r['found']} found. " + (r.get("error") or ""),
                               dedup_key=f"monitor:{r['monitor']}:{db.val(cur, 'select app_now()::date')}")
    # The monitors watch themselves: every monitor ran in this cycle without an error.
    errored = [r["monitor"] for r in results if r.get("error")]
    db.run(cur, "insert into monitor_runs (monitor, ok, found, sample) values ('monitors_ran', %s, %s, %s)",
           not errored, len(errored), J(errored))
    return results


def latest(cur) -> list[dict]:
    rows = db.all(cur, """select distinct on (monitor) monitor, at, ok, found, sample, error from monitor_runs
                          order by monitor, at desc""")
    titles = {k: v["title"] for k, v in MONITORS.items()}
    titles["monitors_ran"] = "Every check ran in the last cycle"
    for r in rows:
        r["title"] = titles.get(r["monitor"], r["monitor"])
    return rows
