"""The shared world's slice, loaded as the demo (WORLD=world; docs/WORLD.md).

This is the one module that opens the vendored release. Everything else reaches it through the functions here, and the
desk itself still never reads `sim_*` tables. The slice is checked against its manifest before a single row is used; a
file that does not match is refused, never patched around.

What it does:
  build()        accounts, people, hidden people, seat changes and the CRM's deals, from the slice (mirrors world.build)
  day_signals()  one day's raw signals, in the shape the signal sources ingest today (mirrors signals_gen.day_signals)
  roster()       the users, from the team file
  window()       the demo's start (the cut) and end (the world's now)
  behavior()     the buyer functions the runner reads for meetings and opportunities
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .. import db
from ..db import J
from ..gate import country_name
from ..signals import normalize_name
from . import signals_gen

ROOT = Path(__file__).resolve().parents[3] / "world"
FORMAT_VERSION = "1"
TRUTH = "truth/"      # the folder that holds what only the simulated vendors and the simulator may read
PUBLIC = "public/"

KNOWN_SHARE = 0.55    # of the people in seats on the first day, the share the CRM already holds (legacy: 55%)
UNOWNED_SHARE = 0.12  # accounts that arrive with no owner (legacy: 12%)
# Account Desk's users that already exist under another address: the roster renames Grace Osei to Leah Ahn.
ALIASES = {"grace.osei@lumenledger.example": "leah.ahn@lumenledger.example"}
DESK_ROLES = ("sdr", "gtm", "manager")
TYPE_MAP = {"new_finance_leader": "new_exec"}
SOURCE_MAP = {"job_change_feed": "people_moves"}
# Billing tools that leave the "we replace this" list in the settings: the seller's competitors, plus the two that were
# already on it.
EXTRA_REPLACED = ("Chargebee", "Zuora")


class SliceError(RuntimeError):
    """The slice is not the one the manifest describes."""


# ------------------------------------------------------------------------------------------------ reading the slice

def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(root: Path | str | None = None) -> dict:
    """Check every file the manifest lists against its sha256. Returns the manifest; raises SliceError on any mismatch."""
    root = Path(root) if root else ROOT
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SliceError(f"No readable manifest.json in {root}: {exc}") from exc
    if str(manifest.get("format_version")) != FORMAT_VERSION:
        raise SliceError(f"The slice is format {manifest.get('format_version')}; this desk reads format {FORMAT_VERSION}.")
    bad = []
    for rel, want in sorted((manifest.get("sha256") or {}).items()):
        p = root / rel
        if not p.is_file():
            bad.append(f"{rel} (missing)")
        elif _sha(p) != want:
            bad.append(f"{rel} (checksum differs)")
    if not manifest.get("sha256"):
        bad.append("manifest lists no files")
    if bad:
        raise SliceError("The slice does not match its manifest, so nothing was loaded: " + "; ".join(bad))
    return manifest


def _csv(root: Path, rel: str) -> list[dict]:
    with open(root / rel, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass
class Slice:
    root: Path
    manifest: dict
    clock: dict
    seller: dict
    team: list[dict]
    companies: list[dict]            # sorted by world id
    data: dict[str, dict]            # what a company-data vendor returns, by world id
    people: dict[str, dict]          # by person id
    people_by_company: dict[str, list[dict]]
    seat_changes: list[dict]
    signals_by_day: dict[str, list[dict]]
    deals: list[dict]
    customers: list[dict]
    behavior: dict


_CACHE: dict[tuple, Slice] = {}


def load_slice(root: Path | str | None = None) -> Slice:
    """Verify the slice, then read it. Parsed once per process and per set of checksums."""
    root = Path(root) if root else ROOT
    manifest = verify(root)
    key = (str(root.resolve()), json.dumps(manifest["sha256"], sort_keys=True))
    if key in _CACHE:
        return _CACHE[key]
    people = _csv(root, TRUTH + "people.csv")
    by_company: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(people, key=lambda r: r["person_id"]):
        by_company[p["company_world_id"]].append(p)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for s in sorted(_csv(root, TRUTH + "signals.csv"), key=lambda r: (r["at"], r["signal_id"])):
        by_day[s["at"][:10]].append(s)
    sl = Slice(
        root=root, manifest=manifest,
        clock=json.loads((root / PUBLIC / "clock.json").read_text(encoding="utf-8")),
        seller=json.loads((root / PUBLIC / "seller.json").read_text(encoding="utf-8")),
        team=_csv(root, PUBLIC + "team.csv"),
        companies=sorted(_csv(root, TRUTH + "companies.csv"), key=lambda r: r["world_id"]),
        data={r["world_id"]: r for r in _csv(root, TRUTH + "company_data.csv")},
        people={p["person_id"]: p for p in people}, people_by_company=dict(by_company),
        seat_changes=sorted(_csv(root, TRUTH + "seat_changes.csv"), key=lambda r: (r["at"], r["person_id"])),
        signals_by_day=dict(by_day), deals=_csv(root, TRUTH + "deals.csv"), customers=_csv(root, TRUTH + "customers.csv"),
        behavior=json.loads((root / TRUTH / "behavior.json").read_text(encoding="utf-8")))
    _CACHE.clear()
    _CACHE[key] = sl
    return sl


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def frac(key: str) -> float:
    """A number in [0, 1) that depends only on the key: the world's yes-or-no choices are made by hash, not by draw."""
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 2 ** 32


