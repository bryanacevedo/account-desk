"""Plays suggested from call learnings (docs/PLAY-SUGGESTIONS.md section 8): the Fisher test, the rule, the life of a
suggestion, who may see and act on one, the prefilled editor's save, erasure and the migration's checks."""
from __future__ import annotations

import itertools
import math
import os

import psycopg
import pytest

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from outbound import db, pipeline, privacy, stats, suggestions, themes  # noqa: E402,F401
from outbound.db import J  # noqa: E402

_ids = itertools.count(1)


# ---------------------------------------------------------------- the Fisher test

def test_fisher_matches_published_values():
    # Fisher's tea-tasting table [[3, 1], [1, 3]], one-sided: 17/70 (R: fisher.test(..., alternative = "greater")).
    assert stats.fisher_greater(3, 4, 4, 8) == pytest.approx(17 / 70)
    assert stats.fisher_greater(4, 4, 4, 8) == pytest.approx(1 / 70)
    # Against an independent sum of the hypergeometric terms in floating point (log-gamma, not exact integers).
    def lgc(n, k):
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    for k, n_in, m, total in ((10, 12, 13, 30), (5, 6, 7, 45), (2, 9, 3, 40)):
        tail = sum(math.exp(lgc(m, x) + lgc(total - m, n_in - x) - lgc(total, n_in)) for x in range(k, min(m, n_in) + 1))
        assert stats.fisher_greater(k, n_in, m, total) == pytest.approx(tail, rel=1e-9)
    assert stats.fisher_greater(0, 5, 3, 20) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        stats.fisher_greater(6, 5, 6, 20)


# ---------------------------------------------------------------- the rule, on a table of learnings

def rows(theme: int, segment: str, *, heard: int, size: int, elsewhere: int, others: int, sdrs: int = 2,
         start: int = 0) -> list[dict]:
    """Accounts in `segment` (size of them, `heard` hearing the theme) and `others` accounts elsewhere (`elsewhere`
    of them hearing it). Notes in the segment are written by `sdrs` different SDRs in turn."""
    out = []
    for i in range(size):
        out.append({"id": next(_ids), "theme_id": theme if i < heard else None, "theme_kind": "reason_to_buy",
                    "signal_type": segment, "account_id": start + i, "sdr": 900 + i % sdrs})
    for i in range(others):
        out.append({"id": next(_ids), "theme_id": theme if i < elsewhere else None, "theme_kind": "reason_to_buy",
                    "signal_type": None, "account_id": start + size + i, "sdr": 900})
    return out


def test_the_rule_passes_at_its_thresholds_and_fails_just_under_each():
    ok = suggestions.evaluate(rows(1, "s", heard=5, size=6, elsewhere=1, others=30))[(1, "s")]
    assert ok["passes"] and ok["accounts"] == 5 and ok["sdrs"] == 2 and ok["pairs_tested"] == 1
    four = suggestions.evaluate(rows(1, "s", heard=4, size=4, elsewhere=0, others=30))[(1, "s")]
    assert four["p"] < four["alpha"] and not four["passes"]  # clear, but heard at only 4 accounts
    one_sdr = suggestions.evaluate(rows(1, "s", heard=5, size=6, elsewhere=1, others=30, sdrs=1))[(1, "s")]
    assert not one_sdr["passes"]
    # Heard at 5 of 10 here against 4 of 20 elsewhere: p is about 0.11, not clear.
    weak = suggestions.evaluate(rows(1, "s", heard=5, size=10, elsewhere=4, others=20))[(1, "s")]
    assert weak["p"] > 0.05 and not weak["passes"]


def test_only_sdrs_count_as_sdrs():
    r = rows(1, "s", heard=5, size=6, elsewhere=1, others=30)
    for x in r:
        if x["sdr"] == 901:
            x["sdr"] = None  # a manager or GTM wrote these notes: `_window` gives no SDR for them
    assert not suggestions.evaluate(r)[(1, "s")]["passes"]


