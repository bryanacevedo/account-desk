"""Erasure. Deletes the person and everything that quotes them, scrubs their address from logs and the CRM queue,
and leaves a hashed suppression so they are never added again (docs/SPEC.md 22.17)."""
from __future__ import annotations

from . import audit, db


def erase(cur, person_id: int, *, actor_id: int | None) -> dict:
    p = db.one(cur, "select id, email, full_name, linkedin_url from people where id = %s for update", person_id)
    if p is None:
        return {"ok": False, "reason": "No such person"}
    email = (p["email"] or "").lower()
    counts = {}
    counts["learnings"] = db.run(cur, "delete from learnings where quote ilike %s", f"%{p['full_name']}%")
    counts["replies"] = db.run(cur, "delete from replies where person_id = %s or (%s <> '' and from_addr = %s)",
                               person_id, email, email)
    counts["touches"] = db.run(cur, "delete from touches where person_id = %s", person_id)
    counts["facts"] = db.run(cur, "delete from facts where person_id = %s", person_id)
    counts["tasks"] = db.run(cur, "delete from tasks where person_id = %s", person_id)
    counts["meetings"] = db.run(cur, "delete from meetings where person_id = %s", person_id)
    counts["signals"] = db.run(cur, "update signals set person_id = null, evidence = evidence - 'quote' where person_id = %s",
                               person_id)
    if email:
        counts["crm_outbox"] = db.run(cur, "update crm_outbox set payload = payload - 'email' where payload->>'email' = %s", email)
        counts["llm_calls"] = db.run(cur, "update llm_calls set output = '{}'::jsonb where output::text ilike %s", f"%{email}%")
        counts["audit_log"] = db.run(cur, "update audit_log set detail = '{}'::jsonb where detail::text ilike %s", f"%{email}%")
        db.run(cur, "delete from suppressions where kind = 'email' and value = %s", email)
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hash', "
                    "encode(sha256(convert_to(%s, 'UTF8')), 'hex'), 'Erased on request', 'erasure')", email)
    counts["people"] = db.run(cur, "delete from people where id = %s", person_id)  # enrollments and messages cascade
    audit.log(cur, "person", "erased", "person", person_id, {"counts": counts}, actor_id=actor_id)
    return {"ok": True, "counts": counts}
