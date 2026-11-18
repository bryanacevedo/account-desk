"""Builds the public demo as a static snapshot: the web app plus every response it needs, saved as files.

It runs the API in this process against the built demo database, with PUBLIC_DEMO=1, and reads it the way the screens do,
as each person the demo can act as. It writes:

  <out>/                          the built web app, with the snapshot's fetch shim, noindex and the demo note
  <out>/_snapshot/abc.json.gz     saved responses, sharded by the first 3 hex digits of a key's SHA-1
  <out>/_snapshot/accounts.json.gz  every account row, for the Accounts page's search
  <out>/_snapshot/config.json.gz  who the demo can act as (the shim needs each person's role) and the default
  <out>/_headers, robots.txt      noindex everywhere
  <out>/snapshot-manifest.json    every saved request, for the tests and the runbook

A key is the request as the shim sees it: method, path, sorted query pairs and the body with sorted keys. Under a key an
answer is saved for everyone ("*"), for a kind of person ("r:sdr", "r:mgr": money and the manager pages differ) or for one
person ("u:<id>": Today, In flight, mine). An answer is saved once when everyone gets the same one. The crawl sends only
GETs and two reads that take a body (the check on an email's text, a play's preview), and the database's fingerprint is
compared before and after, so the build stops if the crawl changed anything.

    python scripts/build_static_snapshot.py --out .snapshot      # DATABASE_URL names the demo database
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SHIM = Path(__file__).resolve().parent / "static_snapshot" / "shim.js"
READ_POSTS = (re.compile(r"^/api/messages/\d+/check$"), re.compile(r"^/api/play-preview$"))
MAX_FILES = 19_000              # Cloudflare Pages takes 20,000 files a deployment on the free plan
ACCOUNT_VIEWS = ("priority", "in_play", "rising", "all")
REPLY_VIEWS = ("mine", "all", "hot", "needs_person")
PLAY_FIELDS = ("name", "hypothesis", "angle", "personas", "max_people", "holdout_pct", "urgent", "latency_hours",
               "sequence", "trigger")      # sheets.tsx DraftPreview: the body it sends, key for key


# ---------------------------------------------------------------- the key, the same as shim.js keyOf

def _canon(v):
    if isinstance(v, list):
        return [_canon(x) for x in v]
    if isinstance(v, dict):
        return {k: _canon(v[k]) for k in sorted(v)}
    return v


def request_key(method: str, path: str, body=None) -> str:
    parts = urlsplit(path)
    pairs = sorted([list(p) for p in parse_qsl(parts.query, keep_blank_values=True)])
    return json.dumps([method.upper(), parts.path, pairs, None if body is None else _canon(body)],
                      separators=(",", ":"), ensure_ascii=False)


def request_hash(method: str, path: str, body=None) -> str:
    return hashlib.sha1(request_key(method, path, body).encode()).hexdigest()


def is_read(method: str, path: str) -> bool:
    return method == "GET" or (method == "POST" and any(r.match(urlsplit(path).path) for r in READ_POSTS))


# ---------------------------------------------------------------- what the screens ask for, read from web/src

LITERAL = re.compile(r"`([^`]*)`|\"([^\"]*)\"")


def web_read_templates(src: Path = WEB / "src") -> list[str]:
    """Every path the screens read, as written in the code: the first path in each useData call, and each api call with
    no options (a GET). The tests check each one has a saved answer; writes are not listed: the shim refuses them."""
    found: set[str] = set()
    for f in sorted(src.rglob("*.tsx")) + sorted(src.rglob("*.ts")):
        text = f.read_text()
        for m in re.finditer(r"\buseData(?:<[^>]*>)?\(", text):
            for lit in LITERAL.finditer(text, m.end(), m.end() + 300):
                s = lit.group(1) if lit.group(1) is not None else lit.group(2)
                if s.startswith("/"):
                    found.add(s)
                    break
        for m in re.finditer(r"\bapi(?:<[^>]*>)?\(\s*(?:`([^`]*)`|\"([^\"]*)\")\s*\)", text):
            found.add(m.group(1) if m.group(1) is not None else m.group(2))
    return sorted(t for t in found if t.startswith("/api/"))


def template_pattern(t: str) -> re.Pattern:
    """A template's path part as a pattern: each ${...} matches part of one path segment."""
    parts = re.split(r"\$\{(?:[^{}]|\{[^{}]*\})*\}", t)
    marked = "\0".join(parts).split("?", 1)[0]
    return re.compile("^" + "[^/?]*".join(re.escape(p) for p in marked.split("\0")) + "$")


