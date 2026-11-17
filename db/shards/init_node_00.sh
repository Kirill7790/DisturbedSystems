#!/bin/bash
set -e

echo "==> Initializing postgres_00 (db_0..db_3)"

for db in db_0 db_1 db_2 db_3; do
    echo "Creating database $db"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE DATABASE $db;
EOSQL
    # Створюємо схему в кожній БД
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" -f /docker-entrypoint-initdb.d/schema.sql
done

echo "==> postgres_00 initialized"