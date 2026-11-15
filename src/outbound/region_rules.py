"""Country email rules you can edit (bl_130, decision 85). Every change goes through `change`, which writes the history
row and the rule together; the database refuses a rule insert, update or delete that did not come through it (migration 0035)."""
from __future__ import annotations

from . import db, gate

ORDER = ["blocked", "consent_required", "basis_required", "allowed"]   # strictest first
CHOICES = ORDER


class RuleError(Exception):
    def __init__(self, status: int, message: str, current: str | None = None):
        super().__init__(message)
        self.status, self.current = status, current


def country_name(code: str) -> str:
    """The name as the page shows it, without the article ("Netherlands", "United Kingdom")."""
    n = gate.COUNTRY_NAMES.get(code.upper(), code.upper())
    return n[4:] if n.startswith("the ") else n


def is_loosening(old_rule: str, old_ic: bool, new_rule: str, new_ic: bool) -> bool:
    if ORDER.index(new_rule) > ORDER.index(old_rule):
        return True
    return new_rule == old_rule and old_ic and not new_ic


def change(cur, country: str, rule: str, individual_consent: bool, reason: str, changed_by: int | None, *,
           expect_rule: str | None = None, expect_consent: bool | None = None, confirm: str | None = None, skip_confirm: bool = False, **new_row) -> dict:
    """Validate and apply one change. Raises RuleError (404 unknown country, 422 no change / reason / name, 409 stale).
    A country with no row can be added by passing `allow_new=True`."""
    allow_new = new_row.pop("allow_new", False)
    country = country.upper()
    row = db.one(cur, "select rule, individual_consent from region_rules where country = %s for update", country)
    if row is None and not allow_new:
        raise RuleError(404, "No such country rule.")
    if rule not in ORDER:
        raise RuleError(422, "Unknown rule.")
    if len((reason or "").strip()) < 10:
        raise RuleError(422, "Say why in at least 10 characters.")
    if row is not None:
        if (expect_rule is not None and expect_rule != row["rule"]) or (
                expect_consent is not None and expect_consent != row["individual_consent"]):
            raise RuleError(409, "The rule changed while you were editing.", row["rule"])
        if rule == row["rule"] and individual_consent == row["individual_consent"]:
            raise RuleError(422, "No change.")
        if not skip_confirm and is_loosening(row["rule"], row["individual_consent"], rule, individual_consent):
            name = country_name(country)
            if (confirm or "").strip().lower() != name.lower():
                raise RuleError(422, f"Type {name} to confirm a looser rule.")
    db.run(cur, "select change_region_rule(%s, %s, %s, %s, %s, %s, %s, %s)", country, rule, individual_consent,
           reason.strip(), changed_by, new_row.get("note", "Counsel to confirm."), new_row.get("call_rule", "blocked"),
           new_row.get("dnc_register"))
    return {"country": country, "from": row["rule"] if row else "none", "to": rule}


def changes_for(cur, country: str) -> list[dict]:
    return db.all(cur, """select c.id, c.country, c.at, c.from_rule, c.to_rule, c.from_individual_consent,
                                 c.to_individual_consent, c.reason, u.name as changed_by_name
                          from region_rule_changes c left join users u on u.id = c.changed_by
                          where c.country = %s order by c.id desc limit 200""", country)


def listing(cur) -> dict:
    rules = db.all(cur, """select r.*, c.at as changed_at, u.name as changed_by_name, c.reason as changed_reason
                           from region_rules r
                           left join lateral (select * from region_rule_changes where country = r.country
                                              order by id desc limit 1) c on true
                           left join users u on u.id = c.changed_by order by r.country""")
    for r in rules:
        r["name"] = country_name(r["country"])
    changes = db.all(cur, """select c.id, c.country, c.at, c.from_rule, c.to_rule, c.from_individual_consent,
                                    c.to_individual_consent, c.reason, u.name as changed_by_name
                             from region_rule_changes c left join users u on u.id = c.changed_by
                             order by c.id desc limit 200""")
    return {"regions": rules, "changes": changes}
