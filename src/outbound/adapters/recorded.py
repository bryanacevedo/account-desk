"""The CRM half of the demo build, replayed from the shared rehearsal's journal (shared-world DESIGN.md 4.3).

The rehearsal records every request a desk made of CRM Desk and the answer it was given, one JSON object per line:
  {"actor": "account_desk", "at": ..., "method": "POST", "path": "/contacts/contactability", "query": {...},
   "idempotency_key": "...", "body": {...}, "status": 200, "answer": {...}}
`path` has no /api/v1 prefix. `query` (GET params), `idempotency_key` and `body` are written when the request had them.

RecordedCrm is the real CrmDeskCrm adapter on a client that serves each request from the actor's next journal step, so
the desk's own logic runs unchanged. Any difference raises JournalMismatch: a request the journal does not have next, a
different method, path, query, idempotency key or body, or steps left over when `finish()` is called. `at` is the one
volatile field and is not compared. A mismatch is also remembered, so `finish()` raises it even if the desk caught it.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .crmdesk import CrmDeskCrm

ACTOR = "account_desk"
API_PREFIX = "/api/v1"
DEFAULT_JOURNAL = "world/journal.jsonl"
# Optional CRM methods and the journal path that shows the recorded CRM offered them.
OPTIONAL = {"accounts_changed": "/changes/accounts", "campaign_members_changed": "/changes/campaign_members",
            "contactability": "/contacts/contactability"}


class JournalMismatch(Exception):
    """The build asked the CRM for something the journal does not have next."""


def _canon(v) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def read_steps(path, actor: str = ACTOR) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise JournalMismatch(f"journal {p} does not exist")
    out = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                s = json.loads(line)
            except ValueError as exc:
                raise JournalMismatch(f"journal {p} line {n} is not JSON") from exc
            if s.get("actor") == actor:
                out.append(s)
    return out


def _shape(method: str, path: str, query, key, body) -> dict:
    return {"method": method.upper(), "path": path, "query": {k: str(v) for k, v in (query or {}).items()},
            "idempotency_key": key, "body": body}


def _request_parts(method: str, url: str, kw: dict) -> dict:
    path = url[len(API_PREFIX):] if url.startswith(API_PREFIX) else url
    return _shape(method, path, kw.get("params"), (kw.get("headers") or {}).get("idempotency-key"), kw.get("json"))


class _ReplayClient:
    def __init__(self, steps: list[dict]):
        self.steps = steps
        self.i = 0
        self.failure: JournalMismatch | None = None

    def _fail(self, msg: str):
        self.failure = self.failure or JournalMismatch(msg)
        raise JournalMismatch(msg)

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        got = _request_parts(method, url, kw)
        where = f"call {self.i + 1} of {len(self.steps)}"
        if self.i >= len(self.steps):
            self._fail(f"{where}: the build made {got['method']} {got['path']} but the journal has no more steps")
        s = self.steps[self.i]
        want = _shape(s.get("method", ""), s.get("path", ""), s.get("query"), s.get("idempotency_key"), s.get("body"))
        for field in ("method", "path", "query", "idempotency_key", "body"):
            if _canon(got[field]) != _canon(want[field]):
                self._fail(f"{where}: the build made {got['method']} {got['path']} with a different {field}; the journal "
                           f"has {want['method']} {want['path']}")
        self.i += 1
        req = httpx.Request(got["method"], "http://recorded" + API_PREFIX + got["path"])
        return httpx.Response(int(s.get("status", 200)), json=s.get("answer"), request=req)

    def finish(self) -> None:
        if self.failure:
            raise self.failure
        if self.i < len(self.steps):
            nxt = self.steps[self.i]
            raise JournalMismatch(f"{len(self.steps) - self.i} journal steps were not used; next is "
                                  f"{nxt.get('method')} {nxt.get('path')}")


class RecordedCrm:
    """Serves the recorded CRM. push, deals_changed and owners_changed are always offered; each optional method only
    when the journal's paths show the recorded CRM had it, so the desk's getattr checks behave as they did."""
    name = "recorded"
    configured = True

    def __init__(self, steps: list[dict]):
        self._client = _ReplayClient(steps)
        self._crm = CrmDeskCrm("http://recorded", "recorded", client=self._client)
        paths = {s.get("path", "").split("?")[0] for s in steps}
        self._offered = {name for name, p in OPTIONAL.items() if p in paths}

    @classmethod
    def from_journal(cls, path=None) -> RecordedCrm:
        return cls(read_steps(path or os.environ.get("JOURNAL_PATH") or DEFAULT_JOURNAL))

    def push(self, cur, kind, payload, idempotency_key):
        return self._crm.push(cur, kind, payload, idempotency_key)

    def deals_changed(self, cur, since, limit):
        return self._crm.deals_changed(cur, since, limit)

    def owners_changed(self, cur, since, limit):
        return self._crm.owners_changed(cur, since, limit)

    def __getattr__(self, name):
        if name in OPTIONAL and name in self.__dict__.get("_offered", ()):
            return getattr(self._crm, name)
        raise AttributeError(name)

    def finish(self) -> None:
        """Every step must have been used."""
        self._client.finish()


class _RecordingClient:
    def __init__(self, inner: httpx.Client, journal: Path, actor: str):
        self.inner, self.journal, self.actor = inner, journal, actor

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        r = self.inner.request(method, url, **kw)
        step = {"actor": self.actor, "at": datetime.now(timezone.utc).isoformat(), "status": r.status_code,
                **{k: v for k, v in _request_parts(method, url, kw).items() if v not in (None, {})}}
        try:
            step["answer"] = r.json()
        except ValueError:
            step["answer"] = None
        with self.journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps(step, sort_keys=True) + "\n")
        return r


class RecordingCrm:
    """Writes the journal steps for the calls an inner CrmDeskCrm makes, then returns its answers unchanged. The rehearsal
    does this on the CRM Desk side; tests use it to produce a journal to replay."""
    def __init__(self, inner: CrmDeskCrm, journal_path, actor: str = ACTOR):
        self._inner = inner
        inner.c = _RecordingClient(inner.c, Path(journal_path), actor)

    def __getattr__(self, name):
        return getattr(self._inner, name)
