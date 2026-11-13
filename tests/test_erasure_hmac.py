"""Erasure hashes are keyed HMACs with this install's own key (shared-world DESIGN 6.4)."""
from __future__ import annotations

import pytest
from test_guarantees import refused, scene, send  # noqa: F401

from outbound import db, privacy
from outbound.config import Config

NEW = ("email_hmac", "linkedin_hmac", "phone_hmac")
OLD = ("email_hash", "linkedin_hash", "phone_hash")


def _kinds(cur, since: int) -> set[str]:
    return {r["kind"] for r in db.all(cur, "select kind from suppressions where id > %s", since)}


def _mark(cur) -> int:
    return db.val(cur, "select coalesce(max(id), 0) from suppressions")


def test_erase_writes_only_keyed_hashes(cur, scene):  # noqa: F811
    db.run(cur, "update people set linkedin_url = 'https://www.linkedin.com/in/ana-h', phone = '+1 215 555 0101' where id = %s",
           scene["person"])
    email = db.val(cur, "select email from people where id = %s", scene["person"])
    mark = _mark(cur)
    assert privacy.erase(cur, scene["person"], actor_id=scene["user"])["ok"]
    assert _kinds(cur, mark) == set(NEW)
    assert db.val(cur, "select exists (select 1 from suppressions where kind = 'email_hmac' and value = %s)",
                  privacy.email_hmac(email))
    assert privacy.erased(cur, email=email.upper(), linkedin_url=None)
    assert privacy.erased(cur, email=None, linkedin_url="http://LinkedIn.com/in/ana-h/")


def test_an_opt_out_purge_and_other_channels_write_only_keyed_hashes(cur, scene):  # noqa: F811
    db.run(cur, "update people set linkedin_url = 'https://www.linkedin.com/in/ana-o', phone = '+1 215 555 0102' where id = %s",
           scene["person"])
    mark = _mark(cur)
    privacy.suppress_other_channels(cur, scene["person"], reason="Unsubscribed", source="reply")
    assert _kinds(cur, mark) <= {"phone", "linkedin_hmac"} and "linkedin_hmac" in _kinds(cur, mark)


def test_the_same_address_under_another_key_does_not_match(cur):
    assert privacy.email_hmac("a@x.example", key="one-key-one-key-1") == privacy.email_hmac(" A@X.example ", key="one-key-one-key-1")
    assert privacy.email_hmac("a@x.example", key="one-key-one-key-1") != privacy.email_hmac("a@x.example", key="two-key-two-key-2")
    assert privacy.linkedin_hmac("https://www.linkedin.com/in/q/", key="k" * 20) != privacy.linkedin_hmac(
        "https://www.linkedin.com/in/q", key="j" * 20)
    # A row written under another install's key does not block this install.
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hmac', %s, 'x', 'erasure')",
           privacy.email_hmac("someone@x.example", key="another-installs-key"))
    assert not privacy.erased(cur, email="someone@x.example", linkedin_url=None)


def test_the_database_refuses_a_send_to_an_erased_person_new_kind(cur, scene):  # noqa: F811
    email = db.val(cur, "select email from people where id = %s", scene["person"])
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hmac', %s, 'erased', 't')",
           privacy.email_hmac(email))
    refused(cur, scene["message"], "suppressed")


def test_the_database_refuses_a_send_to_an_erased_person_legacy_kind(cur, scene):  # noqa: F811
    email = db.val(cur, "select email from people where id = %s", scene["person"])
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hash', "
                "encode(sha256(convert_to(%s, 'UTF8')), 'hex'), 'erased', 't')", email)
    refused(cur, scene["message"], "suppressed")
    assert privacy.erased(cur, email=email, linkedin_url=None)


def test_the_database_refuses_a_linkedin_erasure_by_new_kind(cur, scene):  # noqa: F811
    db.run(cur, "update people set linkedin_url = 'https://www.linkedin.com/in/ana-z' where id = %s", scene["person"])
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('linkedin_hmac', %s, 'erased', 't')",
           privacy.linkedin_hmac("https://linkedin.com/in/ana-z/"))
    refused(cur, scene["message"], "suppressed")


def test_a_row_under_another_key_does_not_block_in_the_database(cur, scene):  # noqa: F811
    email = db.val(cur, "select email from people where id = %s", scene["person"])
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hmac', %s, 'x', 't')",
           privacy.email_hmac(email, key="another-installs-key"))
    send(cur, scene["message"])


def test_a_session_without_the_key_fails_closed_when_keyed_rows_exist(cur, scene):  # noqa: F811
    db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hmac', 'x', 'x', 't')")
    db.run(cur, "select set_config('outbound.erasure_key', '', false)")  # rolled back with the test
    refused(cur, scene["message"], "erasure key not set")


def test_a_session_without_the_key_still_sends_when_no_keyed_rows_exist(cur, scene):  # noqa: F811
    db.run(cur, "delete from suppressions where kind in ('email_hmac', 'linkedin_hmac', 'phone_hmac')")
    db.run(cur, "select set_config('outbound.erasure_key', '', false)")
    send(cur, scene["message"])


def test_every_pooled_connection_carries_the_key(database):
    with db.tx() as cur:
        assert db.val(cur, "select erasure_key()") == db.erasure_key()
        assert db.val(cur, "select erasure_hmac('a@x.example')") == privacy.email_hmac("a@x.example")


def test_a_key_from_the_environment_is_used(database, monkeypatch):
    monkeypatch.setenv("ERASURE_KEY", "an-install-key-of-some-length")
    try:
        db.configure(database, max_size=6)
        assert privacy.email_hmac("a@x.example") == privacy.email_hmac("a@x.example", key="an-install-key-of-some-length")
        with db.tx() as cur:
            assert db.val(cur, "select erasure_key()") == "an-install-key-of-some-length"
    finally:
        monkeypatch.undo()
        db.configure(database, max_size=6)


def _live(monkeypatch, **extra):
    env = {"MODE": "live", "WEBHOOK_SECRET": "w" * 32, "AUTH_MODE": "header", "CF_ACCESS_TEAM_DOMAIN": "t.example",
           "CF_ACCESS_AUD": "aud", "SENDER_COMPANY": "Acme Ltd", "SENDER_ADDRESS": "1 Road, Town", "PRIVACY_URL": "https://acme.example/p"}
    env.update(extra)
    monkeypatch.delenv("ERASURE_KEY", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_live_mode_without_an_erasure_key_refuses_to_start(monkeypatch):
    _live(monkeypatch)
    with pytest.raises(SystemExit, match="ERASURE_KEY"):
        Config().validate()
    monkeypatch.setenv("ERASURE_KEY", "short")
    with pytest.raises(SystemExit, match="ERASURE_KEY"):
        Config().validate()
    monkeypatch.setenv("ERASURE_KEY", "a-long-enough-install-key")
    Config().validate()


def test_demo_mode_needs_no_key(monkeypatch):
    monkeypatch.delenv("ERASURE_KEY", raising=False)
    monkeypatch.setenv("MODE", "demo")
    Config().validate()
