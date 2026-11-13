"""Erasure. Deletes the person and everything that quotes them, scrubs their address from logs and the CRM queue,
and leaves a hashed suppression so they are never added again (docs/SPEC.md 22.17)."""
from __future__ import annotations

import hashlib
import hmac as _hmac
import re

from . import audit, db


def _key(key: str | None) -> bytes:
    k = key or db.erasure_key()
    if not k:
        raise RuntimeError("No erasure key: set ERASURE_KEY (demo mode makes its own once the database is migrated).")
    return k.encode()


def email_hmac(email: str, key: str | None = None) -> str:
    """Keyed hash of an address (DESIGN 6.4). Lower case, trimmed; the key is this install's own, so the hash cannot
    be reversed by guessing likely addresses, and another install's hash of the same address differs."""
    return _hmac.new(_key(key), email.strip().lower().encode(), hashlib.sha256).hexdigest()


def linkedin_hmac(url: str, key: str | None = None) -> str:
    return _hmac.new(_key(key), _linkedin_norm(url).encode(), hashlib.sha256).hexdigest()


def phone_hmac(phone: str, key: str | None = None) -> str:
    return _hmac.new(_key(key), re.sub(r"\D", "", phone).encode(), hashlib.sha256).hexdigest()


def _linkedin_norm(url: str) -> str:
    return url.strip().lower().split("://")[-1].removeprefix("www.").rstrip("/")


def _suppress_hash(cur, kind: str, value: str, reason: str, source: str) -> None:
    db.run(cur, "insert into suppressions (kind, value, reason, source) values (%s, %s, %s, %s)", kind, value, reason, source)


def erased(cur, *, email: str | None, linkedin_url: str | None) -> bool:
    """Whether this address or profile belongs to someone erased on request: they are never added again. Checks the
    keyed hashes and the plain ones written before they existed (those rows cannot be re-keyed: the address is gone)."""
    e = (email or "").strip().lower()
    return bool(db.val(cur, """select exists (select 1 from suppressions where
                                 (kind = 'email_hash' and %s <> '' and value = encode(sha256(convert_to(%s, 'UTF8')), 'hex'))
                              or (kind = 'email_hmac' and %s <> '' and value = %s)
                              or (kind = 'linkedin_hash' and value = %s)
                              or (kind = 'linkedin_hmac' and value = %s))""",
                       e, e, e, email_hmac(e) if e else "",
                       linkedin_hash(linkedin_url) if linkedin_url else "",
                       linkedin_hmac(linkedin_url) if linkedin_url else ""))


def linkedin_hash(url: str) -> str:
    """Legacy plain hash, read only: rows written before the keyed ones. Nothing writes it any more."""
    return hashlib.sha256(_linkedin_norm(url).encode()).hexdigest()


