"""The static snapshot (scripts/build_static_snapshot.py): every read the screens make has a saved answer, the crawl
changes nothing, the shim and the build agree on each request's key, each person gets their own answer and every change
gets the public demo's own refusal."""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from outbound import db

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "scripts" / "static_snapshot" / "shim.js"
_spec = importlib.util.spec_from_file_location("build_static_snapshot", ROOT / "scripts" / "build_static_snapshot.py")
snap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snap)
NODE = shutil.which("node")


@pytest.fixture(scope="module")
def crawled(world):
    """The small simulated world, crawled the way the build crawls the demo."""
    from outbound.api import app as appmod
    appmod.rate_limit, saved = (lambda *a, **k: None), appmod.rate_limit
    try:
        with TestClient(appmod.app) as client:
            before = snap.fingerprint(db._url)
            ids = snap.ids_of(db._url)
            k = snap.crawl(client, ids, log=lambda *_: None)
            after = snap.fingerprint(db._url)
            samples = {}
            for kind, path in (("person", "/api/people/{}"), ("message", "/api/messages/{}"),
                               ("task", "/api/tasks/{}")):
                for rid in ids[kind][:3]:
                    samples[path.format(rid)] = [client.get(path.format(rid), headers={"X-Acting-As": str(u["id"])}).json()
                                                 for u in ids["users"]]
    finally:
        appmod.rate_limit = saved
    return k, ids, before, after, samples


def test_every_read_the_screens_make_has_a_saved_response(crawled):
    k, ids, *_ = crawled
    templates = snap.web_read_templates()
    # The parser finds the reads that matter, so an empty or broken parse cannot pass.
    for must in ("/api/me", "/api/today", "/api/accounts/${id}", "/api/people/${id}", "/api/plays/${id}/accounts",
                 "/api/in-flight?mine=${scope === \"mine\"}", "/api/replies?view=${view}", "/api/settings", "/api/ops"):
        assert any(t == must or t.startswith(must.split("${")[0]) for t in templates), must
    assert snap.uncovered(k, templates, ids) == []
    assert all(not ({500, 429} & set(e["status"])) for e in k.manifest)
    assert ids["account"] and ids["person"] and ids["message"]


def test_the_crawl_changes_nothing(crawled):
    k, _, before, after, _ = crawled
    assert before == after
    assert k.sent and all(snap.is_read(m, p) for m, p in k.sent)
    assert {m for m, _ in k.sent} <= {"GET", "POST"}


def test_a_record_that_reads_the_same_for_everyone_does(crawled):
    """The build saves a person, a message, a reply and a task once, for everyone: that is only right when it is true."""
    _, _, _, _, samples = crawled
    assert samples
    for path, answers in samples.items():
        assert all(a == answers[0] for a in answers), path


def test_a_rep_gets_no_money_and_a_manager_does(crawled):
    k, ids, *_ = crawled
    results = k.saved[snap.request_hash("GET", "/api/results")]
    assert set(results) == {"r:sdr", "r:mgr"}
    assert "spend" not in results["r:sdr"][1] and "spend" in results["r:mgr"][1]
    ops = k.saved[snap.request_hash("GET", "/api/ops")]
    assert ops["r:sdr"][0] == 403 and ops["r:mgr"][0] == 200
    me = k.saved[snap.request_hash("GET", "/api/me")]
    assert {f"u:{u['id']}" for u in ids["users"]} == set(me)


def _node(js: str):
    return json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout)


def test_the_shim_and_the_build_agree_on_each_key():
    if not NODE:
        pytest.skip("node is not installed")
    cases = [
        ["GET", "/api/me", None],
        ["GET", "/api/accounts?view=all&owner=3&page=2", None],
        ["GET", "/api/accounts?page=2&owner=3&view=all", None],
        ["GET", "/api/in-flight?mine=true", None],
        ["GET", "/api/replies?view=needs_person", None],
        ["POST", "/api/messages/12/check", {"subject": "Hi, Ana", "body": "Line\n\nBye é", "z": [{"b": 1, "a": None}]}],
        ["POST", "/api/play-preview", {"name": "x", "sequence": [{"channel": "email", "day": 0}], "urgent": False}],
    ]
    js = (f"globalThis.window = globalThis; globalThis.location = {{ href: 'https://snap.example/', origin: 'https://snap.example' }};"
          f"{SHIM.read_text()};"
          f"const cases = {json.dumps(cases)};"
          "console.log(JSON.stringify(cases.map(([m, p, b]) => window.__snapshotKey(m, new URL(p, location.href), b))));")
    out = _node(js)
    assert out == [snap.request_key(m, p, b) for m, p, b in cases]
    assert out[1] == out[2]  # query order does not matter


