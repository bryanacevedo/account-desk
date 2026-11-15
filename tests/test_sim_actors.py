"""Outside actors in the simulation (the rehearsal's AEs) and the CRM loss reason read as words."""
from datetime import datetime, timezone

import pytest

from outbound import signals
from outbound.sim import runner


@pytest.mark.parametrize("reason", ["timing", "Timing", "not this quarter, revisit after their audit", "pushed to next FY",
                                    "come back after Q1 close", "bad timing, mid reorg"])
def test_timing_losses_are_read_from_code_or_words(reason):
    assert signals.lost_on_timing(reason)


@pytest.mark.parametrize("reason", [None, "", "price", "went with Meterly", "went dark after demo", "Too expensive vs budget"])
def test_other_losses_are_not_timing(reason):
    assert not signals.lost_on_timing(reason)


def test_actor_hook_calls_act_each_hour_and_is_off_by_default(tmp_path, monkeypatch):
    f = tmp_path / "actors.py"
    f.write_text("calls = []\ndef act(at):\n    calls.append(at)\n")
    at = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    monkeypatch.delenv("SIM_ACTORS", raising=False)
    monkeypatch.setattr(runner, "_ACTORS", None)
    runner._outside_actors(at)
    assert runner._ACTORS is None
    monkeypatch.setenv("SIM_ACTORS", str(f))
    monkeypatch.delenv("PUBLIC_DEMO", raising=False)
    runner._outside_actors(at)
    runner._outside_actors(at)
    assert runner._ACTORS.calls == [at, at]


def test_actor_hook_refused_on_the_public_demo(monkeypatch):
    monkeypatch.setenv("SIM_ACTORS", "/nowhere.py")
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    with pytest.raises(SystemExit):
        runner._outside_actors(datetime(2026, 9, 1, tzinfo=timezone.utc))
