# ruff: noqa: F811  (fixtures shared from test_guarantees are named as parameters)
"""The email rules for the ten countries the starting list lacked (decision 72), tried the way the older rules are: the
catalog says what each is, the contact gate gives its reason, and the database refuses the send whatever the code did."""
from __future__ import annotations

import pytest
from test_guarantees import refused, scene, send  # noqa: F401  the shared scene fixture

from outbound import db, gate
from outbound.seed import catalog

CONSENT = ["IT", "CH", "SE", "DK", "BE", "AT", "NO"]
BASIS = ["FI", "PT"]
TEN = CONSENT + BASIS + ["MX"]


def _in(cur, scene, country, subscriber="corporate"):
    """The catalog's own rule for the country, and the person and account placed there."""
    rules = dict(catalog.REGION_RULES)
    db.run(cur, "insert into region_rules (country, rule, individual_consent) values (%s, %s, %s) "
                "on conflict (country) do update set rule = excluded.rule, individual_consent = excluded.individual_consent",
           country, rules[country], country in catalog.INDIVIDUAL_CONSENT)
    db.run(cur, "update people set country = %s where id = %s", country, scene["person"])
    db.run(cur, "update accounts set hq_country = %s, subscriber_type = %s where id = %s", country, subscriber,
           scene["account"])


def _codes(cur, scene):
    return [r.code for r in gate.person_reasons(cur, scene["person"], "email")]


def test_every_one_of_the_ten_has_a_rule_a_name_and_a_note():
    rules = dict(catalog.REGION_RULES)
    assert len(rules) == len(catalog.REGION_RULES)                           # no country twice
    for c in TEN:
        assert c in rules and c in gate.COUNTRY_NAMES
        assert catalog.REGION_NOTES[c].endswith(".") and chr(0x2014) not in catalog.REGION_NOTES[c]
    assert {c: rules[c] for c in CONSENT} == dict.fromkeys(CONSENT, "consent_required")
    assert {c: rules[c] for c in BASIS} == dict.fromkeys(BASIS, "basis_required")
    assert rules["MX"] == "blocked"
    # The starting list's own rules are as they were.
    assert rules["US"] == "allowed" and rules["GB"] == "basis_required" and rules["SG"] == "blocked"
    assert catalog.INDIVIDUAL_CONSENT == {"GB", "FI", "PT"}


@pytest.mark.parametrize("country", CONSENT)
def test_a_consent_country_is_not_cold_emailed_until_consent(cur, scene, country):
    _in(cur, scene, country)
    assert "no_consent" in _codes(cur, scene)
    refused(cur, scene["message"], "basis")
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'consent')", scene["person"])
    assert "no_consent" not in _codes(cur, scene)
    send(cur, scene["message"])


@pytest.mark.parametrize("country", CONSENT)
def test_a_recorded_legitimate_interest_does_not_open_a_consent_country(cur, scene, country):
    _in(cur, scene, country)
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'legitimate_interest:LIA-1')", scene["person"])
    assert "no_consent" in _codes(cur, scene)
    refused(cur, scene["message"], "basis")


def test_mexico_is_blocked_and_consent_does_not_open_it(cur, scene):
    _in(cur, scene, "MX")
    assert "region_blocked" in _codes(cur, scene)
    refused(cur, scene["message"], "region blocked")
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'consent')", scene["person"])
    assert "region_blocked" in _codes(cur, scene)
    refused(cur, scene["message"], "region blocked")


@pytest.mark.parametrize("country", BASIS)
def test_a_company_in_finland_or_portugal_needs_a_recorded_basis(cur, scene, country):
    _in(cur, scene, country)
    assert "no_basis" in _codes(cur, scene)
    refused(cur, scene["message"], "basis")
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'legitimate_interest:LIA-1')", scene["person"])
    assert not [c for c in _codes(cur, scene) if c in ("no_basis", "no_consent", "region_blocked") or c.startswith("pecr")]
    send(cur, scene["message"])


@pytest.mark.parametrize("country", BASIS)
@pytest.mark.parametrize("subscriber,code", [("individual", "pecr_individual"), ("unknown", "pecr_unknown")])
def test_a_sole_trader_or_unknown_subscriber_there_needs_consent(cur, scene, country, subscriber, code):
    _in(cur, scene, country, subscriber)
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'legitimate_interest:LIA-1')", scene["person"])
    assert code in _codes(cur, scene)
    refused(cur, scene["message"], "not a limited company")
    db.run(cur, "update contact_basis set basis = 'consent' where person_id = %s", scene["person"])
    assert not [c for c in _codes(cur, scene) if c.startswith("pecr")]
    send(cur, scene["message"])


def test_the_sole_trader_rule_reaches_only_the_countries_that_ask_for_it(cur, scene):
    # France's rule is the same kind as Finland's, but nothing in the starting rules says its sole traders differ.
    db.run(cur, "insert into region_rules (country, rule) values ('FR', 'basis_required') on conflict do nothing")
    db.run(cur, "update people set country = 'FR' where id = %s", scene["person"])
    db.run(cur, "update accounts set hq_country = 'FR', subscriber_type = 'individual' where id = %s", scene["account"])
    db.run(cur, "insert into contact_basis (person_id, basis) values (%s, 'legitimate_interest:LIA-1') "
                "on conflict (person_id) do nothing", scene["person"])
    assert not [c for c in _codes(cur, scene) if c.startswith("pecr")]


def test_the_message_names_the_country(cur, scene):
    _in(cur, scene, "FI", "individual")
    why = next(r for r in gate.person_reasons(cur, scene["person"], "email") if r.code == "pecr_individual")
    assert "Finland" in why.message
    _in(cur, scene, "GB", "individual")
    why = next(r for r in gate.person_reasons(cur, scene["person"], "email") if r.code == "pecr_individual")
    assert "the UK" in why.message
