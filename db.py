from contextlib import contextmanager
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from config import Config

pool = ConnectionPool(
    conninfo=Config.DATABASE_URL,
    min_size=Config.DB_POOL_MIN,
    max_size=Config.DB_POOL_MAX,
    kwargs={"row_factory": dict_row},
    open=True,
)

@contextmanager
def get_conn():
    with pool.connection() as conn:
        yield conn

@contextmanager
def get_cursor(commit: bool = False):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur
            if commit:
                conn.commit()