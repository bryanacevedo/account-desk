"""Read models for the web app. One function per page or side sheet. Money appears only when `money` is true
(managers and GTM); a rep's read never carries it."""
from __future__ import annotations

from . import adapters, alerts, db, monitors, outreach, region_rules, sending, spend, stats, suggestions
from . import plays as plays_mod
from .jobs import request_progress

OPEN = ("proposed", "accepted", "researching", "approving", "active", "engaged", "meeting")
# A person with a reply nobody has read yet (no label, or flagged for a person) and not handled. {person} is the column
# holding the person's id. Their open calls, LinkedIn steps and drafts are held back with "They replied; read it first".
UNREAD_REPLY = """exists (select 1 from replies ur where ur.person_id = {person} and ur.handled_at is null
                          and (ur.label is null or ur.needs_review))"""


def _iso(rows: list[dict]) -> list[dict]:
    return rows


# ---------------------------------------------------------------- today

def today(cur, user: dict) -> dict:
    uid = user["id"]
    mine = "ap.owner_id = %s" if user["role"] == "sdr" else "true"
    args = (uid,) if user["role"] == "sdr" else ()
    proposals = db.all(cur, f"""
        select ap.id, ap.proposed_at, ap.why_now, a.id as account_id, a.name, a.primary_domain, a.fit_tier,
               sc.priority, p.name as play, p.urgent, u.name as owner, u.role as owner_role
        from account_plays ap join accounts a on a.id = ap.account_id join plays p on p.id = ap.play_id
        left join account_scores sc on sc.account_id = a.id left join users u on u.id = ap.owner_id
        where ap.state = 'proposed' and {mine} order by p.urgent desc, sc.priority desc nulls last limit 40""", *args)
    approvals = db.all(cur, f"""
        select m.id, m.subject, m.step_index, email_no(m.enrollment_id, m.step_index) as email_no, m.status, m.created_at, pe.full_name, pe.photo_url, pe.title, a.name as company,
               a.id as account_id, p.name as play
        from messages m join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
        join people pe on pe.id = e.person_id join accounts a on a.id = ap.account_id join plays p on p.id = ap.play_id
        where m.status in ('awaiting_approval', 'failed_gate') and m.channel = 'email' and {mine}
          and not {UNREAD_REPLY.format(person='e.person_id')} order by m.created_at limit 60""", *args)
    hot = db.all(cur, """
        select r.id, r.received_at, r.label, r.cleaned, r.sla_due_at, pe.full_name, pe.photo_url, pe.title, a.name as company,
               a.id as account_id
        from replies r join accounts a on a.id = r.account_id left join people pe on pe.id = r.person_id
        where exists (select 1 from tasks t where t.reply_id = r.id and t.status = 'open'
                        and t.kind in ('reply', 'review_reply') and (t.owner_id = %s or %s))
        order by r.sla_due_at nulls last, r.received_at limit 40""",
        uid, user["role"] != "sdr")
    tasks = db.all(cur, f"""
        select t.id, t.kind, t.title, t.due_at, t.note, pe.id as person_id, pe.full_name, pe.photo_url, pe.title as person_title,
               pe.phone, pe.linkedin_url, a.name as company, a.id as account_id, t.message_id, m.body as draft,
               m.status as draft_status, m.gate -> 'failures' as draft_failures
        from tasks t left join people pe on pe.id = t.person_id left join messages m on m.id = t.message_id
        left join account_plays ap on ap.id = t.account_play_id left join accounts a on a.id = coalesce(ap.account_id, pe.account_id)
        where t.status = 'open' and t.kind not in ('reply', 'review_reply') and t.owner_id = %s and t.due_at <= app_now() + interval '1 day'
          and not {UNREAD_REPLY.format(person='t.person_id')}
        order by t.due_at limit 50""", uid)
    meetings = db.all(cur, """
        select m.id, m.starts_at, m.status, a.name as company, a.id as account_id, pe.full_name, pe.photo_url
        from meetings m join accounts a on a.id = m.account_id left join people pe on pe.id = m.person_id
        where m.owner_id = %s and m.starts_at between app_now() - interval '1 day' and app_now() + interval '7 days'
        order by m.starts_at""", uid)
    # Decision 100: a proposal nobody decided in time stays on Today with "Propose again" until its account has a newer
    # play, a gate blocks it, or 14 days have passed since it lapsed.
    expired = db.all(cur, f"""
        select ap.id, ap.proposed_at, ap.closed_at, ap.why_now, a.id as account_id, a.name, a.primary_domain,
               ap.play_id, ap.trigger_signal_id, ap.owner_id, sc.priority, p.name as play, p.urgent, u.name as owner, u.role as owner_role,
               case when p.urgent then {_ttl("urgent_proposal_ttl_days", 1)} else {_ttl("proposal_ttl_days", 5)} end as limit_days
        from account_plays ap join accounts a on a.id = ap.account_id join plays p on p.id = ap.play_id
        left join account_scores sc on sc.account_id = a.id left join users u on u.id = ap.owner_id
        where ap.state = 'expired' and ap.close_reason = 'expired' and ap.arm = 'treated' and {mine}
          and ap.closed_at > app_now() - interval '14 days'
          and not exists (select 1 from account_plays n where n.account_id = ap.account_id and n.id <> ap.id
                          and n.proposed_at >= ap.proposed_at)
        order by p.urgent desc, ap.closed_at desc limit 20""", *args)
    for r in expired:
        r["why"] = plays_mod.propose_again_blockers(cur, r["account_id"], r)
        r["can_propose_again"] = not r["why"]
    # Decision 108: a person who just replied keeps no call, LinkedIn step or draft to approve in the lists above until
    # their reply is read; each is named here instead, once, with how much is held back.
    read_first = db.all(cur, f"""
        select r.id as reply_id, r.received_at, r.cleaned, pe.id as person_id, pe.full_name, pe.photo_url, a.name as company, a.id as account_id,
               (select count(*) from tasks t where t.person_id = r.person_id and t.status = 'open'
                  and t.kind not in ('reply', 'review_reply') and t.owner_id = %s) as tasks_held,
               (select count(*) from messages m join enrollments e on e.id = m.enrollment_id
                  join account_plays ap on ap.id = e.account_play_id where e.person_id = r.person_id and m.channel = 'email'
                  and m.status in ('awaiting_approval', 'failed_gate') and {mine}) as drafts_held
        from replies r join people pe on pe.id = r.person_id left join accounts a on a.id = r.account_id
        where r.handled_at is null and (r.label is null or r.needs_review)
          and r.id = (select max(x.id) from replies x where x.person_id = r.person_id and x.handled_at is null
                      and (x.label is null or x.needs_review))
          and ((select count(*) from tasks t where t.person_id = r.person_id and t.status = 'open'
                  and t.kind not in ('reply', 'review_reply') and t.owner_id = %s) > 0
               or exists (select 1 from messages m join enrollments e on e.id = m.enrollment_id
                  join account_plays ap on ap.id = e.account_play_id where e.person_id = r.person_id and m.channel = 'email'
                  and m.status in ('awaiting_approval', 'failed_gate') and {mine}))
        order by r.received_at limit 40""", uid, *args, uid, *args)
    return {"proposals": proposals, "expired": expired, "approvals": approvals, "replies": hot, "tasks": tasks,
            "read_first": read_first, "meetings": meetings, "now": db.val(cur, "select app_now()")}


