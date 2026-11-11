"""Read models for the web app. One function per page or side sheet. Money appears only when `money` is true
(managers and GTM); a rep's read never carries it."""
from __future__ import annotations

from . import adapters, db, monitors, outreach, stats

OPEN = ("proposed", "accepted", "researching", "approving", "active", "engaged", "meeting")


def _iso(rows: list[dict]) -> list[dict]:
    return rows


# ---------------------------------------------------------------- today

def today(cur, user: dict) -> dict:
    uid = user["id"]
    mine = "ap.owner_id = %s" if user["role"] == "sdr" else "true"
    args = (uid,) if user["role"] == "sdr" else ()
    proposals = db.all(cur, f"""
        select ap.id, ap.proposed_at, ap.why_now, a.id as account_id, a.name, a.primary_domain, a.fit_tier,
               sc.priority, p.name as play, p.urgent, u.name as owner
        from account_plays ap join accounts a on a.id = ap.account_id join plays p on p.id = ap.play_id
        left join account_scores sc on sc.account_id = a.id left join users u on u.id = ap.owner_id
        where ap.state = 'proposed' and {mine} order by p.urgent desc, sc.priority desc nulls last limit 40""", *args)
    approvals = db.all(cur, f"""
        select m.id, m.subject, m.step_index, m.status, m.created_at, pe.full_name, pe.photo_url, pe.title, a.name as company,
               a.id as account_id, p.name as play
        from messages m join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
        join people pe on pe.id = e.person_id join accounts a on a.id = ap.account_id join plays p on p.id = ap.play_id
        where m.status in ('awaiting_approval', 'failed_gate') and m.channel = 'email' and {mine} order by m.created_at limit 60""", *args)
    hot = db.all(cur, """
        select r.id, r.received_at, r.label, r.cleaned, r.sla_due_at, pe.full_name, pe.photo_url, pe.title, a.name as company,
               a.id as account_id
        from replies r join accounts a on a.id = r.account_id left join people pe on pe.id = r.person_id
        join tasks t on t.reply_id = r.id and t.status = 'open' and t.kind in ('reply', 'review_reply')
        left join account_plays ap on ap.id = t.account_play_id
        where (t.owner_id = %s or %s) order by r.sla_due_at nulls last, r.received_at limit 40""",
        uid, user["role"] != "sdr")
    tasks = db.all(cur, """
        select t.id, t.kind, t.title, t.due_at, t.note, pe.id as person_id, pe.full_name, pe.photo_url, pe.title as person_title,
               pe.phone, pe.linkedin_url, a.name as company, a.id as account_id, t.message_id, m.body as draft,
               m.status as draft_status, m.gate -> 'failures' as draft_failures
        from tasks t left join people pe on pe.id = t.person_id left join messages m on m.id = t.message_id
        left join account_plays ap on ap.id = t.account_play_id left join accounts a on a.id = coalesce(ap.account_id, pe.account_id)
        where t.status = 'open' and t.kind not in ('reply', 'review_reply') and t.owner_id = %s and t.due_at <= app_now() + interval '1 day'
        order by t.due_at limit 50""", uid)
    meetings = db.all(cur, """
        select m.id, m.starts_at, m.status, a.name as company, a.id as account_id, pe.full_name, pe.photo_url
        from meetings m join accounts a on a.id = m.account_id left join people pe on pe.id = m.person_id
        where m.owner_id = %s and m.starts_at between app_now() - interval '1 day' and app_now() + interval '7 days'
        order by m.starts_at""", uid)
    return {"proposals": proposals, "approvals": approvals, "replies": hot, "tasks": tasks, "meetings": meetings,
            "now": db.val(cur, "select app_now()")}


# ---------------------------------------------------------------- accounts

