"""Erasure. Deletes the person and everything that quotes them, scrubs their address from logs and the CRM queue,
and leaves a hashed suppression so they are never added again (docs/SPEC.md 22.17)."""
from __future__ import annotations

import hashlib
import re

from . import audit, db


def erased(cur, *, email: str | None, linkedin_url: str | None) -> bool:
    """Whether this address or profile belongs to someone erased on request: they are never added again."""
    return bool(db.val(cur, """select exists (select 1 from suppressions where
                                 (kind = 'email_hash' and %s <> '' and value = encode(sha256(convert_to(%s, 'UTF8')), 'hex'))
                              or (kind = 'linkedin_hash' and value = %s))""",
                       (email or "").lower(), (email or "").lower(), linkedin_hash(linkedin_url) if linkedin_url else ""))


def linkedin_hash(url: str) -> str:
    """The same profile however it is written: no scheme, no www, no trailing slash, lower case."""
    u = url.strip().lower().split("://")[-1].removeprefix("www.").rstrip("/")
    return hashlib.sha256(u.encode()).hexdigest()


def erase(cur, person_id: int, *, actor_id: int | None) -> dict:
    p = db.one(cur, "select id, email, full_name, linkedin_url from people where id = %s for update", person_id)
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
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('linkedin_hash', %s, 'Erased on request', 'erasure')",
               linkedin_hash(p["linkedin_url"]))
    if email:
        counts["crm_outbox"] = db.run(cur, "update crm_outbox set payload = payload - 'email' where payload->>'email' = %s", email)
        counts["llm_calls"] = db.run(cur, "update llm_calls set output = '{}'::jsonb where output::text ilike %s", f"%{email}%")
        counts["audit_log"] = db.run(cur, "update audit_log set detail = '{}'::jsonb where detail::text ilike %s", f"%{email}%")
        db.run(cur, "delete from suppressions where kind = 'email' and value = %s", email)
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hash', "
                    "encode(sha256(convert_to(%s, 'UTF8')), 'hex'), 'Erased on request', 'erasure')", email)
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
