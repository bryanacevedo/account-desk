// The static snapshot's stand-in for the server (scripts/build_static_snapshot.py). Loaded before the app, it answers
// every call the app makes to /api from the saved responses in /_snapshot, and refuses every change with the public
// demo's own sentence. Nothing here talks to a server: the snapshot has none.
(function () {
  "use strict";
  var REFUSED = "Not available in the public demo.";
  var MISSING = {
    accounts: "That search is not in the snapshot. Run the demo yourself to try it.",
    check: "This check is not in the snapshot.",
    other: "This view is not in the snapshot. Run the demo yourself to see it.",
  };
  // Calls that read with a POST body, as the app does. Anything else that is not a GET is a change.
  var READ_POSTS = [/^\/api\/messages\/\d+\/check$/, /^\/api\/play-preview$/];
  var PER = 100;                       // the accounts list's page size (src/outbound/api/app.py)
  var realFetch = window.fetch.bind(window);
  var shards = {};
  var index = null;
  var config = null;

  function canon(v) {
    if (Array.isArray(v)) return v.map(canon);
    if (v && typeof v === "object") {
      var o = {};
      Object.keys(v).sort().forEach(function (k) { o[k] = canon(v[k]); });
      return o;
    }
    return v;
  }

  function keyOf(method, url, body) {
    var pairs = [];
    url.searchParams.forEach(function (v, k) { pairs.push([k, v]); });
    pairs.sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0; });
    return JSON.stringify([method, url.pathname, pairs, body === undefined ? null : canon(body)]);
  }

  async function sha1(text) {
    var buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
  }

  async function gunzipJson(path) {
    var res = await realFetch(path);
    if (!res.ok) return null;
    var bytes = new Uint8Array(await res.arrayBuffer());
    // A host may already have undone the gzip in transit; only gzip bytes go through the decompressor.
    if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
      var stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
      return JSON.parse(await new Response(stream).text());
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  function shard(name) {
    if (!shards[name]) shards[name] = gunzipJson("/_snapshot/" + name + ".json.gz").catch(function () { return null; });
    return shards[name];
  }

  function reply(status, body) {
    return new Response(JSON.stringify(body), { status: status, headers: { "Content-Type": "application/json" } });
  }
  function fail(status, text) { return reply(status, { detail: text }); }

  // Who is acting: what the app sends in X-Acting-As, else the server's default (the first SDR).
  async function actor(init) {
    if (!config) config = gunzipJson("/_snapshot/config.json.gz");
    var cfg = (await config) || { default: 0, roles: {} };
    var raw = null;
    if (init && init.headers) {
      var h = init.headers;
      raw = h instanceof Headers ? h.get("X-Acting-As") : (h["X-Acting-As"] || h["x-acting-as"] || null);
    }
    var id = raw && cfg.roles[raw] ? String(raw) : String(cfg.default);
    return { id: id, cls: cfg.roles[id] === "sdr" ? "sdr" : "mgr" };
  }

  // A saved entry holds the answer for everyone ("*"), for a kind of person ("r:sdr", "r:mgr") or for one person ("u:<id>").
  function pick(entry, who) {
    return entry["u:" + who.id] || entry["r:" + who.cls] || entry["*"] || null;
  }

  // The accounts list's search, answered from every account the snapshot saved, in the server's own order.
  async function searchAccounts(url) {
    var q = (url.searchParams.get("q") || "").trim().slice(0, 80).toLowerCase();
    var view = url.searchParams.get("view") || "priority";
    var owner = url.searchParams.get("owner");
    var page = Math.max(1, Number(url.searchParams.get("page") || 1));
    if (!index) index = gunzipJson("/_snapshot/accounts.json.gz");
    var ix = await index;
    if (!ix || ["priority", "in_play", "rising", "all"].indexOf(view) === -1) return fail(404, MISSING.accounts);
    var rows = [];
    for (var i = 0; i < ix.rows.length; i++) {
      var r = ix.rows[i];
      if (view !== "all" && r.fit_tier !== "A" && r.fit_tier !== "B") continue;
      if (view === "in_play" && !r.play_state) continue;
      if (view === "rising" && !(r.week_change > 0)) continue;
      if (owner && String(ix.owner[i]) !== owner) continue;
      if (q && String(r.name || "").toLowerCase().indexOf(q) === -1 && String(r.primary_domain || "").toLowerCase().indexOf(q) === -1) continue;
      rows.push(r);
    }
    if (view === "rising") rows = rows.map(function (r, n) { return [r, n]; })
      .sort(function (a, b) { return (b[0].week_change - a[0].week_change) || (a[1] - b[1]); }).map(function (x) { return x[0]; });
    var out = rows.slice((page - 1) * PER, page * PER).map(function (r) { return Object.assign({}, r, { total_n: rows.length }); });
    return reply(200, { accounts: out, total: rows.length, page: page, per_page: PER });
  }

  // For tests/test_static_snapshot.py: the key the shim looks up, compared with the build's.
  window.__snapshotKey = keyOf;

  window.fetch = async function (input, init) {
    var url = new URL(typeof input === "string" || input instanceof URL ? String(input) : input.url, location.href);
    if (url.origin !== location.origin || !/^\/api\//.test(url.pathname)) return realFetch(input, init);
    var method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
    var path = url.pathname;
    var isRead = method === "GET" || (method === "POST" && READ_POSTS.some(function (re) { return re.test(path); }));
    if (!isRead) return fail(403, REFUSED);
    var body = null;
    if (method !== "GET" && init && typeof init.body === "string" && init.body) {
      try { body = JSON.parse(init.body); } catch (e) { body = null; }
    }
    var hash = await sha1(keyOf(method, url, body));
    var saved = await shard(hash.slice(0, 3));
    var entry = saved && saved[hash];
    var hit = entry && pick(entry, await actor(init));
    if (hit) return reply(hit[0], hit[1]);
    if (path === "/api/accounts") return searchAccounts(url);
    if (/^\/api\/messages\/\d+\/check$/.test(path)) return fail(404, MISSING.check);
    return fail(404, MISSING.other);
  };
})();
