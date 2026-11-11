"""Command line: python -m outbound <command>

  migrate            apply migrations
  demo [days]        rebuild the demo database from scratch and simulate N days (default 45)
  simulate [days]    simulate N more days on the current database
  serve              run the web app and API (and the worker in-process)
  monitors           run every monitor once and print the result
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone

from . import db
from .config import CONFIG

DEMO_START = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)  # 60 days later is 2026-11-11


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cmd = argv[1] if len(argv) > 1 else "serve"
    CONFIG.validate()
    if cmd == "migrate":
        print(db.migrate())
    elif cmd == "demo":
        from . import monitors, outreach, pipeline, replies, scheduler, scoring, sending  # noqa: F401 register handlers
        from .sim import runner
        days = int(argv[2]) if len(argv) > 2 else 60
        t0 = time.time()
        runner.reset()
        info = runner.setup(start=DEMO_START)
        totals = runner.run(days)
        print(json.dumps({"world": info, "totals": totals, "seconds": round(time.time() - t0, 1)}))
        db.close()
    elif cmd == "simulate":
        from . import monitors, outreach, pipeline, replies, scheduler, scoring, sending  # noqa: F401
        from .sim import runner
        print(runner.run(int(argv[2]) if len(argv) > 2 else 1, slow_last_days=0, idle_hours=0))
    elif cmd == "monitors":
        from . import monitors
        with db.tx() as cur:
            print(json.dumps(monitors.run_all(cur, {}), indent=2, default=str))
    elif cmd == "serve":
        import uvicorn
        uvicorn.run("outbound.api.app:app", host=__import__("os").environ.get("HOST", "127.0.0.1"),
                    port=int(__import__("os").environ.get("PORT", "8800")), log_level="info")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
