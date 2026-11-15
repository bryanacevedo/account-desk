"""Alerts at the top of Inboxes and Health (bl_125, decision 86): each alert has a tab, an open one is told apart from a
finished one, a condition that raised a row every day shows once, the code that ends a condition resolves it, and a
person can ack."""
# ruff: noqa: F811  (the mailbox fixture is shared from test_placement and named as a parameter)
from __future__ import annotations

import dataclasses
import os
import re
from pathlib import Path

import pytest
from test_placement import FixedSeeds, box, truth  # noqa: F401  the shared mailbox fixture

os.environ.setdefault("NO_WORKER", "1")

from fastapi.testclient import TestClient  # noqa: E402

from outbound import adapters, admin, alerts, db, sending, views  # noqa: E402
from outbound.adapters import DomainTelemetry  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "outbound"


def raise_(cur, kind, *, severity="warn", dedup=None, **kw):
    return alerts.raise_alert(cur, kind=kind, severity=severity, channel="#outbound-ops", title=kw.pop("title", f"{kind} test"),
                              body="b", dedup_key=dedup or f"{kind}:{os.urandom(4).hex()}", **kw)


def open_(cur, scope="inboxes") -> list[dict]:
    return alerts.open_view(cur, scope)["alerts"]


def back_date(cur, alert_id: int, days: int) -> None:
    db.run(cur, "update alerts set at = app_now() - make_interval(days => %s) where id = %s", days, alert_id)


# ---------------------------------------------------------------- scope

def test_every_kind_the_code_raises_has_a_scope():
    kinds = set()
    for f in SRC.rglob("*.py"):
        kinds |= set(re.findall(r"raise_alert\([^)]*?kind=\"(\w+)\"", f.read_text(), re.S))
    assert len(kinds) > 25, kinds
    assert not kinds - set(alerts.KIND_SCOPE), f"kinds with no scope: {sorted(kinds - set(alerts.KIND_SCOPE))}"
    assert set(alerts.KIND_SCOPE.values()) <= {"health", "inboxes", "both"}


def test_unmapped_kind_falls_to_health_and_mailbox_alerts_belong_on_inboxes(cur):
    assert alerts.scope_of("something_new") == "health"
    for kind in ("watch_paused", "reply_drop", "complaint", "dns_broken", "no_mailbox", "spam_rate"):
        assert alerts.scope_of(kind) == "inboxes", kind
    for kind in ("sla_missed", "monitor", "budget", "crm_dead", "job_dead"):
        assert alerts.scope_of(kind) == "health", kind
    a = raise_(cur, "watch_paused", severity="urgent")
    z = raise_(cur, "never_heard_of_it")
    assert db.val(cur, "select scope from alerts where id = %s", a) == "inboxes"
    assert db.val(cur, "select scope from alerts where id = %s", z) == "health"
    assert z in [r["id"] for r in open_(cur, "health")] and z not in [r["id"] for r in open_(cur, "inboxes")]


def test_migration_scope_list_matches_the_code():
    sql = (Path(__file__).resolve().parents[1] / "migrations" / "0036_alert_scope.sql").read_text()
    listed = set(re.findall(r"'(\w+)'", sql.split("set scope = 'inboxes' where kind in (")[1].split(")")[0]))
    assert listed == {k for k, v in alerts.KIND_SCOPE.items() if v == "inboxes"}


# ---------------------------------------------------------------- grouping and ordering

def test_a_condition_that_raised_a_row_every_day_shows_once_and_resolves_together(cur, box):
    ids = [raise_(cur, "mailbox_warn", object_kind="mailbox", object_id=box["id"], dedup=f"mbwarn:{box['id']}:d{i}")
           for i in range(3)]
    for i, a in enumerate(ids):
        back_date(cur, a, i)
    other = raise_(cur, "mailbox_warn", object_kind="mailbox", object_id=box["id"] + 1000, dedup="mbwarn:other")
    rows = open_(cur)
    mine = [r for r in rows if r["object_id"] == box["id"]]
    assert len(mine) == 1 and mine[0]["repeats"] == 3 and mine[0]["id"] == ids[0]  # the newest stands for the three
    assert other in [r["id"] for r in rows]
    assert alerts.resolve(cur, ["mailbox_warn"], object_kind="mailbox", object_id=box["id"]) == 3
    rows = open_(cur)
    assert not [r for r in rows if r["object_id"] == box["id"]] and other in [r["id"] for r in rows]
    assert db.val(cur, "select count(*) from alerts where id = any(%s)", ids) == 3  # kept for the audit trail