def accounts(cur, *, q: str | None, view: str, owner: int | None, limit: int = 200) -> list[dict]:
    where = ["a.fit_tier in ('A','B')"] if view != "all" else ["true"]
    args: list = []
    if view == "in_play":
        where.append("ap.id is not null")
    elif view == "rising":
        where.append("sh.delta > 0")
    if q:
        where.append("(a.name ilike %s or a.primary_domain ilike %s)")
        args += [f"%{q}%", f"%{q}%"]
    if owner:
        where.append("a.owner_id = %s")
        args.append(owner)
    return db.all(cur, f"""
        select a.id, a.name, a.primary_domain, a.industry, a.employees, a.hq_country, a.fit_tier, a.lifecycle,
               sc.priority, sc.fit, sc.intent, sc.engagement, u.name as owner, ap.state as play_state, p.name as play,
               rs.label as reason, rs.type_key as reason_type, rs.observed_at as reason_at, coalesce(sh.delta, 0) as week_change,
               lp.state as last_state, hd.until as hold_until
        from accounts a left join account_scores sc on sc.account_id = a.id
        left join users u on u.id = a.owner_id
        left join account_plays ap on ap.account_id = a.id and ap.state in {OPEN}
        left join plays p on p.id = ap.play_id
        left join lateral (select t.label, s.type_key, s.observed_at from signals s join signal_types t on t.key = s.type_key
                           where s.id = sc.reason_signal_id) rs on true
        left join lateral (select state from account_plays x where x.account_id = a.id
                           order by x.proposed_at desc limit 1) lp on true
        left join lateral (select max(until) as until from holds h where h.account_id = a.id
                           and h.person_id is null and h.until > app_now()) hd on true
        left join lateral (select sum(priority - coalesce(previous, 0)) as delta from score_history h
                           where h.account_id = a.id and h.at > app_now() - interval '7 days') sh on true
        where {' and '.join(where)}
        order by {"coalesce(sh.delta, 0) desc," if view == "rising" else ""} sc.priority desc nulls last, a.name limit %s""",
        *args, limit)


def account(cur, account_id: int, *, money: bool) -> dict | None:
    a = db.one(cur, """select a.*, u.name as owner, p.name as parent_name from accounts a
                       left join users u on u.id = a.owner_id left join accounts p on p.id = a.parent_id where a.id = %s""",
               account_id)
    if a is None:
        return None
    score = db.one(cur, "select * from account_scores where account_id = %s", account_id)
    labels = {r["key"]: r for r in db.all(cur, "select key, label, because, weight, half_life_days from signal_types")}
    sigs = db.all(cur, """select s.id, s.type_key, s.observed_at, s.strength, s.evidence, s.source, p.full_name
                          from signals s left join people p on p.id = s.person_id
                          where s.account_id = %s order by s.observed_at desc limit 60""", account_id)
    for s in sigs:
        s["label"] = labels.get(s["type_key"], {}).get("label", s["type_key"])
    contributions = []
    if score:
        for c in score["breakdown"].get("contributions", []):
            if c["value"] <= 0.05:
                continue
            contributions.append({**c, "label": labels.get(c["type"], {}).get("label", c["type"])})
    plays_ = db.all(cur, """select ap.id, ap.state, ap.arm, ap.proposed_at, ap.closed_at, ap.close_reason, ap.why_now,
                                   ap.brief, p.name as play, p.autonomy, u.name as owner
                            from account_plays ap join plays p on p.id = ap.play_id left join users u on u.id = ap.owner_id
                            where ap.account_id = %s order by ap.proposed_at desc""", account_id)
    current = next((x for x in plays_ if x["state"] in OPEN), None)
    people = db.all(cur, """select p.id, p.full_name, p.photo_url, p.title, p.persona_key, p.email, p.email_status, p.status, p.country,
                                   p.is_champion, p.linkedin_url, p.phone, e.state as enrollment, e.step_index,
                                   e.stop_reason, e.pause_reason, e.next_at
                            from people p left join lateral (select * from enrollments e where e.person_id = p.id
                              order by e.created_at desc limit 1) e on true
                            where p.account_id = %s order by p.persona_key nulls last, p.full_name""", account_id)
    gaps = db.all(cur, """select g.persona_key, g.reason, pe.label from committee_gaps g join personas pe on pe.key = g.persona_key
                          where g.account_play_id = %s""", current["id"]) if current else []
    messages = db.all(cur, """select m.id, m.step_index, m.subject, m.status, m.sent_at, m.scheduled_for, pe.full_name, pe.photo_url,
                                     m.approval_mode
                              from messages m join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
                              join people pe on pe.id = e.person_id where ap.account_id = %s
                              order by coalesce(m.sent_at, m.scheduled_for, m.created_at) desc limit 60""", account_id)
    reps = db.all(cur, """select r.id, r.received_at, r.label, r.cleaned, r.hot, pe.full_name, pe.photo_url from replies r
                          left join people pe on pe.id = r.person_id where r.account_id = %s order by r.received_at desc""",
                  account_id)
    meetings = db.all(cur, """select m.id, m.starts_at, m.status, pe.full_name, pe.photo_url from meetings m
                              left join people pe on pe.id = m.person_id where m.account_id = %s order by m.starts_at desc""",
                      account_id)
    opps = db.all(cur, "select id, name, stage, created_at, won, attribution" + (", amount_cents" if money else "") +
                  " from opportunities where account_id = %s order by created_at desc", account_id)
    holds = db.all(cur, "select reason, until from holds where account_id = %s and until > app_now() order by until desc",
                   account_id)
    calendar = []
    if current:
        calendar = db.all(cur, """
            select pe.full_name, pe.photo_url, e.persona_key, e.state, e.step_index, e.next_at, m.step_index as msg_step,
                   coalesce(m.sent_at, m.scheduled_for) as at, m.status
            from enrollments e join people pe on pe.id = e.person_id
            left join messages m on m.enrollment_id = e.id
            where e.account_play_id = %s order by e.id, m.step_index""", current["id"])
    return {"account": a, "score": score, "contributions": contributions, "signals": sigs, "plays": plays_,
            "current": current, "people": people, "gaps": gaps, "messages": messages, "replies": reps,
            "meetings": meetings, "opportunities": opps, "holds": holds, "calendar": calendar}


