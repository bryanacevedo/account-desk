"""Simulation fixes (2026-11-17): expired proposals on Today with "Propose again" (decision 100), owners that say what
they are and where they came from (decision 101), an SDR's read-only Do not contact and own mailbox (decision 102),
badge counts that equal the lists they open, and the first-visit text. Backend cases run on the shared 21-day world;
the web strings are pinned by reading the source because the web app has no browser test harness."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from outbound import db, plays, views  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"


@pytest.fixture(scope="module")
def client(world):
    from outbound.api.app import app
    return TestClient(app)


def as_(role: str, n: int = 0) -> dict:
    with db.tx() as cur:
        ids = [r["id"] for r in db.all(cur, "select id from users where role = %s and active order by id", role)]
    return {"X-Acting-As": str(ids[n])}


@pytest.fixture
def lapsed(world):
    """One proposed play, expired the way expire_proposals does it, put back as it was afterwards."""
    with db.tx() as cur:
        ap = db.one(cur, """select ap.id, ap.owner_id, ap.account_id from account_plays ap join plays p on p.id = ap.play_id
                            where ap.state = 'proposed' and ap.arm = 'treated' and p.status = 'live'
                            order by ap.id limit 1""")
        if ap is None:
            pytest.skip("the world has no proposed play")
        plays.set_state(cur, ap["id"], "expired", reason="expired", cooldown_key="expired")
        # The shared world leaves this account's priority right at the play's minimum (40 of 40), and any earlier test
        # that rescores it nudges it below. Pin it clearly above the minimum so these cases do not depend on test order.
        minimum = db.val(cur, "select coalesce((p.trigger->>'min_priority')::int, 0) from account_plays x join plays p on p.id = x.play_id where x.id = %s", ap["id"])
        was_priority = db.val(cur, "select priority from account_scores where account_id = %s", ap["account_id"])
        db.run(cur, "update account_scores set priority = %s where account_id = %s", minimum + 20, ap["account_id"])
        ap = {**ap, "min_priority": minimum}
    yield ap
    with db.tx() as cur:
        if was_priority is not None:
            db.run(cur, "update account_scores set priority = %s where account_id = %s", was_priority, ap["account_id"])
        db.run(cur, "delete from account_plays where account_id = %s and id <> %s and proposed_at >= (select proposed_at from account_plays where id = %s)",
               ap["account_id"], ap["id"], ap["id"])
        db.run(cur, "delete from holds where account_id = %s and reason = 'expired'", ap["account_id"])
        db.run(cur, "update account_plays set state = 'proposed', close_reason = null, closed_at = null where id = %s", ap["id"])


def test_a_lapsed_proposal_is_on_today_and_can_be_proposed_again(client, lapsed):
    owner = lapsed["owner_id"]
    h = {"X-Acting-As": str(owner)}
    today = client.get("/api/today", headers=h).json()
    row = next(r for r in today["expired"] if r["id"] == lapsed["id"])
    assert row["can_propose_again"] and row["why"] == []
    assert row["limit_days"] in (1, 5)  # the business days nobody decided in, from settings
    r = client.post(f"/api/account-plays/{lapsed['id']}/propose-again", headers=h)
    assert r.status_code == 200, r.text
    new = r.json()["id"]
    with db.tx() as cur:
        a = db.one(cur, "select state, arm, owner_id, trigger_signal_id from account_plays where id = %s", new)
        old = db.one(cur, "select trigger_signal_id from account_plays where id = %s", lapsed["id"])
        assert a["state"] == "proposed" and a["arm"] == "treated"
        assert a["trigger_signal_id"] == old["trigger_signal_id"]
        assert db.val(cur, "select count(*) from holds where account_id = %s and reason = 'expired' and until > app_now()", lapsed["account_id"]) == 0
        assert db.val(cur, "select count(*) from audit_log where action = 'proposed_again' and object_id = %s", new) == 1
    again = client.get("/api/today", headers=h).json()
    assert all(x["id"] != lapsed["id"] for x in again["expired"])  # it has a newer play now
    assert any(x["id"] == new for x in again["proposals"])
    # A second try is refused: the account already has a newer play.
    assert client.post(f"/api/account-plays/{lapsed['id']}/propose-again", headers=h).status_code == 409


def test_propose_again_is_for_a_lapsed_proposal_and_its_owner_or_a_manager(client, lapsed):
    other = next(u for u in range(4) if str(as_("sdr", u)["X-Acting-As"]) != str(lapsed["owner_id"]))
    with db.tx() as cur:
        role = db.val(cur, "select role from users where id = %s", lapsed["owner_id"])
    if role == "sdr":
        assert client.post(f"/api/account-plays/{lapsed['id']}/propose-again", headers=as_("sdr", other)).status_code == 403
    # A play that is still open cannot be proposed again.
    with db.tx() as cur:
        live = db.val(cur, "select id from account_plays where state = 'proposed' and id <> %s limit 1", lapsed["id"])
    if live:
        assert client.post(f"/api/account-plays/{live}/propose-again", headers=as_("manager")).status_code == 409


def test_a_blocked_account_cannot_be_proposed_again(client, lapsed):
    """A do-not-contact entry on the account stops it, and the Today row says why instead of offering the button."""
    with db.tx() as cur:
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('account', %s, 'test block', 'person:1')", str(lapsed["account_id"]))
    try:
        with db.tx() as cur:
            why = plays.propose_again_blockers(cur, lapsed["account_id"])
        assert why and "do-not-contact" in why[0]
        with pytest.raises(ValueError):
            with db.tx() as cur:
                plays.propose_again(cur, lapsed["id"], user_id=1)
        today = client.get("/api/today", headers=as_("manager")).json()
        row = next(r for r in today["expired"] if r["id"] == lapsed["id"])
        assert not row["can_propose_again"] and row["why"]
    finally:
        with db.tx() as cur:
            db.run(cur, "delete from suppressions where reason = 'test block'")


def test_the_account_list_names_the_expiry_in_plain_words(client, lapsed):
    rows = client.get("/api/accounts?view=all", headers=as_("manager")).json()["accounts"]
    a = next((r for r in rows if r["id"] == lapsed["account_id"]), None)
    if a is None:
        pytest.skip("the account is on a later page")
    assert a["hold_expired"] is True and a["expired_days"] in (1, 5)


def test_badges_equal_the_lists_they_open(client, world):
    for role in ("sdr", "manager", "gtm"):
        h = as_(role)
        today = client.get("/api/today", headers=h).json()
        me = client.get("/api/me", headers=h).json()
        want = len(today["replies"]) + len(today["proposals"]) + len(today["tasks"])
        assert me["counts"]["today"] == want, role
        with db.tx() as cur:
            user = db.one(cur, "select id, role from users where id = %s", int(h["X-Acting-As"]))
            assert views.badge_counts(cur, user)["replies"] == me["counts"]["replies"]


def test_the_replies_badge_counts_what_the_default_replies_view_calls_needs_a_person(client, world):
    h = as_("sdr")
    me = client.get("/api/me", headers=h).json()
    uid = int(h["X-Acting-As"])
    with db.tx() as cur:
        mine = [r for r in views.replies_page(cur, view="mine", user_id=uid) if (r["needs_review"] or r["label"] is None) and not r["handled_at"]]
    assert me["counts"]["replies"] == len(mine)


def test_owner_says_its_role_and_where_it_came_from():
    note = views.owner_note
    assert note(owner_role="sdr", account_owner=True, crm_owner_email="a@x.test", lifecycle="prospect", integrated=set()) == \
        {"role": "SDR", "source": "Account owner, from the CRM record"}
    assert note(owner_role="manager", account_owner=True, crm_owner_email=None, lifecycle="prospect", integrated=set())["source"] \
        == "Account owner, from the account list"
    # Another desk is named only when INTEGRATED_WITH says it is connected: Market Desk for prospects, CRM Desk for customers.
    assert "Market Desk" in note(owner_role="sdr", account_owner=True, crm_owner_email=None, lifecycle="prospect", integrated={"market_desk"})["source"]
    assert "CRM Desk" in note(owner_role="sdr", account_owner=True, crm_owner_email=None, lifecycle="customer", integrated={"crm_desk", "market_desk"})["source"]
    standalone = note(owner_role="sdr", account_owner=True, crm_owner_email="a@x.test", lifecycle="customer", integrated=set())
    assert "Desk" not in standalone["source"]
    assert note(owner_role="sdr", account_owner=False, crm_owner_email=None, lifecycle="prospect", integrated=set())["source"].startswith("Given this play")


def test_every_owner_in_the_api_carries_a_role_and_a_source(client, world):
    rows = client.get("/api/accounts?view=all", headers=as_("manager")).json()["accounts"]
    assert rows
    for r in rows:
        assert r["owner_source"]
        if r["owner"]:
            assert r["owner_role"] in ("SDR", "Manager", "GTM")
    aid = next(r["id"] for r in rows if r["owner"])
    d = client.get(f"/api/accounts/{aid}", headers=as_("manager")).json()
    assert d["account"]["owner_note"]["role"] and d["account"]["owner_note"]["source"]
    assert "answers" in d


def test_a_sent_reply_is_kept_on_the_account(client, world):
    with db.tx() as cur:
        r = db.one(cur, """select r.id, r.account_id, r.person_id from replies r where r.account_id is not null limit 1""")
        u = db.val(cur, "select id from users where role = 'sdr' and active order by id limit 1")
        if r is None:
            pytest.skip("no reply")
        rs = db.val(cur, """insert into reply_sends (reply_id, user_id, person_id, subject, body, body_hash, approved_hash, status, sent_at)
                            values (%s,%s,%s,'Re: test', 'Thursday works.', 'h-simfix', 'h-simfix', 'queued', null) returning id""",
                    r["id"], u, r["person_id"])
    try:
        d = client.get(f"/api/accounts/{r['account_id']}", headers=as_("manager")).json()
        assert any(x["id"] == rs and x["status"] == "queued" for x in d["answers"])
    finally:
        with db.tx() as cur:
            db.run(cur, "delete from reply_sends where id = %s", rs)


def test_an_sdr_sees_only_their_own_mailbox_and_it_cannot_be_changed_from_there(client, world):
    h = as_("sdr")
    r = client.get("/api/my-mailbox", headers=h)
    assert r.status_code == 200
    uid = int(h["X-Acting-As"])
    with db.tx() as cur:
        theirs = {m["address"] for m in db.all(cur, "select address from mailboxes where user_id = %s", uid)}
    got = r.json()
    assert {m["address"] for m in got["mailboxes"]} == theirs
    assert {d["domain"] for d in got["domains"]} <= {m["domain"] for m in got["mailboxes"]}
    # Read only: no write verb is routed there.
    assert client.post("/api/my-mailbox", headers=h, json={}).status_code == 405
    assert client.patch("/api/my-mailbox", headers=h, json={}).status_code == 405


def test_the_do_not_contact_list_is_readable_by_an_sdr_and_hides_erased_values(client, world):
    with db.tx() as cur:
        db.run(cur, "insert into suppressions (kind, value, reason, source) values ('email_hash', 'abc123secret', 'Erased on request', 'erasure')")
    try:
        r = client.get("/api/do-not-contact", headers=as_("sdr"))
        assert r.status_code == 200
        rows = r.json()["entries"]
        assert any(x["kind"] == "email_hash" and x["value"] is None for x in rows)
        assert "abc123secret" not in r.text
        assert client.post("/api/do-not-contact", headers=as_("sdr"), json={}).status_code == 405
        assert client.delete("/api/do-not-contact", headers=as_("sdr")).status_code == 405
    finally:
        with db.tx() as cur:
            db.run(cur, "delete from suppressions where value = 'abc123secret'")


# ---------------------------------------------------------------- the web text, read from the source

def web(name: str) -> str:
    return (WEB / name).read_text()


def test_the_expiry_tooltip_gives_the_reason_and_the_days():
    src = web("pages/Work.tsx")
    assert "Expired: nobody decided in ${a.expired_days} business" in src
    assert "Propose again" in src and "/propose-again" in src


def test_meeting_notes_are_not_used_for_suggestions_unless_ticked():
    src = web("sheets.tsx")
    assert "useState(false); // off until the person ticks it" in src
    assert "useState(true);" not in src.split("export function MeetingSheet")[1].split("const save")[0]


def test_the_sample_notice_is_on_every_screen_and_says_the_four_things():
    app, demo = web("App.tsx"), web("demo.tsx")
    assert "<DemoBar me={me} />" in app and "isSample(me)" in app  # inside main, so it is on the phone as well as the desk
    assert "Sample company, invented data." in demo
    assert "Not available in the public demo." in demo  # the wording the refusal already uses
    assert "Sample day:" in demo and "the demo keeps its own clock" in demo
    # Was: the constant had to be empty (no invented address). Bryan named the address, so the pin is now the exact mailto,
    # the link text, and that a mailto gets no target/rel (only http links do).
    assert 'export const NEXT_STEP_URL = "mailto:bryan@leandrive.io?subject=Account%20Desk%20demo";' in demo
    assert "Write to Bryan about your own data" in demo
    assert 'target: "_blank", rel: "noreferrer noopener"' in demo and "isHttp(NEXT_STEP_URL)" in demo
    assert 'href={NEXT_STEP_URL} target=' not in demo
    assert "Take the tour" in demo and "If you are hiring" in demo and "If you are buying" in demo and "Next step:" in demo


def test_the_count_up_is_gone_and_page_changes_do_not_fade_slowly():
    lib, css = web("lib.tsx"), web("styles.css")
    assert "requestAnimationFrame" not in lib
    ms = [int(x) for x in re.findall(r"\.page-enter \{ animation: enter (\d+)ms", css)]
    assert ms and max(ms) <= 150


def test_there_is_a_skip_link():
    assert 'className="skip-link"' in web("App.tsx") and 'id="main"' in web("App.tsx")


def test_grey_text_is_at_least_4_5_to_1_on_every_background():
    css = web("styles.css")
    root = css.split("}")[0]
    tok = dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", root))

    def lum(h):
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    def ratio(a, b):
        x, y = sorted((lum(a), lum(b)), reverse=True)
        return (x + 0.05) / (y + 0.05)

    for text in ("mute", "faint", "ink-2", "ok", "wait", "stop", "accent"):
        for bg in ("ground", "well", "well-2", "accent-wash"):
            assert ratio(tok[text], tok[bg]) >= 4.5, (text, bg, ratio(tok[text], tok[bg]))


def test_the_accounts_file_import_takes_owner_email_and_ignores_columns_it_has_no_field_for(world):
    """Decision 9 check: Account Desk's own import has no SDR, AE, tier or profile version field. A file that carries
    them is not refused; the columns are not read. Adding fields is a schema change and was not made."""
    from outbound import setup_desk
    csv = ("name,domain,owner_email,sdr,ae,tier,profile_version\n"
           "Simfix Check Co,simfixcheck.example,,Ana,Bo,A,v4\n")
    with db.tx() as cur:
        out = setup_desk.import_accounts(cur, csv)
        assert out["imported"] == 1 and out["refused"] == []
        row = db.one(cur, "select name, fit_tier from accounts where primary_domain = 'simfixcheck.example'")
        assert row["name"] == "Simfix Check Co"
        db.run(cur, "delete from accounts where primary_domain = 'simfixcheck.example'")


# ---- review fixes (2026-11-17): Propose again runs the matching gates; banner is true on Render; smaller items

def _restore(cur, account_id, tier):
    db.run(cur, "update accounts set fit_tier = %s where id = %s", tier, account_id)


def test_propose_again_is_refused_when_the_account_is_now_tier_c(client, lapsed):
    with db.tx() as cur:
        before = db.val(cur, "select fit_tier from accounts where id = %s", lapsed["account_id"])
        db.run(cur, "update accounts set fit_tier = 'C' where id = %s", lapsed["account_id"])
    try:
        with db.tx() as cur:
            ap = db.one(cur, "select * from account_plays where id = %s", lapsed["id"])
            why = plays.propose_again_blockers(cur, lapsed["account_id"], ap)
        assert why and "tier C" in " ".join(why)
        today = client.get("/api/today", headers=as_("manager")).json()
        row = next((r for r in today["expired"] if r["id"] == lapsed["id"]), None)
        assert row is None or not row["can_propose_again"]
        assert client.post(f"/api/account-plays/{lapsed['id']}/propose-again", headers=as_("manager")).status_code in (409, 422)
    finally:
        with db.tx() as cur:
            _restore(cur, lapsed["account_id"], before)


def test_propose_again_is_refused_when_the_play_is_at_its_spend_cap(client, lapsed, monkeypatch):
    from outbound import spend
    monkeypatch.setattr(spend, "play_at_cap", lambda cur, play: True)
    with db.tx() as cur:
        ap = db.one(cur, "select * from account_plays where id = %s", lapsed["id"])
        why = plays.propose_again_blockers(cur, lapsed["account_id"], ap)
    assert why and any("spend cap" in w for w in why)
    r = client.post(f"/api/account-plays/{lapsed['id']}/propose-again", headers=as_("manager"))
    assert r.status_code in (409, 422) and "spend cap" in r.text


def test_propose_again_is_refused_when_the_signal_is_out_of_the_plays_window(client, lapsed):
    with db.tx() as cur:
        sig = db.val(cur, "select trigger_signal_id from account_plays where id = %s", lapsed["id"])
        was = db.val(cur, "select observed_at from signals where id = %s", sig)
        db.run(cur, "update signals set observed_at = app_now() - interval '400 days' where id = %s", sig)
    try:
        with db.tx() as cur:
            ap = db.one(cur, "select * from account_plays where id = %s", lapsed["id"])
            why = plays.propose_again_blockers(cur, lapsed["account_id"], ap)
        assert why and any("window" in w for w in why)
        r = client.post(f"/api/account-plays/{lapsed['id']}/propose-again", headers=as_("manager"))
        assert r.status_code in (409, 422)
    finally:
        with db.tx() as cur:
            db.run(cur, "update signals set observed_at = %s where id = %s", was, sig)


def test_propose_again_is_refused_when_the_priority_is_below_the_plays_minimum(client, lapsed):
    with db.tx() as cur:
        db.run(cur, "update account_scores set priority = %s where account_id = %s", lapsed["min_priority"] - 1, lapsed["account_id"])
        ap = db.one(cur, "select * from account_plays where id = %s", lapsed["id"])
        why = plays.propose_again_blockers(cur, lapsed["account_id"], ap)
    assert why and any("below this play's minimum" in w for w in why)
    r = client.post(f"/api/account-plays/{lapsed['id']}/propose-again", headers=as_("manager"))
    assert r.status_code == 409 and "below this play's minimum" in r.text
    with db.tx() as cur:  # exactly at the minimum is enough
        db.run(cur, "update account_scores set priority = %s where account_id = %s", lapsed["min_priority"], lapsed["account_id"])
        ap = db.one(cur, "select * from account_plays where id = %s", lapsed["id"])
        assert not plays.propose_again_blockers(cur, lapsed["account_id"], ap)


def test_propose_again_and_matching_share_one_set_of_play_gates():
    src = (ROOT / "src" / "outbound" / "plays.py").read_text()
    assert src.count("_play_allows(") >= 3  # defined once, used by match and by the blockers


def test_propose_again_keeps_the_sdr_who_had_it(client, lapsed):
    with db.tx() as cur:
        sdr = db.val(cur, "select active and role = 'sdr' from users where id = %s", lapsed["owner_id"])
    if not sdr:
        pytest.skip("the lapsed proposal's owner is not an SDR")
    r = client.post(f"/api/account-plays/{lapsed['id']}/propose-again", headers=as_("manager"))
    assert r.status_code == 200, r.text
    with db.tx() as cur:
        assert db.val(cur, "select owner_id from account_plays where id = %s", r.json()["id"]) == lapsed["owner_id"]


def test_a_person_set_hold_called_expired_still_blocks_propose_again(client, lapsed):
    with db.tx() as cur:
        db.run(cur, "insert into holds (account_id, reason, until, set_by) values (%s, 'expired', app_now() + interval '3 days', 'person:1')",
               lapsed["account_id"])
    try:
        with db.tx() as cur:
            why = plays.propose_again_blockers(cur, lapsed["account_id"])
        assert why and "On hold" in " ".join(why)
    finally:
        with db.tx() as cur:
            db.run(cur, "delete from holds where account_id = %s and set_by = 'person:1' and reason = 'expired'", lapsed["account_id"])


def test_the_sidebar_opens_the_list_the_replies_badge_counts(client, world):
    for role in ("sdr", "manager"):
        h = as_(role)
        me = client.get("/api/me", headers=h).json()
        listed = client.get("/api/replies?view=needs_person", headers=h).json()["replies"]
        assert me["counts"]["replies"] == len(listed), role
    assert 'to: "/replies?view=needs_person"' in web("App.tsx")


def test_the_banner_has_three_true_branches():
    demo = web("demo.tsx")
    assert "read-only snapshot taken" in demo and "changes are not saved" in demo  # the static snapshot refuses everything
    shared = demo.split("          : me.public_demo")[1].split("Every vendor and signal here is simulated")[0]
    for word in ("accept, skip, approve, propose again or move a day ahead", "seen by every visitor",
                 "Sending, imports, people and settings are refused"):
        assert word in shared
    assert "Changes that would affect all of them are refused" not in demo
    assert "Every vendor and signal here is simulated." in demo  # a local sample desk


def test_the_do_not_contact_page_says_an_sdr_can_add():
    desk = web("pages/Desk.tsx")
    assert "To add or lift an entry, ask a manager" not in desk
    assert "ask a manager" in desk and "An SDR can add a person" in desk


# ---------------------------------------------------------------- integrated week 2: unread replies, email-only list

@pytest.fixture
def unread(world):
    """One reply the desk has not read yet (no label), put away afterwards."""
    from datetime import datetime, timezone

    from outbound import replies
    with db.tx() as cur:
        rid = replies.ingest(cur, from_addr="nobody@unread-case.example", subject="Re: hello", raw="Send me the details.",
                             received_at=datetime(2026, 11, 1, 12, tzinfo=timezone.utc), provider_id="wk2fix-unread-1")
    yield rid
    with db.tx() as cur:
        db.run(cur, "delete from tasks where reply_id = %s", rid)
        db.run(cur, "delete from jobs where kind = 'classify_reply' and payload->>'reply_id' = %s", str(rid))
        db.run(cur, "delete from touches where dedup_key = %s", f"reply:{rid}")
        db.run(cur, "delete from replies where id = %s", rid)


def test_a_person_can_label_a_reply_the_desk_has_not_read_and_the_classifier_leaves_it(client, unread):
    assert "r.needs_review || !r.label ?" in web("sheets.tsx")
    r = client.get(f"/api/replies/{unread}", headers=as_("manager")).json()
    assert r["label"] is None
    res = client.post(f"/api/replies/{unread}/handle", headers=as_("manager"), json={"outcome": "labelled", "label": "other"})
    assert res.status_code == 200 and res.json()["label"] == "other"
    from outbound import replies
    with db.tx() as cur:
        replies.classify_job(cur, {"reply_id": unread})
        assert db.one(cur, "select label, classified_by from replies where id = %s", unread) == {"label": "other", "classified_by": "person"}


def test_an_unread_reply_says_not_read_yet_not_unclear():
    sheets = web("sheets.tsx")
    assert '"Not read yet"' in sheets and "label ? LABEL[label] || LABEL.other" in sheets
    for name in ("sheets.tsx", "pages/Work.tsx", "pages/Flow.tsx"):
        assert "LABEL[r.label] || LABEL.other" not in web(name) and "LABEL[h.r.label]" not in web(name), name


def test_unread_replies_count_as_needing_a_person_in_the_list_and_the_badge(client, unread):
    h = as_("manager")
    with db.tx() as cur:
        user = db.one(cur, "select id, role from users where id = %s", int(h["X-Acting-As"]))
        listed = [r["id"] for r in views.replies_page(cur, view="needs_person")]
        badge = views.badge_counts(cur, user)["replies"]
        open_n = db.val(cur, "select count(*) from replies r where (r.needs_review or r.label is null) and r.handled_at is null")
    assert unread in listed
    assert badge == open_n


def test_the_account_emails_list_holds_email_messages_only(client, world):
    with db.tx() as cur:
        row = db.one(cur, """select ap.account_id, m.id from messages m join enrollments e on e.id = m.enrollment_id
                             join account_plays ap on ap.id = e.account_play_id where m.channel <> 'email' order by m.id limit 1""")
        if row is None:
            pytest.skip("the world has no call or LinkedIn step")
    d = client.get(f"/api/accounts/{row['account_id']}", headers=as_("manager")).json()
    assert row["id"] not in [m["id"] for m in d["messages"]]