# ------------------------------------------------------------------------------------------------ clock, team, seller

def window(root: Path | str | None = None) -> tuple[datetime, datetime]:
    """The demo runs from the cut (the rehearsal's start) to the world's now."""
    c = load_slice(root).clock
    return _ts(c["rehearsal_start"]), _ts(c["now"])


def now(root: Path | str | None = None) -> datetime:
    return window(root)[1]


def behavior(root: Path | str | None = None) -> dict:
    """The buyer functions (reply, meeting, opportunity). The runner reads the meeting and opportunity ones."""
    return load_slice(root).behavior


def seller(root: Path | str | None = None) -> dict:
    return load_slice(root).seller


def sending_domains(legacy: list[tuple[str, int]], root: Path | str | None = None) -> list[tuple[str, int]]:
    """The catalog's sending domains and their ages, on the seller's own domains. A domain keeps its age when the seller
    has one with the same name before the suffix; the rest follow the seller's order with a seasoned age."""
    theirs = seller(root)["sending_domains"]
    by_stem = {d.rsplit(".", 1)[0]: d for d in theirs}
    out, used = [], set()
    for domain, age in legacy:
        d = by_stem.get(domain.rsplit(".", 1)[0])
        if d and d not in used:
            used.add(d)
            out.append((d, age))
    out += [(d, 200) for d in theirs if d not in used]
    return out


def competing_tools(root: Path | str | None = None) -> list[str]:
    return list(seller(root)["competitors"]) + list(EXTRA_REPLACED)


def ae_emails(root: Path | str | None = None) -> list[str]:
    """The account executives, who are not users of this desk but own deals and take hand-offs."""
    return [t["email"] for t in load_slice(root).team if t["team"] == "AE" and not t["left_on"]]


def roster(root: Path | str | None = None) -> list[dict]:
    """The desk's users from the team file: those with an Account Desk role. A person who starts after the world's now is
    on the roster but not active. Ordered as the demo has always ordered them, so a user keeps their id and mailboxes."""
    from ..seed import catalog
    sl = load_slice(root)
    today = _ts(sl.clock["now"]).date()
    rows = [t for t in sl.team if t["account_desk_role"] in DESK_ROLES]
    legacy = [ALIASES.get(e, e) for _, e, _, _ in catalog.USERS]
    rank = {e: i for i, e in enumerate(legacy)}
    rows.sort(key=lambda t: (rank.get(t["email"], len(legacy)), t["email"]))
    out = []
    for t in rows:
        started = date.fromisoformat(t["started_on"])
        left = date.fromisoformat(t["left_on"]) if t["left_on"] else None
        out.append({"name": t["name"], "email": t["email"].lower(), "role": t["account_desk_role"],
                    "timezone": t["timezone"], "active": started <= today and (left is None or left > today),
                    "started_on": started, "portrait": t["portrait"]})
    return out


def portrait_url(key: str | None) -> str | None:
    """A portrait key such as `women/22` as the stock-photo address the demo has always used."""
    return f"https://randomuser.me/api/portraits/{key}.jpg" if key and re.fullmatch(r"(women|men)/\d+", key) else None


