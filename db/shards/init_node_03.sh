#!/bin/bash
set -e

echo "==> Initializing postgres_03 (db_c..db_f)"

for db in db_c db_d db_e db_f; do
    echo "Creating database $db"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE DATABASE $db;
EOSQL
    # Створюємо схему в кожній БД
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" -f /docker-entrypoint-initdb.d/schema.sql
done

echo "==> postgres_01 initialized"