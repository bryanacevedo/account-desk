"""Command line: python -m outbound <command>

  migrate            apply migrations
  demo [days]        rebuild the demo database from scratch and simulate N days (default 90). With WORLD=world it is
                     built from the shared world's slice and runs from the cut to the world's now (default 91 days
                     and 2 hours); an explicit N runs N days from the cut.
  simulate [days]    simulate N more days on the current database
  serve              run the web app and API (and the worker in-process)
  monitors           run every monitor once and print the result
  init FILE          set up a real desk from a JSON file (see examples/desk.example.json)
  import KIND FILE   import accounts or people from a CSV file
  mcp                read-only MCP server on stdio (why an account is hot, what is waiting, how a play did)
  themes backfill    file every learning not yet under a theme, then look for play suggestions
  coverage           count every scenario the built demo shows; exits 1 if any is at zero
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone

from . import db
from .config import CONFIG

# 90 days, so the 90-day window of call notes behind play suggestions is full. 90 days later is 2026-11-11.
DEMO_START = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
WORLD_JOURNAL = "world/journal.jsonl"


def demo_crm(journal_path=WORLD_JOURNAL):
    """The CRM for a world demo build: the journal's account_desk steps replayed, or None (keep the simulated CRM) when
    the journal is absent or holds no step from this desk."""
    from pathlib import Path
    from .adapters import recorded
    if not Path(journal_path).exists() or not recorded.read_steps(journal_path):
        return None
    return recorded.RecordedCrm.from_journal(journal_path)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cmd = argv[1] if len(argv) > 1 else "serve"
    CONFIG.validate()
    if cmd == "migrate":
        print(db.migrate())
    elif cmd == "mcp":
        logging.getLogger().setLevel(logging.WARNING)  # stdout carries the protocol
        from . import mcp_server
        mcp_server.main()
    elif cmd == "init":
        from . import setup_desk
        db.migrate()
        cfg = setup_desk.DeskConfig.model_validate_json(open(argv[2]).read())
        with db.tx() as cur:
            print(json.dumps(setup_desk.init(cur, cfg)))
    elif cmd == "import":
        from . import scoring, setup_desk  # noqa: F401 register the rescore handler
        kind, path = argv[2], argv[3]
        fn = {"accounts": setup_desk.import_accounts, "people": setup_desk.import_people}[kind]
        with db.tx() as cur:
            print(json.dumps(fn(cur, open(path, encoding="utf-8-sig").read()), indent=1))
    elif cmd == "demo":
        from . import monitors, outreach, pipeline, replies, scheduler, scoring, sending, suggestions, themes  # noqa: F401 register handlers
        from . import integration
        from .sim import runner
        mode = integration.world_mode()
        start, days, extra_hours = DEMO_START, int(argv[2]) if len(argv) > 2 else 90, 0
        if mode == "world":
            from .sim import world_load
            start, end = world_load.window()
            span = end - start
            if len(argv) > 2:
                days = int(argv[2])
            else:
                days, extra_hours = span.days, span.seconds // 3600
        replay = demo_crm() if mode == "world" and CONFIG.mode != "live" else None
        if replay is not None:
            from . import adapters
            adapters.get().crm = replay      # the whole build, including the first read of the CRM, is served from the journal
        t0 = time.time()
        runner.reset()
        runner.deterministic_database(True)  # the same seed builds the same desk (runner.deterministic_database)
        info = runner.setup(start=start)
        totals = runner.run(days, extra_hours=extra_hours)
        # Learnings are filed as they arrive; the backfill catches any left over and looks for patterns once more.
        totals["learnings_filed_after"] = themes.backfill()
        runner.deterministic_database(False)
        if replay is not None:
            replay.finish()                  # JournalMismatch if any recorded step was never asked for
        print(json.dumps({"world": info, "world_mode": mode, "totals": totals, "seconds": round(time.time() - t0, 1)},
                         default=str))
        db.close()
    elif cmd == "themes" and len(argv) > 2 and argv[2] == "backfill":
        from . import pipeline, themes  # noqa: F401 register handlers
        print(json.dumps({"filed": themes.backfill()}))
    elif cmd == "simulate":
        from . import monitors, outreach, pipeline, replies, scheduler, scoring, sending, suggestions, themes  # noqa: F401
        from .sim import runner
        print(runner.run(int(argv[2]) if len(argv) > 2 else 1, slow_last_days=0, idle_hours=0))
    elif cmd == "coverage":
        from . import coverage
        return coverage.main()
    elif cmd == "monitors":
        from . import monitors
        with db.tx() as cur:
            print(json.dumps(monitors.run_all(cur, {}), indent=2, default=str))
    elif cmd == "serve":
        import uvicorn

        # Behind a proxy the client's address is the first X-Forwarded-For hop, trusted only from the proxies named in
        # FORWARDED_ALLOW_IPS (default 127.0.0.1, never everyone).
        uvicorn.run("outbound.api.app:app", host=__import__("os").environ.get("HOST", "127.0.0.1"),
                    port=int(__import__("os").environ.get("PORT", "8800")), log_level="info",
                    proxy_headers=True, forwarded_allow_ips=CONFIG.forwarded_allow_ips)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
