"""CRM Desk as Account Desk's CRM, chosen with CRM=crmdesk (docs/CONNECTING.md in the crm-desk repository).

Unset, Account Desk keeps the CRM it has today: the simulated one in demo mode, and in live mode one that refuses.
Every call fails closed: a timeout, a refused connection, a 429 or a 5xx raises, so the outbox keeps the row and tries
again later. A 409 `erased` from CRM Desk is a finished write with nothing written."""
from __future__ import annotations

import os
from datetime import datetime

import httpx

from .. import db
from . import CrmDeal, CrmOwner

SDR_TYPES = {"call": "call", "linkedin_connect": "linkedin", "linkedin_message": "linkedin"}


class CrmDeskDown(Exception):
    """CRM Desk did not answer with a decision."""


class CrmDeskUnresolved(Exception):
    """The row names a person Account Desk holds no address for. It is retried and, after five tries, raised as an
    alert; it is never marked done on a guess."""


def _when(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


class CrmDeskCrm:
    name = "crmdesk"

    def __init__(self, url: str, key: str, client: httpx.Client | None = None):
        self.c = client or httpx.Client(base_url=url.rstrip("/"), timeout=15.0,
                                        headers={"authorization": f"Bearer {key}", "content-type": "application/json"})

    @classmethod
    def from_env(cls) -> CrmDeskCrm:
        url, key = os.environ.get("CRM_DESK_URL", ""), os.environ.get("CRM_DESK_KEY", "")
        if not (url and key):
            raise SystemExit("CRM=crmdesk needs CRM_DESK_URL and CRM_DESK_KEY (a key made with --desk account_desk).")
        return cls(url, key)

    def _call(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self.c.request(method, "/api/v1" + path, **kw)
        except httpx.HTTPError as exc:
            raise CrmDeskDown(f"CRM Desk did not answer: {type(exc).__name__}") from exc
        if r.status_code >= 500 or r.status_code == 429:
            raise CrmDeskDown(f"CRM Desk answered {r.status_code} on {path}")
        return r

    @staticmethod
    def _ok(r: httpx.Response) -> dict:
        if r.status_code >= 400:
            raise CrmDeskDown(f"CRM Desk refused {r.request.url.path}: {r.status_code} {r.text[:200]}")
        return r.json()

    # ------------------------------------------------------------ writes from the outbox

    def push(self, cur, kind: str, payload: dict, idempotency_key: str) -> str:
        pid = payload.get("person_id")
        person = db.one(cur, "select id, email from people where id = %s", pid) if pid else None
        if pid and person is None:
            return "refused:erased"          # Account Desk deletes an erased person's row; nothing is written about them
        email = (person or {}).get("email") or payload.get("email")
        if kind == "opt_out":
            if not email:
                raise CrmDeskUnresolved(f"opt-out {idempotency_key} has no address")
            self._ok(self._call("POST", "/contacts/opt-out", json={"email": email}))
            return "opt_out"
        if not email:
            raise CrmDeskUnresolved(f"{kind} {idempotency_key} names a person with no address")
        if kind == "activity" and payload.get("type") == "email_sent":
            body = {"type": "email", "direction": "out", "contact": email, "subject": payload.get("subject"),
                    "external_id": f"message:{payload['message_id']}"}
        elif kind == "activity":
            body = {"type": SDR_TYPES[payload["kind"]], "contact": email, "outcome": payload.get("outcome"),
                    "external_id": f"task:{payload['task_id']}"}
        elif kind == "meeting":
            domain = db.val(cur, "select primary_domain from accounts where id = %s", payload["account_id"])
            body = {"type": "meeting", "meeting_status": "booked", "meeting_at": payload["starts_at"], "contact": email,
                    **({"account": f"domain:{domain}"} if domain else {}), "external_id": f"meeting:{payload['meeting_id']}"}
        elif kind == "task":
            owner = db.val(cur, "select email from users where id = %s", payload.get("owner")) if payload.get("owner") else None
            body = {"title": "Hot reply" if payload.get("type") == "hot_reply" else "Follow up", "contact": email,
                    **({"owner": owner} if owner else {}), "external_id": f"reply:{payload['reply_id']}"}
        else:
            raise ValueError(f"Unknown outbox kind {kind}")
        r = self._call("POST", "/tasks" if kind == "task" else "/activities", json=body,
                       headers={"idempotency-key": idempotency_key})
        if r.status_code == 409 and r.json().get("code") == "erased":
            return "refused:erased"
        return self._ok(r)["id"]

    # ------------------------------------------------------------ reads

    def deals_changed(self, cur, since: str | None, limit: int) -> list[CrmDeal]:
        """Account Desk stops when a page holds fewer than `limit` deals and builds its next cursor from the last deal.
        Tombstones carry no deal, so pages are read until `limit` deals or the end of the feed."""
        rows, cursor = [], since
        while len(rows) < limit:
            j = self._ok(self._call("GET", "/changes/opportunities", params={"limit": limit, **({"since": cursor} if cursor else {})}))
            rows += [r for r in j["data"] if not (r.get("deleted") or r.get("merged_into"))]
            cursor = j["next"]
            if not j["has_more"]:
                break
        return [CrmDeal(crm_id=r["id"], account_domain=r["account_domain"], name=r["name"], amount_cents=r["amount_cents"] or 0,
                        stage=r["stage"], created_at=_when(r["created_at"]), updated_at=_when(r["updated_at"]),
                        closed_at=_when(r["closed_at"]), won=r["is_won"] if r["is_closed"] else None,
                        loss_reason=r["loss_reason"], contact_email=r["contact_email"]) for r in rows[:limit]]

    def owners_changed(self, cur, since: str | None, limit: int) -> list[CrmOwner]:
        # Which owner Account Desk follows: the account's owner (the default, as before), or, where the CRM keeps the SDR
        # beside the AE (CRM Desk on the shared world), CRM_DESK_OWNER_ROLE=sdr. A CRM Desk without roles ignores it.
        role = os.environ.get("CRM_DESK_OWNER_ROLE", "account").strip().lower()
        params = {"limit": limit, **({"since": since} if since else {}), **({"role": role} if role != "account" else {})}
        j = self._ok(self._call("GET", "/changes/owners", params=params))
        return [CrmOwner(account_domain=r["account_domain"], owner_email=r["owner_email"], updated_at=_when(r["updated_at"]),
                         change_id=r["change_id"]) for r in j["data"]]
