#!/usr/bin/env bash
set -e

REP_USER=${REPLICATION_USER:-repuser}
REP_PASSWORD=${REPLICATION_PASSWORD:-rep_pass}

echo "Creating replication user: $REP_USER"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE $REP_USER WITH LOGIN REPLICATION PASSWORD '$REP_PASSWORD';
EOSQL

echo "Replication user created successfully."