def test_bonferroni_changes_the_verdict():
    # Heard at 5 of 8 here against 3 of 30 elsewhere: p about 0.002. Alone it passes.
    base = rows(1, "s", heard=5, size=8, elsewhere=3, others=30)
    alone = suggestions.evaluate(base)[(1, "s")]
    assert alone["p"] < 0.05 and alone["passes"]
    # Forty other themes each heard once in the segment: 41 pairs, so it now needs p under 0.05 / 41.
    noise = []
    for t in range(2, 42):
        noise.append({"id": next(_ids), "theme_id": t, "theme_kind": "reason_to_buy", "signal_type": "s",
                      "account_id": 0, "sdr": 900})
    many = suggestions.evaluate(base + noise)[(1, "s")]
    assert many["pairs_tested"] == 41 and many["p"] == pytest.approx(alone["p"]) and not many["passes"]


def test_objections_and_quotes_never_make_a_pattern():
    r = rows(1, "s", heard=6, size=6, elsewhere=0, others=30)
    for x in r:
        x["theme_kind"] = "objection"
    assert suggestions.evaluate(r) == {}


# ---------------------------------------------------------------- the life of a suggestion, in the database

@pytest.fixture
def desk(cur, monkeypatch):
    """A segment, two themes, two SDRs, a manager and GTM. The window is replaced by a table the test controls."""
    n = next(_ids)
    db.run(cur, """insert into signal_types (key, label, because, level, weight, half_life_days)
                   values ('t_seg', 'Test segment', 'Because a test needs a segment', 'account', 10, 30),
                          ('t_seg_b', 'Other segment', 'Because a test needs a second segment', 'account', 10, 30)
                   on conflict do nothing""")
    db.run(cur, "insert into personas (key, label, title_patterns, committee_role, angle) values ('cfo', 'Finance leader', "
                "'{cfo}', 'economic_buyer', 'a') on conflict do nothing")
    u = {r: db.val(cur, "insert into users (name, email, role) values (%s, %s, %s) returning id",
                   f"Zed{r.title()} Q{n}", f"{r}{n}@ps.example", r.split("_")[0]) for r in ("sdr_a", "sdr_b", "manager", "gtm")}
    t1 = db.val(cur, "insert into learning_themes (kind, label) values ('reason_to_buy', %s) returning id", f"Zq theme one {n}")
    t2 = db.val(cur, "insert into learning_themes (kind, label) values ('competitor', %s) returning id", f"Zq rival {n}")
    table: list[dict] = []
    monkeypatch.setattr(suggestions, "_window", lambda cur: table)
    return {"users": u, "t1": t1, "t2": t2, "table": table}


def grow(desk, theme: int, heard: int, size: int = 6, segment: str = "t_seg") -> None:
    start = 1000 * theme + (500 if segment != "t_seg" else 0)
    desk["table"][:] = [x for x in desk["table"] if not (x["theme_id"] == theme and x["account_id"] >= start
                                                         and x["account_id"] < start + 500)]
    desk["table"] += rows(theme, segment, heard=heard, size=size, elsewhere=1, others=30, start=start)


def cycle(cur) -> dict:
    """What the daily job does, in one transaction: the check, then each new suggestion opened."""
    lapsed = db.val(cur, "select count(*) from play_suggestions where status = 'lapsed'")
    opened = sum(suggestions.open_suggestion(cur, t, s) is not None for t, s in suggestions.check(cur))
    return {"opened": opened, "lapsed": db.val(cur, "select count(*) from play_suggestions where status = 'lapsed'") - lapsed}


def status(cur, theme: int) -> list[str]:
    return [r["status"] for r in db.all(cur, "select status from play_suggestions where theme_id = %s order by id", theme)]


def test_a_pattern_opens_one_suggestion_with_numbers_and_no_quotes(cur, desk):
    grow(desk, desk["t1"], 5)
    out = cycle(cur)
    assert out["opened"] == 1 and status(cur, desk["t1"]) == ["open"]
    s = db.one(cur, "select * from play_suggestions where theme_id = %s", desk["t1"])
    assert s["evidence"]["accounts"] == 5 and s["evidence"]["pairs_tested"] == 1 and "quote" not in str(s["evidence"])
    assert "t_seg" in s["draft"]["trigger"]["any_of"]
    cycle(cur)
    assert status(cur, desk["t1"]) == ["open"]  # checking again opens nothing new