def test_alerts_with_no_object_are_told_apart_by_who_and_title(cur, box):
    raise_(cur, "no_mailbox", target_user=box["user"], title="An SDR has no healthy mailbox")
    raise_(cur, "no_mailbox", target_user=box["user"], title="An SDR has no healthy mailbox")
    assert len([r for r in open_(cur) if r["kind"] == "no_mailbox"]) == 1


def test_open_alerts_are_ordered_urgent_warn_info_then_newest_and_counted(cur):
    w_old = raise_(cur, "mailbox_warn", object_kind="mailbox", object_id=9001)
    i = raise_(cur, "dns_fixed", severity="info", object_kind="domain", object_key="a.example")
    u = raise_(cur, "complaint", severity="urgent", object_kind="mailbox", object_id=9002)
    w_new = raise_(cur, "placement_hold", object_kind="mailbox", object_id=9003)
    back_date(cur, w_old, 3)
    view = alerts.open_view(cur, "inboxes")
    order = [r["id"] for r in view["alerts"] if r["id"] in (w_old, i, u, w_new)]
    assert order == [u, w_new, w_old, i]
    assert view["counts"]["urgent"] >= 1 and view["counts"]["warn"] >= 2 and view["counts"]["info"] >= 1
    assert view["counts"]["urgent"] == sum(1 for r in view["alerts"] if r["severity"] == "urgent")


# ---------------------------------------------------------------- what counts as open

def test_age_cutoffs(cur):
    event_warn = raise_(cur, "theme_failed", severity="warn")           # an event nobody acked
    event_info = raise_(cur, "owner_changed", severity="info")
    urgent_event = raise_(cur, "monitors_stale", severity="urgent")     # urgent never ages out
    state_warn = raise_(cur, "budget_wait", severity="warn")            # an event, not a state
    mb_warn = raise_(cur, "mailbox_warn", object_kind="mailbox", object_id=9100)  # a state: no cutoff
    unknown = raise_(cur, "send_unknown", object_kind="message", object_id=9101)  # until acked
    for a in (event_warn, event_info, urgent_event, state_warn, mb_warn, unknown):
        back_date(cur, a, 30)
    shown = {r["id"] for r in open_(cur, "health")} | {r["id"] for r in open_(cur, "inboxes")}
    assert urgent_event in shown and mb_warn in shown and unknown in shown
    assert not {event_warn, event_info, state_warn} & shown
    back_date(cur, event_warn, 13)
    assert event_warn in {r["id"] for r in open_(cur, "health")}


def test_ack_closes_the_alert_and_the_rest_of_its_condition(cur, box):
    ids = [raise_(cur, "complaint", severity="urgent", object_kind="mailbox", object_id=box["id"], dedup=f"c:{box['id']}:{i}")
           for i in range(2)]
    assert alerts.ack(cur, ids[0]) == 2
    assert not [r for r in open_(cur) if r["object_id"] == box["id"]]
    assert alerts.ack(cur, ids[0]) == 0 and alerts.ack(cur, -1) is None


def test_a_condition_that_returns_the_day_it_was_resolved_opens_again_without_a_second_post(cur, box):
    key = f"mbwarn:{box['id']}:same-day"
    a = raise_(cur, "mailbox_warn", object_kind="mailbox", object_id=box["id"], dedup=key)
    queued = db.val(cur, "select count(*) from jobs where kind = 'deliver_alert'")
    alerts.resolve(cur, ["mailbox_warn"], object_kind="mailbox", object_id=box["id"])
    assert raise_(cur, "mailbox_warn", object_kind="mailbox", object_id=box["id"], dedup=key) is None
    assert a in [r["id"] for r in open_(cur)]
    assert db.val(cur, "select count(*) from jobs where kind = 'deliver_alert'") == queued


# ---------------------------------------------------------------- the code that ends a condition resolves it

def test_a_paused_mailbox_is_open_until_it_resumes(cur, box):
    boss = db.val(cur, "insert into users (name, email, role) values ('Boss', %s, 'manager') returning id", f"b{id(cur)}@x.example")
    admin.set_mailbox(cur, box["id"], status="paused", reason="Bounce rate 3% over 14 days", by=boss)
    a = raise_(cur, "mailbox_paused", severity="urgent", object_kind="mailbox", object_id=box["id"])
    assert a in [r["id"] for r in open_(cur)]
    admin.set_mailbox(cur, box["id"], status="active", reason=None, by=boss)
    assert a not in [r["id"] for r in open_(cur)]
    assert db.val(cur, "select resolved_at is not null from alerts where id = %s", a)