# ------------------------------------------------------------------------------------------------ building the world

_PRICING_WORDS = {"seat": "seat-based", "usage": "usage-based", "transaction": "per-transaction",
                  "mixed": "a mix of seats and usage"}
_ROLES = ["Billing Specialist", "Revenue Accountant", "Senior Software Engineer", "Account Executive", "Data Analyst",
          "Product Designer", "Customer Success Manager", "Finance Systems Analyst"]


def _pages(c: dict, d: dict | None) -> dict:
    """What a research agent would read on the company's site, composed from the company's own fields."""
    rng = random.Random(f"pages:{c['world_id']}")
    name, employees = c["name"], int(c["employees"])
    where = country_name(c["country"])
    about = ((d or {}).get("description") or "").strip()
    about = f"{about} About {employees} people." if about else f"{name} is headquartered in {where}, about {employees} people."
    word = _PRICING_WORDS.get(c["pricing_model"])
    billing = c["billing_tool"]
    return {
        "about": about,
        "pricing": f"{name} prices its product as {word}." if word else f"{name} does not publish its pricing.",
        "billing": f"Invoices are produced with {billing}.",
        "finance": f"The finance team has about {max(2, employees // rng.randint(45, 90))} people.",
        "careers": "Open roles include " + ", ".join(rng.sample(_ROLES, 3)) + ".",
    }


def _lifecycle(c: dict, open_deal: bool) -> str:
    lc = c["lifecycle_at_cut"]
    if lc == "customer":
        return "customer"
    if lc == "former_customer":
        return "churned"
    if lc == "competitor":
        return "competitor"
    return "open_opp" if open_deal else "prospect"


def _columns(cur, table: str) -> set[str]:
    return {r["column_name"] for r in db.all(cur, "select column_name from information_schema.columns "
                                                 "where table_schema = current_schema() and table_name = %s", table)}


