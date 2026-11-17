import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

MAPPING_FILE = Path(__file__).parent / "mapping.json"

with open(MAPPING_FILE) as f:
    SHARD_MAP = json.load(f)

USER = os.getenv("SHARDS_USER", "postgres")
PASSWORD = os.getenv("SHARDS_PASSWORD", "postgres")
POOL_MIN = int(os.getenv("DB_POOL_MIN", 1))
POOL_MAX = int(os.getenv("DB_POOL_MAX", 10))

_pools: dict[str, ConnectionPool] = {}

def _get_pool(shard_key: str) -> ConnectionPool:
    if shard_key not in _pools:
        info = SHARD_MAP[shard_key]
        conninfo = (
            f"postgresql://{USER}:{PASSWORD}@"
            f"{info['host']}:{info['port']}/{info['dbname']}"
        )
        _pools[shard_key] = ConnectionPool(
            conninfo=conninfo, min_size=POOL_MIN, max_size=POOL_MAX,
            kwargs={"row_factory": dict_row}, open=True,
        )
    return _pools[shard_key]

def shard_for_id(entity_id: str) -> str:
    last = entity_id[-1].lower()
    if last not in SHARD_MAP:
        raise ValueError(f"Invalid shard key: {last}")
    return last

def new_plan_id() -> str:
    return str(uuid.uuid4())

def new_location_id_for_plan(plan_id: str) -> str:
    shard_key = shard_for_id(plan_id)
    raw = str(uuid.uuid4())
    return raw[:-1] + shard_key

@contextmanager
def get_cursor_for(entity_id: str, commit: bool = False):
    shard_key = shard_for_id(entity_id)
    pool = _get_pool(shard_key)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur
            if commit:
                conn.commit()

@contextmanager
def get_cursor_for_shard(shard_key: str, commit: bool = False):
    pool = _get_pool(shard_key)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur
            if commit:
                conn.commit()