# ---------------------------------------------------------------- tasks

def task(cur, task_id: int) -> dict | None:
    t = db.one(cur, """select t.*, pe.full_name, pe.photo_url, pe.title as person_title, pe.phone, pe.phone_status,
                              pe.linkedin_url, a.name as company, a.id as account_id, pl.name as play,
                              m.body as draft, m.status as draft_status, m.gate, m.citations, u.name as owner
                       from tasks t left join people pe on pe.id = t.person_id
                       left join account_plays ap on ap.id = t.account_play_id left join plays pl on pl.id = ap.play_id
                       left join accounts a on a.id = coalesce(ap.account_id, pe.account_id)
                       left join messages m on m.id = t.message_id left join users u on u.id = t.owner_id
                       where t.id = %s""", task_id)
    if t is None:
        return None
    from .sdr_steps import CALL_OUTCOMES, LINKEDIN_OUTCOMES, note_limit
    ids = (t["citations"] or {}).get("ids", []) if t["citations"] else []
    t["sources"] = db.all(cur, "select id, kind, text, source_url as url from facts where id = any(%s)", ids) if ids else []
    t["outcomes"] = LINKEDIN_OUTCOMES.get(t["kind"]) or (CALL_OUTCOMES if t["kind"] == "call" else {"done": "Done"})
    t["max_chars"] = note_limit(cur) if t["kind"] == "linkedin_connect" else None
    return t


# ---------------------------------------------------------------- meetings

def meeting(cur, meeting_id: int, *, money: bool) -> dict | None:
    m = db.one(cur, """select m.*, pe.full_name, pe.photo_url, pe.title as person_title, a.name as company, a.primary_domain,
                              pl.name as play, pl.id as play_id, u.name as owner
                       from meetings m left join people pe on pe.id = m.person_id join accounts a on a.id = m.account_id
                       left join account_plays ap on ap.id = m.account_play_id left join plays pl on pl.id = ap.play_id
                       left join users u on u.id = m.owner_id where m.id = %s""", meeting_id)
    if m is None:
        return None
    m["notes"] = db.all(cur, """select cn.id, cn.text, cn.created_at, cn.worth_learning, u.name as by from call_notes cn
                                left join users u on u.id = cn.marked_by where cn.meeting_id = %s order by cn.created_at""", meeting_id)
    m["learnings"] = db.all(cur, """select l.kind, l.text, l.quote from learnings l join call_notes cn on cn.id = l.call_note_id
                                    where cn.meeting_id = %s""", meeting_id)
    m["deals"] = db.all(cur, "select id, name, stage, attribution, won, closed_at, created_at" + (", amount_cents" if money else "") +
                        " from opportunities where attribution_meeting_id = %s or (account_id = %s and created_at >= %s) "
                        "order by created_at", meeting_id, m["account_id"], m["booked_at"])
    return m


# ---------------------------------------------------------------- people