def test_a_complaint_stays_after_the_mailbox_resumes_until_someone_acks(cur, box):
    boss = db.val(cur, "insert into users (name, email, role) values ('Boss', %s, 'manager') returning id", f"b{id(cur)}@x.example")
    a = raise_(cur, "complaint", severity="urgent", object_kind="mailbox", object_id=box["id"])
    admin.set_mailbox(cur, box["id"], status="paused", reason="complaint", by=boss)
    admin.set_mailbox(cur, box["id"], status="active", reason=None, by=boss)
    assert a in [r["id"] for r in open_(cur)]


def test_placement_recovering_resolves_its_alerts(cur, box):
    truth(cur, box["id"], gmail=0.97, outlook=0.1)
    sending.placement_tests(cur, {"mailbox_id": box["id"]})
    paused = [r for r in open_(cur) if r["kind"] == "placement_pause" and r["object_id"] == box["id"]]
    assert len(paused) == 1
    truth(cur, box["id"], gmail=1.0, outlook=1.0)
    sending.placement_tests(cur, {"mailbox_id": box["id"]})
    # A better result alone does not end the pause (resuming is manual); resuming does.
    assert [r for r in open_(cur) if r["object_id"] == box["id"] and r["kind"] == "placement_pause"]
    boss = db.val(cur, "insert into users (name, email, role) values ('Boss', %s, 'manager') returning id", f"c{id(cur)}@x.example")
    admin.set_mailbox(cur, box["id"], status="active", reason=None, by=boss)
    assert not [r for r in open_(cur) if r["object_id"] == box["id"] and r["kind"].startswith("placement")]


def test_placement_hold_clears_when_the_test_comes_back_healthy(cur, box, monkeypatch):
    monkeypatch.setattr(adapters.get(), "telemetry", FixedSeeds(gmail=19, outlook=13))
    sending.placement_tests(cur, {"mailbox_id": box["id"]})
    assert [r for r in open_(cur) if r["kind"] == "placement_hold" and r["object_id"] == box["id"]]
    monkeypatch.setattr(adapters.get(), "telemetry", FixedSeeds(gmail=20, outlook=20))
    sending.placement_tests(cur, {"mailbox_id": box["id"]})
    assert not [r for r in open_(cur) if r["kind"] == "placement_hold" and r["object_id"] == box["id"]]


class Spam:
    def __init__(self, rate):
        self.rate = rate

    def domains(self, cur, domains):
        return [DomainTelemetry(d, self.rate, "compliant") for d in domains]

    def placement(self, cur, mailbox):
        return []


def test_spam_alerts_name_the_domain_and_clear_when_the_rate_drops(cur, box, monkeypatch):
    monkeypatch.setattr(adapters.get(), "telemetry", Spam(0.004))
    sending.telemetry(cur, {})
    mine = [r for r in open_(cur) if r["object_key"] == box["domain"]]
    assert [(r["kind"], r["object_kind"], r["object_id"]) for r in mine] == [("spam_rate", "domain", None)]
    monkeypatch.setattr(adapters.get(), "telemetry", Spam(0.002))
    sending.telemetry(cur, {})
    assert [r["kind"] for r in open_(cur) if r["object_key"] == box["domain"]] == ["spam_rate_warn"]
    monkeypatch.setattr(adapters.get(), "telemetry", Spam(0.0004))
    sending.telemetry(cur, {})
    assert not [r for r in open_(cur) if r["object_key"] == box["domain"]]


def test_dns_alerts_carry_the_domain_and_the_fix_resolves_the_break(cur, box):
    sending.dns_check(cur, {})
    db.run(cur, "insert into sim_dns (domain, dkim_broken_from, dkim_broken_until) values (%s, app_now() - interval '1 hour', "
                "app_now() + interval '1 day')", box["domain"])
    sending.dns_check(cur, {})
    broken = [r for r in open_(cur) if r["kind"] == "dns_broken" and r["object_key"] == box["domain"]]
    assert len(broken) == 1 and broken[0]["object_kind"] == "domain" and broken[0]["severity"] == "urgent"
    db.run(cur, "delete from sim_dns where domain = %s", box["domain"])
    sending.dns_check(cur, {})
    mine = [r["kind"] for r in open_(cur) if r["object_key"] == box["domain"]]
    assert mine == ["dns_fixed"]  # the break is gone, the good news stays for its 14 days


