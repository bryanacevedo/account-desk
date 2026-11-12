"""Running the team and the sending setup after init: people join, change role or leave; domains and mailboxes are
added, paused, resumed and retired. A manager does all of it, every change is audited, and nothing is left without
an owner: someone who leaves hands their accounts, open plays and work to a named successor."""
from __future__ import annotations

from datetime import date, timedelta

from . import audit, db, jobs
from .signals import normalize_domain


class AdminError(ValueError):
    pass


def add_user(cur, *, name: str, email: str, role: str, timezone: str, slack_id: str | None, by: int) -> int:
    email = email.strip().lower()
    if db.val(cur, "select exists (select 1 from users where email = %s)", email):
        raise AdminError("Someone with that email is already on the desk.")
    uid = db.val(cur, "insert into users (name, email, role, timezone, slack_id) values (%s,%s,%s,%s,%s) returning id",
                 name.strip(), email, role, timezone, slack_id)
    audit.log(cur, "person", "user_added", "user", uid, {"role": role}, actor_id=by)
    return uid


def change_user(cur, uid: int, *, by: int, name: str | None = None, role: str | None = None, timezone: str | None = None,
                slack_id: str | None = None) -> None:
    u = db.one(cur, "select * from users where id = %s for update", uid)
    if u is None:
        raise AdminError("No such person.")
    if role and role != u["role"] and u["role"] == "manager" and _managers(cur) <= 1:
        raise AdminError("The desk needs at least one manager, who launches plays.")
    if role and role != "sdr" and u["role"] == "sdr" and _open_work(cur, uid):
        raise AdminError("They still own accounts or open plays as an SDR. Remove them from the desk and hand their work to an SDR.")
    db.run(cur, """update users set name = coalesce(%s, name), role = coalesce(%s, role), timezone = coalesce(%s, timezone),
                   slack_id = coalesce(%s, slack_id) where id = %s""", name, role, timezone, slack_id, uid)
    audit.log(cur, "person", "user_changed", "user", uid, {"role": role, "name": name}, actor_id=by)


def deactivate(cur, uid: int, *, successor: int | None, by: int) -> dict:
    """They leave: sign-in stops at once, their accounts, open plays, open tasks and booked meetings go to the
    successor, and their mailboxes are retired (sequences in flight move to the successor's mailbox)."""
    u = db.one(cur, "select * from users where id = %s for update", uid)
    if u is None or not u["active"]:
        raise AdminError("No active person with that id.")
    if uid == by:
        raise AdminError("Ask another manager to do this.")
    if u["role"] == "manager" and _managers(cur) <= 1:
        raise AdminError("The desk needs at least one manager.")
    moved = {"accounts": 0, "plays": 0, "tasks": 0, "meetings": 0, "mailboxes": 0}
    if _open_work(cur, uid) or db.val(cur, "select exists (select 1 from mailboxes where user_id = %s and status <> 'retired')", uid):
        s = db.one(cur, "select * from users where id = %s and active and role = 'sdr'", successor) if successor else None
        if s is None:
            raise AdminError("They own accounts or work. Name an active SDR to hand it to.")
        moved["accounts"] = db.run(cur, "update accounts set owner_id = %s where owner_id = %s", s["id"], uid)
        moved["plays"] = db.run(cur, """update account_plays set owner_id = %s where owner_id = %s and state in
                                        ('proposed','accepted','researching','approving','active','engaged','meeting')""", s["id"], uid)
        moved["tasks"] = db.run(cur, "update tasks set owner_id = %s where owner_id = %s and status = 'open'", s["id"], uid)
        moved["meetings"] = db.run(cur, "update meetings set owner_id = %s where owner_id = %s and status = 'booked'", s["id"], uid)
        # Their mailboxes stop; anyone mid-sequence continues from the successor's healthiest mailbox.
        new_box = db.val(cur, "select id from mailboxes where user_id = %s and status = 'active' order by id limit 1", s["id"])
        db.run(cur, """update enrollments set mailbox_id = %s where mailbox_id in (select id from mailboxes where user_id = %s)
                       and state in ('pending','active','paused')""", new_box, uid)
        moved["mailboxes"] = db.run(cur, """update mailboxes set status = 'retired', pause_reason = 'Owner left the desk'
                                            where user_id = %s and status <> 'retired'""", uid)
    db.run(cur, "update users set active = false where id = %s", uid)
    audit.log(cur, "person", "user_deactivated", "user", uid, {"successor": successor, "moved": moved}, actor_id=by)
    return moved


