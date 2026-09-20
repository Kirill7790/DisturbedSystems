import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:1234@localhost:5432/travel_db",
    )
    DB_POOL_MIN = 2
    DB_POOL_MAX = 20
    JSON_SORT_KEYS = False