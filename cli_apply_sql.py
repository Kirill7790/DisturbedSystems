#!/usr/bin/env python3

import argparse
import json
import os
import sys
import psycopg
from psycopg import errors

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPING_FILE = os.path.join(BASE_DIR, "mapping.json")

USER = os.getenv("SHARDS_USER", "postgres")
PASSWORD = os.getenv("SHARDS_PASSWORD", "postgres")


def load_mapping():
    if not os.path.exists(MAPPING_FILE):
        print(f"Помилка: файл {MAPPING_FILE} не знайдено.")
        sys.exit(1)
    with open(MAPPING_FILE, "r") as f:
        return json.load(f)


def apply_script_to_all(sql_script: str, mapping: dict):
    connections = {}
    cursors = {}

    print(f"Встановлення з'єднань з {len(mapping)} базами даних...")

    try:
        for shard_key, info in mapping.items():
            conninfo = f"postgresql://{USER}:{PASSWORD}@{info['host']}:{info['port']}/{info['dbname']}"
            conn = psycopg.connect(conninfo, autocommit=False)
            connections[shard_key] = conn
            cursors[shard_key] = conn.cursor()
    except Exception as e:
        print(f"Помилка підключення до БД {shard_key}: {e}")
        for conn in connections.values():
            conn.close()
        sys.exit(1)

    print("Усі з'єднання встановлено. Початок виконання...")

    success = True
    failed_shard = None

    try:
        for shard_key, cur in cursors.items():
            try:
                cur.execute(sql_script)
                print(f"Успішно виконано на {shard_key} ({mapping[shard_key]['dbname']})")
            except Exception as e:
                print(f"ПОМИЛКА на {shard_key} ({mapping[shard_key]['dbname']}): {e}")
                success = False
                failed_shard = shard_key
                break
    except Exception as e:
        print(f"Критична помилка під час виконання: {e}")
        success = False

    if success:
        print("Усі 16 БД успішні. Виконується COMMIT...")
        for shard_key, conn in connections.items():
            try:
                conn.commit()
            except Exception as e:
                print(f"Помилка при COMMIT на {shard_key}: {e}")
        print("Транзакцію успішно зафіксовано на всіх шардах!")
    else:
        print(f"Збій на шарді {failed_shard}. Виконується ROLLBACK на всіх БД...")
        for shard_key, conn in connections.items():
            try:
                conn.rollback()
            except Exception:
                pass
        print("Транзакцію скасовано. Жодних змін не збережено.")
        sys.exit(1)

    for conn in connections.values():
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Apply SQL script to all shards.")
    parser.add_argument("file", help="Шлях до SQL-файлу (наприклад, migration.sql)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Файл {args.file} не знайдено.")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        sql_script = f.read()

    mapping = load_mapping()
    apply_script_to_all(sql_script, mapping)


if __name__ == "__main__":
    main()