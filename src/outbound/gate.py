"""The contact gate. Returns reasons, never raises. Runs at proposal (account part), enrollment, approval,
scheduling and right before each send. The database trigger on messages is the last line behind it.

Each reason is (code, permanent, message). A permanent reason stops an enrollment; a temporary one waits.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import db

# How each lifecycle reads in a sentence: "Account is an open opportunity", never "a open opp".
LIFECYCLE = {"customer": "a customer", "open_opp": "an open opportunity", "competitor": "a competitor",
             "churned": "a former customer", "prospect": "a prospect"}

# Countries by name, for the reasons a person reads. A code without a name here is shown as the code.
COUNTRY_NAMES = {"US": "the United States", "CA": "Canada", "GB": "the United Kingdom", "DE": "Germany", "FR": "France",
                 "NL": "the Netherlands", "ES": "Spain", "IE": "Ireland", "BR": "Brazil", "AU": "Australia",
                 "SG": "Singapore", "IT": "Italy", "BE": "Belgium", "SE": "Sweden", "DK": "Denmark", "PL": "Poland",
                 "AT": "Austria", "PT": "Portugal", "FI": "Finland", "CH": "Switzerland", "NO": "Norway", "IN": "India",
                 "JP": "Japan", "MX": "Mexico", "NZ": "New Zealand"}


def lifecycle_phrase(lifecycle: str) -> str:
    return LIFECYCLE.get(lifecycle, "a " + lifecycle.replace("_", " "))


def country_name(code: str | None) -> str:
    return COUNTRY_NAMES.get((code or "").upper(), code or "an unknown country")


def no_rule_message(country: str | None) -> str:
    """The named gap for a country the desk has no email rule for. Unknown means no cold email until one exists."""
    if not country:
        return "Their country is not known, so no cold email until it is"
    return f"Email in {country_name(country)} needs a region rule first"


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
        out.append(Reason("lifecycle", True, f"Account is {lifecycle_phrase(a['lifecycle'])}"))
    if a["parent_lifecycle"] in ("customer", "open_opp", "competitor"):
        out.append(Reason("parent_lifecycle", True, f"Parent company is {lifecycle_phrase(a['parent_lifecycle'])}"))
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
          (kind = 'email_hmac' and value = %s) or
          (kind = 'domain' and value = split_part(coalesce(%s, ''), '@', 2)) or
          (kind = 'person' and value = %s) or
          (kind = 'phone' and value = %s and %s = 'call') or
          (kind = 'phone_hash' and value = %s and %s = 'call') or
          (kind = 'phone_hmac' and value = %s and %s = 'call')) limit 1""",
        p["email"] or "", p["email"], _email_hmac(p["email"]), p["email"], str(person_id), p["phone"] or "", channel,
        _phone_hash(p["phone"]), channel, _phone_hmac(p["phone"]), channel)
    if sup:
        out.append(Reason("suppressed", True, f"Do not contact: {sup['reason']}"))
    elif p["linkedin_url"]:
        from .privacy import linkedin_hash, linkedin_hmac
        why = db.val(cur, """select reason from suppressions where (expires_at is null or expires_at > app_now())
                             and ((kind = 'linkedin_hash' and value = %s) or (kind = 'linkedin_hmac' and value = %s))
                             limit 1""", linkedin_hash(p["linkedin_url"]), linkedin_hmac(p["linkedin_url"]))
        if why:
            out.append(Reason("suppressed", True, f"Do not contact: {why}"))
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
        if rule is None and basis != "consent":
            # No rule for their country (or no known country): treated as needing consent, so nobody is cold-emailed
            # somewhere the desk has not been told the law. A manager adds the rule; the database refuses it too.
            out.append(Reason("no_region_rule", True, no_rule_message(p["country"])))
        elif rule == "blocked":
            out.append(Reason("region_blocked", True, "Not emailed in this country"))
        elif rule == "consent_required" and basis != "consent":
            out.append(Reason("no_consent", True, "This country needs consent before a cold email"))
        elif rule == "basis_required" and basis is None:
            out.append(Reason("no_basis", False, "No recorded basis for contact yet"))
        pecr = pecr_reason(cur, p, basis)
        if pecr:
            out.append(pecr)
    if channel == "call":
        out += call_reasons(cur, p)
    return out


def pecr_reason(cur, p: dict, basis: str | None) -> Reason | None:
    """UK PECR: a sole trader or partnership is an individual subscriber, so cold email to them needs consent. Only
    a limited company (corporate) may be emailed without it; not knowing which counts as individual."""
    a = db.one(cur, "select hq_country, subscriber_type from accounts where id = %s", p["account_id"]) or {}
    if "GB" not in (p.get("country"), a.get("hq_country")) or basis == "consent":
        return None
    kind = a.get("subscriber_type") or "unknown"
    if kind == "corporate":
        return None
    if kind == "individual":
        return Reason("pecr_individual", True, "A UK sole trader or partnership needs consent before a cold email")
    return Reason("pecr_unknown", True, "Not known whether this UK company is a limited company, so no cold email "
                                        "without consent")


