"""Live adapters, chosen by which env keys are present. Filled in vendor by vendor; until a vendor's key is set,
its simulated adapter stays in place and /api/health says so."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

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
        # Relaxed alignment holds when the mail is signed with this domain's own DKIM key, which is what we check.
        aligned = bool(dkim) and tags.get("adkim", "r").strip().lower() in ("r", "s")
        return DnsResult(domain, len(spf) == 1, bool(dkim), bool(dmarc),
                         policy if policy in ("none", "quarantine", "reject") else None, aligned and bool(dmarc), None,
                         {"spf": spf, "dmarc": dmarc, "dkim_selector": dkim_selector, "dkim_found": bool(dkim),
                          "spf_records": len(spf)})


class Missing:
    """Stands in for every vendor without a key in live mode. It never invents a result: paid lookups and sends
    raise VendorMissing (the job waits and the team is told), and reads return 'unknown' or nothing."""
    def __init__(self, vendor: str):
        self.vendor = vendor
        self.name = f"missing:{vendor}"

    def _stop(self, *_a, **_k):
        raise VendorMissing(f"no {self.vendor} configured")

    # people search, finder, verifier, phone, email channel, CRM writes: refuse
    search = find = verify = send = lookup = push = _stop

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
    missing = [a.vendor for a in vars(live).values() if isinstance(a, Missing)]
    live.notes.append("Live: DNS checks (DNS-over-HTTPS)" if not isinstance(live.dns, Missing) else "Live: nothing yet")
    if missing:
        live.notes.append("Not configured, so that work waits: " + ", ".join(missing))
    return live


def fetch_source(cur, source: str) -> list[dict]:
    return []
