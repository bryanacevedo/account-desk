#!/bin/sh
# Runs once while the image is built: creates the demo database inside the image, so a start (or a wake from
# sleep) only boots Postgres. WORLD (set by the Dockerfile, `world` unless built with --build-arg DEMO_WORLD=legacy)
# picks the source: the shared world's 3,000 accounts over its 91 days, or the desk's own generator for 90 days. Either
# takes about ten to fifteen minutes on a laptop and longer on a small builder; the database it leaves is about 125 MB.
set -e
WORLD="${WORLD:-world}"
export WORLD
PGBIN=$(ls -d /usr/lib/postgresql/*/bin | tail -1)
su postgres -c "$PGBIN/initdb -D /data -U postgres --auth=trust -E UTF8" >/dev/null
cat >> /data/postgresql.conf <<'CONF'
fsync = off
shared_buffers = 32MB
max_connections = 30
unix_socket_directories = '/tmp'
listen_addresses = '127.0.0.1'
CONF
su postgres -c "$PGBIN/pg_ctl -D /data -l /tmp/pg.log -w start"
su postgres -c "$PGBIN/createdb -h 127.0.0.1 -U postgres outbound"
if [ "$WORLD" = "world" ]; then
  /app/.venv/bin/python -m outbound demo
else
  /app/.venv/bin/python -m outbound demo 90
fi
# The image is only built when the demo shows every scenario (src/outbound/coverage.py): a scenario at zero means the
# live demo cannot show it, so the build fails here and Render keeps the last good image.
/app/.venv/bin/python -m outbound coverage
su postgres -c "$PGBIN/pg_ctl -D /data -m fast -w stop"