# ---------------------------------------------------------------- the database

def connect(url: str):
    import psycopg
    return psycopg.connect(url, autocommit=True)


def fingerprint(url: str) -> dict:
    with connect(url) as c:
        tables = [r[0] for r in c.execute("select tablename from pg_tables where schemaname = 'public' order by 1")]
        out = {}
        for t in tables:
            n, x = c.execute(f'select count(*), coalesce(max(xmin::text::bigint), 0) from "{t}"').fetchone()
            out[t] = [n, x]
        return out


def ids_of(url: str) -> dict:
    """Every id a screen can open, straight from the database (read only)."""
    q = {"account": "accounts", "person": "people", "message": "messages", "reply": "replies", "task": "tasks",
         "meeting": "meetings", "play": "plays", "suggestion": "play_suggestions"}
    with connect(url) as c:
        out = {k: [r[0] for r in c.execute(f"select id from {t} order by id")] for k, t in q.items()}
        out["owners"] = {r[0]: r[1] for r in c.execute("select id, owner_id from accounts")}
        out["users"] = [{"id": r[0], "role": r[1], "name": r[2]} for r in
                        c.execute("select id, role, name from users where active order by role desc, name")]
        out["default"] = c.execute("select id from users where role = 'sdr' and active order by id limit 1").fetchone()[0]
    return out


# ---------------------------------------------------------------- the crawl

class Crawl:
    """Reads as a person and keeps what comes back. `save` stores one answer per request, with who it is for."""

    def __init__(self, client, who: dict, log=print):
        self.c = client
        self.who = who                     # {"sdr": id, "mgr": id, "all": [ids], "role": {id: role}}
        self.saved: dict[str, dict] = {}
        self.manifest: list[dict] = []
        self.sent: list[tuple[str, str]] = []
        self.log = log

    def _ask(self, method: str, path: str, body, uid: int):
        self.sent.append((method, path))
        headers = {"X-Acting-As": str(uid)}
        if method == "POST":
            headers.update({"Content-Type": "application/json"})
            r = self.c.post(path, headers=headers, json=body)
        else:
            r = self.c.get(path, headers=headers)
        if r.status_code >= 500 or r.status_code == 429:
            raise SystemExit(f"{method} {path} as {uid} answered {r.status_code}: {r.text[:200]}")
        return [r.status_code, r.json() if r.content else None]

    def read(self, path: str, readers: str = "class", body=None, method: str = "GET"):
        """readers: "one" (the manager answers for everyone), "class" (an SDR and the manager: money and the manager pages
        differ) or "each" (every person: Today, In flight, mine). Returns the manager's answer, or None if it was not 200."""
        if readers == "one":
            asked = {"*": self._ask(method, path, body, self.who["mgr"])}
        elif readers == "class":
            asked = {"r:sdr": self._ask(method, path, body, self.who["sdr"]), "r:mgr": self._ask(method, path, body, self.who["mgr"])}
        else:
            asked = {f"u:{u}": self._ask(method, path, body, u) for u in self.who["all"]}
        vals = list(asked.values())
        stored = {"*": vals[0]} if all(v == vals[0] for v in vals) else asked
        h = request_hash(method, path, body)
        if h not in self.saved:
            self.saved[h] = stored
            self.manifest.append({"method": method, "path": path, "body": body, "hash": h,
                                  "status": sorted({v[0] for v in vals}), "scopes": sorted(stored)})
        mgr = asked.get("*") or asked.get("r:mgr") or asked.get(f"u:{self.who['mgr']}")
        return mgr[1] if mgr and mgr[0] == 200 else None

    def get(self, path: str, readers: str = "class"):
        return self.read(path, readers)


