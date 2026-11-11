#!/bin/sh
# Start the Postgres that the image already holds the demo in, then serve.
set -e
PGBIN=$(ls -d /usr/lib/postgresql/*/bin | tail -1)
su postgres -c "$PGBIN/pg_ctl -D /data -l /tmp/pg.log -w start"
exec /app/.venv/bin/python -m outbound serve
