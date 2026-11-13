"""WORLD=world: the demo built from the shared world's slice (docs/WORLD.md).

The tests share one database in which the world is built once and then run five days. They are written to run in
file order: what only holds before the run comes first, the rebuild (which wipes the database) comes last."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from conftest import BASE, PREFIX, _admin

from outbound import db
from outbound.sim import world_load as wl

N = 120
EXAMPLE = ".example"


@pytest.fixture(scope="module")
def wdb(database):
    """A database of its own with WORLD=world, so the shared test database is never touched."""
    mp = pytest.MonkeyPatch()
    mp.setenv("WORLD", "world")
    name = f"{PREFIX}world_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'create database "{name}"')
    url = BASE.rsplit("/", 1)[0] + "/" + name
    db.configure(url, max_size=6)
    db.migrate(url)
    yield url
    db.close()
    with psycopg.connect(_admin(BASE), autocommit=True) as c:
        c.execute(f'drop database if exists "{name}" with (force)')
    db.configure(database, max_size=6)
    mp.undo()


@pytest.fixture(scope="module")
def built(wdb):
    from outbound import monitors, outreach, pipeline, replies, scheduler, scoring, sending  # noqa: F401
    from outbound.sim import runner
    start, _ = wl.window()
    info = runner.setup(start=start, n_accounts=N)
    return {"start": start, "info": info}


def q(sql, *args):
    with db.tx() as cur:
        return db.all(cur, sql, *args)


def v(sql, *args):
    with db.tx() as cur:
        return db.val(cur, sql, *args)


def taken():
    return {c["world_id"] for c in wl.load_slice().companies[:N]}


# ---------------------------------------------------------------------------------------------------- the slice

def test_the_window_is_the_cut_to_the_worlds_now():
    start, end = wl.window()
    assert start == datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)


def test_a_slice_that_does_not_match_its_manifest_is_refused(tmp_path):
    copy = tmp_path / "world"
    shutil.copytree(wl.ROOT, copy)
    wl.verify(copy)  # an untouched copy is fine
    f = copy / "truth" / "companies.csv"
    f.write_bytes(f.read_bytes().replace(b"Fintech", b"Fintecj", 1))
    with pytest.raises(wl.SliceError, match="companies.csv"):
        wl.load_slice(copy)
    with pytest.raises(wl.SliceError):
        wl.window(copy)


def test_a_missing_file_or_manifest_is_refused(tmp_path):
    copy = tmp_path / "world"
    shutil.copytree(wl.ROOT, copy)
    (copy / "truth" / "signals.csv").unlink()
    with pytest.raises(wl.SliceError, match="signals.csv"):
        wl.load_slice(copy)
    (copy / "manifest.json").unlink()
    with pytest.raises(wl.SliceError, match="manifest"):
        wl.load_slice(copy)


def test_a_manifest_in_another_format_is_refused(tmp_path):
    copy = tmp_path / "world"
    shutil.copytree(wl.ROOT, copy)
    m = json.loads((copy / "manifest.json").read_text())
    m["format_version"] = "2"
    (copy / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(wl.SliceError, match="format"):
        wl.verify(copy)


def test_a_build_on_a_bad_slice_loads_nothing(built, tmp_path):
    copy = tmp_path / "world"
    shutil.copytree(wl.ROOT, copy)
    (copy / "truth" / "people.csv").write_bytes(b"person_id\n")
    before = v("select count(*) from accounts")
    with pytest.raises(wl.SliceError):
        with db.tx() as cur:
            wl.build(cur, start=built["start"], n_accounts=5, root=copy)
    assert v("select count(*) from accounts") == before


# ---------------------------------------------------------------------------------------------------- what was loaded

def test_the_counts_match_the_slice(built):
    sl, ids, _start = wl.load_slice(), taken(), built["start"]
    info = built["info"]
    assert v("select count(*) from accounts") == N == info["accounts"]
    assert v("select count(*) from sim_accounts") == N
    domains = sum(len([d for d in c["domains"].split(";") if d]) for c in sl.companies[:N])
    assert v("select count(*) from account_domains") == domains
    # Every person of the taken companies is accounted for: held by the CRM, hidden, gone before the cut, or left out
    # because no vendor can find them (only while the schema cannot say so).
    in_slice = sum(len(sl.people_by_company.get(w, [])) for w in ids)
    assert v("select count(*) from people") == info["known"]
    assert v("select count(*) from sim_people") == info["known"]
    assert v("select count(*) from sim_hidden_people") == info["hidden"]
    assert in_slice == info["known"] + info["hidden"] + info["left_before_start"] + info["unfindable_left_out"]
    assert 0.45 < info["known"] / (info["known"] + info["hidden"] + info["unfindable_left_out"]) < 0.65
    deals = [d for d in sl.deals if d["company_world_id"] in ids and d["era"] == "history"]
    assert v("select count(*) from sim_crm_deals") == len(deals) == info["deals"]
    assert v("select count(*) from sim_crm_deals where closed_at is not null") == sum(
        1 for d in deals if d["outcome_at_cut"] in ("won", "lost"))
    assert v("select count(*) from accounts where world_id is not null") == N
    assert v("select count(*) from people where world_id like 'pe\\_%%'") == info["known"]
    assert v("select count(*) from accounts where crm_id like 'CRM-A%%'") == N


def test_the_values_are_the_slices(built):
    sl = wl.load_slice()
    by = {c["world_id"]: c for c in sl.companies}
    for r in q("""select a.world_id, a.name, a.primary_domain, a.employees, a.industry, a.region, a.hq_country, sa.need::float as need,
                         sa.billing, sa.pages from accounts a join sim_accounts sa on sa.account_id = a.id"""):
        c = by[r["world_id"]]
        assert (r["name"], r["primary_domain"], r["employees"], r["industry"], r["region"], r["hq_country"]) == (
            c["name"], c["domain"], int(c["employees"]), c["industry"], c["region"], c["country"])
        assert r["need"] == pytest.approx(float(c["need"]), abs=0.0006) and r["billing"] == c["billing_tool"]
        assert set(r["pages"]) == {"about", "pricing", "billing", "finance", "careers"}
        assert c["billing_tool"] in r["pages"]["billing"]
    p = sl.people[q("select world_id from people order by id limit 1")[0]["world_id"]]
    row = q("select * from people where world_id = %s", p["person_id"])[0]
    assert (row["full_name"], row["email"], row["title"], row["country"]) == (p["full_name"], p["email"].lower(), p["title"], p["country"])
    if p["portrait"]:
        assert row["photo_url"] == f"https://randomuser.me/api/portraits/{p['portrait']}.jpg"


def test_lifecycle_follows_the_customer_file(built):
    sl = wl.load_slice()
    customers = {c["company_world_id"]: c for c in sl.customers}
    for r in q("select world_id, lifecycle from accounts"):
        c = next(x for x in sl.companies if x["world_id"] == r["world_id"])
        cust = customers.get(r["world_id"])
        if cust and cust["era"] == "history" and not cust["churned_on"]:
            assert r["lifecycle"] == "customer"
        if cust and cust["churn_era"] == "history":
            assert r["lifecycle"] == "churned"
        assert (c["lifecycle_at_cut"] == "customer") == (r["lifecycle"] == "customer")
    assert v("select count(*) from accounts where lifecycle = 'customer'") > 0


def test_every_address_in_the_world_is_example(built):
    for sql in ["select primary_domain from accounts", "select domain from account_domains",
                "select email from people where email is not null", "select true_email from sim_hidden_people",
                "select true_email from sim_people", "select domain from sending_domains", "select address from mailboxes",
                "select email from users"]:
        bad = [list(r.values())[0] for r in q(sql) if not list(r.values())[0].endswith(EXAMPLE)]
        assert bad == [], (sql, bad[:3])
    seller = wl.seller()
    assert {r["domain"] for r in q("select domain from sending_domains")} == set(seller["sending_domains"])
    assert all(r["email"].endswith("@lumenledger.example") for r in q("select email from users"))


def test_the_roster_is_the_team_file(built):
    sl = wl.load_slice()
    users = {r["email"]: r for r in q("select * from users")}
    want = {t["email"]: t for t in sl.team if t["account_desk_role"] in ("sdr", "gtm", "manager")}
    assert set(users) == set(want)
    for e, t in want.items():
        assert (users[e]["name"], users[e]["role"], users[e]["timezone"]) == (t["name"], t["account_desk_role"], t["timezone"])
    # An account executive or a viewer has no login here.
    assert not {t["email"] for t in sl.team if not t["account_desk_role"]} & set(users)
    assert "leah.ahn@lumenledger.example" in users and users["leah.ahn@lumenledger.example"]["role"] == "sdr"
    assert q("select u.email from user_aliases a join users u on u.id = a.user_id where a.alias = %s",
             "grace.osei@lumenledger.example") == [{"email": "leah.ahn@lumenledger.example"}]
    assert q("select 1 from users where email like 'grace.osei%%' or name = 'Grace Osei'") == []
    assert users["nadia.haddad@lumenledger.example"]["active"] is False
    assert sum(1 for u in users.values() if not u["active"]) == 1
    # Mailboxes and ownership go only to people who work here today.
    assert q("""select 1 from mailboxes m join users u on u.id = m.user_id where not u.active""") == []
    assert q("""select 1 from accounts a join users u on u.id = a.owner_id where not u.active or u.role <> 'sdr'""") == []


def test_ownership_follows_the_region_and_leaves_some_unowned(built):
    rows = q("""select a.region, u.timezone from accounts a left join users u on u.id = a.owner_id""")
    owned = [r for r in rows if r["timezone"]]
    assert 0.8 < len(owned) / len(rows) < 0.95
    assert all(r["timezone"].startswith("Europe") for r in owned if r["region"] == "Europe")
    assert all(not r["timezone"].startswith("Europe") for r in owned if r["region"] != "Europe")


def test_hidden_people_are_reachable_only_through_people_search(built):
    from outbound.adapters.sim import SimPeopleSearch
    hidden = q("select * from sim_hidden_people")
    assert hidden
    assert q("""select 1 from sim_hidden_people h join people p on p.linkedin_url = h.linkedin_url
                or lower(p.email) = lower(h.true_email)""") == []
    assert all(h["found_person_id"] is None for h in hidden)
    # Seated, hidden, and found by a title search at their company.
    with db.tx() as cur:
        h = db.one(cur, """select h.*, a.id as aid from sim_hidden_people h join accounts a on a.id = h.account_id
                           where h.role_started <= app_now()::date and (h.left_at is null or h.left_at > app_now())
                           order by h.id limit 1""")
        acct = db.one(cur, "select * from accounts where id = %s", h["aid"])
        found = SimPeopleSearch().search(cur, acct, [], 100)
    assert h["linkedin_url"] in {c.linkedin_url for c in found}
    # Nobody who starts after today is found yet, and nobody who has left.
    with db.tx() as cur:
        future = db.all(cur, "select account_id, linkedin_url from sim_hidden_people where role_started > app_now()::date")
        assert future, "the slice plants people who start during the rehearsal"
        for f in future[:5]:
            acct = db.one(cur, "select * from accounts where id = %s", f["account_id"])
            assert f["linkedin_url"] not in {c.linkedin_url for c in SimPeopleSearch().search(cur, acct, [], 100)}


def test_seat_changes_are_the_slices(built):
    sl, start = wl.load_slice(), built["start"]
    want = {s["person_id"]: s for s in sl.seat_changes if s["company_world_id"] in taken() and wl._ts(s["at"]) > start}
    assert want
    got = q("""select c.at, c.announced, h.full_name, h.title, h.role_started, a.world_id from sim_seat_changes c
               join sim_hidden_people h on h.id = c.hidden_person_id join accounts a on a.id = c.account_id order by c.id""")
    assert len(got) == len(want) == built["info"]["seat_changes"]
    people = {p["full_name"] + "|" + p["company_world_id"]: p for p in map(sl.people.get, want)}
    for g in got:
        p = people[g["full_name"] + "|" + g["world_id"]]
        s = want[p["person_id"]]
        assert g["at"] == wl._ts(s["at"]) and g["announced"] == (s["announced"] == "true")
        assert g["role_started"] == date.fromisoformat(p["role_started"]) and g["title"] == p["title"]


def test_people_who_leave_have_a_leave_date(built):
    sl = wl.load_slice()
    for r in q("select p.world_id, s.left_at from people p join sim_people s on s.person_id = p.id"):
        left = sl.people[r["world_id"]]["left_at"]
        assert (r["left_at"] is None) == (left == "")
        if left:
            assert r["left_at"] == wl._ts(left)
    assert v("select count(*) from sim_people where left_at is not null") > 0


def test_deals_are_the_crm_history(built):
    sl, start = wl.load_slice(), built["start"]
    deals = {f"CRM-O-{d['deal_id'][3:]}": d for d in sl.deals if d["company_world_id"] in taken() and d["era"] == "history"}
    for r in q("select * from sim_crm_deals"):
        d = deals[r["crm_id"]]
        assert r["amount_cents"] == int(d["amount_usd_cents"])
        if d["outcome_at_cut"] == "open":
            assert r["closed_at"] is None and r["stage"] == d["stage_at_cut"] and r["close_on"] > start
            assert r["will_win"] == (d["planned_outcome"] == "won")
        else:
            assert r["won"] == (d["outcome_at_cut"] == "won") and r["closed_at"] <= start
    # The desk learned them on its first read.
    assert v("select count(*) from opportunities") >= sum(1 for _ in deals)


def test_the_cut_and_the_clock(built):
    assert v("select app_now()") == built["start"]


# ---------------------------------------------------------------------------------------------------- the run

@pytest.fixture(scope="module")
def ran(built):
    from outbound.sim import runner
    return runner.run(5, seed=11, slow_last_days=0, idle_hours=0)


def test_a_five_day_run_ingests_the_csv_signals(ran, built):
    sl, start = wl.load_slice(), built["start"]
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
    want = {}
    for day in range(5):
        for s in sl.signals_by_day.get((midnight + timedelta(days=day)).date().isoformat(), []):
            if s["company_world_id"] in taken():
                want[s["signal_id"]] = s
    assert want and ran["signals"] == len(want)
    got = q("select s.external_id, s.observed_at, s.type_key, s.source, s.status, s.evidence from signals s "
            "where s.external_id ~ '-sg_[0-9a-f]{12}$'")
    assert len(got) == len(want)
    for g in got:
        s = want[g["external_id"].rsplit("-", 1)[-1]]
        assert g["observed_at"] == wl._ts(s["at"]) and g["status"] == "matched"
        assert g["type_key"] == wl.TYPE_MAP.get(s["type"], s["type"]) and g["source"] == wl.SOURCE_MAP.get(s["source"], s["source"])
        assert g["evidence"].get("summary") and (g["evidence"].get("url") or g["evidence"].get("quote"))
    assert min(g["observed_at"] for g in got) >= start and max(g["observed_at"] for g in got) < midnight + timedelta(days=5)


def test_no_signal_is_invented_in_world_mode(ran):
    # Everything a source reported comes from the file: nothing from a company outside the account list, no noise.
    assert v("select count(*) from signals where status <> 'matched' and external_id ~ '-sg_'") == 0
    assert v("select count(*) from signals where raw_company is not null") == 0
    assert v("select count(*) from sim_events where kind = 'second_move_source'") == 0


def test_the_desk_did_real_work_on_the_worlds_signals(ran):
    assert v("select count(*) from account_plays") > 0
    assert v("select count(*) from jobs where status = 'dead'") == 0


def test_every_signal_type_the_world_uses_exists_in_the_catalog(built):
    from outbound.seed import catalog
    types = {t[0] for t in catalog.SIGNAL_TYPES}
    sources = {s[0] for s in catalog.SIGNAL_SOURCES}
    sl = wl.load_slice()
    for s in {(x["type"], x["source"]) for d in sl.signals_by_day.values() for x in d}:
        assert wl.TYPE_MAP.get(s[0], s[0]) in types and wl.SOURCE_MAP.get(s[1], s[1]) in sources, s


def test_the_run_can_end_at_the_worlds_now(ran):
    from outbound.sim import runner
    before = v("select app_now()")
    runner.run(0, extra_hours=2, seed=3, slow_last_days=0, idle_hours=0)
    assert v("select app_now()") == before + timedelta(hours=2)


def test_the_meeting_functions_come_from_the_worlds_behavior_file():
    b = wl.behavior()
    assert b["no_show"]["base"] == 0.18 and b["opportunity_from_meeting"]["per_need"] == 0.45


# ---------------------------------------------------------------------------------------------------- the same build twice

TABLES = ["users", "user_aliases", "sending_domains", "mailboxes", "accounts", "account_domains", "sim_accounts", "people",
          "sim_people", "sim_hidden_people", "sim_seat_changes", "sim_crm_deals"]


def _digest():
    h = hashlib.sha256()
    for t in TABLES:
        for r in q(f"select * from {t} order by 1, 2"):
            h.update(json.dumps(r, sort_keys=True, default=str).encode())
    return h.hexdigest()


def test_two_builds_of_one_slice_are_identical(built):
    from outbound.sim import runner
    start, _ = wl.window()
    digests = []
    for _ in range(2):
        runner.reset()
        runner.setup(start=start, n_accounts=60)
        digests.append(_digest())
    assert digests[0] == digests[1]
    assert v("select count(*) from accounts") == 60


# ---------------------------------------------------------------------------------------------------- legacy

def test_legacy_is_the_default_and_unchanged(monkeypatch):
    monkeypatch.delenv("WORLD", raising=False)
    from outbound.seed import catalog, load
    from outbound.sim import runner
    assert not runner.world_on()
    assert load._users(False) == [(*u, True) for u in catalog.USERS]
    assert any(e.endswith("grace.osei@lumenledger.example") for _, e, _, _ in catalog.USERS)