def crawl(client, db: dict, *, log=print) -> Crawl:
    """Reads everything a visitor can reach, as everyone the demo can act as."""
    roles = {u["id"]: u["role"] for u in db["users"]}
    mgr = next(u["id"] for u in db["users"] if u["role"] == "manager")
    k = Crawl(client, {"sdr": db["default"], "mgr": mgr, "all": [u["id"] for u in db["users"]], "role": roles}, log)

    # Who is acting, and each person's own pages.
    k.get("/api/me", "each")
    k.get("/api/today", "each")
    for mine in ("true", "false"):
        k.get(f"/api/in-flight?mine={mine}", "each")
    for view in REPLY_VIEWS:
        k.get(f"/api/replies?view={view}", "each")

    # Pages that do not change with the person, or only by role (money; the manager's pages answer an SDR with 403).
    for p in ("/api/signals", "/api/plays", "/api/results", "/api/deliverability", "/api/vendors", "/api/ops",
              "/api/settings", "/api/admin", "/api/play-suggestions", "/api/do-not-contact", "/api/product-facts"):
        k.get(p)
    k.get("/api/my-mailbox", "each")  # an SDR's own mailboxes: one answer per person

    # Accounts: every page of each view, and each person's own.
    for view in ACCOUNT_VIEWS:
        _pages(k, f"/api/accounts?view={view}")
    for u in db["users"]:
        _pages(k, f"/api/accounts?view=all&owner={u['id']}")

    # Every record a screen can open. A person, a message, a reply, a task and a play suggestion read the same for
    # everyone; an account, a meeting and a play's origin carry money or are for managers only.
    spec = (("account", "/api/accounts/{}", "class"), ("person", "/api/people/{}", "one"), ("message", "/api/messages/{}", "one"),
            ("reply", "/api/replies/{}", "each"), ("task", "/api/tasks/{}", "one"), ("meeting", "/api/meetings/{}", "class"),
            ("suggestion", "/api/play-suggestions/{}", "class"))
    messages: dict[int, dict] = {}
    for kind, tmpl, readers in spec:
        n = 0
        for rid in db[kind]:
            data = k.get(tmpl.format(rid), readers)
            if kind == "message" and data:
                messages[rid] = data
            n += 1
            if n % 2000 == 0:
                log(f"  {kind}: {n} of {len(db[kind])}")
        log(f"  {kind}: {len(db[kind])}")
    plays = k.get("/api/plays") or {}
    for pid in db["play"]:
        k.get(f"/api/plays/{pid}/accounts", "one")
        k.get(f"/api/plays/{pid}/origin")
    # Reads that take a body: the check on an email's text as it opens, and a play's preview as its sheet opens.
    for mid, m in messages.items():
        if m.get("status") in ("awaiting_approval", "failed_gate"):
            k.read(f"/api/messages/{mid}/check", "one", {"subject": m.get("subject") or "", "body": m.get("body") or ""}, "POST")
    for p in plays.get("plays", []):
        k.read("/api/play-preview", "class", {f: p[f] for f in PLAY_FIELDS if f in p}, "POST")
    return k