def person(cur, person_id: int) -> dict | None:
    """One person, everything the desk has done with them, oldest commitments first: plays they were in, every touch
    on every channel, their replies and meetings, signals they set off, and whether they may be contacted at all."""
    p = db.one(cur, """select p.*, a.name as company, a.primary_domain, a.id as account_id from people p
                       left join accounts a on a.id = p.account_id where p.id = %s""", person_id)
    if p is None:
        return None
    enrollments = db.all(cur, """select e.id, e.state, e.step_index, e.stop_reason, e.pause_reason, e.next_at, e.created_at,
                                        e.persona_key, pl.id as play_id, pl.name as play, pl.sequence, ap.id as account_play_id,
                                        ap.state as play_state,
                                        (select json_build_object('id', m.id, 'person_id', m.person_id, 'name', pe.full_name,
                                                                  'starts_at', m.starts_at, 'status', m.status)
                                         from meetings m left join people pe on pe.id = m.person_id
                                         where m.account_play_id = ap.id order by m.booked_at desc limit 1) as meeting
                                 from enrollments e join account_plays ap on ap.id = e.account_play_id
                                 join plays pl on pl.id = ap.play_id where e.person_id = %s order by e.created_at desc""", person_id)
    touches = db.all(cur, """select t.id, t.channel, t.direction, t.kind, t.at, t.source, t.message_id, m.subject, m.step_index
                             from touches t left join messages m on m.id = t.message_id
                             where t.person_id = %s order by t.at desc limit 100""", person_id)
    reps = db.all(cur, """select id, received_at, label, cleaned, hot, channel from replies where person_id = %s
                          order by received_at desc""", person_id)
    meetings = db.all(cur, """select m.id, m.starts_at, m.booked_at, m.status, m.source, pl.name as play from meetings m
                              left join account_plays ap on ap.id = m.account_play_id left join plays pl on pl.id = ap.play_id
                              where m.person_id = %s order by m.starts_at desc""", person_id)
    sigs = db.all(cur, """select s.id, s.type_key, t.label, s.observed_at, s.evidence from signals s
                          join signal_types t on t.key = s.type_key where s.person_id = %s order by s.observed_at desc limit 20""",
                  person_id)
    blocked = db.all(cur, """select kind, reason, created_at from suppressions
                             where (expires_at is null or expires_at > app_now()) and (
                               (kind = 'person' and value = %s) or (kind = 'email' and value = %s) or (kind = 'phone' and value = %s)
                               or (kind = 'domain' and value = split_part(%s, '@', 2)))""",
                     str(person_id), p["email"] or "", p["phone"] or "", p["email"] or "")
    return {"person": p, "enrollments": enrollments, "touches": touches, "replies": reps, "meetings": meetings,
            "signals": sigs, "suppressed": blocked}


# ---------------------------------------------------------------- signals

def signals_page(cur) -> dict:
    # One query per status, so each walks the (status, ingested_at) index instead of sorting every signal.
    feed = []
    for status in ("matched", "unmatched"):
        feed += db.all(cur, """select s.id, s.type_key, t.label, s.observed_at, s.ingested_at, s.evidence, s.source, s.status,
                                      s.status_reason, s.raw_company, s.raw_domain, a.id as account_id, a.name, a.primary_domain, a.fit_tier
                               from signals s join signal_types t on t.key = s.type_key
                               left join accounts a on a.id = s.account_id
                               where s.status = %s order by s.ingested_at desc limit 120""", status)
    sources = db.all(cur, """select s.key, s.label, s.cadence_minutes, s.paid, s.enabled, s.provider,
                                    r.started_at as last_run, r.fetched, r.matched, r.unmatched, r.error,
                                    (select count(*) from signals x where x.source = s.key
                                       and x.ingested_at > app_now() - interval '7 days') as week
                             from signal_sources s left join lateral (select * from source_runs r where r.source_key = s.key
                               order by started_at desc limit 1) r on true order by s.label""")
    types = signal_performance(cur)
    return {"feed": feed, "sources": sources, "types": types}


def signal_performance(cur) -> list[dict]:
    """For each signal type: accounts it started a play for, and meetings within 60 days, treated against the
    comparison group. Aggregates from account plays (thousands), never from all signals (millions)."""
    rows = db.all(cur, """
        with ap as (
          select s.type_key, ap.arm, ap.account_id, ap.proposed_at
          from account_plays ap join signals s on s.id = ap.trigger_signal_id
        ), outcome as (
          select ap.*, exists (select 1 from meetings m where m.account_id = ap.account_id
                               and m.booked_at between ap.proposed_at and ap.proposed_at + interval '60 days') as met,
                       exists (select 1 from replies r where r.account_id = ap.account_id and r.hot
                               and r.received_at between ap.proposed_at and ap.proposed_at + interval '60 days') as pos
          from ap
        )
        select t.key, t.label, t.because, t.weight, t.half_life_days,
          (select count(*) from signals s where s.type_key = t.key and s.status = 'matched'
             and s.ingested_at > app_now() - interval '90 days') as seen,
          count(o.*) filter (where o.arm = 'treated') as treated,
          count(o.*) filter (where o.arm = 'holdout') as holdout,
          count(o.*) filter (where o.arm = 'treated' and o.met) as treated_meetings,
          count(o.*) filter (where o.arm = 'holdout' and o.met) as holdout_meetings,
          count(o.*) filter (where o.arm = 'treated' and o.pos) as positive
        from signal_types t left join outcome o on o.type_key = t.key
        group by t.key order by t.weight desc""")
    for r in rows:
        r["meeting_rate"] = (r["treated_meetings"] / r["treated"]) if r["treated"] else None
    return rows


