"""Each shipped play must hold together as a sales leader would read it: what starts it, what it says and who it reaches.
Found by hand on 2026-11-11: 'Moving to usage-based pricing' could start on a free-tier sign-up, which the drafter may
never cite, while its angle told the email to name the pricing change."""
from outbound.outreach import PRIVATE_SIGNALS
from outbound.seed import catalog


def _plays():
    return [dict(zip(("key", "name", "hypothesis", "trigger", "personas", "max_people", "sequence", "angle"), p[:8]))
            for p in catalog.PLAYS]


def test_a_play_started_by_tracking_never_asks_the_email_to_name_it():
    for p in _plays():
        private = set(p["trigger"]["any_of"]) & set(PRIVATE_SIGNALS)
        if private:
            assert "without naming" in p["angle"].lower(), (
                f"{p['key']} can start on {sorted(private)}, which an email may never cite, so its angle must say it "
                f"works without naming what we saw: {p['angle']!r}")


def test_every_trigger_and_persona_exists():
    types = {t[0] for t in catalog.SIGNAL_TYPES}
    personas = {x[0] for x in catalog.PERSONAS}
    for p in _plays():
        assert set(p["trigger"]["any_of"]) <= types, p["key"]
        assert set(p["personas"]) <= personas, p["key"]