def build(cur, *, start: datetime, n_accounts: int | None = None, root: Path | str | None = None) -> dict:
    """The world as the CRM and the people vendors hold it on `start`, from the slice. Same tables as world.build."""
    sl = load_slice(root)
    companies = sl.companies[:n_accounts] if n_accounts else sl.companies
    taken = {c["world_id"] for c in companies}
    hidden_cols = _columns(cur, "sim_hidden_people")
    has_wid, has_find = "world_id" in hidden_cols, "vendor_findable" in hidden_cols
    reps = db.all(cur, "select id, timezone from users where role = 'sdr' and active order by id")
    eu_reps = [r["id"] for r in reps if r["timezone"].startswith("Europe")] or [r["id"] for r in reps][:1]
    other_reps = [r["id"] for r in reps if not r["timezone"].startswith("Europe")] or [r["id"] for r in reps]
    seat_for = {s["person_id"]: s for s in sl.seat_changes if s["company_world_id"] in taken}
    deals_by = defaultdict(list)
    for dl in sl.deals:
        if dl["company_world_id"] in taken and dl["era"] == "history" and _ts(dl["created_at"]) <= start:
            deals_by[dl["company_world_id"]].append(dl)

    stats = {"accounts": 0, "people": 0, "known": 0, "hidden": 0, "seat_changes": 0, "deals": 0, "left_before_start": 0,
             "unfindable_left_out": 0}
    account_of: dict[str, int] = {}
    parents: list[tuple[int, str]] = []
    used_email: set[str] = set()
    used_linkedin: set[str] = set()
    for i, c in enumerate(companies):
        wid = c["world_id"]
        rng = random.Random(f"account:{wid}")
        d = sl.data.get(wid)
        deals = sorted(deals_by.get(wid, []), key=lambda r: (r["created_at"], r["deal_id"]))
        lifecycle = _lifecycle(c, any(x["outcome_at_cut"] == "open" for x in deals))
        europe = c["region"] == "Europe"
        pool = eu_reps if europe else other_reps
        owner = pool[i % len(pool)] if pool else None
        if frac("unowned:" + wid) < UNOWNED_SHARE:
            owner = None
        domains = [x for x in c["domains"].split(";") if x] or [c["domain"]]
        tech = sorted({t for t in c["tech"].split(";") if t})
        desc = ((d or {}).get("description") or "").strip() or f"{c['name']} is based in {c['hq_city']}."
        aid = db.val(cur, """
            insert into accounts (name_key, name, primary_domain, industry, employees, revenue_band, hq_country, region, tech,
                                  description, lifecycle, owner_id, crm_id, source, created_at, subscriber_type, world_id)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'crm',%s,%s,%s) returning id""",
            normalize_name(c["name"]), c["name"], c["domain"].lower(), c["industry"], int(c["employees"]), c["revenue_band"],
            c["country"], c["region"], tech, desc, lifecycle, owner, f"CRM-A{1000 + i}",
            start - timedelta(days=rng.randint(60, 900)), "individual" if c["sole_trader"] == "true" else "corporate", wid)
        account_of[wid] = aid
        stats["accounts"] += 1
        if c["parent_world_id"]:
            parents.append((aid, c["parent_world_id"]))
        for dom in domains:
            db.run(cur, "insert into account_domains (domain, account_id) values (%s, %s) on conflict do nothing",
                   dom.lower(), aid)
        db.run(cur, "insert into sim_accounts (account_id, need, pages, billing) values (%s, %s, %s, %s)",
               aid, round(float(c["need"]), 3), J(_pages(c, d)), c["billing_tool"])

        hidden_of: dict[str, int] = {}
        for p in sl.people_by_company.get(wid, []):
            started = date.fromisoformat(p["role_started"])
            left = _ts(p["left_at"]) if p["left_at"] else None
            if left is not None and left <= start:
                stats["left_before_start"] += 1
                continue                           # gone before the world opens: nobody holds or finds them
            seated = started <= start.date()
            findable = p["vendor_findable"] == "true"
            known = seated and frac("known:" + p["person_id"]) < KNOWN_SHARE
            email = p["email"].strip().lower()
            if known and (email in used_email or p["linkedin_url"] in used_linkedin):
                known = False                      # one row per address and per profile; the other copy waits to be found
            photo = portrait_url(p["portrait"])
            champion = p["is_champion"] == "true"
            phone = p["phone"] or None
            if known:
                used_email.add(email)
                used_linkedin.add(p["linkedin_url"])
                pid = db.val(cur, """
                    insert into people (account_id, full_name, first_name, last_name, title, seniority, email, email_status,
                                        linkedin_url, country, timezone, source, crm_id, created_at, is_champion, photo_url,
                                        world_id)
                    values (%s,%s,%s,%s,%s,%s,%s,'unknown',%s,%s,%s,'crm',%s,%s,%s,%s,%s) returning id""",
                    aid, p["full_name"], p["first_name"], p["last_name"], p["title"], p["seniority"], email,
                    p["linkedin_url"], p["country"], p["timezone"], f"CRM-C{p['person_id'][3:]}",
                    max(start - timedelta(days=random.Random("created:" + p["person_id"]).randint(10, 700)),
                        datetime.combine(started, start.timetz())), champion, photo, p["person_id"])
                db.run(cur, """insert into sim_people (person_id, true_email, email_truth, responsiveness, phone_truth,
                                                       role_started, left_at) values (%s,%s,%s,%s,%s,%s,%s)""",
                       pid, email, p["email_truth"], float(p["responsiveness"]), phone, started, left)
                stats["known"] += 1
                stats["people"] += 1
                continue
            # Not on the CRM's books: only a people search finds them. A person no vendor can find is left out unless the
            # news names them (the announcement still needs someone in the seat), or the schema can say they are unfindable.
            if not findable and not has_find and p["person_id"] not in seat_for:
                stats["unfindable_left_out"] += 1
                continue
            cols = ["account_id", "full_name", "first_name", "last_name", "title", "seniority", "linkedin_url", "country",
                    "timezone", "true_email", "email_truth", "responsiveness", "phone_truth", "is_champion", "photo_url",
                    "role_started", "left_at"]
            vals = [aid, p["full_name"], p["first_name"], p["last_name"], p["title"], p["seniority"], p["linkedin_url"],
                    p["country"], p["timezone"], email, p["email_truth"], float(p["responsiveness"]), phone, champion,
                    photo, started, left]
            if has_wid:
                cols.append("world_id")
                vals.append(p["person_id"])
            if has_find:
                cols.append("vendor_findable")
                vals.append(findable)
            hid = db.val(cur, f"insert into sim_hidden_people ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
                              "returning id", *vals)
            hidden_of[p["person_id"]] = hid
            stats["hidden"] += 1
            stats["people"] += 1
        # A planned change of finance leader: the news names the person who starts in the seat.
        for pid_, hid in hidden_of.items():
            sc = seat_for.get(pid_)
            if sc is not None and _ts(sc["at"]) > start:
                db.run(cur, "insert into sim_seat_changes (account_id, at, hidden_person_id, announced) values (%s,%s,%s,%s)",
                       aid, _ts(sc["at"]), hid, sc["announced"] == "true")
                stats["seat_changes"] += 1
        # History lives in the CRM; the desk learns it on its first read, like a real install.
        for dl in deals:
            _deal(cur, aid, c, dl, start)
            stats["deals"] += 1
    for aid, parent in parents:
        if parent in account_of:
            db.run(cur, "update accounts set parent_id = %s where id = %s", account_of[parent], aid)
    db.run(cur, "insert into settings (key, value) values ('world_slice', %s) on conflict (key) do update set value = excluded.value",
           J({"world_version": sl.manifest.get("world_version"), "seed": sl.manifest.get("seed"),
              "manifest_sha256": hashlib.sha256(json.dumps(sl.manifest["sha256"], sort_keys=True).encode()).hexdigest()}))
    stats["world_version"] = sl.manifest.get("world_version")
    stats["hidden_columns"] = {"world_id": has_wid, "vendor_findable": has_find}
    return stats


