"""Each shipped play must hold together as a sales leader would read it: what starts it, what it says and who it reaches.
Found by hand on 2026-11-11: 'Moving to usage-based pricing' could start on a free-tier sign-up, which the drafter may
never cite, while its angle told the email to name the pricing change."""
from outbound.outreach import PRIVATE_SIGNALS
from test_guarantees import scene  # noqa: F401
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


def test_a_first_stage_play_is_not_held_by_drafts_it_can_never_have(cur, scene):  # noqa: F811
    """At the first stage the SDR writes everything, so the desk has no drafts to judge. Asking for 50 approved
    drafts would keep the play there for ever (found 2026-11-11)."""
    from outbound import db, views
    play = db.one(cur, "select * from plays order by id limit 1")
    play["autonomy"] = "research"
    check = views.promotion_check(cur, play)
    labels = {c["label"] for c in check["checks"]}
    assert "50 drafts approved by a person" not in labels and "Approved without edits" not in labels
    assert check["next"] == "draft"


def test_no_shipped_play_starts_with_autonomy_it_has_not_earned():
    """Autonomy is earned per play (DECISIONS 22): a new play starts with the SDR approving every email, or lower.
    Found 2026-11-11: 'A past champion joined' shipped at stage 3 with no accounts."""
    for p in catalog.PLAYS:
        assert p[8] in ("research", "draft"), (p[0], p[8])
