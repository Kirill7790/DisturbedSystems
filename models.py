from db import get_cursor
from errors import ApiError


PLAN_FIELDS = ("title", "description", "start_date", "end_date",
               "budget", "currency", "is_public")

def list_plans(limit: int, offset: int, is_public: bool | None = None):
    with get_cursor() as cur:
        where, params = "", []
        if is_public is not None:
            where = "WHERE is_public = %s"
            params.append(is_public)
        cur.execute(
            f"""SELECT * FROM travel_plans {where}
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s""",
            (*params, limit, offset),
        )
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) AS cnt FROM travel_plans {where}", params)
        total = cur.fetchone()["cnt"]
    return rows, total

def get_plan(plan_id: str, with_locations: bool = True):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM travel_plans WHERE id = %s", (plan_id,))
        plan = cur.fetchone()
        if not plan:
            return None
        if with_locations:
            cur.execute(
                """SELECT * FROM locations
                   WHERE travel_plan_id = %s
                   ORDER BY visit_order ASC""",
                (plan_id,),
            )
            plan["locations"] = cur.fetchall()
        return plan

def create_plan(data: dict) -> dict:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO travel_plans
               (title, description, start_date, end_date,
                budget, currency, is_public)
               VALUES (%(title)s, %(description)s, %(start_date)s, %(end_date)s,
                       %(budget)s, %(currency)s, %(is_public)s)
               RETURNING *""",
            data,
        )
        return cur.fetchone()

def update_plan(plan_id: str, data: dict, expected_version: int) -> dict:
    update_fields = {k: v for k, v in data.items() if k in PLAN_FIELDS and v is not None}
    if not update_fields:
        raise ApiError("Nothing to update", 400)

    set_clause = ", ".join(f"{k} = %({k})s" for k in update_fields)
    params = {**update_fields, "id": plan_id, "ver": expected_version}

    with get_cursor(commit=True) as cur:
        cur.execute(
            f"""UPDATE travel_plans
                SET {set_clause},
                    version = version + 1,
                    updated_at = NOW()
                WHERE id = %(id)s AND version = %(ver)s
                RETURNING *""",
            params,
        )
        row = cur.fetchone()
        if row:
            return row

        cur.execute("SELECT version FROM travel_plans WHERE id = %s", (plan_id,))
        existing = cur.fetchone()
        if not existing:
            raise ApiError("Travel plan not found", 404)
        raise ApiError(
            "Version conflict",
            409,
            details={"expected": expected_version, "actual": existing["version"]},
        )

def delete_plan(plan_id: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM travel_plans WHERE id = %s RETURNING id", (plan_id,))
        if not cur.fetchone():
            raise ApiError("Travel plan not found", 404)


LOCATION_FIELDS = ("name", "address", "latitude", "longitude",
                   "visit_order", "arrival_date", "departure_date",
                   "budget", "notes")

def add_location(plan_id: str, data: dict, expected_version: int) -> dict:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT version FROM travel_plans WHERE id = %s FOR UPDATE",
            (plan_id,),
        )
        plan = cur.fetchone()
        if not plan:
            raise ApiError("Travel plan not found", 404)

        if plan["version"] != expected_version:
            raise ApiError(
                "Version conflict",
                409,
                details={"expected": expected_version, "actual": plan["version"]},
            )

        cols = ["travel_plan_id"] + [f for f in LOCATION_FIELDS if f in data and data[f] is not None]
        vals = [plan_id] + [data[f] for f in LOCATION_FIELDS if f in data and data[f] is not None]
        placeholders = ", ".join(["%s"] * len(cols))

        try:
            cur.execute(
                f"""INSERT INTO locations ({', '.join(cols)})
                    VALUES ({placeholders})
                    RETURNING *""",
                vals,
            )
            location = cur.fetchone()
        except Exception as e:
            if "unique_plan_order" in str(e):
                raise ApiError("visit_order already taken in this plan", 409)
            raise

        cur.execute(
            """UPDATE travel_plans
               SET version = version + 1, updated_at = NOW()
               WHERE id = %s
               RETURNING version""",
            (plan_id,),
        )
        plan = cur.fetchone()
        location["plan_version"] = plan["version"]  # ← додати до локації
        return location

def get_location(location_id: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM locations WHERE id = %s", (location_id,))
        return cur.fetchone()

def update_location(location_id: str, data: dict, expected_version: int) -> dict:
    with get_cursor(commit=True) as cur:
        # 1. Дізнаємось план цієї локації й блокуємо його
        cur.execute(
            "SELECT travel_plan_id FROM locations WHERE id = %s",
            (location_id,),
        )
        loc = cur.fetchone()
        if not loc:
            raise ApiError("Location not found", 404)
        plan_id = loc["travel_plan_id"]

        cur.execute(
            "SELECT version FROM travel_plans WHERE id = %s FOR UPDATE",
            (plan_id,),
        )
        plan = cur.fetchone()

        if plan["version"] != expected_version:
            raise ApiError(
                "Version conflict",
                409,
                details={"expected": expected_version, "actual": plan["version"]},
            )

        fields = {k: v for k, v in data.items()
                  if k in LOCATION_FIELDS and v is not None}
        if not fields:
            raise ApiError("Nothing to update", 400)

        set_clause = ", ".join(f"{k} = %({k})s" for k in fields)
        params = {**fields, "id": location_id}

        try:
            cur.execute(
                f"""UPDATE locations
                    SET {set_clause}
                    WHERE id = %(id)s
                    RETURNING *""",
                params,
            )
        except Exception as e:
            if "unique_plan_order" in str(e):
                raise ApiError("visit_order already taken in this plan", 409)
            raise

        updated = cur.fetchone()

        cur.execute(
            """UPDATE travel_plans
               SET version = version + 1, updated_at = NOW()
               WHERE id = %s
               RETURNING version""",
            (plan_id,),
        )
        new_ver = cur.fetchone()["version"]
        updated["plan_version"] = new_ver
        return updated

def delete_location(location_id: str, expected_version: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT travel_plan_id FROM locations WHERE id = %s", (location_id,))
        loc = cur.fetchone()
        if not loc:
            raise ApiError("Location not found", 404)
        plan_id = loc["travel_plan_id"]

        cur.execute(
            "SELECT version FROM travel_plans WHERE id = %s FOR UPDATE",
            (plan_id,),
        )
        plan = cur.fetchone()
        if plan["version"] != expected_version:
            raise ApiError(
                "Version conflict",
                409,
                details={"expected": expected_version, "actual": plan["version"]},
            )

        cur.execute("DELETE FROM locations WHERE id = %s", (location_id,))
        cur.execute(
            """UPDATE travel_plans
               SET version = version + 1, updated_at = NOW()
               WHERE id = %s""",
            (plan_id,),
        )
def plan_exists(plan_id: str) -> bool:
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM travel_plans WHERE id = %s", (plan_id,))
        return cur.fetchone() is not None

def location_exists(location_id: str) -> bool:
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM locations WHERE id = %s", (location_id,))
        return cur.fetchone() is not None