def erase(cur, person_id: int, *, actor_id: int | None) -> dict:
    p = db.one(cur, "select id, email, phone, full_name, linkedin_url from people where id = %s for update", person_id)
    if p is None:
        return {"ok": False, "reason": "No such person"}
    email = (p["email"] or "").lower()
    counts = {}
    name_like = "%" + p["full_name"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    # Themes whose learnings go with this person, so a theme left empty goes too (with its suggestions).
    themes = [r["theme_id"] for r in db.all(cur, """
        select distinct l.theme_id from learnings l join call_notes cn on cn.id = l.call_note_id
        join meetings m on m.id = cn.meeting_id where l.theme_id is not null and (l.quote ilike %s or m.person_id = %s)""",
        name_like, person_id)]
    counts["learnings"] = db.run(cur, "delete from learnings where quote ilike %s", name_like)
    counts["replies"] = db.run(cur, "delete from replies where person_id = %s or (%s <> '' and from_addr = %s)",
                               person_id, email, email)
    counts["touches"] = db.run(cur, "delete from touches where person_id = %s", person_id)
    counts["facts"] = db.run(cur, "delete from facts where person_id = %s", person_id)
    counts["tasks"] = db.run(cur, "delete from tasks where person_id = %s", person_id)
    counts["meetings"] = db.run(cur, "delete from meetings where person_id = %s", person_id)
    # The quote goes (a signal keeps a link or a quote, so it becomes a placeholder) and the name leaves the summary.
    counts["signals"] = db.run(cur, """update signals set person_id = null, evidence = evidence
                                         || jsonb_build_object('summary', replace(evidence->>'summary', %s, 'Someone'))
                                         || case when evidence ? 'quote' then '{"quote": "Removed on request"}'::jsonb else '{}'::jsonb end
                                       where person_id = %s""", p["full_name"], person_id)
    counts["deals"] = db.run(cur, "update opportunities set contact_email = null where %s <> '' and contact_email = %s", email, email)
    counts["llm_calls_by_name"] = db.run(cur, "update llm_calls set output = '{}'::jsonb where output::text ilike %s",
                                         "%" + p["full_name"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if p["linkedin_url"]:
        _suppress_hash(cur, "linkedin_hmac", linkedin_hmac(p["linkedin_url"]), "Erased on request", "erasure")
    if p["phone"]:
        _suppress_hash(cur, "phone_hmac", phone_hmac(p["phone"]), "Erased on request", "erasure")
    if email:
        counts["crm_outbox"] = db.run(cur, "update crm_outbox set payload = payload - 'email' where payload->>'email' = %s", email)
        counts["llm_calls"] = db.run(cur, "update llm_calls set output = '{}'::jsonb where output::text ilike %s", f"%{email}%")
        counts["audit_log"] = db.run(cur, "update audit_log set detail = '{}'::jsonb where detail::text ilike %s", f"%{email}%")
        db.run(cur, "delete from suppressions where kind = 'email' and value = %s", email)
        _suppress_hash(cur, "email_hmac", email_hmac(email), "Erased on request", "erasure")
    counts["people"] = db.run(cur, "delete from people where id = %s", person_id)  # enrollments and messages cascade
    if themes:
        # A theme left with no learnings, and every suggestion on it, goes. A drafted suggestion's play stays, and the
        # play and the suggestion's record stop pointing at the theme (the foreign keys set them to null).
        empty = [r["id"] for r in db.all(cur, """select id from learning_themes t where id = any(%s)
                                                and not exists (select 1 from learnings l where l.theme_id = t.id)""", themes)]
        counts["play_suggestions"] = db.run(cur, "delete from play_suggestions where theme_id = any(%s) and status <> 'drafted'", empty)
        counts["learning_themes"] = db.run(cur, "delete from learning_themes where id = any(%s)", empty)
    # A theme label never should name a person (the filing check refuses it), but one that does loses the name here.
    # Should the new label match another theme's, the learnings move to that theme and this one goes.
    pattern = re.compile(re.escape(p["full_name"]), re.I)
    renamed = 0
    for t in db.all(cur, "select id, kind, label from learning_themes where label ilike %s", name_like):
        label = pattern.sub("someone", t["label"]).strip()
        same = db.val(cur, "select id from learning_themes where kind = %s and lower(label) = lower(%s) and id <> %s",
                      t["kind"], label, t["id"])
        if same:
            db.run(cur, "update learnings set theme_id = %s where theme_id = %s", same, t["id"])
            db.run(cur, "delete from play_suggestions where theme_id = %s and status <> 'drafted'", t["id"])
            db.run(cur, "update plays set suggested_from = %s where suggested_from = %s", same, t["id"])
            db.run(cur, "delete from learning_themes where id = %s", t["id"])
        else:
            db.run(cur, "update learning_themes set label = %s where id = %s", label, t["id"])
        renamed += 1
    counts["themes_renamed"] = renamed
    audit.log(cur, "person", "erased", "person", person_id, {"counts": counts}, actor_id=actor_id)
    return {"ok": True, "counts": counts}


def suppress_other_channels(cur, person_id: int, *, reason: str, source: str) -> None:
    """An opt-out covers every channel: no call to their number and no LinkedIn note to their profile either."""
    p = db.one(cur, "select phone, linkedin_url from people where id = %s", person_id)
    if p is None:
        return
    if p["phone"]:
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('phone', %s, %s, %s)",
               p["phone"], reason, source)
    if p["linkedin_url"]:
        _suppress_hash(cur, "linkedin_hmac", linkedin_hmac(p["linkedin_url"]), reason, source)


def phone_hash(phone: str) -> str:
    """Legacy plain hash, read only. The same number however it is written: digits only."""
    return hashlib.sha256(re.sub(r"\D", "", phone).encode()).hexdigest()


def purge_stale(cur, *, months: int | None = None, batch: int = 500) -> dict:
    """Retention: a prospect who never replied and has had no activity for `months` (setting retention_months,
    default 12) is deleted. An opt-out they gave outlives the record as hashes of their email, phone and LinkedIn
    profile, so they are never contacted or added again. CRM records, customers, champions, and anyone in a
    sequence, a meeting, an open task or a deal stay."""
    if months is None:
        v = db.val(cur, "select value from settings where key = 'retention_months'")
        months = int(v) if v is not None else 12
    rows = db.all(cur, """
        select p.id, p.email, p.phone, p.linkedin_url from people p left join accounts a on a.id = p.account_id
         where p.created_at < app_now() - make_interval(months => %s)
           and p.source <> 'crm' and not p.is_champion and coalesce(a.lifecycle, 'prospect') = 'prospect'
           and not exists (select 1 from replies r where r.person_id = p.id)
           and not exists (select 1 from touches t where t.person_id = p.id and t.at > app_now() - make_interval(months => %s))
           and not exists (select 1 from meetings m where m.person_id = p.id)
           and not exists (select 1 from enrollments e where e.person_id = p.id and e.state in ('pending', 'active', 'paused'))
           and not exists (select 1 from tasks k where k.person_id = p.id and k.status = 'open')
           and not exists (select 1 from opportunities o where p.email is not null and o.contact_email = p.email)
         order by p.id limit %s""", months, months, batch)
    kept = 0
    for p in rows:
        email, phone = (p["email"] or "").lower(), p["phone"] or ""
        opted_out = db.val(cur, """select exists (select 1 from suppressions where (expires_at is null or expires_at > app_now())
                                     and ((kind = 'person' and value = %s) or (kind = 'email' and %s <> '' and value = %s)
                                          or (kind = 'phone' and %s <> '' and value = %s)))""",
                           str(p["id"]), email, email, phone, phone)
        if opted_out:
            kept += 1
            if email:
                _suppress_hash(cur, "email_hmac", email_hmac(email), "Opted out; record purged", "retention")
            if phone:
                _suppress_hash(cur, "phone_hmac", phone_hmac(phone), "Opted out; record purged", "retention")
            if p["linkedin_url"]:
                _suppress_hash(cur, "linkedin_hmac", linkedin_hmac(p["linkedin_url"]), "Opted out; record purged", "retention")
        db.run(cur, """delete from suppressions where (kind = 'person' and value = %s)
                       or (kind = 'email' and %s <> '' and value = %s) or (kind = 'phone' and %s <> '' and value = %s)""",
               str(p["id"]), email, email, phone, phone)
        if email:
            db.run(cur, "update crm_outbox set payload = payload - 'email' where payload->>'email' = %s", email)
        db.run(cur, "delete from people where id = %s", p["id"])
    if rows:
        audit.log(cur, "desk", "retention_purge", "people", None,
                  {"deleted": len(rows), "opt_outs_kept_as_hashes": kept, "months": months})
    return {"deleted": len(rows), "opt_outs_kept": kept}
