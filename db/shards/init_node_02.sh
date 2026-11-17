#!/bin/bash
set -e

echo "==> Initializing postgres_02 (db_8..db_b)"

for db in db_8 db_9 db_a db_b; do
    echo "Creating database $db"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE DATABASE $db;
EOSQL
    # Створюємо схему в кожній БД
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" -f /docker-entrypoint-initdb.d/schema.sql
done

echo "==> postgres_01 initialized"