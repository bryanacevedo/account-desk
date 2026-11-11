"""The MCP server answers from the desk, reads no money, and cannot write."""
from __future__ import annotations

import asyncio
import json

import psycopg
import pytest

from outbound import db, mcp_server


def test_every_tool_is_read_only(world):
    tools = asyncio.run(mcp_server.server.list_tools())
    names = {t.name for t in tools}
    assert {"find_accounts", "why_hot", "waiting_on", "play_report", "results_summary"} <= names
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_why_hot_explains_an_account_in_a_play(world):
    with db.tx() as cur:
        domain = db.val(cur, """select a.primary_domain from account_plays ap join accounts a on a.id = ap.account_id
                                where ap.arm = 'treated' and ap.state in ('active','engaged','meeting') limit 1""")
    out = mcp_server.why_hot(domain)
    assert out["account"]["primary_domain"] == domain
    assert out["current_play"] and out["latest_signals"] and out["scores"]["priority"] is not None


def test_waiting_on_and_unknowns_say_so(world):
    with db.tx() as cur:
        email = db.val(cur, "select email from users where role = 'sdr' order by id limit 1")
    assert "replies_to_answer" in mcp_server.waiting_on(email)
    assert "error" in mcp_server.waiting_on("nobody@nowhere.example")
    assert "error" in mcp_server.why_hot("no-such-company.example")


def test_no_money_anywhere(world):
    with db.tx() as cur:
        play = db.val(cur, "select name from plays order by id limit 1")
    text = json.dumps([mcp_server.results_summary(), mcp_server.play_report(play)])
    assert "cents" not in text and "amount" not in text


def test_a_tool_cannot_write(world):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        mcp_server._read(lambda cur: db.run(cur, "update settings set value = '1' where key = 'kill_switch'"))
