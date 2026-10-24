#!/usr/bin/env bash
set -e

if [ -s "$PGDATA/PG_VERSION" ]; then
    echo "Database already initialized. Starting standby..."
    exec docker-entrypoint.sh "$@"
fi

echo "Initializing physical replica from master..."

until pg_isready -h postgres -p 5432 -U repuser; do
  echo "Waiting for master to be ready..."
  sleep 2
done

pg_basebackup -h postgres -p 5432 -U repuser -D "$PGDATA" -Fp -Xs -P -R

echo "Physical replica initialized. Starting standby..."
exec docker-entrypoint.sh "$@"