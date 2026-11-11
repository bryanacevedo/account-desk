"""Adapter contracts. Each vendor kind has one small interface; the desk only talks to these.

`get()` returns the simulated adapters in demo mode and the live ones (selected by env keys) in live mode.
Every paid call is wrapped by spend.paid_call by the caller, never inside the adapter, so an adapter cannot spend
without leaving a ledger row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..config import CONFIG


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
    spam_rate: float | None      # None means unknown
    status: str | None
    as_of: object | None = None


class PeopleSearch(Protocol):
    def search(self, cur, account: dict, title_patterns: list[str], limit: int) -> list[Candidate]: ...
    def saved(self, cur, candidate: Candidate, person_id: int) -> None: ...


class EmailFinder(Protocol):
    name: str
    def find(self, cur, person: dict, domain: str) -> str | None: ...


class EmailVerifier(Protocol):
    name: str
    def verify(self, cur, email: str) -> str: ...  # valid | invalid | risky


class PhoneFinder(Protocol):
    def find(self, cur, person: dict) -> str | None: ...


class Research(Protocol):
    def pages(self, cur, account: dict) -> list[Page]: ...


class EmailChannel(Protocol):
    def send(self, cur, message: dict, mailbox: dict, person: dict, headers: dict) -> SendResult: ...
    def lookup(self, cur, idempotency_key: str) -> SendResult: ...


class Telemetry(Protocol):
    def domains(self, cur, domains: list[str]) -> list[DomainTelemetry]: ...


class Chat(Protocol):
    def post(self, channel: str, text: str, blocks: list | None = None) -> bool: ...
    def ensure_channel(self, name: str, invite: list[str]) -> str: ...


class Crm(Protocol):
    def push(self, cur, kind: str, payload: dict, idempotency_key: str) -> str: ...


@dataclass
class Adapters:
    people: PeopleSearch
    finder: EmailFinder
    verifier: EmailVerifier
    phone: PhoneFinder
    research: Research
    email: EmailChannel
    telemetry: Telemetry
    chat: Chat
    crm: Crm
    notes: list[str] = field(default_factory=list)


_cached: Adapters | None = None


def get() -> Adapters:
    global _cached
    if _cached is None:
        from . import sim
        _cached = sim.adapters()
        if CONFIG.mode == "live":
            from . import live
            _cached = live.adapters(_cached)
    return _cached


def override(a: Adapters | None) -> None:
    """Tests swap adapters in and out."""
    global _cached
    _cached = a