def _deal(cur, aid: int, c: dict, dl: dict, start: datetime) -> None:
    created = _ts(dl["created_at"])
    outcome = dl["outcome_at_cut"]
    planned_close = _ts(dl["planned_close_at"]) if dl["planned_close_at"] else start + timedelta(days=30)
    name = f"{c['name']} {'expansion' if dl['kind'] == 'expansion' else 'new business'}"
    crm_id = f"CRM-O-{dl['deal_id'][3:]}"
    amount = int(dl["amount_usd_cents"] or dl["amount_cents"])
    if outcome in ("won", "lost"):
        stage = "Closed Won" if outcome == "won" else "Closed Lost"
        db.run(cur, """insert into sim_crm_deals (crm_id, account_id, name, amount_cents, stage, created_at, updated_at,
                                                 closed_at, won, loss_reason, close_on, will_win)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
               crm_id, aid, name, amount, stage, created, planned_close, planned_close, outcome == "won",
               None if outcome == "won" else (dl["loss_code"] or None), planned_close, outcome == "won")
        return
    # Open on the cut: the rehearsal closes it on the day the world planned, the way it planned.
    updated = max(created, start - timedelta(days=int(frac("moved:" + dl["deal_id"]) * 9)))
    db.run(cur, """insert into sim_crm_deals (crm_id, account_id, name, amount_cents, stage, created_at, updated_at,
                                             close_on, will_win)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
           crm_id, aid, name, amount, dl["stage_at_cut"] or "Discovery", created, updated,
           max(planned_close, start + timedelta(days=1)), dl["planned_outcome"] == "won")


# ------------------------------------------------------------------------------------------------ signals

