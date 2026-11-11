"""The contact gate. Returns reasons, never raises. Runs at proposal (account part), enrollment, approval,
scheduling and right before each send. The database trigger on messages is the last line behind it.

Each reason is (code, permanent, message). A permanent reason stops an enrollment; a temporary one waits.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import db


@dataclass(frozen=True)
class Reason:
    code: str
    permanent: bool
    message: str


def _setting(cur, key: str, default):
    v = db.val(cur, "select value from settings where key = %s", key)
    return default if v is None else v


def account_reasons(cur, account_id: int, *, for_proposal: bool = True) -> list[Reason]:
    """Gate rules 1, 3 and 4, plus one open account play and the cooldown holds (section 22.14)."""
    out: list[Reason] = []
    if _setting(cur, "kill_switch", False):
        out.append(Reason("kill_switch", False, "Sending is stopped for everyone"))
    a = db.one(cur, """select a.lifecycle, a.fit_tier, p.lifecycle as parent_lifecycle
                       from accounts a left join accounts p on p.id = a.parent_id where a.id = %s""", account_id)
    if a["lifecycle"] in ("customer", "open_opp", "competitor"):
        out.append(Reason("lifecycle", True, f"Account is a {a['lifecycle'].replace('_', ' ')}"))
    if a["parent_lifecycle"] in ("customer", "open_opp", "competitor"):
        out.append(Reason("parent_lifecycle", True, f"Parent company is a {a['parent_lifecycle'].replace('_', ' ')}"))
    if a["fit_tier"] == "X":
        out.append(Reason("excluded", True, "Outside the ideal customer profile"))
    if db.val(cur, """select exists (select 1 from suppressions where kind = 'account' and value = %s
                       and (expires_at is null or expires_at > app_now()))""", str(account_id)):
        out.append(Reason("suppressed_account", True, "Account is on the do-not-contact list"))
    hold = db.one(cur, """select reason, until from holds where account_id = %s and person_id is null
                          and until > app_now() order by until desc limit 1""", account_id)
    if hold:
        out.append(Reason("account_hold", False, f"On hold until {hold['until']:%d %b}: {hold['reason']}"))
    if for_proposal and db.val(cur, """select exists (select 1 from account_plays where account_id = %s and state in
                 ('proposed','accepted','researching','approving','active','engaged','meeting'))""", account_id):
        out.append(Reason("open_play", False, "Already in a play"))
    return out


def person_reasons(cur, person_id: int, channel: str, *, account_play_id: int | None = None,
                   enrollment_id: int | None = None) -> list[Reason]:
    out: list[Reason] = []
    p = db.one(cur, "select * from people where id = %s", person_id)
    if p is None:
        return [Reason("missing", True, "Person no longer exists")]
    if p["account_id"] is None:
        return [Reason("no_account", True, "Person has no company")]
    out += [r for r in account_reasons(cur, p["account_id"], for_proposal=False)]
    if p["status"] != "active":
        out.append(Reason("person_" + p["status"], True, f"Person is marked {p['status']}"))
    sup = db.one(cur, """
        select kind, reason from suppressions where (expires_at is null or expires_at > app_now()) and (
          (kind = 'email' and value = %s) or
          (kind = 'email_hash' and value = encode(sha256(convert_to(coalesce(%s, ''), 'UTF8')), 'hex')) or
          (kind = 'domain' and value = split_part(coalesce(%s, ''), '@', 2)) or
          (kind = 'person' and value = %s) or
          (kind = 'phone' and value = %s and %s = 'call')) limit 1""",
        p["email"] or "", p["email"], p["email"], str(person_id), p["phone"] or "", channel)
    if sup:
        out.append(Reason("suppressed", True, f"Do not contact: {sup['reason']}"))
    elif p["linkedin_url"]:
        from .privacy import linkedin_hash
        if db.val(cur, """select exists (select 1 from suppressions where kind = 'linkedin_hash' and value = %s
                          and (expires_at is null or expires_at > app_now()))""", linkedin_hash(p["linkedin_url"])):
            out.append(Reason("suppressed", True, "Do not contact: erased on request"))
    hold = db.one(cur, """select reason, until from holds where person_id = %s and until > app_now()
                          order by until desc limit 1""", person_id)
    if hold:
        out.append(Reason("person_hold", False, f"On hold until {hold['until']:%d %b}: {hold['reason']}"))
    if channel == "call" and p.get("phone_dnc"):
        out.append(Reason("phone_dnc", True, "Their number is on a do-not-call register, so the desk will not call it"))
    if channel == "email":
        if not p["email"]:
            out.append(Reason("no_email", True, "No email address"))
        elif p["email_status"] == "invalid":
            out.append(Reason("email_invalid", True, "Email address does not work"))
        elif p["email_status"] in ("catch_all", "risky"):
            out.append(Reason("email_unconfirmed", True, "Their company accepts every address, so theirs could not be confirmed"))
        elif p["email_status"] == "unknown":
            out.append(Reason("verify_due", False, "Email not verified yet"))
        else:
            max_age = int(_setting(cur, "verify_max_age_days", 45))
            stale = db.val(cur, "select %s < app_now() - (%s || ' days')::interval", p["email_verified_at"], max_age)
            if stale:
                out.append(Reason("verify_due", False, f"Email verified more than {max_age} days ago"))
    other = db.val(cur, """select count(*) from enrollments where person_id = %s and state in ('pending','active','paused')
                           and (%s::bigint is null or id <> %s::bigint)""", person_id, enrollment_id, enrollment_id)
    if other:
        out.append(Reason("other_enrollment", True, "Already in another sequence"))
    cooldown = int(_setting(cur, "person_cooldown_days", 90))
    touched = db.val(cur, """
        select exists (select 1 from touches t where t.person_id = %s and t.direction = 'out' and t.source in ('desk', 'sdr')
                       and t.at > app_now() - (%s || ' days')::interval
                       and (%s::bigint is null or t.account_play_id is distinct from %s::bigint))""",
        person_id, cooldown, account_play_id, account_play_id)
    if touched:
        out.append(Reason("cooldown", True, f"Contacted by the desk in the last {cooldown} days"))
    pause_h = int(_setting(cur, "account_reply_pause_hours", 72))
    unhandled = db.val(cur, """select exists (select 1 from replies where account_id = %s and handled_at is null
                               and received_at > app_now() - (%s || ' hours')::interval
                               and coalesce(label, '') not in ('out_of_office', 'auto_reply'))""", p["account_id"], pause_h)
    if unhandled:
        out.append(Reason("account_reply", False, "Someone at the account replied and nobody has answered yet"))
    if channel == "email":
        rule = db.val(cur, "select rule from region_rules where country = %s", p["country"])
        basis = db.val(cur, "select basis from contact_basis where person_id = %s", person_id)
        if rule == "blocked":
            out.append(Reason("region_blocked", True, "Not emailed in this country"))
        elif rule == "consent_required" and basis != "consent":
            out.append(Reason("no_consent", True, "This country needs consent before a cold email"))
        elif rule == "basis_required" and basis is None:
            out.append(Reason("no_basis", False, "No recorded basis for contact yet"))
    return out


def blocking(reasons: list[Reason]) -> bool:
    return bool(reasons)


def describe(reasons: list[Reason]) -> list[dict]:
    return [{"code": r.code, "permanent": r.permanent, "message": r.message} for r in reasons]


def is_temporary_only(reasons: list[Reason]) -> bool:
    return bool(reasons) and not any(r.permanent for r in reasons)


def now(cur) -> datetime:
    return db.val(cur, "select app_now()")