def add_domain(cur, *, domain: str, registered: date, dkim_selector: str | None, by: int) -> str:
    d = normalize_domain(domain)
    if not d:
        raise AdminError("That is not a domain.")
    if db.val(cur, "select exists (select 1 from sending_domains where domain = %s)", d):
        raise AdminError("That domain is already set up.")
    # Unauthenticated until the DNS check reads it: nothing sends from it before then.
    db.run(cur, """insert into sending_domains (domain, spf, dkim, dmarc, dmarc_aligned, registered_at, dkim_selector)
                   values (%s, false, false, false, false, %s, %s)""", d, registered, dkim_selector)
    jobs.enqueue(cur, "dns_check", {}, dedupe_key=f"dns_check:new:{d}")
    audit.log(cur, "person", "domain_added", "domain", None, {"domain": d}, actor_id=by)
    return d


def add_mailbox(cur, *, address: str, user_id: int, provider: str, warmup_started: date, by: int) -> int:
    address = address.strip().lower()
    domain = address.split("@")[-1]
    if not db.val(cur, "select exists (select 1 from sending_domains where domain = %s)", domain):
        raise AdminError(f"Set up {domain} as a sending domain first.")
    if db.val(cur, "select count(*) from mailboxes where domain = %s and status <> 'retired'", domain) >= 3:
        raise AdminError("A domain carries at most three mailboxes. Add another domain.")
    owner = db.one(cur, "select name from users where id = %s and active and role = 'sdr'", user_id)
    if owner is None:
        raise AdminError("A mailbox belongs to an active SDR.")
    mid = db.val(cur, """insert into mailboxes (address, domain, provider, display_name, user_id, warmup_started, ramp_start)
                         values (%s,%s,%s,%s,%s,%s,%s) returning id""",
                 address, domain, provider, owner["name"], user_id, warmup_started, warmup_started + timedelta(days=14))
    jobs.enqueue(cur, "placement_tests", {"mailbox_id": mid}, dedupe_key=f"placement:{mid}")
    audit.log(cur, "person", "mailbox_added", "mailbox", mid, {"address": address}, actor_id=by)
    return mid


def set_mailbox(cur, mid: int, *, status: str, reason: str | None, by: int) -> None:
    """Pause, resume or retire a mailbox. Resuming one the desk paused (bounces, placement, a complaint) is a
    person's decision after checking why, so it is audited with the reason it was paused."""
    m = db.one(cur, "select * from mailboxes where id = %s for update", mid)
    if m is None:
        raise AdminError("No such mailbox.")
    if m["status"] == "retired":
        raise AdminError("A retired mailbox stays retired. Add a new one.")
    if status in ("paused", "retired") and not (reason or "").strip():
        raise AdminError("Say why.")
    db.run(cur, "update mailboxes set status = %s, pause_reason = %s where id = %s",
           status, None if status == "active" else reason, mid)
    if status == "retired":
        db.run(cur, """update enrollments set mailbox_id = null where mailbox_id = %s and state in ('pending','active','paused')""", mid)
    audit.log(cur, "person", f"mailbox_{status}", "mailbox", mid, {"was": m["status"], "was_reason": m["pause_reason"],
                                                                     "reason": reason}, actor_id=by)


def _managers(cur) -> int:
    return db.val(cur, "select count(*) from users where role = 'manager' and active")


def _open_work(cur, uid: int) -> bool:
    return bool(db.val(cur, """select exists (select 1 from accounts where owner_id = %s)
                               or exists (select 1 from account_plays where owner_id = %s and state in
                                          ('proposed','accepted','researching','approving','active','engaged','meeting'))
                               or exists (select 1 from tasks where owner_id = %s and status = 'open')""", uid, uid, uid))