def _evidence(sig: dict, kind: str, acct: dict, at: datetime, person: dict | None, rng: random.Random) -> dict:
    """The proof that goes with a signal: signals_gen's own wording, with the slice's detail where it fits."""
    detail = sig["detail"].strip()
    name, dom = acct["name"], acct["primary_domain"]
    slug = signals_gen._slug(name)
    if kind == "job_change":
        who = person["full_name"] if person else "Someone"
        return {"summary": f"{who} joined {name}.", "url": f"https://social.example.net/in/{sig['signal_id']}",
                "quote": f"Started a new position at {name}"}
    ev = signals_gen.evidence(rng, kind, {**acct, "billing": detail} if kind in ("competitor_review", "tech_removed")
                              and detail else acct, at, person)
    n = ev["url"].rsplit("-", 1)[-1] if "url" in ev else rng.randint(1000, 9999)
    low = detail[:1].lower() + detail[1:] if detail else ""
    if kind == "hiring_function" and detail.startswith("Hiring: "):
        role = detail[len("Hiring: "):]
        ev = {"summary": f"Posted a job for {signals_gen.article(role)} {role}.",
              "url": f"https://jobs.example.net/{slug}/{signals_gen._slug(role)}-{n}",
              "quote": f"You will own monthly invoicing and revenue reconciliation as the {role}."}
    elif kind == "funding":
        m = re.fullmatch(r"(.+?), (\$\d+(?:\.\d+)?)M", detail)
        if m:
            rnd, amt = m.group(1), m.group(2)
            ev = {"summary": f"Raised {signals_gen.article(amt)} {amt}M {rnd} on {signals_gen.day_month(at)}.",
                  "url": ev["url"], "quote": f"{name} raised {amt} million in {rnd} funding."}
    elif kind == "intent_topic" and detail:
        ev = {"summary": f"Research on {detail} above their usual level.", "url": ev["url"], "quote": f"Topic surge: {detail}"}
    elif kind == "tech_added" and detail:
        ev = {"summary": f"Started using {detail}.", "url": f"https://stack.example.net/{dom}/{signals_gen._slug(detail)}",
              "quote": f"Detected: {detail}"}
    elif kind == "pricing_change" and detail:
        ev = {"summary": f"{name} {low}.", "url": ev["url"], "quote": f"Today {name} {low}."}
    elif kind == "social_engaged" and detail:
        who = person["full_name"] if person else "Someone at the company"
        ev = {"summary": f"{who} {low}.", "url": ev["url"], "quote": ev["quote"]}
    elif kind == "event_attended" and detail:
        who = person["full_name"] if person else "Someone at the company"
        ev = {"summary": f"{who} attended {detail}.", "url": ev["url"], "quote": ev["quote"]}
    elif kind == "news_negative" and detail:
        ev = {"summary": f"{name} {low}.", "url": ev["url"], "quote": f"{name}: {low}."}
    return ev


def day_signals(cur, day_start: datetime, root: Path | str | None = None) -> dict[str, list[dict]]:
    """Raw signals per source for one day, from the slice's signal file. A signal at a company the desk does not hold
    (a build of fewer accounts) is skipped. Same raw shape the sources ingest from signals_gen."""
    sl = load_slice(root)
    todays = [s for s in sl.signals_by_day.get(day_start.date().isoformat(), []) if day_start <= _ts(s["at"]) < day_start + timedelta(days=1)]
    if not todays:
        return {}
    wids = sorted({s["company_world_id"] for s in todays})
    accts = {r["world_id"]: r for r in db.all(cur, """select a.world_id, a.name, a.primary_domain, sa.billing
                                                      from accounts a join sim_accounts sa on sa.account_id = a.id
                                                      where a.world_id = any(%s)""", wids)}
    out: dict[str, list[dict]] = {}
    for s in todays:
        acct = accts.get(s["company_world_id"])
        if acct is None:
            continue
        kind = TYPE_MAP.get(s["type"], s["type"])
        source = SOURCE_MAP.get(s["source"], s["source"])
        at = _ts(s["at"])
        rng = random.Random(s["signal_id"])
        who = sl.people.get(s["person_id"]) if s["person_id"] else None
        person = {"full_name": who["full_name"], "title": who["title"]} if who else None
        domain = rng.choice([acct["primary_domain"], "www." + acct["primary_domain"]])
        raw = {"type": kind, "external_id": f"{source}-{kind}-{s['signal_id']}", "observed_at": at, "domain": domain,
               "strength": round(min(1.0, rng.uniform(0.4, 0.9)), 2)}
        if kind == "new_exec":
            raw["strength"] = round(rng.uniform(0.75, 0.95), 2)
        elif kind == "job_change":
            raw["strength"] = 0.9
        raw["evidence"] = _evidence(s, kind, acct, at, person, rng)
        if who is not None and kind in ("new_exec", "job_change", "social_engaged", "event_attended"):
            if kind == "new_exec":
                raw["person"] = {"full_name": who["full_name"], "title": who["title"], "linkedin_url": who["linkedin_url"]}
            else:
                raw["person"] = {"linkedin_url": who["linkedin_url"], "email": who["email"].lower()}
        out.setdefault(source, []).append(raw)
    return out


def sim_event_lag(signal_external_id: str) -> timedelta:
    """How long after a signal happens the source reports it: 20 minutes to 6 hours, fixed by the signal."""
    return timedelta(minutes=random.Random("lag:" + signal_external_id).randint(20, 6 * 60))