def test_an_open_suggestion_lapses_when_its_pattern_goes_away(cur, desk):
    grow(desk, desk["t1"], 5)
    cycle(cur)
    grow(desk, desk["t1"], 4)
    assert cycle(cur)["lapsed"] == 1
    assert status(cur, desk["t1"]) == ["lapsed"]


def test_not_now_comes_back_only_when_the_pattern_grows_by_half(cur, desk):
    grow(desk, desk["t1"], 6, size=10)
    cycle(cur)
    sid = db.val(cur, "select id from play_suggestions where theme_id = %s", desk["t1"])
    with pytest.raises(ValueError):
        suggestions.decide(cur, sid, decision="not_now", reason="  ", user_id=desk["users"]["manager"])
    suggestions.decide(cur, sid, decision="not_now", reason="Busy with the launch", user_id=desk["users"]["manager"])
    assert db.val(cur, "select accounts_at_decision from play_suggestions where id = %s", sid) == 6
    grow(desk, desk["t1"], 8, size=10)  # 8 is under 1.5 times 6
    cycle(cur)
    assert status(cur, desk["t1"]) == ["not_now"]
    grow(desk, desk["t1"], 9, size=10)  # 9 is 1.5 times 6
    cycle(cur)
    assert status(cur, desk["t1"]) == ["not_now", "open"]


def test_not_now_in_one_segment_is_not_reopened_by_another(cur, desk):
    grow(desk, desk["t1"], 6, size=10)
    cycle(cur)
    sid = db.val(cur, "select id from play_suggestions where theme_id = %s", desk["t1"])
    suggestions.decide(cur, sid, decision="not_now", reason="Busy with the launch", user_id=desk["users"]["manager"])
    grow(desk, desk["t1"], 9, size=9, segment="t_seg_b")  # clear in the other segment, and more than 1.5 times 6
    cycle(cur)
    assert status(cur, desk["t1"]) == ["not_now"]


def test_a_dismissed_theme_never_comes_back(cur, desk):
    grow(desk, desk["t2"], 5)
    cycle(cur)
    sid = db.val(cur, "select id from play_suggestions where theme_id = %s", desk["t2"])
    suggestions.decide(cur, sid, decision="dismissed", reason=None, user_id=desk["users"]["gtm"])
    grow(desk, desk["t2"], 20, size=20)
    cycle(cur)
    assert status(cur, desk["t2"]) == ["dismissed"]
    assert db.val(cur, "select count(*) from audit_log where object_kind = 'play_suggestion' and object_id = %s", sid) == 2


def test_a_theme_with_a_play_is_not_suggested_again(cur, desk):
    db.run(cur, """insert into plays (key, name, hypothesis, trigger, personas, sequence, angle, suggested_from)
                   values (%s, 'P', 'h', '{}', '{cfo}', '[]', 'a', %s)""", f"ps{desk['t1']}", desk["t1"])
    grow(desk, desk["t1"], 6)
    assert cycle(cur)["opened"] == 0


def test_a_draft_that_names_a_company_or_an_unknown_signal_is_refused(cur, desk):
    db.run(cur, "insert into accounts (name, primary_domain) values ('Quillbright Analytics', 'quillbright.example')")
    cat = suggestions.catalog(cur, "t_seg")
    good = {"name": "A play", "hypothesis": "Teams in this segment need us because of this.",
            "trigger": {"any_of": ["t_seg"]}, "personas": ["cfo"], "angle": "Teams like these often find the close slow."}
    assert suggestions.check_draft(cur, good, "t_seg", cat) == []
    named = {**good, "angle": "Quillbright Analytics found the close slow, and so might you."}
    assert any("Quillbright" in f for f in suggestions.check_draft(cur, named, "t_seg", cat))
    stranger = {**good, "trigger": {"any_of": ["t_seg", "telepathy"]}, "personas": ["cfo", "ceo"]}
    fails = suggestions.check_draft(cur, stranger, "t_seg", cat)
    assert any("telepathy" in f for f in fails) and any("ceo" in f for f in fails)
    assert suggestions.check_draft(cur, {**good, "trigger": {"any_of": ["new_exec"]}}, "t_seg", cat)


