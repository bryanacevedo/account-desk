#!/bin/sh
# Runs once while the image is built: creates the demo database inside the image, so a start (or a wake from
# sleep) only boots Postgres. The 3,000-account, 90-day simulation takes about ten minutes on a laptop and longer on
# a small builder; the database it leaves is about 125 MB.
set -e
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
/app/.venv/bin/python -m outbound demo 90
su postgres -c "$PGBIN/pg_ctl -D /data -m fast -w stop"
