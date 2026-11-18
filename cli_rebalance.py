#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
import psycopg

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPING_FILE = os.path.join(BASE_DIR, "mapping.json")

USER = os.getenv("SHARDS_USER", "postgres")
PASSWORD = os.getenv("SHARDS_PASSWORD", "postgres")


def get_conninfo(host, port, dbname):
    return f"postgresql://{USER}:{PASSWORD}@{host}:{port}/{dbname}"


def get_admin_conninfo(host, port):
    return get_conninfo(host, port, "postgres")


def load_mapping():
    with open(MAPPING_FILE, "r") as f:
        return json.load(f)


def save_mapping(mapping):
    with open(MAPPING_FILE, "w") as f:
        json.dump(mapping, f, indent=2)


def migrate_db(shard_key: str, source_host: str, target_host: str):
    source_db = f"db_{shard_key}"
    target_db = f"db_{shard_key}"

    print(f"\nПочаток міграції {source_db} з {source_host} на {target_host}...")

    print(f"Створення бази {target_db} на {target_host}...")
    try:
        with psycopg.connect(get_admin_conninfo(target_host, 5432), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {target_db} WITH (FORCE);")
                cur.execute(f"CREATE DATABASE {target_db};")
    except Exception as e:
        print(f"Помилка створення бази: {e}")
        sys.exit(1)

    print(f"Створення схеми (таблиць)...")
    with psycopg.connect(get_conninfo(source_host, 5432, source_db)) as src_conn, \
            psycopg.connect(get_conninfo(target_host, 5432, target_db)) as tgt_conn:

        with src_conn.cursor() as src_cur, tgt_conn.cursor() as tgt_cur:
            src_cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [row[0] for row in src_cur.fetchall()]

            for table in tables:
                src_cur.execute(
                    f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}'")
                cols = src_cur.fetchall()
                cols_def = ", ".join([f"{c[0]} {c[1]}" for c in cols])
                tgt_cur.execute(f"CREATE TABLE {table} ({cols_def});")
        tgt_conn.commit()

    print(f"Налаштування логічної реплікації...")
    pub_name = f"pub_{shard_key}"

    with psycopg.connect(get_conninfo(source_host, 5432, source_db), autocommit=True) as src_conn:
        with src_conn.cursor() as cur:
            cur.execute(f"DROP PUBLICATION IF EXISTS {pub_name};")
            cur.execute(f"CREATE PUBLICATION {pub_name} FOR ALL TABLES;")

    with psycopg.connect(get_conninfo(target_host, 5432, target_db), autocommit=True) as tgt_conn:
        with tgt_conn.cursor() as cur:
            cur.execute(f"DROP SUBSCRIPTION IF EXISTS {pub_name};")
            sub_conninfo = get_conninfo(source_host, 5432, source_db)
            cur.execute(f"CREATE SUBSCRIPTION {pub_name} CONNECTION '{sub_conninfo}' PUBLICATION {pub_name};")

    print(f" Синхронізація даних (очікування 5 секунд)...")
    time.sleep(5)

    print(f"Блокування таблиць і перемикання трафіку...")
    with psycopg.connect(get_conninfo(source_host, 5432, source_db)) as src_conn:
        with src_conn.cursor() as cur:
            for t in tables:
                cur.execute(f"LOCK TABLE {t} IN ACCESS EXCLUSIVE MODE;")

            mapping = load_mapping()
            mapping[shard_key]["host"] = target_host
            save_mapping(mapping)
            print(f"mapping.json оновлено: {shard_key} -> {target_host}")

            cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;")

    print(f"Відключення реплікації...")
    with psycopg.connect(get_conninfo(target_host, 5432, target_db), autocommit=True) as tgt_conn:
        with tgt_conn.cursor() as cur:
            cur.execute(f"DROP SUBSCRIPTION {pub_name};")

    print(f"Міграцію {source_db} успішно завершено!")


def main():
    parser = argparse.ArgumentParser(description="Rebalance databases between shards.")
    parser.add_argument("shard", help="Ключ шарду (наприклад, 0, a, f)")
    parser.add_argument("target_host", help="Новий хост (наприклад, postgres_03)")
    args = parser.parse_args()

    mapping = load_mapping()
    if args.shard not in mapping:
        print(f"Шард {args.shard} не знайдено в mapping.json")
        sys.exit(1)

    current_host = mapping[args.shard]["host"]
    if current_host == args.target_host:
        print(f"База {args.shard} вже знаходиться на {args.target_host}")
        sys.exit(0)

    migrate_db(args.shard, current_host, args.target_host)


if __name__ == "__main__":
    main()