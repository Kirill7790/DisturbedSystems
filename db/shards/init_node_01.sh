#!/bin/bash
set -e

echo "==> Initializing postgres_01 (db_4..db_7)"

for db in db_4 db_5 db_6 db_7; do
    echo "Creating database $db"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE DATABASE $db;
EOSQL
    # Створюємо схему в кожній БД
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" -f /docker-entrypoint-initdb.d/schema.sql
done

echo "==> postgres_01 initialized"