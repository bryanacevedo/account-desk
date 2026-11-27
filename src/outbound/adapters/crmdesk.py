"""CRM Desk as Account Desk's CRM, chosen with CRM=crmdesk (docs/CONNECTING.md in the crm-desk repository).

Unset, Account Desk keeps the CRM it has today: the simulated one in demo mode, and in live mode one that refuses.
Every call fails closed: a timeout, a refused connection, a 429 or a 5xx raises, so the outbox keeps the row and tries
again later. A 409 `erased` from CRM Desk is a finished write with nothing written."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

import httpx

from .. import crmq, db
from . import CrmAccount, CrmCampaignMember, CrmDeal, CrmOwner

SDR_TYPES = {"call": "call", "linkedin_connect": "linkedin", "linkedin_message": "linkedin"}


class CrmDeskDown(Exception):
    """CRM Desk did not answer with a decision."""


class CrmDeskUnresolved(Exception):
    """The row names a person Account Desk holds no address for. It is retried and, after five tries, raised as an
    alert; it is never marked done on a guess."""


def _when(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def _day(v) -> str | None:
    """A date the CRM sent, as YYYY-MM-DD, or None."""
    return v[:10] if isinstance(v, str) and len(v) >= 10 and v[4] == "-" and v[7] == "-" else None


# What the CRM's contactability answer calls a flag, in the words a person reads in the stop reason.
FLAG_WORDS = {"do_not_contact": "marked do not contact", "do_not_email": "marked do not email",
              "do_not_call": "marked do not call", "unsubscribed": "unsubscribed", "bounced": "address bounced",
              "left_company": "left the company"}
# The flags that bar a channel. A bounce bars email only; a do-not-call bars calls only.
BARS = {"email": {"do_not_contact", "do_not_email", "unsubscribed", "bounced", "left_company"},
        "call": {"do_not_contact", "do_not_call", "left_company"},
        "linkedin": {"do_not_contact", "left_company"}}


class CrmDeskCrm:
    name = "crmdesk"
    configured = True      # a real CRM: the desk asks it before a person's first touch and waits when it cannot answer

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
        person = db.one(cur, "select id, email, world_id from people where id = %s", pid) if pid else None
        if pid and person is None:
            return "refused:erased"          # Account Desk deletes an erased person's row; nothing is written about them
        email = (person or {}).get("email") or payload.get("email")
        if kind == "deal_context":
            return self._deal_context(payload)
        if kind == "meeting_outcome":
            return self._meeting_outcome(cur, payload, idempotency_key)
        if kind == "task_close":
            return self._task_close(cur, payload, idempotency_key)
        if kind == "contact":
            return self._contact(cur, pid, idempotency_key)
        if kind in ("activity", "meeting", "task", "reply_in", "meeting_note") and pid and not db.val(
                cur, "select 1 from crm_outbox where idempotency_key = %s", f"contact:{pid}"):
            # A first activity whose person was never queued for a contact write (an SDR step done by hand): the contact
            # goes first, here, and is noted as written so it is not written again.
            ref = self._contact(cur, pid, f"contact:{pid}")
            crmq.enqueue(cur, "contact", {"person_id": pid}, f"contact:{pid}", done=ref)
        if kind == "opt_out":
            if not email:
                raise CrmDeskUnresolved(f"opt-out {idempotency_key} has no address")
            self._ok(self._call("POST", "/contacts/opt-out", json={"email": email}))
            return "opt_out"
        if not email and (person or {}).get("world_id"):
            # No address yet (an inbound booking from someone the desk has only a profile for): the CRM knows the contact by
            # the shared world's person id, which `_contact` wrote it under.
            email = f"ext:world_people:{person['world_id']}"
        if not email:
            raise CrmDeskUnresolved(f"{kind} {idempotency_key} names a person with no address")
        # When it happened is when the desk queued it, never when the CRM happens to hear: a retry after an outage, or a
        # CRM that is behind, must not move a send to another day.
        queued = (db.val(cur, "select created_at from crm_outbox where idempotency_key = %s", idempotency_key)
                  if cur is not None else None)
        when = {"occurred_at": queued.isoformat()} if queued else {}
        if kind == "activity" and payload.get("type") == "email_sent":
            body = {"type": "email", "direction": "out", "contact": email, "subject": payload.get("subject"),
                    "external_id": (f"reply_send:{payload['reply_send_id']}" if payload.get("reply_send_id")
                                    else f"message:{payload['message_id']}"), **when}
        elif kind == "activity":
            body = {"type": SDR_TYPES[payload["kind"]], "contact": email, "outcome": payload.get("outcome"),
                    "external_id": f"task:{payload['task_id']}", **when}
        elif kind == "meeting":
            domain = db.val(cur, "select primary_domain from accounts where id = %s", payload["account_id"])
            body = {"type": "meeting", "meeting_status": "booked", "meeting_at": payload["starts_at"], "contact": email,
                    # What an AE sees on the activity: a buyer who asked for a demo came to us; the rest an SDR booked.
                    **({"subject": "Demo request from the website"} if payload.get("source") == "inbound" else {}),
                    **({"account": f"domain:{domain}"} if domain else {}), "external_id": f"meeting:{payload['meeting_id']}"}
        elif kind == "reply_in":
            # What the person wrote, as an inbound email on their contact: the cleaned words, never the raw message with
            # its quoted history. The reply row is gone when the person was erased.
            r = db.one(cur, "select received_at, subject, cleaned, channel from replies where id = %s", payload["reply_id"])
            if r is None:
                return "refused:erased"
            body = {"type": "linkedin" if r["channel"] == "linkedin" else "email", "direction": "in", "contact": email, "subject": r["subject"],
                    "body": (r["cleaned"] or "")[:8000], "occurred_at": r["received_at"].isoformat(),
                    "external_id": f"reply_in:{payload['reply_id']}"}
        elif kind == "meeting_note":
            # A meeting the desk booked was moved: the CRM keeps the booking as it was and gets the change as a note.
            body = {"type": "note", "contact": email, "subject": "Meeting moved", "body": payload["text"],
                    "external_id": f"meeting_note:{payload['meeting_id']}:{payload['key']}", **when}
        elif kind == "task":
            owner = db.val(cur, "select email from users where id = %s", payload.get("owner")) if payload.get("owner") else None
            body = {"title": "Hot reply" if payload.get("type") == "hot_reply" else "Follow up", "contact": email,
                    **({"owner": owner} if owner else {}), "external_id": f"reply:{payload['reply_id']}"}
        else:
            raise ValueError(f"Unknown outbox kind {kind}")
        r = self._call("POST", "/tasks" if kind == "task" else "/activities", json=body,
                       headers={"idempotency-key": idempotency_key})
        if r.status_code == 404 and kind == "meeting" and "account" in body:
            # The CRM holds no account for this domain (it holds only the accounts its other desks sent), and an activity
            # never creates one: the meeting goes on the contact, which the CRM does hold.
            body.pop("account")
            r = self._call("POST", "/activities", json=body, headers={"idempotency-key": idempotency_key})
        if r.status_code == 409 and r.json().get("code") == "erased":
            return "refused:erased"
        return self._ok(r)["id"]

    def _contact(self, cur, person_id: int, idempotency_key: str) -> str:
        """The person, written to the CRM before their first activity: by the shared world's person id when this desk
        has one (`ext:world_people:<pe_id>`, so a second desk that found the same person lands on one contact), else by
        address. The CRM fills blanks only and a person's own edits win there."""
        p = db.one(cur, """select p.email, p.first_name, p.last_name, p.full_name, p.title, p.linkedin_url, p.country,
                                  p.world_id, a.name as company, a.primary_domain
                           from people p left join accounts a on a.id = p.account_id where p.id = %s""", person_id)
        if p is None:
            return "refused:erased"
        if not p["email"] and not p["world_id"]:
            raise CrmDeskUnresolved(f"contact {idempotency_key} names a person with no address and no world id")
        first, last = p["first_name"], p["last_name"]
        if not first and p["full_name"]:
            first, _, rest = p["full_name"].partition(" ")
            last = last or rest or None
        body = {k: v for k, v in {"first_name": first, "last_name": last, "title": p["title"], "linkedin_url": p["linkedin_url"],
                                  "country": p["country"], "company_name": p["company"], "email": p["email"],
                                  "domain": p["primary_domain"]}.items() if v}
        # The key carries a digest of what is written: a retry sends the same key, while a person whose details changed
        # since (or a rebuilt desk reusing a number) is a different write to the CRM, not a conflicting one.
        digest = hashlib.sha256(json.dumps([p["world_id"], p["email"], body], sort_keys=True).encode()).hexdigest()[:10]
        headers = {"idempotency-key": f"{idempotency_key}:{digest}"}
        if p["world_id"]:
            r = self._call("PUT", f"/contacts/by-ext/world_people/{p['world_id']}", json=body, headers=headers)
        else:
            body.pop("email", None)
            r = self._call("PUT", f"/contacts/by-email/{p['email']}", json=body, headers=headers)
        if r.status_code == 409 and r.json().get("code") == "duplicate" and body.get("linkedin_url"):
            # One LinkedIn profile, two seats (a job mover): the CRM keeps the profile on the other record, and this
            # contact is written without it, so the meeting still reaches the CRM.
            body.pop("linkedin_url")
            headers = {"idempotency-key": f"{idempotency_key}:{digest}:no-linkedin"}
            if p["world_id"]:
                r = self._call("PUT", f"/contacts/by-ext/world_people/{p['world_id']}", json=body, headers=headers)
            else:
                body.pop("email", None)
                r = self._call("PUT", f"/contacts/by-email/{p['email']}", json=body, headers=headers)
        if r.status_code == 409 and r.json().get("code") == "erased":
            return "refused:erased"
        return self._ok(r)["id"]

    def _deal_context(self, payload: dict) -> str:
        """The play, the signal and the SDR's note for the deal's handoff (BL-111). CRM Desk keeps a person's words and refuses
        a value another desk owns; neither is an error here, so a refusal in the answer is read and passed over."""
        body = {k: payload[k] for k in ("handoff_play", "handoff_signal", "handoff_note") if payload.get(k)}
        r = self._call("PATCH", f"/opportunities/{payload['crm_id']}", json=body)
        if r.status_code == 404:
            return "skipped:no_such_deal"           # the CRM no longer holds the deal (deleted or merged): nothing to carry
        return self._ok(r)["id"]

    def _task_close(self, cur, payload: dict, idempotency_key: str) -> str:
        """Close the "Hot reply" task this desk made for a reply, by the external id it was made under. It waits for the
        task to reach the CRM first. A CRM Desk with no such route (404 or 405 from an older one), or with no open task
        by that id (already closed there), is a finished write with a note: the desk works with the CRM it has."""
        made = db.one(cur, "select status, payload->>'crm_ref' as ref from crm_outbox where idempotency_key = %s",
                      f"task:reply:{payload['reply_id']}")
        if made and made["status"] == "pending":
            raise CrmDeskUnresolved(f"the task for reply {payload['reply_id']} has not reached the CRM yet")
        if made and (made["ref"] or "").startswith("refused:"):
            return made["ref"]
        r = self._call("POST", "/tasks/close", headers={"idempotency-key": idempotency_key},
                       json={"external_id": f"reply:{payload['reply_id']}", "outcome": payload.get("outcome", "done"),
                             "note": payload.get("note") or ""})
        if r.status_code in (404, 405):
            return "skipped:no_open_task" if r.status_code == 404 else "skipped:unsupported"
        return self._ok(r)["id"]

    def _meeting_outcome(self, cur, payload: dict, idempotency_key: str) -> str:
        """Held, no show or cancelled, on the meeting this desk booked. The activity's id is the booking's `crm_ref`; a
        booking that has not reached the CRM yet makes this raise, so the row is tried again later."""
        booked = db.one(cur, "select status, payload->>'crm_ref' as ref from crm_outbox where idempotency_key = %s",
                        f"meeting:{payload['meeting_id']}")
        ref = (booked or {}).get("ref")
        if not ref or booked["status"] != "done":
            raise CrmDeskUnresolved(f"meeting {payload['meeting_id']} has not reached the CRM yet")
        if ref.startswith("refused:"):
            return ref
        r = self._call("PATCH", f"/activities/{ref}", json={"meeting_status": payload["status"]},
                       headers={"idempotency-key": idempotency_key})
        if r.status_code == 409 and r.json().get("code") == "erased":
            return "refused:erased"
        self._ok(r)
        return ref

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

    # ------------------------------------------------------------ optional reads (the desk does without them when absent)

    def _feed(self, name: str, since: str | None, limit: int) -> list[dict]:
        """`limit` live rows of one change feed, oldest first. Tombstones (deleted or merged) carry nothing to keep and
        are skipped; pages are read on until `limit` rows or the end of the feed."""
        rows, cursor = [], since
        while len(rows) < limit:
            j = self._ok(self._call("GET", f"/changes/{name}", params={"limit": limit, **({"since": cursor} if cursor else {})}))
            rows += [r for r in j["data"] if not (r.get("deleted") or r.get("merged_into"))]
            cursor = j["next"]
            if not j["has_more"]:
                break
        return rows[:limit]

    def accounts_changed(self, cur, since: str | None, limit: int) -> list[CrmAccount]:
        out = []
        for r in self._feed("accounts", since, limit):
            m = r.get("market") or {}
            tier = m.get("tier") if m.get("tier") in ("A", "B", "C", "X") else None   # "Not judged" is no tier
            out.append(CrmAccount(domain=(r.get("domain") or "").lower(), name=r.get("name") or r.get("domain") or "", world_id=r.get("world_id"),
                                  crm_id=r["id"], tier=tier, segment=m.get("segment"), fit=m.get("fit_score"),
                                  icp_version=None if m.get("icp_version") is None else str(m["icp_version"]),
                                  sdr_owner_email=((r.get("sdr_owner") or {}).get("email") or "").lower() or None,
                                  updated_at=_when(r["updated_at"]), change_id=r["id"]))
        return out

    bulk_contacts = True     # POST /contacts/batch; set False once a CRM Desk answers 404 or 405 to it

    def _contacts(self, ids: list[str]) -> dict[str, dict]:
        """Each contact once, read in batches of 200 (POST /contacts/batch) instead of one request each. A CRM Desk
        without the route (404 or 405), or an id the batch calls missing, is read one at a time as before."""
        want = list(dict.fromkeys(ids))
        got: dict[str, dict] = {}
        if self.bulk_contacts:
            for i in range(0, len(want), 200):
                chunk = want[i:i + 200]
                r = self._call("POST", "/contacts/batch", json={"ids": chunk})
                if r.status_code in (404, 405):
                    self.bulk_contacts = False
                    break
                j = self._ok(r)
                for c in j.get("contacts") or []:
                    got[str(c["id"])] = c
        for cid in want:
            if cid not in got:
                got[cid] = self._ok(self._call("GET", f"/contacts/{cid}"))
        return got

    def campaign_members_changed(self, cur, since: str | None, limit: int) -> list[CrmCampaignMember]:
        campaigns: dict[str, dict] = {}
        rows = self._feed("campaign_members", since, limit)
        contacts = self._contacts([r["contact_id"] for r in rows])
        out = []
        for r in rows:
            c = campaigns.get(r["campaign_id"]) or campaigns.setdefault(
                r["campaign_id"], self._ok(self._call("GET", f"/campaigns/{r['campaign_id']}")))
            k = contacts[r["contact_id"]]
            out.append(CrmCampaignMember(campaign_ref=r["campaign_id"], campaign_name=c.get("name") or "", campaign_type=c.get("type") or "other",
                                         event_name=c.get("name"), status=r["status"], contact_email=(r.get("contact_email") or k.get("email") or "").lower() or None,
                                         contact_crm_id=r["contact_id"], account_domain=k.get("account_domain"),
                                         updated_at=_when(r["updated_at"]), change_id=r["id"],
                                         event_starts_on=_day(c.get("start_date")), event_ends_on=_day(c.get("end_date"))))
        return out

    def contactability(self, cur, items: list[dict]) -> list[dict]:
        """May each person be contacted. Items are {ref, email, world_id?}; answers come back in the same order, as
        {can_email, can_call, flags: [{kind, reason}], suppressed, erased}. An address the CRM does not hold is
        `suppressed` only when it is on its suppression list (unsubscribed or erased, which it does not tell apart)."""
        if not items:
            return []
        def ask(it: dict) -> dict:
            if it.get("email"):      # by address when there is one, else by name at the company's domain
                keys = ("ref", "email", "world_id")
            else:
                keys = ("ref", "world_id", "full_name", "domain")
            return {k: str(it[k]) if k == "ref" else it[k] for k in keys if it.get(k)}
        j = self._ok(self._call("POST", "/contacts/contactability", json={"contacts": [ask(it) for it in items]}))
        by_ref = {str(r.get("ref")): r for r in j["results"]}
        out = []
        for it in items:
            r = by_ref.get(str(it["ref"]))
            if r is None:
                raise CrmDeskDown(f"CRM Desk gave no answer for {it['ref']}")
            flags, can_email, can_call, erased = [], r.get("can_email", True), r.get("can_call", True), False
            for c in r.get("contacts") or []:
                erased = erased or bool(c.get("erased"))
                can_email = can_email and c.get("can_email", True)
                can_call = can_call and c.get("can_call", True)
                for kind in FLAG_WORDS:
                    f = c.get(kind)
                    on = f if kind == "left_company" else (f or {}).get("value")
                    if on:
                        src = "" if kind == "left_company" else (f.get("source") or "")
                        flags.append({"kind": kind, "reason": FLAG_WORDS[kind] + (f" ({src})" if src else "")})
            out.append({"can_email": bool(can_email), "can_call": bool(can_call), "flags": flags,
                        "suppressed": bool(r.get("suppressed")), "erased": erased})
        return out
