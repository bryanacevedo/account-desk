#!/usr/bin/env bash
# A private Postgres for local runs and tests, kept in .data/pg. Uses the Postgres binaries already installed.
set -euo pipefail
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
cd "$(dirname "$0")/.."
DATA=.data/pg; PORT="${PGPORT_LOCAL:-54329}"
command -v pg_ctl >/dev/null || { echo "Postgres binaries not found. Install Postgres 18, or set DATABASE_URL, or run: docker compose up" >&2; exit 1; }
if [ ! -f "$DATA/PG_VERSION" ]; then
  mkdir -p "$DATA"
  initdb -D "$DATA" -U postgres --auth=trust -E UTF8 >/dev/null
  echo "listen_addresses = 'localhost'" >> "$DATA/postgresql.conf"
  echo "port = $PORT" >> "$DATA/postgresql.conf"
  echo "unix_socket_directories = ''" >> "$DATA/postgresql.conf"
  echo "fsync = off" >> "$DATA/postgresql.conf"
fi
case "${1:-start}" in
  start) pg_ctl -D "$DATA" status >/dev/null 2>&1 || pg_ctl -D "$DATA" -l .data/pg.log -w start >/dev/null
         psql -h localhost -p "$PORT" -U postgres -tAc "select 1 from pg_database where datname='outbound'" | grep -q 1 \
           || createdb -h localhost -p "$PORT" -U postgres outbound
         echo "postgres://postgres@localhost:$PORT/outbound" ;;
  stop) pg_ctl -D "$DATA" -m fast stop ;;
esac