def test_a_draft_triggered_by_a_private_signal_must_open_without_naming_it(cur, desk):
    db.run(cur, """insert into signal_types (key, label, because, level, weight, half_life_days)
                   values ('pricing_visit', 'Looked at our pricing', 'Someone read our pricing page.', 'account', 18, 7)
                   on conflict do nothing""")
    cat = suggestions.catalog(cur, "t_seg")
    assert "pricing_visit" not in {t["key"] for t in cat["signal_types"]}  # never added on its own
    cat = suggestions.catalog(cur, "pricing_visit")
    d = {"name": "A play", "hypothesis": "Teams in this segment need us because of this.",
         "trigger": {"any_of": ["pricing_visit"]}, "personas": ["cfo"], "angle": "Teams like these often find the close slow."}
    assert any("without naming" in f for f in suggestions.check_draft(cur, d, "pricing_visit", cat))
    d["angle"] += " Open on that, without naming what we saw."
    assert suggestions.check_draft(cur, d, "pricing_visit", cat) == []


# ---------------------------------------------------------------- filing under themes

def test_a_theme_label_naming_a_desk_user_or_an_email_is_refused(cur, desk):
    first = db.val(cur, "select split_part(name, ' ', 1) from users where id = %s", desk["users"]["sdr_a"])
    fails = themes.check_choice(cur, {"theme_id": None, "new_label": f"{first} says the close is slow"}, "reason_to_buy", {})
    assert any(first in f for f in fails)
    assert themes.check_choice(cur, {"theme_id": None, "new_label": "Write to cfo@x.example"}, "reason_to_buy", {})
    assert themes.check_choice(cur, {"theme_id": 999999, "new_label": None}, "reason_to_buy", {1: "a"})
    assert themes.check_choice(cur, {"theme_id": None, "new_label": "x" * 81}, "reason_to_buy", {})
    assert themes.check_choice(cur, {"theme_id": None, "new_label": "Month-end close is slow"}, "reason_to_buy", {}) == []


# ---------------------------------------------------------------- the migration's checks

def _refused(cur, sql: str, *args) -> bool:
    try:
        with cur.connection.transaction():
            db.run(cur, sql, *args)
    except psycopg.errors.IntegrityError:
        return True
    return False


def test_the_database_refuses_a_suggestion_in_a_bad_state(cur, desk):
    ins = "insert into play_suggestions (theme_id, segment_signal_type, evidence, draft, status, reason, decided_by, decided_at, play_id) "
    t, mgr = desk["t1"], desk["users"]["manager"]
    db.run(cur, ins + "values (%s, 't_seg', '{}', '{}', 'open', null, null, null, null)", t)
    assert _refused(cur, ins + "values (%s, 't_seg', '{}', '{}', 'open', null, null, null, null)", t)  # two open
    assert _refused(cur, ins + "values (%s, 't_seg', '{}', '{}', 'not_now', ' ', %s, now(), null)", t, mgr)  # no reason
    assert _refused(cur, ins + "values (%s, 't_seg', '{}', '{}', 'dismissed', null, null, now(), null)", t)  # no decider
    assert _refused(cur, ins + "values (%s, 't_seg', '{}', '{}', 'drafted', null, %s, now(), null)", t, mgr)  # no play
    assert _refused(cur, ins + "values (%s, 't_seg', '{}', '{}', 'lapsed', null, null, null, null)", t)  # no time
    assert not _refused(cur, ins + "values (%s, 't_seg', '{}', '{}', 'not_now', 'Later', %s, now(), null)", t, mgr)
    assert _refused(cur, "insert into learning_themes (kind, label) values ('competitor', upper(%s))",
                    db.val(cur, "select label from learning_themes where id = %s", desk["t2"]))  # unique whatever the case


# ---------------------------------------------------------------- erasure