# ---------------------------------------------------------------- plays

FUNNEL = """
    count(*) filter (where arm = 'treated') as proposed,
    count(*) filter (where arm = 'treated' and state not in ('proposed','skipped','expired')) as accepted,
    count(*) filter (where arm = 'treated' and exists (select 1 from touches t where t.account_play_id = ap.id
                     and t.direction = 'out')) as contacted,
    count(*) filter (where arm = 'treated' and exists (select 1 from replies r join enrollments e on e.person_id = r.person_id
                     and e.account_play_id = ap.id where r.received_at >= ap.proposed_at
                     and coalesce(r.label, 'other') not in ('out_of_office','auto_reply','bounce'))) as replied,
    count(*) filter (where arm = 'treated' and exists (select 1 from replies r join enrollments e on e.person_id = r.person_id
                     and e.account_play_id = ap.id where r.hot and r.received_at >= ap.proposed_at)) as positive,
    count(*) filter (where arm = 'treated' and exists (select 1 from meetings m where m.account_play_id = ap.id
                     and m.source <> 'inbound' and m.status <> 'cancelled')) as meetings,
    count(*) filter (where arm = 'holdout') as holdout,
    -- The comparison counts any meeting or deal at the account, whatever started it, the same way in both arms.
    count(*) filter (where arm = 'treated' and exists (select 1 from meetings m where m.account_id = ap.account_id
                     and m.status <> 'cancelled' and m.booked_at between ap.proposed_at and ap.proposed_at + interval '60 days')) as treated_meetings_any,
    count(*) filter (where arm = 'holdout' and exists (select 1 from meetings m where m.account_id = ap.account_id
                     and m.status <> 'cancelled' and m.booked_at between ap.proposed_at and ap.proposed_at + interval '60 days')) as holdout_meetings,
    count(*) filter (where arm = 'treated' and exists (select 1 from opportunities o where o.account_id = ap.account_id
                     and o.created_at between ap.proposed_at and ap.proposed_at + interval '90 days')) as treated_deals,
    count(*) filter (where arm = 'holdout' and exists (select 1 from opportunities o where o.account_id = ap.account_id
                     and o.created_at between ap.proposed_at and ap.proposed_at + interval '90 days')) as holdout_deals
"""


def lifts(f: dict) -> tuple[dict, dict]:
    return (stats.lift_report(f["treated_meetings_any"], f["proposed"], f["holdout_meetings"], f["holdout"]),
            stats.lift_report(f["treated_deals"], f["proposed"], f["holdout_deals"], f["holdout"]))


def plays_page(cur, *, money: bool) -> list[dict]:
    out = []
    for p in db.all(cur, "select p.*, u.name as owner from plays p left join users u on u.id = p.owner_id order by p.id"):
        f = db.one(cur, "select " + FUNNEL + """,
                   count(*) filter (where state in ('proposed','accepted','researching','approving','active','engaged','meeting')) as open
            from account_plays ap where ap.play_id = %s""", p["id"])
        approvals = db.one(cur, """
            select count(*) filter (where approval_mode = 'person') as by_person,
                   count(*) filter (where approval_mode = 'person' and not edited) as unedited,
                   count(*) filter (where status = 'rejected') as rejected,
                   count(*) filter (where status = 'sent') as sent,
                   count(*) filter (where status = 'failed_gate') as failed
            from messages m join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
            where ap.play_id = %s and m.channel = 'email'""", p["id"])
        bounces = db.val(cur, """select count(*) from deliveries d join messages m on m.id = d.message_id
                                 join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
                                 where ap.play_id = %s and d.event = 'bounced_hard'""", p["id"])
        latency = db.val(cur, """select percentile_cont(0.5) within group (order by extract(epoch from (t.first_at - s.ingested_at)) / 3600)
                                 from account_plays ap join signals s on s.id = ap.trigger_signal_id
                                 join lateral (select min(at) as first_at from touches t where t.account_play_id = ap.id
                                               and t.direction = 'out') t on t.first_at is not null
                                 where ap.play_id = %s""", p["id"])
        row = {**p, "funnel": f, "approvals": approvals, "bounces": bounces, "median_hours_to_first_touch": latency,
               "lift": lifts(f)[0], "deal_lift": lifts(f)[1], "promotion": promotion_check(cur, p)}
        if money:
            row["pipeline_cents"] = db.val(cur, """select coalesce(sum(amount_cents), 0) from opportunities
                                                   where source_play_id = %s and attribution = 'sourced'""", p["id"])
        out.append(row)
    return out