def _ttl(key: str, default: int) -> str:
    """A proposal time limit, in business days, as a SQL expression."""
    return f"coalesce((select (value #>> '{{}}')::int from settings where key = '{key}'), {default})"


ROLE_WORD = {"sdr": "SDR", "manager": "Manager", "gtm": "GTM"}


def owner_note(*, owner_role: str | None, account_owner: bool, crm_owner_email: str | None, lifecycle: str | None,
               integrated: set[str]) -> dict:
    """Decision 1: an owner is never shown bare. `role` says what the person is here; `source` says where the name
    came from, in plain words, and names another desk only when INTEGRATED_WITH says it is connected.
    Two kinds of owner exist: the owner of the account (set by the record it came from) and the SDR a play was given to
    (chosen by this desk: the account's owner when that is an SDR, else the SDR with the fewest open plays)."""
    role = ROLE_WORD.get(owner_role or "", None)
    if account_owner:
        customer = lifecycle in ("customer", "open_opp")
        if "crm_desk" in integrated and customer:
            src = "Account owner, from customer records (CRM Desk)"
        elif "market_desk" in integrated and not customer:
            src = "Account owner, from the account plan (Market Desk)"
        elif crm_owner_email:
            src = "Account owner, from the CRM record"
        else:
            src = "Account owner, from the account list"
    else:
        src = "Given this play by the desk: fewest open plays"
    return {"role": role, "source": src}


# ---------------------------------------------------------------- accounts

def owner_differs(cur, a: dict, integrated: set[str]) -> dict | None:
    """When the CRM holds another owner for this account than this desk does (decision 113): who the CRM names, which
    desk that is, and where this desk's owner came from. None when they agree, or the CRM has said nothing. Two desks can
    answer different questions (the CRM's owner is an AE, this desk's is the SDR), so this says so and decides nothing."""
    email = (a.get("crm_owner_email") or "").strip().lower()
    if not email:
        return None
    from .pipeline import desk_user
    theirs = desk_user(cur, email)
    if theirs is not None and theirs["id"] == a.get("owner_id"):
        return None
    return {"crm_owner": theirs["name"] if theirs else email, "crm_desk": "CRM Desk" if "crm_desk" in integrated else "The CRM",
            "here": a.get("owner"), "here_source": (a.get("owner_note") or {}).get("source")}


def accounts(cur, *, q: str | None, view: str, owner: int | None, limit: int = 100, offset: int = 0) -> list[dict]:
    where = ["a.fit_tier in ('A','B')"] if view != "all" else ["true"]
    args: list = []
    if view == "in_play":
        where.append("ap.id is not null")
    elif view == "rising":
        where.append("sh.delta > 0")
    if q:
        where.append("(a.name ilike %s or a.primary_domain ilike %s)")
        args += [like_pattern(q), like_pattern(q)]
    if owner:
        where.append("a.owner_id = %s")
        args.append(owner)
    rows = db.all(cur, f"""
        select a.id, a.name, a.primary_domain, a.industry, a.employees, a.hq_country, a.fit_tier, a.lifecycle,
               count(*) over () as total_n, sc.priority, sc.fit, sc.intent, sc.engagement, coalesce(u.name, apu.name) as owner, (u.id is not null) as owner_is_account_owner,
               coalesce(u.role, apu.role) as owner_role, a.crm_owner_email, hd.reason as hold_reason, lp.urgent as last_urgent,
               rs.label as reason, rs.type_key as reason_type, rs.observed_at as reason_at, coalesce(sh.delta, 0) as week_change,
               lp.state as last_state, hd.until as hold_until,
               {_ttl("proposal_ttl_days", 5)} as ttl_days, {_ttl("urgent_proposal_ttl_days", 1)} as urgent_ttl_days
        from accounts a left join account_scores sc on sc.account_id = a.id
        left join users u on u.id = a.owner_id
        left join account_plays ap on ap.account_id = a.id and ap.state in {OPEN}
        left join plays p on p.id = ap.play_id
        left join users apu on apu.id = ap.owner_id
        left join lateral (select t.label, s.type_key, s.observed_at from signals s join signal_types t on t.key = s.type_key
                           where s.id = sc.reason_signal_id) rs on true
        left join lateral (select x.state, pl.urgent from account_plays x join plays pl on pl.id = x.play_id
                           where x.account_id = a.id order by x.proposed_at desc limit 1) lp on true
        left join lateral (select h.until, h.reason from holds h where h.account_id = a.id
                           and h.person_id is null and h.until > app_now() order by h.until desc limit 1) hd on true
        left join lateral (select sum(priority - coalesce(previous, 0)) as delta from score_history h
                           where h.account_id = a.id and h.at > app_now() - interval '7 days') sh on true
        where {' and '.join(where)}
        order by {"coalesce(sh.delta, 0) desc," if view == "rising" else ""} sc.priority desc nulls last, a.name limit %s offset %s""",
        *args, limit, offset)
    from . import integration
    integrated = integration.integrated_with()
    for r in rows:
        r.update(owner_note(owner_role=r["owner_role"], account_owner=r["owner_is_account_owner"],
                            crm_owner_email=r["crm_owner_email"], lifecycle=r["lifecycle"], integrated=integrated)
                 if r["owner"] else {"role": None, "source": "No owner yet: the desk gives the account to an SDR when it proposes a play"})
        r["owner_role"], r["owner_source"] = r.pop("role"), r.pop("source")
        r["hold_expired"] = r["hold_reason"] == "expired"
        r["expired_days"] = r["urgent_ttl_days"] if r["last_urgent"] else r["ttl_days"]
        for k in ("crm_owner_email", "owner_is_account_owner", "ttl_days", "urgent_ttl_days", "last_urgent"):
            r.pop(k, None)
    return rows