def _pages(k: Crawl, base: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        d = k.get(f"{base}&page={page}", "one")
        rows += (d or {}).get("accounts", [])
        if not d or page * d["per_page"] >= d["total"]:
            return rows
        page += 1


# ---------------------------------------------------------------- the bundle

def write_bundle(out: Path, k: Crawl, db: dict, taken_on: str) -> dict:
    snap = out / "_snapshot"
    snap.mkdir(parents=True, exist_ok=True)
    # The snapshot is a snapshot: the shell says so, and it calls no other desk.
    me = k.saved[request_hash("GET", "/api/me")]
    for entry in me.values():
        if entry[0] == 200:
            entry[1]["snapshot"] = {"taken_on": taken_on}
            entry[1].setdefault("integration", {})["links"] = {}
    shards: dict[str, dict] = {}
    for h, v in k.saved.items():
        shards.setdefault(h[:3], {})[h] = v
    raw = 0
    for name, items in shards.items():
        data = json.dumps(items, separators=(",", ":"), ensure_ascii=False).encode()
        raw += len(data)
        (snap / f"{name}.json.gz").write_bytes(gzip.compress(data, 9, mtime=0))
    # The Accounts page's search: every account row in the server's own order, with who owns it.
    rows = []
    page = 1
    while True:
        d = k.saved[request_hash("GET", f"/api/accounts?view=all&page={page}")]["*"][1]
        rows += d["accounts"]
        if page * d["per_page"] >= d["total"]:
            break
        page += 1
    index = {"rows": [{kk: v for kk, v in r.items() if kk != "total_n"} for r in rows], "owner": [db["owners"].get(r["id"]) for r in rows]}
    (snap / "accounts.json.gz").write_bytes(gzip.compress(json.dumps(index, separators=(",", ":"), ensure_ascii=False).encode(), 9, mtime=0))
    config = {"default": str(db["default"]), "roles": {str(u["id"]): u["role"] for u in db["users"]}}
    (snap / "config.json.gz").write_bytes(gzip.compress(json.dumps(config, separators=(",", ":")).encode(), 9, mtime=0))
    (out / "snapshot-manifest.json").write_text(json.dumps({"taken_on": taken_on, "requests": k.manifest}, separators=(",", ":")))
    return {"responses": len(k.saved), "shards": len(shards), "raw_bytes": raw}


CSP = ("default-src 'self'; img-src 'self' data: https://randomuser.me https://media.licdn.com; style-src 'self' 'unsafe-inline'; "
       "font-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def finish_web(out: Path) -> None:
    """The built app gets the shim before its own script, noindex, and the headers file."""
    html = (out / "index.html").read_text()
    html = html.replace("<head>", '<head>\n    <meta name="robots" content="noindex,nofollow" />\n    <script src="/snapshot-shim.js"></script>', 1)
    (out / "index.html").write_text(html)
    shutil.copyfile(SHIM, out / "snapshot-shim.js")
    (out / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n  X-Content-Type-Options: nosniff\n  X-Frame-Options: DENY\n"
                                  f"  Referrer-Policy: same-origin\n  Content-Security-Policy: {CSP}\n"
                                  "\n/_snapshot/*\n  Cache-Control: public, max-age=0, must-revalidate\n")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n")


def dir_size(p: Path) -> tuple[int, int]:
    files = [f for f in p.rglob("*") if f.is_file()]
    return len(files), sum(f.stat().st_size for f in files)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / ".snapshot"))
    ap.add_argument("--skip-web-build", action="store_true", help="use web/dist as it is")
    ap.add_argument("--max-mb", type=float, default=60.0, help="fail when the bundle is larger")
    a = ap.parse_args(argv)
    url = os.environ.get("DATABASE_URL", "postgres://postgres@127.0.0.1:54329/outbound")
    if re.search(r"/(sim_[^/?]*|neondb)(\?.*)?$", url) or "neon.tech" in url:
        raise SystemExit("Refusing a simulation database: the snapshot reads a demo database of its own.")
    # Read as the public demo does; the in-process rate limits are for visitors, not for this one reader.
    os.environ.update(PUBLIC_DEMO="1", NO_WORKER="1", MODE="demo", AUTH_MODE="demo")
    os.environ.pop("LIVE_SEND", None)
    sys.path.insert(0, str(ROOT / "src"))
    out = Path(a.out).resolve()
    t0 = time.time()
    if not a.skip_web_build:
        subprocess.run(["npm", "run", "build"], cwd=WEB, check=True)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB / "dist", out)

    import logging
    logging.disable(logging.INFO)
    from fastapi.testclient import TestClient

    from outbound import db as outdb
    from outbound.api import app as appmod
    appmod.rate_limit = lambda *args, **kw: None
    with TestClient(appmod.app) as client:
        before = fingerprint(url)
        db = ids_of(url)
        k = crawl(client, db)
        after = fingerprint(url)
    outdb.close()
    if before != after:
        changed = [t for t in before if before[t] != after.get(t)]
        raise SystemExit(f"The crawl changed the database ({', '.join(changed)}). Nothing is published.")
    writes = [s for s in k.sent if not is_read(*s)]
    if writes:
        raise SystemExit(f"The crawl sent a change: {writes[:3]}")
    taken_on = dt.date.today().strftime("%-d %B %Y")
    stats = write_bundle(out, k, db, taken_on)
    finish_web(out)
    files, size = dir_size(out)
    missing = uncovered(k, ids=db)
    report = {**stats, "files": files, "bytes": size, "seconds": round(time.time() - t0), "uncovered": missing}
    print(json.dumps(report, indent=1))
    if missing:
        raise SystemExit(f"Screens read paths the snapshot did not save: {missing}")
    if size > a.max_mb * 1_000_000:
        raise SystemExit(f"The bundle is {size / 1e6:.1f} MB, over {a.max_mb} MB.")
    if files > MAX_FILES:
        raise SystemExit(f"The bundle has {files} files, over {MAX_FILES}.")
    return 0


def uncovered(k: Crawl, templates: list[str] | None = None, ids: dict | None = None) -> list[str]:
    """Paths the screens read that have no saved answer. A path for a kind of record the database has none of (play
    suggestions come from call notes, and a small world has none) has nothing to open, so it is not asked for."""
    none = ["/api/play-suggestions/"] if ids is not None and not ids["suggestion"] else []
    paths = [urlsplit(e["path"]).path for e in k.manifest if e["method"] == "GET" and set(e["status"]) & {200, 403}]
    out = []
    for t in templates if templates is not None else web_read_templates():
        pat = template_pattern(t)
        if any(t.startswith(n) for n in none):
            continue
        if not any(pat.match(p) for p in paths):
            out.append(t)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
