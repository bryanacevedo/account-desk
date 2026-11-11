"""A live desk never acts on simulated data: a vendor without a key refuses or answers 'unknown', never invents."""
from __future__ import annotations

import pytest

from outbound.adapters import VendorMissing, live, sim


def test_live_mode_replaces_every_simulated_vendor():
    a = live.adapters(sim.adapters())
    for name in ("people", "finder", "verifier", "phone", "research", "email", "telemetry", "chat", "crm"):
        assert not type(getattr(a, name)).__module__.endswith(".sim"), name
    with pytest.raises(VendorMissing):
        a.verifier.verify(None, "real.person@company.example")  # never "invalid" for someone it cannot check
    with pytest.raises(VendorMissing):
        a.email.send(None, {}, {}, {}, {})
    assert a.telemetry.domains(None, ["send.example"])[0].spam_rate is None  # unknown, never "clean"
    assert a.telemetry.placement(None, {}) == []                             # no seed test, so capacity holds
    assert a.chat.post("#ops", "x") is False                                 # an alert it could not send stays undelivered
    assert a.crm.deals_changed(None, None, 10) == []
    assert any("Not configured" in n for n in a.notes)
