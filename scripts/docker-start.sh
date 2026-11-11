#!/bin/sh
# Start Postgres inside the container, build the demo, then serve. The container user is root; Postgres runs as postgres.
set -e
PGBIN=$(ls -d /usr/lib/postgresql/*/bin | tail -1)
if [ ! -f /data/PG_VERSION ]; then
  su postgres -c "$PGBIN/initdb -D /data -U postgres --auth=trust -E UTF8" >/dev/null
  echo "fsync = off" >> /data/postgresql.conf
  echo "shared_buffers = 32MB" >> /data/postgresql.conf
  echo "max_connections = 30" >> /data/postgresql.conf
  echo "unix_socket_directories = '/tmp'" >> /data/postgresql.conf
  echo "listen_addresses = '127.0.0.1'" >> /data/postgresql.conf
fi
su postgres -c "$PGBIN/pg_ctl -D /data -l /tmp/pg.log -w start"
su postgres -c "$PGBIN/createdb -h 127.0.0.1 -U postgres outbound" 2>/dev/null || true
/app/.venv/bin/python -m outbound demo 60
exec /app/.venv/bin/python -m outbound serve
