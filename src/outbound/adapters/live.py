"""Live adapters, chosen by which env keys are present. Filled in vendor by vendor; until a vendor's key is set,
its simulated adapter stays in place and /api/health says so."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from . import Adapters, DnsResult

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


def adapters(sim: Adapters) -> Adapters:
    if os.environ.get("LIVE_DNS", "1") != "0":
        sim.dns = DohDns()
        sim.notes.append("DNS checks are live (DNS-over-HTTPS); blocklists need a vendor key")
    sim.notes.append("Live mode: other vendors stay simulated until their keys are set")
    return sim


def fetch_source(cur, source: str) -> list[dict]:
    return []
