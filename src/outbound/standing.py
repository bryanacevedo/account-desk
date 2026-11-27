"""Standing approvals (BL-171, decision 121): the Supervised stage's automatic approval of follow-up emails as an owned policy.

A standing approval names a manager, a reason, the play version it covers and an end date. While one is in force the desk may
approve that play's follow-up emails once they passed the checks (1 in 5 still goes to a person); without one a Supervised play
behaves like Draft. It never covers a first email, a reply, a call, a LinkedIn step, a draft that failed a check, an unread reply,
or a person in a region that needs judgment (a country whose rule is not `allowed`, or an HQ country with one). It ends on its date,
on a revoke, and on any change of the play's stage, edit or pause; an ending (except the simulated history's own) returns what was
queued under it to a person."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from . import audit, db, jobs
from .config import CONFIG

log = logging.getLogger("outbound.standing")

TERM_MAX_DAYS = 90
TIERS = ("A", "B")

# In force: not revoked, not past its date, the play live at Supervised and still the version that was signed.
IN_FORCE = """s.revoked_at is null and app_now()::date <= s.ends_on
              and exists (select 1 from plays p where p.id = s.play_id and p.status = 'live' and p.autonomy = 'supervised'
                          and p.version = s.play_version)"""


def in_force(cur, play_id: int) -> dict | None:
    return db.one(cur, f"select s.* from standing_approvals s where s.play_id = %s and {IN_FORCE} order by s.id desc limit 1", play_id)


def first_desk_email(sequence: list[dict]) -> int | None:
    return next((i for i, st in enumerate(sequence) if st["channel"] == "email" and st["by"] == "desk"), None)


def region_needs_person(cur, person_country: str | None, hq_country: str | None) -> bool:
    """A country whose rule is not `allowed`, or that carries individual consent, for the person or the account's HQ."""
    for c in (person_country, hq_country):
        if not c:
            continue
        r = db.one(cur, "select rule, individual_consent from region_rules where country = %s", c)
        if r is None or r["rule"] != "allowed" or r["individual_consent"]:
            return True
    return False


def covered(cur, pol: dict, m: dict) -> str | None:
    """Why this follow-up is NOT covered by the policy, or None when it is. `m` is a message row joined with its play, account
    and person (see `message_context`)."""
    first = first_desk_email(m["sequence"])
    if first is None or m["step_index"] <= first:
        return "It is not a follow-up"
    if pol["regions"] == "carried_over":
        # The simulated history's policy applies the old rule as it was: any follow-up, whatever the tier, the first email's
        # author or the country, so the recorded replay of that history stays exact (decision 121).
        return None if not pol["steps"] or m["email_no"] in pol["steps"] else "This email is not one the policy covers"
    if not db.val(cur, """select exists (select 1 from messages x where x.enrollment_id = %s and x.step_index = %s
                          and x.approval_mode = 'person' and x.status in ('approved', 'scheduled', 'sending', 'sent'))""",
                  m["enrollment_id"], first):
        return "The first email was not approved by a person"
    if m["fit_tier"] not in (pol["tiers"] or []):
        return f"The account is tier {m['fit_tier']}"
    if pol["steps"] and m["email_no"] not in pol["steps"]:
        return "This email is not one the policy covers"
    if pol["regions"] == "allowed_only" and region_needs_person(cur, m["country"], m["hq_country"]):
        return "Their country needs a person to judge"
    return None


def message_context(cur, message_id: int) -> dict | None:
    return db.one(cur, """select m.id, m.status, m.step_index, m.enrollment_id, m.approval_mode, m.standing_approval_id,
                                 email_no(m.enrollment_id, m.step_index) as email_no, pl.id as play_id, pl.sequence,
                                 pl.autonomy, a.fit_tier, a.hq_country, pe.country
                          from messages m join enrollments e on e.id = m.enrollment_id
                          join account_plays ap on ap.id = e.account_play_id join plays pl on pl.id = ap.play_id
                          join accounts a on a.id = ap.account_id join people pe on pe.id = e.person_id where m.id = %s""", message_id)