# Time zones for a country, used when the person's own is not known. A country spanning several has its extremes,
# so a call is placed only when it is within calling hours in all of them.
COUNTRY_ZONES = {"US": ["America/New_York", "America/Los_Angeles"], "CA": ["America/Halifax", "America/Vancouver"],
                 "BR": ["America/Sao_Paulo", "America/Manaus"], "AU": ["Australia/Sydney", "Australia/Perth"],
                 "GB": ["Europe/London"], "IE": ["Europe/Dublin"], "DE": ["Europe/Berlin"], "FR": ["Europe/Paris"],
                 "NL": ["Europe/Amsterdam"], "ES": ["Europe/Madrid"], "IT": ["Europe/Rome"], "BE": ["Europe/Brussels"],
                 "SE": ["Europe/Stockholm"], "DK": ["Europe/Copenhagen"], "PL": ["Europe/Warsaw"], "AT": ["Europe/Vienna"],
                 "PT": ["Europe/Lisbon"], "FI": ["Europe/Helsinki"], "CH": ["Europe/Zurich"], "NO": ["Europe/Oslo"],
                 "SG": ["Asia/Singapore"], "IN": ["Asia/Kolkata"], "JP": ["Asia/Tokyo"], "NZ": ["Pacific/Auckland"]}


def call_zones(p: dict) -> list[str] | None:
    if p.get("timezone"):
        return [p["timezone"]]
    return COUNTRY_ZONES.get((p.get("country") or "").upper())


def call_reasons(cur, p: dict) -> list[Reason]:
    """Calls follow the country's call rule, which names the do-not-call register screened first. An unknown
    country, a country with no call rule, or an unknown time zone means no call."""
    if not p.get("country"):
        return [Reason("no_call_rule", True, "Their country is not known, so no calls until it is")]
    rule = db.one(cur, "select call_rule, dnc_register from region_rules where country = %s", p["country"])
    if rule is None:
        return [Reason("no_call_rule", True, f"Calls to {country_name(p['country'])} need a region rule first")]
    if rule["call_rule"] != "allowed":
        return [Reason("call_blocked", True, f"The desk does not call {country_name(p['country'])}")]
    if call_zones(p) is None:
        return [Reason("call_time_unknown", True, "Their time zone is not known, so the desk cannot keep to calling hours")]
    return []


def call_window(cur) -> tuple[str, str]:
    w = _setting(cur, "call_window", ["09:00", "18:00"])
    return w[0], w[1]


def in_call_hours(cur, p: dict, at: datetime, *, _days_off: set | None = None) -> bool:
    """Whether `at` falls within calling hours on a weekday that is not a public holiday, in every zone the person
    could be in."""
    from zoneinfo import ZoneInfo
    zones = call_zones(p)
    if not zones:
        return False
    start, end = call_window(cur)
    if _days_off is None:
        _days_off = {r["day"] for r in db.all(cur, "select day from holidays where country = %s", p.get("country"))}
    for z in zones:
        local = at.astimezone(ZoneInfo(z))
        if local.weekday() >= 5 or not (start <= local.strftime("%H:%M") < end) or local.date() in _days_off:
            return False
    return True


def next_call_time(cur, p: dict, at: datetime) -> datetime | None:
    """The first moment from `at`, in half-hour steps over the next ten days, that is within calling hours."""
    from datetime import timedelta
    days_off = {r["day"] for r in db.all(cur, "select day from holidays where country = %s", p.get("country"))}
    t = at
    for _ in range(2 * 24 * 10):
        if in_call_hours(cur, p, t, _days_off=days_off):
            return t
        t = (t + timedelta(minutes=30)).replace(second=0, microsecond=0)
        t = t.replace(minute=0 if t.minute < 30 else 30)
    return None


def _phone_hash(phone: str | None) -> str:
    if not phone:
        return ""
    from .privacy import phone_hash
    return phone_hash(phone)


def blocking(reasons: list[Reason]) -> bool:
    return bool(reasons)


def describe(reasons: list[Reason]) -> list[dict]:
    return [{"code": r.code, "permanent": r.permanent, "message": r.message} for r in reasons]


def is_temporary_only(reasons: list[Reason]) -> bool:
    return bool(reasons) and not any(r.permanent for r in reasons)


def now(cur) -> datetime:
    return db.val(cur, "select app_now()")


def _email_hmac(email: str | None) -> str:
    from .privacy import email_hmac
    return email_hmac(email) if email else ""


def _phone_hmac(phone: str | None) -> str:
    from .privacy import phone_hmac
    return phone_hmac(phone) if phone else ""