def account(cur, account_id: int, *, money: bool) -> dict | None:
    a = db.one(cur, """select a.*, u.name as owner, u.role as owner_role_raw, p.name as parent_name from accounts a
                       left join users u on u.id = a.owner_id left join accounts p on p.id = a.parent_id where a.id = %s""",
               account_id)
    if a is None:
        return None
    from . import integration
    integrated = integration.integrated_with()
    a["owner_note"] = owner_note(owner_role=a.pop("owner_role_raw"), account_owner=bool(a["owner_id"]) and a["owner"] is not None,
                                 crm_owner_email=a.get("crm_owner_email"), lifecycle=a.get("lifecycle"), integrated=integrated)
    a["owner_differs"] = owner_differs(cur, a, integrated)
    score = db.one(cur, "select * from account_scores where account_id = %s", account_id)
    labels = {r["key"]: r for r in db.all(cur, "select key, label, because, weight, half_life_days from signal_types")}
    sigs = db.all(cur, """select s.id, s.type_key, s.observed_at, s.strength, s.evidence, s.source, p.full_name
                          from signals s left join people p on p.id = s.person_id
                          where s.account_id = %s order by s.observed_at desc limit 60""", account_id)
    # One thing seen by two sources is one line with two sources. Scoring already clusters these; this is display only.
    merged: dict[tuple, dict] = {}
    for s in sigs:
        s["label"] = labels.get(s["type_key"], {}).get("label", s["type_key"])
        key = (s["type_key"], (s["evidence"] or {}).get("summary"), s["observed_at"], s["full_name"])
        if (s["evidence"] or {}).get("summary") and key in merged:
            merged[key]["sources"].append(s["source"])
            continue
        s["sources"] = [s["source"]]
        merged[key] = s
    sigs = [s for s in sigs if s.get("sources")]
    contributions = []
    if score:
        for c in score["breakdown"].get("contributions", []):
            if c["value"] <= 0.05:
                continue
            contributions.append({**c, "label": labels.get(c["type"], {}).get("label", c["type"])})
    plays_ = db.all(cur, """select ap.id, ap.state, ap.arm, ap.proposed_at, ap.closed_at, ap.close_reason, ap.why_now,
                                   ap.brief, ap.owner_id, p.id as play_id, p.name as play, p.autonomy, u.name as owner, u.role as owner_role
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
    messages = db.all(cur, """select m.id, m.step_index, email_no(m.enrollment_id, m.step_index) as email_no, m.subject, m.status, m.sent_at, m.scheduled_for, pe.full_name, pe.photo_url,
                                     m.approval_mode
                              from messages m join enrollments e on e.id = m.enrollment_id join account_plays ap on ap.id = e.account_play_id
                              join people pe on pe.id = e.person_id where ap.account_id = %s and m.channel = 'email'
                              order by coalesce(m.sent_at, m.scheduled_for, m.created_at) desc limit 60""", account_id)
    reps = db.all(cur, """select r.id, r.received_at, r.label, r.cleaned, r.hot, pe.full_name, pe.photo_url from replies r
                          left join people pe on pe.id = r.person_id where r.account_id = %s order by r.received_at desc""",
                  account_id)
    # Our answers to those replies, kept with the account so the thread reads both ways (S5 review).
    answers = db.all(cur, """select rs.id, rs.reply_id, rs.status, rs.subject, rs.sent_at, rs.created_at, pe.full_name, u.name as sent_by
                             from reply_sends rs join replies r on r.id = rs.reply_id left join people pe on pe.id = rs.person_id
                             left join users u on u.id = rs.user_id
                             where r.account_id = %s and rs.status <> 'cancelled' order by coalesce(rs.sent_at, rs.created_at) desc""",
                     account_id)
    meetings = db.all(cur, """select m.id, m.starts_at, m.status, m.person_id, pe.full_name, pe.photo_url from meetings m
                              left join people pe on pe.id = m.person_id where m.account_id = %s order by m.starts_at desc""",
                      account_id)
    opps = db.all(cur, "select id, name, stage, created_at, won, attribution" + (", amount_cents" if money else "") +
                  " from opportunities where account_id = %s order by created_at desc", account_id)
    holds = db.all(cur, "select reason, until from holds where account_id = %s and until > app_now() order by until desc",
                   account_id)
    calendar = []
    if current:
        calendar = db.all(cur, """
            select pe.id as person_id, pe.full_name, pe.photo_url, e.persona_key,
                   (select pl.sequence from account_plays ap join plays pl on pl.id = ap.play_id where ap.id = e.account_play_id) as sequence, e.state, e.step_index, e.next_at, e.stop_reason, e.pause_reason, m.step_index as msg_step,
                   coalesce(m.sent_at, m.scheduled_for) as at, m.status
            from enrollments e join people pe on pe.id = e.person_id
            left join messages m on m.enrollment_id = e.id
            where e.account_play_id = %s order by e.id, m.step_index""", current["id"])
    return {"account": a, "score": score, "contributions": contributions, "signals": sigs, "plays": plays_,
            "current": current, "people": people, "gaps": gaps, "messages": messages, "replies": reps, "answers": answers,
            "meetings": meetings, "opportunities": opps, "holds": holds, "calendar": calendar,
            # What became of the work Accept queued (research, people, first drafts): queued, running, done or failed.
            "work": request_progress(cur, f"account_play:{plays_[0]['id']}", detail=money) if plays_ else None}


# ---------------------------------------------------------------- in flight

FLIGHT_STAGES = ["accepted", "researching", "approving", "active", "engaged", "meeting"]


def in_flight(cur, user: dict, *, mine: bool) -> dict:
    """Every open play past the decision, with each person's sequence: where it stands and what happens next."""
    who = user["id"] if mine else None
    plays_ = db.all(cur, """
        select ap.id, ap.state, ap.proposed_at, ap.owner_id, u.name as owner, a.id as account_id, a.name, a.primary_domain,
               a.fit_tier, pl.id as play_id, pl.name as play, pl.sequence, sc.priority,
               (select max(at) from touches t where t.account_play_id = ap.id) as last_touch,
               (select r.id from replies r where r.account_id = a.id and r.handled_at is null
                 and not exists (select 1 from reply_sends rs where rs.reply_id = r.id and rs.status in ('queued', 'sending'))
                 order by r.received_at desc limit 1) as reply_id,
               (select r.id from replies r where r.account_id = a.id and r.handled_at is null
                 and exists (select 1 from reply_sends rs where rs.reply_id = r.id and rs.status in ('queued', 'sending'))
                 order by r.received_at desc limit 1) as answer_queued_id,
               (select json_build_object('id', m.id, 'starts_at', m.starts_at, 'status', m.status, 'person_id', m.person_id)
                 from meetings m where m.account_play_id = ap.id
                 order by (m.status = 'booked') desc, m.starts_at desc limit 1) as meeting,
               (select m.id from messages m join enrollments e on e.id = m.enrollment_id where e.account_play_id = ap.id
                 and m.channel = 'email' and m.status in ('awaiting_approval', 'failed_gate') order by m.id limit 1) as draft_id,
               (select m.step_index from messages m join enrollments e on e.id = m.enrollment_id where e.account_play_id = ap.id
                 and m.channel = 'email' and m.status in ('awaiting_approval', 'failed_gate') order by m.id limit 1) as draft_step
        from account_plays ap join accounts a on a.id = ap.account_id join plays pl on pl.id = ap.play_id
        left join users u on u.id = ap.owner_id left join account_scores sc on sc.account_id = a.id
        where ap.state = any(%s) and ap.arm = 'treated' and (%s::bigint is null or ap.owner_id = %s)
        order by sc.priority desc nulls last, ap.proposed_at desc limit 400""", FLIGHT_STAGES, who, who)
    people = db.all(cur, """
        select e.account_play_id, e.id, e.state, e.step_index, e.next_at, e.stop_reason, e.pause_reason,
               p.id as person_id, p.full_name, coalesce(p.first_name, p.full_name) as first_name, p.photo_url,
               (select coalesce(json_agg(m.step_index), '[]') from messages m where m.enrollment_id = e.id and m.status = 'sent') as sent,
               (select count(*) from tasks t where t.account_play_id = e.account_play_id and t.person_id = e.person_id
                 and t.kind = 'call' and t.status = 'done') as calls_done
        from enrollments e join people p on p.id = e.person_id
        where e.account_play_id = any(%s) order by e.id""", [x["id"] for x in plays_])
    by_ap: dict[int, list] = {}
    for r in people:
        by_ap.setdefault(r["account_play_id"], []).append(r)
    for x in plays_:
        x["people"] = by_ap.get(x["id"], [])
        # A call is done by hand and leaves a finished task, not a sent message: the first N call steps are done.
        call_steps = [i for i, s in enumerate(x["sequence"]) if s.get("channel") == "call"]
        for r in x["people"]:
            r["sent"] = sorted(set(r["sent"]) | set(call_steps[:int(r.pop("calls_done") or 0)]))
        upcoming = [r for r in x["people"] if r["state"] == "active" and r["next_at"]]
        nxt = min(upcoming, key=lambda r: r["next_at"]) if upcoming else None
        x["next"] = ({"at": nxt["next_at"], "person": nxt["first_name"], "index": nxt["step_index"],
                      "step": x["sequence"][nxt["step_index"]]}
                     if nxt and nxt["step_index"] < len(x["sequence"]) else None)
    # Soonest next step first; plays waiting on a person (a reply, a draft, a meeting) after, by priority.
    plays_.sort(key=lambda x: (x["next"] is None, x["next"]["at"] if x["next"] else 0))
    counts = {st: sum(1 for x in plays_ if x["state"] == st) for st in FLIGHT_STAGES}
    return {"plays": plays_, "counts": counts, "mine": mine}


# ---------------------------------------------------------------- tasks

def task(cur, task_id: int) -> dict | None:
    t = db.one(cur, """select t.*, pe.full_name, pe.photo_url, pe.title as person_title, pe.phone, pe.phone_status, pe.phone_type, pe.phone_dnc,
                              pe.timezone as person_timezone, pe.country as person_country, pe.linkedin_url, a.name as company, a.id as account_id, pl.name as play,
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
    # Why the call, and what this person has already had, so the SDR does not dial cold.
    t["why"] = db.one(cur, """select st.label, s.evidence->>'summary' as summary, s.evidence->>'url' as url, s.observed_at from account_plays ap
                              join signals s on s.id = ap.trigger_signal_id join signal_types st on st.key = s.type_key
                              where ap.id = %s""", t["account_play_id"]) if t["account_play_id"] else None
    t["so_far"] = db.all(cur, """select m.step_index, email_no(m.enrollment_id, m.step_index) as email_no, m.channel, m.subject, m.sent_at from messages m
                                 join enrollments e on e.id = m.enrollment_id
                                 where e.account_play_id = %s and e.person_id = %s and m.status = 'sent'
                                 order by m.sent_at""", t["account_play_id"], t["person_id"]) if t["account_play_id"] else []
    t["max_chars"] = note_limit(cur) if t["kind"] == "linkedin_connect" else None
    from . import replies
    t["read_first"] = replies.unread_reply(cur, t["person_id"]) if t["kind"] not in ("reply", "review_reply") else None
    if t["kind"] == "call":
        from .gate import call_window
        t["call_hours"] = "{} to {}".format(*call_window(cur))
        # Their clock, so a rep does not dial at 7 AM. Unknown zone: no time shown and no verdict.
        from zoneinfo import ZoneInfo

        from .gate import call_zones, in_call_hours
        from .gate import now as app_now
        person = {"timezone": t.get("person_timezone"), "country": t.get("person_country")}
        zones = call_zones(person)
        at = app_now(cur)
        t["local_now"] = at.astimezone(ZoneInfo(zones[0])).strftime("%H:%M") if zones else None
        t["in_call_hours"] = in_call_hours(cur, person, at) if zones else None
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
                        " from opportunities where attribution_meeting_id = %s or (account_id = %s and created_at >= %s "
                        "and attribution_meeting_id is null) "
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
    touches = db.all(cur, """select t.id, t.channel, t.direction, t.kind, t.at, t.source, t.message_id, m.subject, m.step_index, email_no(m.enrollment_id, m.step_index) as email_no
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
    from .privacy import email_hmac, linkedin_hash, linkedin_hmac
    blocked = db.all(cur, """select kind, reason, created_at from suppressions
                             where (expires_at is null or expires_at > app_now()) and (
                               (kind = 'person' and value = %s) or (kind = 'email' and value = %s) or (kind = 'phone' and value = %s)
                               or (kind = 'domain' and value = split_part(%s, '@', 2))
                               or (kind = 'account' and value = %s)
                               or (kind = 'email_hash' and %s <> '' and value = encode(sha256(convert_to(%s, 'UTF8')), 'hex'))
                               or (kind = 'email_hmac' and %s <> '' and value = %s)
                               or (kind = 'linkedin_hash' and value = %s)
                               or (kind = 'linkedin_hmac' and value = %s))""",
                     str(person_id), p["email"] or "", p["phone"] or "", p["email"] or "", str(p["account_id"] or ""),
                     p["email"] or "", p["email"] or "", p["email"] or "", email_hmac(p["email"]) if p["email"] else "",
                     linkedin_hash(p["linkedin_url"]) if p["linkedin_url"] else "",
                     linkedin_hmac(p["linkedin_url"]) if p["linkedin_url"] else "")
    waiting = db.all(cur, """select 'task' as kind, t.id, t.kind as what, t.title as label, t.due_at as at from tasks t
                             where t.person_id = %s and t.status = 'open'
                             union all
                             select 'message', m.id, m.channel, 'Email ' || email_no(m.enrollment_id, m.step_index) || ' to approve', m.created_at
                             from messages m join enrollments e on e.id = m.enrollment_id
                             where e.person_id = %s and m.channel = 'email' and m.status in ('awaiting_approval', 'failed_gate')
                             order by at""", person_id, person_id)
    from . import replies
    return {"person": p, "enrollments": enrollments, "touches": touches, "replies": reps, "meetings": meetings,
            "signals": sigs, "suppressed": blocked, "waiting": waiting, "read_first": replies.unread_reply(cur, person_id)}


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
    sources = db.all(cur, """select s.key, s.label, s.cadence_minutes, s.paid, s.enabled, s.provider, s.adapter,
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
          select distinct on (s.type_key, ap.account_id) s.type_key, ap.arm, ap.account_id, ap.proposed_at
          from account_plays ap join signals s on s.id = ap.trigger_signal_id
          order by s.type_key, ap.account_id, ap.proposed_at
        ), outcome as (
          select ap.*, exists (select 1 from meetings m where m.account_id = ap.account_id and m.status <> 'cancelled'
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
    from .stats import lift_report, within_reach
    total = db.val(cur, "select count(*) from accounts")
    triggers = {k for r in db.all(cur, "select trigger from plays where status = 'live'") for k in (r["trigger"] or {}).get("any_of", [])}
    for r in rows:
        r["meeting_rate"] = (r["treated_meetings"] / r["treated"]) if r["treated"] else None
        r["lift"] = within_reach(lift_report(r["treated_meetings"], r["treated"], r["holdout_meetings"], r["holdout"]),
                                 max(0, total - r["treated"] - r["holdout"])) if r["treated"] else None
        # A type no live play starts on still moves priority, but its effect is not measured here.
        r["starts_plays"] = r["key"] in triggers
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
    count(*) filter (where arm = 'holdout') as holdout
"""


def lifts(cur, play_id: int | None = None) -> tuple[dict, dict]:
    """Treated against held back, intention to treat on each account's FIRST assignment: an account offered again
    after a cooldown, or held back once and treated later, counts once, in the group it was first put in."""
    r = db.one(cur, """
        with first as (select distinct on (ap.account_id) ap.account_id, ap.arm, ap.proposed_at from account_plays ap
                       where (%s::bigint is null or ap.play_id = %s) order by ap.account_id, ap.proposed_at, ap.id)
        select count(*) filter (where arm = 'treated') as n_t, count(*) filter (where arm = 'holdout') as n_h,
          count(*) filter (where arm = 'treated' and exists (select 1 from meetings m where m.account_id = f.account_id
            and m.status <> 'cancelled' and m.booked_at between f.proposed_at and f.proposed_at + interval '60 days')) as m_t,
          count(*) filter (where arm = 'holdout' and exists (select 1 from meetings m where m.account_id = f.account_id
            and m.status <> 'cancelled' and m.booked_at between f.proposed_at and f.proposed_at + interval '60 days')) as m_h,
          count(*) filter (where arm = 'treated' and exists (select 1 from opportunities o where o.account_id = f.account_id
            and o.created_at between f.proposed_at and f.proposed_at + interval '90 days')) as d_t,
          count(*) filter (where arm = 'holdout' and exists (select 1 from opportunities o where o.account_id = f.account_id
            and o.created_at between f.proposed_at and f.proposed_at + interval '90 days')) as d_h
        from first f""", play_id, play_id)
    room = max(0, db.val(cur, "select count(*) from accounts") - r["n_t"] - r["n_h"])
    return (stats.within_reach(stats.lift_report(r["m_t"], r["n_t"], r["m_h"], r["n_h"]), room),
            stats.within_reach(stats.lift_report(r["d_t"], r["n_t"], r["d_h"], r["n_h"]), room))


def plays_page(cur, *, money: bool) -> list[dict]:
    out = []
    for p in db.all(cur, """select p.*, u.name as owner, t.label as suggested_theme from plays p
                            left join users u on u.id = p.owner_id left join learning_themes t on t.id = p.suggested_from
                            order by p.id"""):
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
               "covers_suggested": suggestions.covered_by(cur, p["id"]),
               "lift": (lf := lifts(cur, p["id"]))[0], "deal_lift": lf[1], "promotion": promotion_check(cur, p),
               "cap_use": [{"key": k, "cap": float(v), "used": spend.play_month_used(cur, p["id"], "anthropic" if k == "anthropic_cents" else k)}
                           for k, v in (p.get("monthly_cap") or {}).items()] if money else []}
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
                             and mb.status = 'active') and (d.spam_rate is null or d.spam_rate_at is null
                             or d.spam_rate_at < app_now() - interval '7 days')""") or 0
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
    if idx == 0:
        # At the first stage the SDR writes everything, so there are no desk drafts to judge: the move to drafts the
        # SDR approves is a manager's call, held back only by complaints or sending domains with unknown spam data.
        checks = [c for c in checks if c["label"] in ("Spam complaints", "Complaint data for every sending domain")]
    return {"next": STAGES[idx + 1], "ready": all(c["ok"] for c in checks), "checks": checks}


# ---------------------------------------------------------------- approvals and replies

def message(cur, message_id: int) -> dict | None:
    m = db.one(cur, """select m.*, email_no(m.enrollment_id, m.step_index) as email_no, e.person_id, pe.full_name, pe.photo_url, pe.first_name, pe.title, pe.email, pe.country, a.name as company,
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
    slot = outreach.message_slot(cur, message_id) if m["status"] in ("awaiting_approval", "failed_gate") else None
    from . import replies
    m["read_first"] = replies.unread_reply(cur, m["person_id"]) if m["status"] in ("awaiting_approval", "failed_gate") else None
    m["next_slot"] = slot["at"] if slot else None
    m["slot_label"] = {k: v for k, v in slot.items() if k != "at"} if slot else None
    if m["channel"] == "email" and m["status"] in ("awaiting_approval", "failed_gate"):
        lo, hi = outreach.step_limits(cur, m)
        m["limit"] = [lo, hi]
        m["words"] = outreach.edit_words(m["body"])
    return m


def replies_page(cur, *, view: str, user_id: int | None = None, own_only: bool = False) -> list[dict]:
    """`own_only` (an SDR) limits "needs a person" to their own accounts, so the sidebar number equals this list."""
    mine = f"""coalesce((select ap.owner_id from account_plays ap where ap.account_id = r.account_id
                         order by ap.proposed_at desc limit 1), (select owner_id from accounts where id = r.account_id))
                         = {int(user_id or 0)}"""
    where = {"needs_person": "(r.needs_review or r.label is null) and r.handled_at is null" + (f" and {mine}" if own_only else ""),
             "hot": "r.hot", "all": "true", "mine": mine}.get(view, "true")
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
        # The meeting this reply led to: its id, and when it is, so the closed reply still says when.
        r["meeting"] = db.one(cur, """select id, starts_at, status from meetings where account_id = %s and booked_at >= %s
                                      order by booked_at limit 1""", r["account_id"], r["received_at"]) if r["account_id"] else None
        r["meeting_id"] = r["meeting"]["id"] if r["meeting"] else None
        from . import replies
        r["can_relabel"] = replies.can_relabel(r)
        r["colleagues_waiting"] = db.val(cur, """select count(*) from enrollments e join account_plays ap on ap.id = e.account_play_id
                                                 where ap.account_id = %s and e.state = 'paused' and e.pause_reason = 'account_reply'
                                                 and e.person_id is distinct from %s""", r["account_id"], r["person_id"]) if r["account_id"] else 0
    return r


# ---------------------------------------------------------------- deliverability

def deliverability(cur) -> dict:
    domains = db.all(cur, """select d.*, (app_now()::date - d.registered_at) as age_days,
                                    (select count(*) from mailboxes m where m.domain = d.domain) as mailboxes
                             from sending_domains d order by d.domain""")
    boxes = []
    warmup = adapters.get().warmup
    for m in db.all(cur, """select m.*, u.name as owner from mailboxes m join users u on u.id = m.user_id order by m.domain, m.address"""):
        stats_ = db.one(cur, """select count(*) filter (where event = 'sent') as sent,
                                       count(*) filter (where event = 'bounced_hard') as bounced,
                                       count(*) filter (where event = 'complaint') as complaints
                                from deliveries where mailbox_id = %s and at > app_now() - interval '14 days'""", m["id"])
        seeds = db.all(cur, """select distinct on (provider) provider, inbox, spam, missing, seeds, at from placement_tests
                               where mailbox_id = %s order by provider, at desc""", m["id"])
        boxes.append({**m, **stats_, "today": outreach.sent_today(cur, m["id"]), "cap": outreach.mailbox_capacity(cur, m),
                      "blocked": outreach.mailbox_sendable(cur, m), "placement": {r["provider"]: r for r in seeds},
                      "warmup": warmup.status(cur, m) if warmup else None,
                      "placement_at": min((r["at"] for r in seeds), default=None)})
    forecast = db.all(cur, """select date_trunc('day', scheduled_for) as day, count(*) as scheduled from messages
                              where status = 'scheduled' and scheduled_for < app_now() + interval '14 days'
                              group by 1 order by 1""")
    names = {r["key"]: r["name"] for r in db.all(cur, "select key, name from plays")}
    watch = db.all(cur, "select * from play_step_watch order by paused desc, template_key")
    for w in watch:
        parts = w["template_key"].split(":")  # play:step, or play:vN:step since steps are watched per version
        key, step = parts[0], parts[-1]
        w["play"] = names.get(key, key) + (f", version {parts[1][1:]}" if len(parts) == 3 and parts[1] != "v1" else "")
        w["step"] = int(step or 0) + 1
    capacity = sum(b["cap"] for b in boxes if not b["blocked"])
    thresholds = {k: float(outreach.setting(cur, k, d)) for k, d in (("placement_hold_below", 0.8), ("placement_pause_below", 0.5))}
    shown = alerts.open_view(cur, "inboxes")
    return {"domains": domains, "mailboxes": boxes, "forecast": forecast, "capacity": capacity, "watch": watch,
            "placement": thresholds, "alerts": shown["alerts"], "alert_counts": shown["counts"]}


# ---------------------------------------------------------------- results

def my_results(cur, user_id: int) -> dict:
    """The signed-in person's own numbers (decision 113): their plays down the same funnel, the hot replies they answered
    and how fast, and the meetings they own that an outbound play booked."""
    f = db.one(cur, "select " + FUNNEL + " from account_plays ap where ap.owner_id = %s", user_id)
    ans = db.one(cur, """select count(*) as answered,
                                percentile_cont(0.5) within group (order by extract(epoch from (handled_at - received_at)) / 3600) as median_hours
                         from replies where hot and handled_by = %s and handled_at is not null""", user_id)
    booked = db.val(cur, """select count(*) from meetings where owner_id = %s and account_play_id is not null
                            and source <> 'inbound' and status <> 'cancelled'""", user_id)
    return {"funnel": f, "answered": ans["answered"], "median_hours": ans["median_hours"], "meetings": booked}


def results(cur, *, money: bool, user_id: int | None = None) -> dict:
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
    # within 60 days of their first touch there. A person reached on two channels counts in both.
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
                   and m.booked_at between o.first_at and o.first_at + interval '60 days')) as meetings
        from first_out o group by 1 order by reached desc""")
    meeting_lift, deal_lift = lifts(cur)
    out = {"funnel": f, "lift": meeting_lift, "deal_lift": deal_lift,
           "opportunities": opps, "sla": sla, "labels": labels, "signals": signal_performance(cur), "learnings": learn,
           "channels": channels}
    if user_id is not None:
        out["mine"] = my_results(cur, user_id)
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
    from .jobs import job_name
    jobs = [{**j, "name": job_name(j["kind"])} for j in db.all(
        cur, "select kind, status, count(*) as n from jobs where status in ('queued','running','failed','dead') group by 1,2 order by 1")]
    outbox = db.all(cur, "select status, count(*) as n from crm_outbox group by status")
    shown = alerts.open_view(cur, "health")
    undelivered = db.val(cur, "select count(*) from alerts where delivered_at is null and at > app_now() - interval '14 days'")
    budgets = db.all(cur, """select b.vendor, b.monthly_cap_cents as cap, coalesce((select sum(case when b.vendor = 'anthropic'
                               then l.cost_cents else l.qty end) from ledger l where l.vendor = b.vendor
                               and l.at >= date_trunc('month', app_now())), 0) as used from budgets b order by b.vendor""")
    llm_calls = db.all(cur, "select task, source, count(*) as n from llm_calls group by 1,2 order by 1,2")
    # Guarantee 21: the checks themselves are checked. They run every 6 hours; older than 12 means they stopped.
    last_run = db.val(cur, "select max(at) from monitor_runs")
    stale = last_run is None or db.val(cur, "select %s < app_now() - interval '12 hours'", last_run)
    return {"monitors": monitors.latest(cur), "jobs": jobs, "outbox": outbox, "alerts": shown["alerts"],
            "alert_counts": shown["counts"], "undelivered_alerts": undelivered, "budgets": budgets,
            "checks_ran_at": last_run, "checks_stale": bool(stale), "llm": llm_calls, "adapters": adapters.get().notes,
            "kill_switch": bool(db.val(cur, "select value from settings where key = 'kill_switch'"))}


# The settings the Settings page may show. Anything else in the table (secrets, cursors, schedule marks) stays out,
# including keys added later that nobody thought to hide.
SETTINGS_SHOWN = ("kill_switch", "account_max_active", "account_max_active_wide", "person_cooldown_days",
                  "account_reply_pause_hours", "verify_max_age_days", "proposal_ttl_days", "urgent_proposal_ttl_days",
                  "stagger_days", "send_window", "mailbox_max_daily", "sla_business_hours", "approval_lapse_business_days",
                  "placement_hold_below", "placement_pause_below", "placement_max_age_days", "linkedin_note_max_chars",
                  "competing_tools", "call_window", "retention_months", "lia_ref", "lia_review_due")


def like_pattern(q: str) -> str:
    """A search text as an ilike pattern that matches it literally: % and _ in it are not wildcards."""
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def integration_state() -> dict:
    """Which other desks are present and which this install links to (shared-world DESIGN 2b and 9). Both empty
    when the desk runs alone: the screen is then exactly the standalone one."""
    from . import integration
    return {"integrated_with": sorted(integration.integrated_with()), "links": integration.desk_links()}


def kept_in_market_desk(cur) -> dict | None:
    """What Market Desk keeps when it is present: the profile version in force and when accounts were last read from
    the record. None when it is not present. The accounts column arrives with migration 0031, so it is read
    through to_jsonb and works before and after."""
    from . import integration
    if not integration.has("market_desk"):
        return None
    return {"icp": db.one(cur, "select id, published_at, note from icp_versions order by published_at desc limit 1"),
            "accounts_read_at": db.val(cur, "select max((to_jsonb(a)->>'crm_read_at')::timestamptz) from accounts a")}


def settings(cur) -> dict:
    return {"integration": integration_state(), "kept": kept_in_market_desk(cur),
            "settings": {r["key"]: r["value"] for r in db.all(cur, "select key, value from settings where key = any(%s)",
                                                              list(SETTINGS_SHOWN))},
            "signal_types": db.all(cur, "select * from signal_types order by weight desc"),
            "icp": db.one(cur, "select * from icp_versions order by published_at desc limit 1"),
            "personas": db.all(cur, "select * from personas"),
            "suggestion_rule": suggestions.RULE,
            **{("regions" if k == "regions" else "region_changes"): v for k, v in region_rules.listing(cur).items()},
            "suppressions": db.all(cur, "select id, kind, value, reason, source, created_at, expires_at from suppressions where expires_at is null or expires_at > app_now() "
                                        "order by created_at desc limit 100")}


# ---------------------------------------------------------------- an SDR's read-only views (decision 6)

def my_mailbox(cur, user_id: int) -> dict:
    """The mailboxes this person sends from, how each is doing, and the domain it sits on. Nothing here can be changed
    from this view: a manager changes mailboxes."""
    d = deliverability(cur)
    boxes = [m for m in d["mailboxes"] if m["user_id"] == user_id]
    domains = {m["domain"] for m in boxes}
    keep = ("id", "address", "domain", "provider", "status", "pause_reason", "sent", "bounced", "complaints", "today", "cap",
            "blocked", "placement", "placement_at", "warmup")
    return {"mailboxes": [{k: m.get(k) for k in keep} for m in boxes],
            "domains": [{k: x.get(k) for k in ("domain", "spf", "dkim", "dmarc", "dmarc_aligned", "dmarc_policy", "blocklisted",
                                                  "spam_rate", "age_days", "checked_at")} for x in d["domains"] if x["domain"] in domains],
            "thresholds": d["placement"], "bounce_check_from": sending.BOUNCE_FLOOR}


def do_not_contact(cur) -> list[dict]:
    """Everyone and everything the desk will not contact, newest first. Erased people show only as a scrambled copy."""
    rows = db.all(cur, """select id, kind, value, reason, source, created_at from suppressions
                          where expires_at is null or expires_at > app_now() order by created_at desc limit 300""")
    for r in rows:
        if r["kind"].endswith(("_hash", "_hmac")):
            r["value"] = None  # an erased person stays only as a scrambled copy; the copy is not shown
    return rows


def badge_counts(cur, user: dict) -> dict:
    """The sidebar numbers, defined by the lists they open. `today` is replies to answer plus plays to decide plus calls
    and LinkedIn tasks due, the first, second and fourth boxes of Today. `replies` is the replies that need a person
    among this person's own for an SDR and everyone's otherwise: the list the sidebar opens, Replies "Needs a person"."""
    uid, sdr = user["id"], user["role"] == "sdr"
    # Each box on Today shows at most its limit (40 replies, 40 plays, 50 tasks), so the number counts no more than that.
    today_n = db.val(cur, """
        select least((select count(distinct r.id) from replies r join accounts a on a.id = r.account_id
                  join tasks t on t.reply_id = r.id and t.status = 'open'
                  and t.kind in ('reply', 'review_reply') where (t.owner_id = %s or %s)), 40)
             + least((select count(*) from account_plays where state = 'proposed' and (owner_id = %s or %s)), 40)
             + least((select count(*) from tasks t where t.status = 'open' and t.owner_id = %s and t.kind not in ('reply', 'review_reply')
                  and t.due_at <= app_now() + interval '1 day'
                  and not """ + UNREAD_REPLY.format(person="t.person_id") + """), 50)""", uid, not sdr, uid, not sdr, uid)
    mine = """coalesce((select ap.owner_id from account_plays ap where ap.account_id = r.account_id
                        order by ap.proposed_at desc limit 1), (select owner_id from accounts where id = r.account_id)) = %s"""
    replies_n = db.val(cur, "select count(*) from replies r where (r.needs_review or r.label is null) and r.handled_at is null"
                            + (f" and {mine}" if sdr else ""), *([uid] if sdr else []))
    return {"today": today_n, "replies": replies_n}