def sign(cur, play_id: int, *, owner_id: int, reason: str, tiers: list[str] | None = None, steps: list[int] | None = None,
         ends_on: date | None = None, signed_by_person: bool = True, regions: str = "allowed_only",
         replaces: str = "replaced") -> int:
    """A manager signs a standing approval for a live Supervised play. Signing again ends the earlier one (kind `replaced`)."""
    play = db.one(cur, "select id, name, status, autonomy, version from plays where id = %s for update", play_id)
    if play is None or play["status"] != "live" or play["autonomy"] != "supervised":
        raise ValueError("A standing approval is for a live play at the Supervised stage")
    who = db.one(cur, "select role, active from users where id = %s", owner_id)
    if who is None or who["role"] != "manager" or not who["active"]:
        raise ValueError("A manager signs a standing approval")
    if len((reason or "").strip()) < 10:
        raise ValueError("Say why, in a sentence")
    tiers = sorted(set(tiers or ["B"]))
    if not tiers or any(t not in TIERS for t in tiers):
        raise ValueError("Tiers are A, B or both")
    today = db.val(cur, "select app_now()::date")
    ends_on = ends_on or today + timedelta(days=TERM_MAX_DAYS)
    if not today < ends_on <= today + timedelta(days=TERM_MAX_DAYS):
        raise ValueError(f"The end date is from tomorrow to {TERM_MAX_DAYS} days ahead")
    steps = sorted(set(steps)) if steps else None
    if steps and any(s < 2 for s in steps):
        raise ValueError("A standing approval covers follow-ups, email 2 and later")
    sid = db.val(cur, """insert into standing_approvals (play_id, play_version, tiers, steps, owner_id, reason, signed_by_person, regions, ends_on)
                         values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                 play_id, play["version"], tiers, steps, owner_id, reason.strip(), signed_by_person, regions, ends_on)
    for old in db.all(cur, "select id from standing_approvals where play_id = %s and id <> %s and revoked_at is null", play_id, sid):
        end(cur, old["id"], kind=replaces, reason="Replaced by a new standing approval", by=owner_id, successor=sid)
    audit.log(cur, "person" if signed_by_person else "desk", "standing_approval_signed", "standing_approval", sid,
              {"play": play["name"], "tiers": tiers, "steps": steps, "ends_on": ends_on.isoformat(), "reason": reason.strip(),
               "regions": regions}, actor_id=owner_id)
    return sid


def end(cur, sid: int, *, kind: str, reason: str, by: int | None = None, successor: int | None = None) -> bool:
    """End one policy now and put what was queued under it back to a person, except for the simulated history's own carried-over
    policies (their queued mail goes as it always did) and, on a replacement, what the new policy still covers."""
    pol = db.one(cur, "select * from standing_approvals where id = %s for update", sid)
    if pol is None or pol["revoked_at"] is not None:
        return False
    db.run(cur, """update standing_approvals set revoked_at = app_now(), revoked_by = %s, revoke_reason = %s, revoke_kind = %s
                   where id = %s""", by, reason, kind, sid)
    audit.log(cur, "person" if by else "desk", "standing_approval_revoked", "standing_approval", sid,
              {"kind": kind, "reason": reason}, actor_id=by)
    succ = db.one(cur, "select * from standing_approvals where id = %s", successor) if successor else None
    if pol["regions"] != "carried_over" or succ is not None:
        for m in db.all(cur, """select id from messages where standing_approval_id = %s and approval_mode = 'auto_supervised'
                                and status in ('approved', 'scheduled')""", sid):
            ctx = message_context(cur, m["id"])
            if succ is not None and covered(cur, succ, ctx) is None:
                db.run(cur, "update messages set standing_approval_id = %s where id = %s", succ["id"], m["id"])
            else:
                return_to_person(cur, m["id"], f"The standing approval ended ({kind})")
    return True


def end_for_play(cur, play_id: int, *, kind: str, reason: str, by: int | None = None) -> int:
    n = 0
    for r in db.all(cur, "select id from standing_approvals where play_id = %s and revoked_at is null", play_id):
        n += end(cur, r["id"], kind=kind, reason=reason, by=by)
    return n


def return_to_person(cur, message_id: int, why: str) -> None:
    """An automatic approval that has not gone out goes back to waiting for a person (as a person's take-back does)."""
    db.run(cur, "select 1 from messages where id = %s for update", message_id)
    cur.execute("""update messages set status = 'awaiting_approval', approved_hash = null, approved_by = null, approval_mode = null,
                   approved_at = null, scheduled_for = null, planned_for = null, trace_parent = null, standing_approval_id = null
                   where id = %s and status in ('approved', 'scheduled')""", (message_id,))
    if cur.rowcount:                  # one that already went out is not "returned"
        audit.log(cur, "desk", "auto_approval_returned", "message", message_id, {"reason": why})


def on_stage_change(cur, play_id: int, from_stage: str, to_stage: str, *, by: int | None, reason: str,
                    carried_over: bool = False, tiers: list[str] | None = None, steps: list[int] | None = None,
                    ends_on: date | None = None, end_kind: str = "play_changed") -> int | None:
    """Every change of a play's stage goes through here. Leaving Supervised ends its policies. Entering it signs one: a manager's
    promotion signs for that manager (both tiers, every follow-up, 90 days unless said otherwise); the simulated history's own
    promotions sign a carried-over one (`carried_over`), and a demotion from Autonomous (nobody to sign) gets one too, so follow-ups
    keep going as the stage already allowed until a manager signs."""
    if from_stage == "supervised" and to_stage != "supervised":
        end_for_play(cur, play_id, kind=end_kind, reason=reason, by=by if end_kind == "person" else None)
    if to_stage != "supervised":
        return None
    order = ("research", "draft", "supervised", "autonomous")
    promotion = order.index(to_stage) > order.index(from_stage)
    if not promotion:
        # A demotion into Supervised signs nothing on a live desk: follow-ups wait for a person until a manager signs. The
        # simulated demo keeps its history exact with a carried-over policy (decision 121).
        if CONFIG.mode == "live" or by is not None:
            return None
        by = None
    owner = by or db.val(cur, """select decided_by from play_stage_changes p where play_id = %s and to_stage = 'supervised'
                                 and decided_by is not null and exists (select 1 from users u where u.id = p.decided_by and u.active
                                 and u.role = 'manager') order by at desc limit 1""", play_id) \
        or db.val(cur, "select id from users where role = 'manager' and active order by id limit 1")
    if owner is None:
        return None
    nobody = by is None or carried_over
    try:
        return sign(cur, play_id, owner_id=owner, reason=reason if len(reason.strip()) >= 10 else f"Promoted to Supervised: {reason}",
                    tiers=tiers or ["A", "B"], steps=steps, ends_on=ends_on,
                    signed_by_person=not nobody, regions="carried_over" if carried_over or by is None else "allowed_only")
    except ValueError:
        if promotion:
            raise
        log.warning("no standing approval signed for play %s after its demotion", play_id)
        return None


def refuse_at_send(cur, message_id: int) -> bool:
    """The send path asks: is this automatic approval still under a policy in force? When not, it goes back to a person and the
    send does not happen. Carried-over policies are exempt (the simulated history sends as it always did)."""
    m = db.one(cur, "select approval_mode, standing_approval_id from messages where id = %s", message_id)
    if m is None or m["approval_mode"] != "auto_supervised":
        return False
    pol = db.one(cur, f"select s.*, ({IN_FORCE}) as ok from standing_approvals s where s.id = %s",
                 m["standing_approval_id"]) if m["standing_approval_id"] else None
    if pol is not None and pol["regions"] == "carried_over":
        return False
    if pol is not None and pol["ok"]:
        ctx = message_context(cur, message_id)
        if covered(cur, pol, ctx) is None:
            return False
    return_to_person(cur, message_id, "No standing approval in force")
    return True


@jobs.handler("standing_approvals_watch")
def watch(cur, payload: dict) -> None:
    """Daily: write the expiry of a policy that ran past its date (and put its queued mail back), and warn a week ahead."""
    from . import alerts
    for s in db.all(cur, """select s.id, s.owner_id, s.ends_on, p.name, s.revoked_at from standing_approvals s join plays p on p.id = s.play_id
                            where s.revoked_at is null and app_now()::date > s.ends_on order by s.id"""):
        end(cur, s["id"], kind="expired", reason=f"It ran to {s['ends_on']:%d %b}")
        alerts.raise_alert(cur, kind="standing_approval", severity="warn", channel="#outbound-ops",
                           title=f"{s['name']}: standing approval ended", target_user=s["owner_id"],
                           body="Follow-ups wait for a person until a manager signs a new one.",
                           dedup_key=f"standing_end:{s['id']}")
    for s in db.all(cur, """select s.id, s.owner_id, s.ends_on, p.name from standing_approvals s join plays p on p.id = s.play_id
                            where s.revoked_at is null and s.ends_on between app_now()::date and app_now()::date + 7 order by s.id"""):
        alerts.raise_alert(cur, kind="standing_approval", severity="info", channel="#outbound-ops",
                           title=f"{s['name']}: standing approval ends {s['ends_on']:%d %b}", target_user=s["owner_id"],
                           body="Follow-ups wait for a person once it ends, unless a manager signs a new one.",
                           dedup_key=f"standing_soon:{s['id']}")


def listing(cur) -> dict:
    """Settings: every policy with what it did, the supervised plays with none, and who last turned the Autonomous stage on or off."""
    rows = db.all(cur, f"""
        select s.id, s.play_id, p.name as play, s.tiers, s.steps, s.reason, s.signed_by_person, s.regions, s.signed_at, s.ends_on,
               s.revoked_at, s.revoke_kind, s.revoke_reason, u.name as owner, rb.name as revoked_by, ({IN_FORCE}) as in_force,
               (select count(*) from messages m where m.standing_approval_id = s.id and m.approval_mode = 'auto_supervised')::int as auto_approved,
               (select count(*) from messages m where m.standing_approval_id = s.id and m.approval_mode = 'person')::int as sampled
        from standing_approvals s join plays p on p.id = s.play_id join users u on u.id = s.owner_id left join users rb on rb.id = s.revoked_by
        order by ({IN_FORCE}) desc, s.signed_at desc, s.id desc limit 40""")
    without = db.all(cur, f"""select p.id, p.name from plays p where p.status = 'live' and p.autonomy = 'supervised'
                              and not exists (select 1 from standing_approvals s where s.play_id = p.id and {IN_FORCE}) order by p.id""")
    auto = db.one(cur, """select s.value, s.updated_at, u.name as by,
                                 (select a.detail->>'reason' from audit_log a where a.action in ('autonomous_stage_on', 'autonomous_stage_off')
                                  order by a.id desc limit 1) as reason
                          from settings s left join users u on u.id = s.updated_by where s.key = 'autonomous_stage'""")
    supervised = db.all(cur, "select p.id, p.name from plays p where p.status = 'live' and p.autonomy = 'supervised' order by p.id")
    return {"policies": rows, "plays_without": without, "plays_supervised": supervised, "term_max_days": TERM_MAX_DAYS,
            "autonomous": {"on": auto["value"] is not False if auto else True, "by": auto["by"] if auto else None,
                           "at": auto["updated_at"] if auto else None, "reason": auto["reason"] if auto else None}}