STAGES = ["research", "draft", "supervised", "autonomous"]


def promotion_check(cur, play: dict) -> dict:
    """Whether the play has earned the next autonomy stage (docs/SPEC.md section 9 and 22.5)."""
    idx = STAGES.index(play["autonomy"])
    if idx == len(STAGES) - 1:
        return {"next": None, "ready": False, "checks": []}
    last = db.all(cur, """select m.edited, m.status from messages m join enrollments e on e.id = m.enrollment_id
                          join account_plays ap on ap.id = e.account_play_id
                          where ap.play_id = %s and m.approval_mode = 'person' and m.channel = 'email' order by m.approved_at desc limit 50""", play["id"])
    unedited = sum(1 for m in last if not m["edited"])
    sent = db.val(cur, """select count(*) from messages m join enrollments e on e.id = m.enrollment_id
                          join account_plays ap on ap.id = e.account_play_id where ap.play_id = %s and m.status = 'sent' and m.channel = 'email'""",
                  play["id"]) or 0
    bounces = db.val(cur, """select count(*) from deliveries d join messages m on m.id = d.message_id
                             join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
                             where ap.play_id = %s and d.event = 'bounced_hard'""", play["id"]) or 0
    complaints = db.val(cur, """select count(*) from deliveries d join messages m on m.id = d.message_id
                                join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
                                where ap.play_id = %s and d.event = 'complaint'""", play["id"]) or 0
    unknown = db.val(cur, """select count(*) from sending_domains d where exists (select 1 from mailboxes mb where mb.domain = d.domain
                             and mb.status = 'active') and d.spam_rate is null""") or 0
    positives = db.val(cur, """select count(*) from replies r join messages m on m.id = r.message_id join enrollments e on e.id = m.enrollment_id
                               join account_plays ap on ap.id = e.account_play_id where ap.play_id = %s and r.hot""", play["id"]) or 0
    checks = [
        {"label": "50 drafts approved by a person", "value": f"{len(last)} of 50", "ok": len(last) >= 50},
        {"label": "Approved without edits", "value": f"{(unedited / len(last)):.0%}" if last else "None yet",
         "ok": bool(last) and unedited / len(last) >= 0.9},
        {"label": "Spam complaints", "value": str(complaints), "ok": complaints == 0},
        {"label": "Bounce rate", "value": f"{(bounces / sent):.1%}" if sent else "None sent",
         "ok": bool(sent) and bounces / sent < 0.02},
        {"label": "Positive reply rate", "value": f"{(positives / sent):.1%}" if sent else "None sent",
         "ok": bool(sent) and positives / sent >= float(play["positive_floor"])},
        {"label": "Complaint data for every sending domain", "value": "Known" if not unknown else f"{unknown} unknown",
         "ok": unknown == 0},
    ]
    return {"next": STAGES[idx + 1], "ready": all(c["ok"] for c in checks), "checks": checks}


# ---------------------------------------------------------------- approvals and replies

def message(cur, message_id: int) -> dict | None:
    m = db.one(cur, """select m.*, pe.full_name, pe.photo_url, pe.first_name, pe.title, pe.email, pe.country, a.name as company,
                              a.id as account_id, p.name as play, p.autonomy, ap.why_now, ap.brief, u.name as owner,
                              mb.address as mailbox
                       from messages m join enrollments e on e.id = m.enrollment_id
                       join account_plays ap on ap.id = e.account_play_id join people pe on pe.id = e.person_id
                       join accounts a on a.id = ap.account_id join plays p on p.id = ap.play_id
                       left join users u on u.id = ap.owner_id left join mailboxes mb on mb.id = coalesce(m.mailbox_id, e.mailbox_id)
                       where m.id = %s""", message_id)
    if m is None:
        return None
    ids = (m["citations"] or {}).get("ids", [])
    m["facts"] = db.all(cur, "select id, kind, text, source_url, observed_at from facts where id = any(%s)", ids) if ids else []
    return m


