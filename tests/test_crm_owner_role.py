"""CRM_DESK_OWNER_ROLE: Account Desk follows the account's owner by default, or the SDR where the CRM keeps both."""
import httpx

from outbound.adapters.crmdesk import CrmDeskCrm


def _crm(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"data": [], "next": "", "has_more": False})
    return CrmDeskCrm("http://crm.test", "rd_x", client=httpx.Client(base_url="http://crm.test", transport=httpx.MockTransport(handler)))


def test_default_follows_the_account_owner(monkeypatch):
    monkeypatch.delenv("CRM_DESK_OWNER_ROLE", raising=False)
    seen = []
    _crm(seen).owners_changed(None, None, 10)
    assert "role" not in seen[0]


def test_sdr_role_asks_for_the_sdr(monkeypatch):
    monkeypatch.setenv("CRM_DESK_OWNER_ROLE", "sdr")
    seen = []
    _crm(seen).owners_changed(None, None, 10)
    assert seen[0]["role"] == "sdr"
