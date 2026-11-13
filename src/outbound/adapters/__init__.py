"""Adapter contracts. Each vendor kind has one small interface; the desk only talks to these.

`get()` returns the simulated adapters in demo mode and the live ones (selected by env keys) in live mode.
Every paid call is wrapped by spend.paid_call by the caller, never inside the adapter, so an adapter cannot spend
without leaving a ledger row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..config import CONFIG


class VendorMissing(Exception):
    """A live desk asked for a vendor it has no key for. Work that needs it waits, and the team is told; nothing is
    invented in its place."""


@dataclass
class Candidate:
    full_name: str
    first_name: str
    last_name: str
    title: str
    seniority: str | None
    linkedin_url: str | None
    country: str | None = None
    timezone: str | None = None
    vendor_ref: str | None = None
    photo_url: str | None = None
    # What a people-data vendor returns beyond the name (Apollo-style person enrichment).
    departments: list[str] = field(default_factory=list)
    role_started_at: object = None        # date the current role started
    city: str | None = None
    headline: str | None = None
    match_confidence: str | None = None   # high | medium | low: how sure the vendor is this is the right person


@dataclass
class SendResult:
    outcome: str  # sent | failed | unknown
    provider_id: str | None = None
    error: str | None = None


@dataclass
class Page:
    kind: str
    text: str
    url: str


@dataclass
class DomainTelemetry:
    domain: str
    spam_rate: float | None      # None means unknown: the provider has no data, which is not the same as clean
    status: str | None           # the provider's compliance verdict: "compliant" | "needs_work"; None means no verdict yet
    as_of: object | None = None


@dataclass
class WarmupStatus:
    state: str                   # warming | maintaining
    day: int                     # days since warm-up began
    score: int | None = None     # the vendor's reputation score, 0 to 100, once it has one


@dataclass
class PlacementResult:
    provider: str                # gmail | outlook
    seeds: int
    inbox: int
    spam: int
    missing: int


class PeopleSearch(Protocol):
    def search(self, cur, account: dict, title_patterns: list[str], limit: int) -> list[Candidate]: ...
    def saved(self, cur, candidate: Candidate, person_id: int) -> None: ...
    # Refresh one known person (a people match by name, company and profile). None when the vendor has no match.
    def enrich(self, cur, person: dict) -> Candidate | None: ...


@dataclass
class CompanyData:
    """What a company-data vendor returns that matters for account-based outbound."""
    industry: str | None = None
    employees: int | None = None
    revenue_band: str | None = None
    technologies: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    founded_year: int | None = None
    total_funding_cents: int | None = None
    latest_funding_round: str | None = None
    latest_funding_at: object = None
    parent_domain: str | None = None
    headcount: dict = field(default_factory=dict)        # department -> people
    open_roles: list[dict] = field(default_factory=list)  # {title, department, seen_at}
    confidence: float | None = None


class CompanyEnricher(Protocol):
    name: str
    def enrich(self, cur, account: dict) -> CompanyData | None: ...


@dataclass
class PhoneHit:
    number: str
    type: str = "unknown"   # mobile | direct | office | unknown
    dnc: bool = False       # on a do-not-call register


class EmailFinder(Protocol):
    name: str
    def find(self, cur, person: dict, domain: str) -> str | None: ...


class EmailVerifier(Protocol):
    name: str
    def verify(self, cur, email: str) -> str: ...  # valid | invalid | risky | catch_all


class EmailResolver(Protocol):
    """A second opinion for catch-all servers, which accept every address so a normal check proves nothing."""
    name: str
    def resolve(self, cur, email: str) -> tuple[str, float]: ...  # (valid | invalid | catch_all, confidence)


class PhoneFinder(Protocol):
    def find(self, cur, person: dict) -> "PhoneHit | str | None": ...


class Research(Protocol):
    def pages(self, cur, account: dict) -> list[Page]: ...


class EmailChannel(Protocol):
    def send(self, cur, message: dict, mailbox: dict, person: dict, headers: dict) -> SendResult: ...
    def lookup(self, cur, idempotency_key: str) -> SendResult: ...


class Telemetry(Protocol):
    def domains(self, cur, domains: list[str]) -> list[DomainTelemetry]: ...
    def placement(self, cur, mailbox: dict) -> list[PlacementResult]: ...  # a seed test, one result per provider


class Warmup(Protocol):
    """A warm-up vendor: swaps mail between mailboxes to build a sender reputation. It reports; the desk's own
    ramp (outreach.mailbox_capacity) still decides how much the desk sends."""
    name: str
    def status(self, cur, mailbox: dict) -> WarmupStatus | None: ...


@dataclass
class DnsResult:
    domain: str
    spf: bool
    dkim: bool
    dmarc: bool
    dmarc_policy: str | None
    dmarc_aligned: bool
    blocklists: list[str] | None  # None: not checked (needs a vendor), never "clean"
    detail: dict


class Dns(Protocol):
    def check(self, cur, domain: str, dkim_selector: str | None) -> DnsResult: ...


class Chat(Protocol):
    def post(self, channel: str, text: str, blocks: list | None = None) -> bool: ...
    def ensure_channel(self, name: str, invite: list[str]) -> str: ...


@dataclass
class CrmDeal:
    """One deal as the CRM holds it (Salesforce opportunity, HubSpot deal)."""
    crm_id: str
    account_domain: str
    name: str
    amount_cents: int
    stage: str
    created_at: object
    updated_at: object
    closed_at: object | None = None
    won: bool | None = None
    loss_reason: str | None = None
    contact_email: str | None = None


@dataclass
class CrmOwner:
    """An account's owner as the CRM holds it."""
    account_domain: str
    owner_email: str
    updated_at: object
    change_id: str = ""  # with updated_at, the cursor: changes sharing a timestamp are never skipped