def test_the_shim_answers_each_person_from_the_saved_answers(crawled, tmp_path):
    if not NODE:
        pytest.skip("node is not installed")
    k, ids, *_ = crawled
    out = tmp_path / "bundle"
    out.mkdir()
    snap.write_bundle(out, k, ids, "17 November 2026")
    users = ids["users"]
    mgr = next(u["id"] for u in users if u["role"] == "manager")
    sdr = ids["default"]
    one = ids["account"][0]
    js = f"""
globalThis.window = globalThis; globalThis.location = {{ href: 'https://snap.example/', origin: 'https://snap.example' }};
const fs = require('fs');
window.fetch = async (u) => {{ const p = new URL(u, location.href).pathname; const f = {json.dumps(str(out))} + p;
  return fs.existsSync(f) ? new Response(fs.readFileSync(f)) : new Response('', {{ status: 404 }}); }};
{SHIM.read_text()};
(async () => {{
  const get = async (p, as, o = {{}}) => {{ const r = await window.fetch(p, {{ headers: as ? {{ 'X-Acting-As': String(as) }} : {{}}, ...o }}); return [r.status, await r.json()]; }};
  const res = {{}};
  res.defaultMe = (await get('/api/me'))[1].user.id;
  res.mgrMe = (await get('/api/me', {mgr}))[1].user.id;
  res.snapshotNote = (await get('/api/me'))[1].snapshot.taken_on;
  res.sdrOps = (await get('/api/ops'))[0];
  res.mgrOps = (await get('/api/ops', {mgr}))[0];
  res.account = (await get('/api/accounts/{one}'))[1].account.id;
  res.write = await get('/api/messages/1/approve', 0, {{ method: 'POST', body: '{{}}' }});
  res.missing = await get('/api/accounts/999999999');
  const all = (await get('/api/accounts?view=all'))[1];
  const name = all.accounts[0].name;
  const found = (await get('/api/accounts?view=all&q=' + encodeURIComponent(name.toLowerCase().slice(0, 6))))[1];
  res.searchFinds = found.accounts.some((a) => a.id === all.accounts[0].id);
  res.searchTotal = found.total === found.accounts[0].total_n;
  console.log(JSON.stringify(res));
}})();
"""
    res = _node(js)
    assert res["defaultMe"] == sdr and res["mgrMe"] == mgr
    assert res["snapshotNote"] == "17 November 2026"
    assert (res["sdrOps"], res["mgrOps"]) == (403, 200)
    assert res["account"] == one
    assert res["write"] == [403, {"detail": "Not available in the public demo."}]
    assert res["missing"][0] == 404 and "not in the snapshot" in res["missing"][1]["detail"]
    assert res["searchFinds"] and res["searchTotal"]


def test_every_change_gets_the_public_demos_own_refusal():
    shim = SHIM.read_text()
    from outbound.api import app as appmod
    said = re.search(r'var REFUSED = "([^"]+)"', shim).group(1)
    assert said == appmod.PUBLIC_DEMO_MESSAGE
    if NODE:
        js = ("globalThis.window = globalThis; globalThis.location = { href: 'https://snap.example/', origin: 'https://snap.example' };"
              f"{shim};"
              "(async () => { const out = []; for (const [m, p] of [['POST', '/api/messages/1/approve'], ['POST', '/api/kill-switch'],"
              " ['DELETE', '/api/suppressions/1'], ['PUT', '/api/icp'], ['POST', '/api/sim/advance'], ['POST', '/api/replies/1/send']]) {"
              " const r = await window.fetch(p, { method: m, body: '{}' }); out.push([r.status, (await r.json()).detail]); }"
              " console.log(JSON.stringify(out)); })();")
        assert _node(js) == [[403, said]] * 6
    # The shim and the build agree on which POSTs only read.
    js = re.findall(r"/\^(.*?)\$/", re.search(r"var READ_POSTS = \[(.*?)\];", shim).group(1))
    assert [j.replace("\\/", "/").replace("\\d", "\\d") for j in js] == [r.pattern.strip("^$") for r in snap.READ_POSTS]
    assert not snap.is_read("POST", "/api/messages/1/approve") and not snap.is_read("POST", "/api/replies/1/check")
    assert snap.is_read("POST", "/api/messages/1/check") and snap.is_read("POST", "/api/play-preview")


def test_the_bundle_is_noindex(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><html><head><title>x</title></head><body></body></html>")
    snap.finish_web(tmp_path)
    html = (tmp_path / "index.html").read_text()
    assert '<meta name="robots" content="noindex,nofollow" />' in html
    assert html.index("snapshot-shim.js") < html.index("</head>")
    assert "X-Robots-Tag: noindex" in (tmp_path / "_headers").read_text()
    assert "Disallow: /" in (tmp_path / "robots.txt").read_text()
    assert (tmp_path / "snapshot-shim.js").read_text() == SHIM.read_text()


def test_the_build_refuses_a_simulation_database(monkeypatch, tmp_path):
    for url in ("postgres://postgres@127.0.0.1:5432/sim_account", "postgres://u:p@ep-x.neon.tech/neondb"):
        monkeypatch.setenv("DATABASE_URL", url)
        with pytest.raises(SystemExit, match="simulation database"):
            snap.main(["--out", str(tmp_path / "out"), "--skip-web-build"])