def replies_page(cur, *, view: str, user_id: int | None = None) -> list[dict]:
    where = {"needs_person": "r.needs_review and r.handled_at is null", "hot": "r.hot", "all": "true",
             "mine": f"""coalesce((select ap.owner_id from account_plays ap where ap.account_id = r.account_id
                         order by ap.proposed_at desc limit 1), (select owner_id from accounts where id = r.account_id))
                         = {int(user_id or 0)}"""}.get(view, "true")
    return db.all(cur, f"""select r.id, r.received_at, r.label, r.confidence, r.classified_by, r.cleaned, r.hot,
                                  r.needs_review, r.review_reason, r.handled_at, r.outcome, r.sla_due_at, r.same_person,
                                  r.language, pe.full_name, pe.photo_url, pe.title, a.name as company, a.id as account_id
                           from replies r left join people pe on pe.id = r.person_id left join accounts a on a.id = r.account_id
                           where {where} order by r.received_at desc limit 200""")


def reply(cur, reply_id: int) -> dict | None:
    r = db.one(cur, """select r.*, pe.full_name, pe.photo_url, pe.title, pe.first_name, a.name as company, m.subject as our_subject,
                              m.body as our_body
                       from replies r left join people pe on pe.id = r.person_id left join accounts a on a.id = r.account_id
                       left join messages m on m.id = r.message_id where r.id = %s""", reply_id)
    if r:
        r["extracted"] = {k: v for k, v in (r["extracted"] or {}).items() if not k.startswith("_")}
    return r


# ---------------------------------------------------------------- deliverability

def deliverability(cur) -> dict:
    domains = db.all(cur, """select d.*, (app_now()::date - d.registered_at) as age_days,
                                    (select count(*) from mailboxes m where m.domain = d.domain) as mailboxes
                             from sending_domains d order by d.domain""")
    boxes = []
    for m in db.all(cur, """select m.*, u.name as owner from mailboxes m join users u on u.id = m.user_id order by m.domain, m.address"""):
        stats_ = db.one(cur, """select count(*) filter (where event = 'sent') as sent,
                                       count(*) filter (where event = 'bounced_hard') as bounced,
                                       count(*) filter (where event = 'complaint') as complaints
                                from deliveries where mailbox_id = %s and at > app_now() - interval '14 days'""", m["id"])
        seeds = db.all(cur, """select distinct on (provider) provider, inbox, spam, missing, seeds, at from placement_tests
                               where mailbox_id = %s order by provider, at desc""", m["id"])
        boxes.append({**m, **stats_, "today": outreach.sent_today(cur, m["id"]), "cap": outreach.mailbox_capacity(cur, m),
                      "blocked": outreach.mailbox_sendable(cur, m), "placement": {r["provider"]: r for r in seeds},
                      "placement_at": min((r["at"] for r in seeds), default=None)})
    forecast = db.all(cur, """select date_trunc('day', scheduled_for) as day, count(*) as scheduled from messages
                              where status = 'scheduled' and scheduled_for < app_now() + interval '14 days'
                              group by 1 order by 1""")
    names = {r["key"]: r["name"] for r in db.all(cur, "select key, name from plays")}
    watch = db.all(cur, "select * from play_step_watch order by paused desc, template_key")
    for w in watch:
        key, _, step = w["template_key"].partition(":")
        w["play"] = names.get(key, key)
        w["step"] = int(step or 0) + 1
    capacity = sum(b["cap"] for b in boxes if not b["blocked"])
    thresholds = {k: float(outreach.setting(cur, k, d)) for k, d in (("placement_hold_below", 0.8), ("placement_pause_below", 0.5))}
    return {"domains": domains, "mailboxes": boxes, "forecast": forecast, "capacity": capacity, "watch": watch,
            "placement": thresholds}


# ---------------------------------------------------------------- results