@dataclass
class CrmAccount:
    """An account as the CRM holds it, with the market fields (tier, segment, fit) and the SDR who works it."""
    domain: str
    name: str
    world_id: str | None = None
    crm_id: str | None = None
    tier: str | None = None          # A | B | C | X, or None when the CRM holds none ("Not judged" is read as None)
    segment: str | None = None
    fit: int | None = None
    icp_version: str | None = None
    sdr_owner_email: str | None = None
    updated_at: object = None
    change_id: str = ""              # the feed's id for this row; with updated_at it is the cursor


@dataclass
class CrmCampaignMember:
    """One person's place in a campaign (an event) as the CRM holds it."""
    campaign_ref: str
    campaign_name: str
    campaign_type: str               # event | webinar | email | outbound | other
    event_name: str | None
    status: str                      # sent | registered | attended | met | no_show | responded
    contact_email: str | None
    contact_crm_id: str | None
    account_domain: str | None
    updated_at: object = None
    change_id: str = ""


class Crm(Protocol):
    """What a CRM must do. These three are all a CRM needs for the whole flow to run. A CRM may also have the optional
    methods below; the desk looks each up with getattr and does without it when absent, so an adapter shaped for a
    Salesforce-style CRM never has to learn them:

      accounts_changed(cur, since, limit) -> list[CrmAccount]                the SDR books, with tier and segment
      campaign_members_changed(cur, since, limit) -> list[CrmCampaignMember]  event members, for event follow-up
      contactability(cur, items) -> list[dict]                               {can_email, can_call, flags: [{kind, reason}],
                                                                             suppressed, erased} per item, same order
      configured: bool                                                       True for a real CRM the desk must ask before
                                                                             a first send (absent or False for the sim)
      accepts_kinds: set[str]                                                outbox kinds it takes; absent means all
    """
    def push(self, cur, kind: str, payload: dict, idempotency_key: str) -> str: ...
    def deals_changed(self, cur, since: str | None, limit: int) -> list[CrmDeal]: ...  # since is 'time|crm_id', oldest first
    def owners_changed(self, cur, since: str | None, limit: int) -> list[CrmOwner]: ...  # since is 'time|change_id', oldest first


@dataclass
class Adapters:
    people: PeopleSearch
    finder: EmailFinder
    verifier: EmailVerifier
    phone: PhoneFinder
    research: Research
    email: EmailChannel
    telemetry: Telemetry
    dns: Dns
    chat: Chat
    crm: Crm
    notes: list[str] = field(default_factory=list)
    # The email waterfall: finders tried in order until one returns an address that verifies. Empty means the
    # single `finder` above. Each finder has a `provider` key and charges only for an address it returns.
    finders: list = field(default_factory=list)
    company: "CompanyEnricher | None" = None     # company data; None means imports and the CRM are all there is
    resolver: "EmailResolver | None" = None      # catch-all resolution; None means catch-all addresses are not sent
    warmup: "Warmup | None" = None               # warm-up vendor; None means no warm-up status is shown


_cached: Adapters | None = None


def get() -> Adapters:
    global _cached
    if _cached is None:
        from . import sim
        _cached = sim.adapters()
        if CONFIG.mode == "live":
            from . import live
            _cached = live.adapters(_cached)
        _cached.crm = choose_crm(_cached.crm)
    return _cached


def choose_crm(current):
    """CRM picks the desk's CRM. Unset keeps today's: the simulated CRM in demo mode, a refusing one in live mode.
    `crmdesk` is CRM Desk. `salesforce` is refused until a Salesforce adapter exists, rather than run on a stand-in."""
    import os
    choice = os.environ.get("CRM", "").strip().lower()
    if choice in ("", "default"):
        return current
    if choice == "crmdesk":
        from .crmdesk import CrmDeskCrm
        return CrmDeskCrm.from_env()
    if choice == "sim" and CONFIG.mode != "live":
        return current
    if choice == "salesforce":
        raise SystemExit("CRM=salesforce: this desk has no Salesforce adapter yet. Leave CRM unset or use CRM=crmdesk.")
    raise SystemExit(f"CRM={choice} is not a CRM this desk knows. Use crmdesk, or leave it unset.")


def override(a: Adapters | None) -> None:
    """Tests swap adapters in and out."""
    global _cached
    _cached = a