def test_erasing_a_person_takes_themes_left_empty_and_their_suggestions(cur, desk):
    u = desk["users"]
    a = db.val(cur, "insert into accounts (name, primary_domain) values ('Erase Co', %s) returning id", f"erase{desk['t1']}.example")
    p = db.val(cur, "insert into people (account_id, full_name, first_name, source) values (%s, 'Ines Quarrow', 'Ines', 'test') returning id", a)
    m = db.val(cur, """insert into meetings (account_id, person_id, booked_at, starts_at, status, source)
                       values (%s, %s, now(), now(), 'held', 'sdr') returning id""", a, p)
    other = db.val(cur, """insert into meetings (account_id, booked_at, starts_at, status, source)
                           values (%s, now(), now(), 'held', 'sdr') returning id""", a)
    n1 = pipeline.record_call_notes(cur, m, "Close is slow.", u["sdr_a"])
    n2 = pipeline.record_call_notes(cur, other, "Ines Quarrow uses Rivalco.", u["sdr_b"])
    t3 = db.val(cur, "insert into learning_themes (kind, label) values ('reason_to_buy', 'Zq kept theme') returning id")
    for note, kind, text, quote, theme in ((n1, "reason_to_buy", "Close is slow", "Close is slow.", desk["t1"]),
                                           (n2, "competitor", "Rivalco", "Ines Quarrow uses Rivalco.", desk["t2"]),
                                           (n2, "reason_to_buy", "Other", "Other.", t3)):
        db.run(cur, "insert into learnings (call_note_id, kind, text, quote, theme_id) values (%s,%s,%s,%s,%s)",
               note, kind, text, quote, theme)
    play = db.val(cur, """insert into plays (key, name, hypothesis, trigger, personas, sequence, angle, suggested_from)
                          values (%s, 'P', 'h', '{}', '{cfo}', '[]', 'a', %s) returning id""", f"er{desk['t2']}", desk["t2"])
    db.run(cur, """insert into play_suggestions (theme_id, segment_signal_type, evidence, draft, status) values
                   (%s, 't_seg', '{}', '{}', 'open')""", desk["t1"])
    kept = db.val(cur, """insert into play_suggestions (theme_id, segment_signal_type, evidence, draft, status, decided_by,
                          decided_at, play_id) values (%s, 't_seg', '{}', '{}', 'drafted', %s, now(), %s) returning id""",
                  desk["t2"], u["gtm"], play)
    out = privacy.erase(cur, p, actor_id=u["gtm"])
    assert out["counts"]["learning_themes"] == 2 and out["counts"]["play_suggestions"] == 1
    assert not db.val(cur, "select exists (select 1 from learning_themes where id = any(%s))", [desk["t1"], desk["t2"]])
    assert db.val(cur, "select exists (select 1 from learning_themes where id = %s)", t3)
    assert db.val(cur, "select suggested_from from plays where id = %s", play) is None
    assert db.one(cur, "select status, theme_id from play_suggestions where id = %s", kept) == {"status": "drafted", "theme_id": None}


# ---------------------------------------------------------------- the API: roles and the prefilled editor's save

@pytest.fixture(scope="module")
def client(world):
    from outbound.api.app import app
    return TestClient(app)


@pytest.fixture
def open_suggestion(world):
    with db.tx() as cur:
        t = db.val(cur, "insert into learning_themes (kind, label) values ('reason_to_buy', 'Zq api theme') returning id")
        seg = db.val(cur, "select key from signal_types where key = 'new_exec'")
        draft = {"name": "Zq suggested play", "hypothesis": "New finance leaders often need this, because of a reason.",
                 "trigger": {"any_of": [seg]}, "personas": ["cfo", "controller"], "angle": "Teams like theirs often find this."}
        sid = db.val(cur, """insert into play_suggestions (theme_id, segment_signal_type, evidence, draft) values
                             (%s, %s, %s, %s) returning id""", t, seg,
                     J({"accounts": 5, "segment_accounts": 6, "elsewhere": 1, "elsewhere_accounts": 30, "p": 0.0001,
                        "alpha": 0.01, "pairs_tested": 5, "sdrs": 2}), J(draft))
    yield {"id": sid, "theme_id": t, "draft": draft}
    with db.tx() as cur:
        play = db.val(cur, "select play_id from play_suggestions where id = %s", sid)
        db.run(cur, "delete from play_suggestions where id = %s", sid)
        db.run(cur, "delete from plays where suggested_from = %s or id = %s", t, play)
        db.run(cur, "delete from learning_themes where id = %s", t)


