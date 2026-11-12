"""Live adapters, chosen by which env keys are present. Filled in vendor by vendor; until a vendor's key is set,
its simulated adapter stays in place and /api/health says so."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from . import Adapters, DnsResult, DomainTelemetry, VendorMissing

DOH = "https://cloudflare-dns.com/dns-query"


def _txt(name: str) -> list[str]:
    """TXT records over DNS-over-HTTPS: no resolver library, and the same answer from anywhere."""
    req = urllib.request.Request(f"{DOH}?{urllib.parse.urlencode({'name': name, 'type': 'TXT'})}",
                                 headers={"accept": "application/dns-json"})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed https host
        data = json.load(r)
    return ["".join(part.strip('"') for part in a["data"].split('" "')) for a in data.get("Answer", []) if a.get("type") == 16]


class DohDns:
    """SPF, DKIM and DMARC read from public DNS. Blocklists are not checked here: the main lists refuse queries
    that come through public resolvers, so that needs a vendor key, and the result says 'not checked'."""
    def check(self, cur, domain: str, dkim_selector: str | None) -> DnsResult:
        spf = [t for t in _txt(domain) if t.lower().startswith("v=spf1")]
        dmarc = [t for t in _txt(f"_dmarc.{domain}") if t.lower().startswith("v=dmarc1")]
        dkim = [t for t in _txt(f"{dkim_selector}._domainkey.{domain}") if "p=" in t] if dkim_selector else []
        tags = dict(kv.strip().split("=", 1) for kv in dmarc[0].split(";") if "=" in kv) if dmarc else {}
        policy = tags.get("p", "").strip().lower() or None
        # Alignment as far as DNS can show it: the domain publishes its own DKIM key under the selector the mail
        # provider signs with, so mail signed with it aligns with the From domain. Whether the provider really signs
        # with that key is only visible in a sent message's headers (a seed test checks that).
        aligned = bool(dkim)
        return DnsResult(domain, len(spf) == 1, bool(dkim), bool(dmarc),
                         policy if policy in ("none", "quarantine", "reject") else None, aligned and bool(dmarc), None,
                         {"spf": spf, "dmarc": dmarc, "dkim_selector": dkim_selector, "dkim_found": bool(dkim),
                          "spf_records": len(spf)})


POSTMASTER = "https://gmailpostmastertools.googleapis.com/v2"
POSTMASTER_TOKEN_URL = "https://oauth2.googleapis.com/token"
POSTMASTER_SCOPE = "https://www.googleapis.com/auth/postmaster.traffic.readonly"


def postmaster_stats_body(today: date, days: int = 7) -> dict:
    """The domainStats:query request for the spam rate over the last few days, one entry per day. All Postmaster
    request field names live here and in postmaster_telemetry below (names read from Google's v2 reference on
    2026-11-12; the shape of timeQuery.dateRanges is the least certain, so check it first against a real response)."""
    def d(x: date) -> dict:
        return {"year": x.year, "month": x.month, "day": x.day}
    return {"metricDefinitions": [{"name": "spam_rate", "baseMetric": {"standardMetric": "SPAM_RATE"}}],
            "timeQuery": {"dateRanges": {"dateRanges": [{"start": d(today - timedelta(days=days)), "end": d(today)}]}},
            "aggregationGranularity": "DAILY", "pageSize": days + 1}


def postmaster_telemetry(domain: str, compliance: dict | None, stats: dict | None) -> DomainTelemetry:
    """Map Google's answers to the desk's telemetry. `compliance` is the domains/{d}/complianceStatus response and
    `stats` the domainStats:query response; either is None when Google has nothing for the domain. A missing value
    stays None ("no data yet"), never zero, because a low-volume domain with no data is not a clean one."""
    spam, as_of = None, None
    for s in (stats or {}).get("domainStats", []):
        v = s.get("value", {})
        val = v.get("doubleValue", v.get("floatValue"))
        dt = s.get("date") or {}
        day = date(dt["year"], dt["month"], dt["day"]) if dt.get("year") else None
        if val is not None and (as_of is None or (day is not None and day > as_of)):
            spam, as_of = float(val), day
    verdict = None
    data = (compliance or {}).get("complianceData") or {}
    v = data.get("deliverabilityStatusVerdict") or {}
    state = (v.get("state") or {}).get("status")
    if v.get("reason") != "MESSAGE_VOLUME_LOW" and state in ("COMPLIANT", "NEEDS_WORK"):
        verdict = state.lower()
    elif not v:  # no overall verdict: fall back to the per-requirement rows
        rows = [(r.get("status") or {}).get("status") for r in data.get("rowData", [])]
        if "NEEDS_WORK" in rows:
            verdict = "needs_work"
        elif rows and all(r == "COMPLIANT" for r in rows):
            verdict = "compliant"
    return DomainTelemetry(domain, spam, verdict, as_of)


def _google_http(method: str, url: str, token: str | None, body: dict | None = None, form: dict | None = None) -> dict:
    data = urllib.parse.urlencode(form).encode() if form else (json.dumps(body).encode() if body is not None else None)
    headers = {"content-type": "application/x-www-form-urlencoded" if form else "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed https hosts
        return json.load(r)


class PostmasterTelemetry:
    """Sending-domain reputation from Google Postmaster Tools (API v2): the latest spam rate and the compliance
    verdict. A domain Google has no data for, or one not verified in Postmaster Tools, is 'no data yet'.
    Seed-test placement needs another vendor, so it stays unknown here."""
    name = "google:postmaster"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, http=_google_http, today=date.today):
        self.creds = {"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token,
                      "grant_type": "refresh_token"}
        self.http, self.today = http, today

    def _get(self, token: str, method: str, url: str, body: dict | None = None) -> dict | None:
        try:
            return self.http(method, url, token, body)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):  # not registered or verified in Postmaster Tools, or no data
                return None
            raise

    def domains(self, cur, domains: list[str]) -> list[DomainTelemetry]:
        token = self.http("POST", POSTMASTER_TOKEN_URL, None, None, self.creds)["access_token"]
        body = postmaster_stats_body(self.today())
        out = []
        for d in domains:
            comp = self._get(token, "GET", f"{POSTMASTER}/domains/{d}/complianceStatus")
            stats = self._get(token, "POST", f"{POSTMASTER}/domains/{d}/domainStats:query", body)
            out.append(postmaster_telemetry(d, comp, stats))
        return out

    def placement(self, *_a, **_k) -> list:
        return []


class Missing:
    """Stands in for every vendor without a key in live mode. It never invents a result: paid lookups and sends
    raise VendorMissing (the job waits and the team is told), and reads return 'unknown' or nothing."""
    def __init__(self, vendor: str):
        self.vendor = vendor
        self.name = f"missing:{vendor}"

    def _stop(self, *_a, **_k):
        raise VendorMissing(f"no {self.vendor} configured")

    # people search, finder, verifier, phone, email channel, CRM writes: refuse
    search = find = verify = send = lookup = push = enrich = resolve = _stop

    def saved(self, *_a, **_k) -> None:
        return None

    def pages(self, *_a, **_k) -> list:  # research: no pages, so no facts, never invented ones
        return []

    def domains(self, cur, domains: list[str]) -> list[DomainTelemetry]:  # spam rate unknown, never clean
        return [DomainTelemetry(d, None, None) for d in domains]

    def placement(self, *_a, **_k) -> list:  # no seed test: placement stays unknown, which holds capacity
        return []

    def deals_changed(self, *_a, **_k) -> list:
        return []

    def owners_changed(self, *_a, **_k) -> list:
        return []

    def post(self, *_a, **_k) -> bool:  # an alert that could not be delivered stays undelivered
        return False

    def ensure_channel(self, *_a, **_k) -> str:
        return ""


def adapters(sim: Adapters) -> Adapters:
    """Live mode replaces every simulated vendor. A vendor with a key gets its live adapter; one without gets
    Missing, so a live desk never acts on simulated data."""
    m = Missing
    live = Adapters(people=m("people search"), finder=m("email finder"), verifier=m("email verifier"),
                    phone=m("phone finder"), research=m("website research"), email=m("mail provider"),
                    telemetry=m("deliverability telemetry"), dns=m("DNS"), chat=m("Slack"), crm=m("CRM"), notes=[])
    if os.environ.get("LIVE_DNS", "1") != "0":
        live.dns = DohDns()
    from ..config import CONFIG
    if CONFIG.postmaster_client_id and CONFIG.postmaster_client_secret and CONFIG.postmaster_refresh_token:
        live.telemetry = PostmasterTelemetry(CONFIG.postmaster_client_id, CONFIG.postmaster_client_secret,
                                             CONFIG.postmaster_refresh_token)
    missing = [a.vendor for a in vars(live).values() if isinstance(a, Missing)]
    live.notes.append("Live: DNS checks (DNS-over-HTTPS)" if not isinstance(live.dns, Missing) else "Live: nothing yet")
    if isinstance(live.telemetry, PostmasterTelemetry):
        live.notes.append("Live: Google Postmaster Tools (spam rate and compliance verdict)")
    if missing:
        live.notes.append("Not configured, so that work waits: " + ", ".join(missing))
    return live


def fetch_source(cur, source: str) -> list[dict]:
    return []