def test_a_healthy_mailbox_found_resolves_no_mailbox(cur, box):
    a = raise_(cur, "no_mailbox", target_user=box["user"])
    assert alerts.resolve(cur, ["no_mailbox"], target_user=box["user"]) == 1
    assert a not in [r["id"] for r in open_(cur)]


def test_the_mailbox_bounce_rate_falling_resolves_the_warning(cur, box):
    a = raise_(cur, "mailbox_warn", object_kind="mailbox", object_id=box["id"])
    for _ in range(60):
        db.run(cur, "insert into deliveries (at, mailbox_id, event) values (app_now(), %s, 'sent')", box["id"])
    sending.mailbox_health(cur, {})
    assert a not in [r["id"] for r in open_(cur)]


# ---------------------------------------------------------------- the pages' data and the endpoint

@pytest.fixture(scope="module")
def client(database):
    from outbound.api.app import app
    return TestClient(app)


@pytest.fixture
def people(database):
    with db.tx() as cur:
        ids = {r: db.val(cur, "insert into users (name, email, role) values (%s, %s, %s) returning id",
                         f"Alert {r}", f"al-{r}-{os.urandom(3).hex()}@x.example", r) for r in ("manager", "gtm", "sdr")}
    yield {r: {"X-Acting-As": str(i)} for r, i in ids.items()}
    with db.tx() as cur:
        db.run(cur, "delete from alerts where dedup_key like 'tabtest:%%'")
        db.run(cur, "delete from jobs where kind = 'deliver_alert' and status = 'queued'")
        db.run(cur, "delete from audit_log where actor_id = any(%s)", list(ids.values()))
        db.run(cur, "delete from users where id = any(%s)", list(ids.values()))


def _make(kind, severity, key, **kw) -> int:
    with db.tx() as cur:
        return alerts.raise_alert(cur, kind=kind, severity=severity, channel="#outbound-ops", title=f"{kind} tabtest",
                                  body="b", dedup_key=f"tabtest:{key}", **kw)


def test_deliverability_carries_inbox_alerts_and_ops_carries_health_alerts(client, people):
    inbox = _make("complaint", "urgent", "i1", object_kind="mailbox", object_id=987654)
    health = _make("sla_missed", "urgent", "h1", object_kind="reply", object_id=987655)
    d = client.get("/api/deliverability", headers=people["manager"]).json()
    assert inbox in [a["id"] for a in d["alerts"]] and health not in [a["id"] for a in d["alerts"]]
    row = next(a for a in d["alerts"] if a["id"] == inbox)
    assert {"id", "at", "kind", "severity", "title", "body", "object_kind", "object_id", "area"} <= set(row)
    assert row["area"] == "inboxes" and d["alert_counts"]["urgent"] >= 1
    o = client.get("/api/ops", headers=people["manager"]).json()
    assert health in [a["id"] for a in o["alerts"]] and inbox not in [a["id"] for a in o["alerts"]]
    assert o["alert_counts"]["urgent"] >= 1 and "undelivered_alerts" in o


def test_the_ack_endpoint(client, people, monkeypatch):
    a = _make("complaint", "urgent", "a1", object_kind="mailbox", object_id=987660)
    assert client.post(f"/api/alerts/{a}/ack", headers=people["sdr"]).status_code == 403
    assert client.post("/api/alerts/999999999/ack", headers=people["gtm"]).status_code == 404
    from outbound.api import app as api
    monkeypatch.setattr(api, "CONFIG", dataclasses.replace(api.CONFIG, public_demo=True))
    r = client.post(f"/api/alerts/{a}/ack", headers=people["manager"])
    assert r.status_code == 403 and r.json()["detail"] == "Not available in the public demo."
    monkeypatch.undo()
    r = client.post(f"/api/alerts/{a}/ack", headers=people["manager"])
    assert r.status_code == 200 and r.json()["acked"] == 1
    assert a not in [x["id"] for x in client.get("/api/deliverability", headers=people["gtm"]).json()["alerts"]]
    with db.tx() as cur:
        assert db.val(cur, "select count(*) from audit_log where action = 'alert_acked' and object_id = %s", a) == 1


def test_views_deliverability_returns_the_shape_without_a_request(cur):
    d = views.deliverability(cur)
    assert isinstance(d["alerts"], list) and set(d["alert_counts"]) == {"urgent", "warn", "info"}