def _as(role: str) -> dict:
    with db.tx() as cur:
        return {"X-Acting-As": str(db.val(cur, "select id from users where role = %s order by id limit 1", role))}


def test_only_managers_and_gtm_see_or_decide_suggestions(client, open_suggestion):
    sid = open_suggestion["id"]
    for path in ("/api/play-suggestions", f"/api/play-suggestions/{sid}"):
        assert client.get(path, headers=_as("sdr")).status_code == 403
        assert client.get(path, headers=_as("manager")).status_code == 200
        assert client.get(path, headers=_as("gtm")).status_code == 200
    assert any(s["id"] == sid for s in client.get("/api/play-suggestions", headers=_as("gtm")).json()["suggestions"])
    r = client.post(f"/api/play-suggestions/{sid}/decide", json={"decision": "not_now", "reason": "x"}, headers=_as("sdr"))
    assert r.status_code == 403
    r = client.post(f"/api/play-suggestions/{sid}/decide", json={"decision": "not_now"}, headers=_as("manager"))
    assert r.status_code == 422  # not now needs a reason


def test_saving_the_prefilled_editor_makes_a_draft_play_and_marks_the_suggestion(client, open_suggestion):
    s = client.get(f"/api/play-suggestions/{open_suggestion['id']}", headers=_as("gtm")).json()
    assert s["draft"] == open_suggestion["draft"] and s["theme_id"] == open_suggestion["theme_id"]
    # What the editor sends: the drafted fields over its defaults for a new play.
    body = {**s["draft"], "trigger": {**s["draft"]["trigger"], "fit_tiers": ["A", "B"], "min_priority": 40, "within_days": 30},
            "max_people": 2, "holdout_pct": 20, "urgent": False, "latency_hours": 48, "suggested_from": s["theme_id"],
            "sequence": [{"day": 0, "channel": "email", "job": "open", "by": "desk"}]}
    assert client.post("/api/plays", json=body, headers=_as("manager")).status_code == 403  # GTM writes plays
    r = client.post("/api/plays", json=body, headers=_as("gtm"))
    assert r.status_code == 200, r.text
    with db.tx() as cur:
        play = db.one(cur, "select status, autonomy, suggested_from, holdout_pct from plays where id = %s", r.json()["id"])
        sug = db.one(cur, "select status, play_id, decided_by from play_suggestions where id = %s", open_suggestion["id"])
    assert play == {"status": "draft", "autonomy": "draft", "suggested_from": s["theme_id"], "holdout_pct": 20}
    assert sug["status"] == "drafted" and sug["play_id"] == r.json()["id"] and sug["decided_by"]
    again = client.post("/api/plays", json={**body, "name": "Zq second try"}, headers=_as("gtm"))
    assert again.status_code == 409


# ---------------------------------------------------------------- the demo, honestly

def test_the_demo_suggests_exactly_what_passes_the_rule(database):
    """`make demo`'s own command, in a database of its own, with the thresholds untouched. Builds differ run to run, so
    which pattern opens varies and a build may open none (README says so). What must hold in every build: the planted
    reason is visible in the notes, every open suggestion passes the rule, and every passing pattern not set aside has
    one. Slow: the full 90-day demo, about two minutes."""
    import subprocess
    import sys
    import uuid
    from pathlib import Path

    from psycopg.rows import dict_row
    name = f"outbound_demo_{uuid.uuid4().hex[:8]}"
    admin = database.rsplit("/", 1)[0] + "/postgres"
    url = database.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'create database "{name}"')
    try:
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(root / "src")}
        subprocess.run([sys.executable, "-m", "outbound", "demo"], cwd=root, env=env, check=True, capture_output=True)
        assert suggestions.RULE == {"min_accounts": 5, "min_sdrs": 2, "window_days": 90, "alpha": 0.05, "regrow": 1.5}
        with psycopg.connect(url, row_factory=dict_row) as c:
            opened = c.execute("select theme_id, segment_signal_type from play_suggestions where status = 'open'").fetchall()
            rows = c.execute("""
                select l.id, l.theme_id, t.kind as theme_kind, l.signal_type, m.account_id,
                       case when u.role = 'sdr' then cn.written_by end as sdr
                from learnings l join call_notes cn on cn.id = l.call_note_id join meetings m on m.id = cn.meeting_id
                left join learning_themes t on t.id = l.theme_id left join users u on u.id = cn.written_by
                where cn.created_at > app_now() - interval '90 days'""").fetchall()
        pairs = suggestions.evaluate(rows)
        for s in opened:
            assert pairs[(s["theme_id"], s["segment_signal_type"])]["passes"]
        passing = {e["theme_id"] for e in pairs.values() if e["passes"]}
        assert passing == {s["theme_id"] for s in opened}
        # The plant shows: in some planted segment, a theme is heard at half or more of its accounts.
        planted = ("new_exec", "hiring_function", "pricing_change", "competitor_review")
        assert any(e["segment"] in planted and e["segment_accounts"] >= 3 and e["rate"] >= 0.5 for e in pairs.values())
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'drop database if exists "{name}" with (force)')