def results(cur, *, money: bool) -> dict:
    f = db.one(cur, "select " + FUNNEL + " from account_plays ap")
    opps = db.one(cur, """select count(*) filter (where attribution = 'sourced') as sourced,
                                 count(*) filter (where attribution = 'influenced') as influenced""" +
                  (""", coalesce(sum(amount_cents) filter (where attribution = 'sourced'), 0) as sourced_cents,
                       coalesce(sum(amount_cents) filter (where attribution = 'influenced'), 0) as influenced_cents""" if money else "") +
                  " from opportunities where attribution <> 'none'")
    sla = db.one(cur, """select percentile_cont(0.5) within group (order by extract(epoch from (handled_at - received_at)) / 3600) as median_hours,
                                count(*) filter (where escalated_at is not null) as missed, count(*) as total
                         from replies where hot and handled_at is not null""")
    labels = db.all(cur, "select label, count(*) as n from replies where label is not null group by label order by n desc")
    # The model extracted each item from one call; code groups them, so a theme shows how many calls raised it.
    learn = db.all(cur, """
        select l.kind, l.text, count(distinct l.call_note_id) as calls, max(cn.created_at) as last_at,
               array_agg(distinct a.name) as companies, array_agg(distinct p.name) filter (where p.name is not null) as plays,
               (array_agg(l.quote order by cn.created_at desc))[1] as quote
        from learnings l join call_notes cn on cn.id = l.call_note_id join meetings m on m.id = cn.meeting_id
        join accounts a on a.id = m.account_id left join plays p on p.id = l.play_id
        group by l.kind, l.text order by calls desc, last_at desc""")
    # Each channel judged on its own terms over 90 days: people reached there, how many answered there, and meetings
    # within 30 days of their first touch there. A person reached on two channels counts in both.
    channels = db.all(cur, """
        with first_out as (
          select channel, person_id, min(at) as first_at from touches
          where direction = 'out' and channel in ('email', 'linkedin', 'call') and person_id is not null
            and at > app_now() - interval '90 days' group by 1, 2)
        select o.channel, count(*) as reached,
               count(*) filter (where exists (select 1 from replies r where r.person_id = o.person_id
                   and r.channel = o.channel and r.received_at >= o.first_at
                   and coalesce(r.label, 'other') not in ('out_of_office', 'auto_reply', 'bounce'))) as replied,
               count(*) filter (where exists (select 1 from touches t where t.person_id = o.person_id
                   and t.kind = 'linkedin_accepted' and t.at >= o.first_at)) as accepted,
               count(*) filter (where exists (select 1 from touches t where t.person_id = o.person_id
                   and t.kind = 'call_connected' and t.at >= o.first_at)) as spoke,
               count(*) filter (where exists (select 1 from meetings m where m.person_id = o.person_id
                   and m.booked_at between o.first_at and o.first_at + interval '30 days')) as meetings
        from first_out o group by 1 order by reached desc""")
    meeting_lift, deal_lift = lifts(f)
    out = {"funnel": f, "lift": meeting_lift, "deal_lift": deal_lift,
           "opportunities": opps, "sla": sla, "labels": labels, "signals": signal_performance(cur), "learnings": learn,
           "channels": channels}
    if money:
        spend = db.all(cur, """select vendor, unit, sum(qty) as qty, sum(cost_cents) as cost_cents from ledger
                               where at >= date_trunc('month', app_now()) group by vendor, unit order by vendor""")
        out["spend"] = spend
        total_cents = sum(float(s["cost_cents"]) for s in spend)
        # This month's spend over this month's outbound meetings: the same window on both sides.
        month_meetings = db.val(cur, """select count(*) from meetings where account_play_id is not null and source <> 'inbound'
                                        and status <> 'cancelled' and booked_at >= date_trunc('month', app_now())""")
        out["meetings_this_month"] = month_meetings
        out["cost_per_meeting_cents"] = (total_cents / month_meetings) if month_meetings else None
    return out


# ---------------------------------------------------------------- health and settings

def health(cur) -> dict:
    jobs = db.all(cur, "select kind, status, count(*) as n from jobs where status in ('queued','running','failed','dead') group by 1,2 order by 1")
    outbox = db.all(cur, "select status, count(*) as n from crm_outbox group by status")
    alerts = db.all(cur, "select id, at, kind, severity, channel, title, body, delivered_at, delivery_error from alerts order by at desc limit 40")
    budgets = db.all(cur, """select b.vendor, b.monthly_cap_cents as cap, coalesce((select sum(case when b.vendor = 'anthropic'
                               then l.cost_cents else l.qty end) from ledger l where l.vendor = b.vendor
                               and l.at >= date_trunc('month', app_now())), 0) as used from budgets b order by b.vendor""")
    llm_calls = db.all(cur, "select task, source, count(*) as n from llm_calls group by 1,2 order by 1,2")
    return {"monitors": monitors.latest(cur), "jobs": jobs, "outbox": outbox, "alerts": alerts, "budgets": budgets,
            "llm": llm_calls, "adapters": adapters.get().notes,
            "kill_switch": bool(db.val(cur, "select value from settings where key = 'kill_switch'"))}


def settings(cur) -> dict:
    return {"settings": {r["key"]: r["value"] for r in db.all(cur, "select key, value from settings where key not like 'sched:%%' "
                                                       "and key <> 'unsubscribe_secret'")},
            "signal_types": db.all(cur, "select * from signal_types order by weight desc"),
            "icp": db.one(cur, "select * from icp_versions order by published_at desc limit 1"),
            "personas": db.all(cur, "select * from personas"),
            "regions": db.all(cur, "select * from region_rules order by country"),
            "suppressions": db.all(cur, "select id, kind, value, reason, source, created_at, expires_at from suppressions "
                                        "order by created_at desc limit 100")}