# ---------------------------------------------------------------- two at once

def _in_thread(fn):
    import threading
    out: dict = {}

    def run():
        try:
            out["value"] = fn()
        except Exception as exc:  # surfaced by the caller
            out["error"] = exc
    t = threading.Thread(target=run)
    t.start()
    return t, out


def test_a_check_waits_for_a_decision_and_never_lapses_it(world, monkeypatch):
    import time
    monkeypatch.setattr(suggestions, "_window", lambda cur: [])  # nothing passes: the check would lapse any open one
    with db.tx() as cur:
        mgr = db.val(cur, "select id from users where role = 'manager' order by id limit 1")
        seg = db.val(cur, "select key from signal_types where key = 'new_exec'")
        t = db.val(cur, "insert into learning_themes (kind, label) values ('reason_to_buy', 'Zq race theme') returning id")
        sid = db.val(cur, """insert into play_suggestions (theme_id, segment_signal_type, evidence, draft)
                             values (%s, %s, '{"accounts": 5}', '{}') returning id""", t, seg)
    try:
        with db.pool().connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    suggestions.decide(cur, sid, decision="not_now", reason="After the board meeting", user_id=mgr)

                    def check():
                        with db.tx() as c2:
                            return suggestions.check(c2)
                    th, out = _in_thread(check)
                    time.sleep(0.5)
                    assert th.is_alive()  # the check waits for the decision's lock
        th.join(10)
        assert "error" not in out, out.get("error")
        with db.tx() as cur:
            row = db.one(cur, "select status, decided_by from play_suggestions where id = %s", sid)
        assert row == {"status": "not_now", "decided_by": mgr}
    finally:
        with db.tx() as cur:
            db.run(cur, "delete from play_suggestions where id = %s", sid)
            db.run(cur, "delete from learning_themes where id = %s", t)


def test_two_workers_filing_the_same_new_label_end_on_one_theme(world):
    import time
    label = "Zq race label for two workers"
    try:
        with db.pool().connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    first = themes.theme_for_label(cur, "objection", label)

                    def second():
                        with db.tx() as c2:
                            return themes.theme_for_label(c2, "objection", label.upper())
                    th, out = _in_thread(second)
                    time.sleep(0.5)
        th.join(10)
        assert "error" not in out, out.get("error")
        assert out["value"] == first
    finally:
        with db.tx() as cur:
            db.run(cur, "delete from learning_themes where kind = 'objection' and lower(label) = lower(%s)", label)


def test_erasure_takes_a_name_out_of_a_theme_label(cur, desk):
    a = db.val(cur, "insert into accounts (name, primary_domain) values ('Label Co', %s) returning id", f"label{desk['t1']}.example")
    p = db.val(cur, "insert into people (account_id, full_name, first_name, source) values (%s, 'Odile Varnum', 'Odile', 'test') returning id", a)
    t = db.val(cur, "insert into learning_themes (kind, label) values ('objection', 'Odile Varnum wants a pilot first') returning id")
    privacy.erase(cur, p, actor_id=desk["users"]["gtm"])
    assert db.val(cur, "select label from learning_themes where id = %s", t) == "someone wants a pilot first"


def test_fisher_refuses_an_impossible_table():
    with pytest.raises(ValueError):
        stats.fisher_greater(0, 9, 9, 10)  # nine of ten in the group and nine heard it, yet none overlap
