import sharding
from errors import ApiError


PLAN_FIELDS = ("title", "description", "start_date", "end_date",
               "budget", "currency", "is_public")

def list_plans(limit: int, offset: int, is_public: bool | None = None):
    all_rows = []
    total = 0

    where, params = "", []
    if is_public is not None:
        where = "WHERE is_public = %s"
        params.append(is_public)

    for shard_key in sharding.SHARD_MAP:
        try:
            with sharding.get_cursor_for_shard(shard_key) as cur:
                cur.execute(
                    f"""SELECT id, title, description, start_date, end_date,
                               budget, currency, is_public, version,
                               created_at, updated_at,
                               COUNT(*) OVER() AS total_count
                        FROM travel_plans {where}
                        ORDER BY updated_at DESC""",
                    params,
                )
                rows = cur.fetchall()
                if rows:
                    total += rows[0]["total_count"]
                    for r in rows:
                        r.pop("total_count", None)
                    all_rows.extend(rows)
        except Exception:
            continue

    all_rows.sort(key=lambda x: x["updated_at"], reverse=True)
    paginated = all_rows[offset : offset + limit]
    return paginated, total

def get_plan(plan_id: str, with_locations: bool = True):
    with sharding.get_cursor_for(plan_id) as cur:
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
    plan_id = sharding.new_plan_id()          # ← генеруємо ID в Python
    shard_key = sharding.shard_for_id(plan_id)  # ← визначаємо шард

    with sharding.get_cursor_for_shard(shard_key, commit=True) as cur:
        cur.execute(
            """INSERT INTO travel_plans
               (id, title, description, start_date, end_date,
                budget, currency, is_public, version)
               VALUES (%(id)s, %(title)s, %(description)s, %(start_date)s, %(end_date)s,
                       %(budget)s, %(currency)s, %(is_public)s, 1)
               RETURNING *""",
            {**data, "id": plan_id},
        )
        return cur.fetchone()

def update_plan(plan_id: str, data: dict, expected_version: int) -> dict:
    update_fields = {k: v for k, v in data.items()
                     if k in PLAN_FIELDS and v is not None}
    if not update_fields:
        raise ApiError("Nothing to update", 400)

    set_clause = ", ".join(f"{k} = %({k})s" for k in update_fields)
    params = {**update_fields, "id": plan_id, "ver": expected_version}

    with sharding.get_cursor_for(plan_id, commit=True) as cur:
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

def delete_plan(plan_id: str) -> None:
    with sharding.get_cursor_for(plan_id, commit=True) as cur:
        cur.execute("DELETE FROM travel_plans WHERE id = %s RETURNING id", (plan_id,))
        if not cur.fetchone():
            raise ApiError("Travel plan not found", 404)


LOCATION_FIELDS = ("name", "address", "latitude", "longitude",
                   "visit_order", "arrival_date", "departure_date",
                   "budget", "notes")


def add_location(plan_id: str, data: dict, expected_version: int) -> dict:
    with sharding.get_cursor_for(plan_id, commit=True) as cur:
        cur.execute(
            "SELECT version FROM travel_plans WHERE id = %s FOR UPDATE",
            (plan_id,),
        )
        plan = cur.fetchone()
        if not plan:
            raise ApiError("Travel plan not found", 404)

        if plan["version"] != expected_version:
            raise ApiError(
                "Version conflict", 409,
                details={"expected": expected_version, "actual": plan["version"]},
            )

        location_id = sharding.new_location_id_for_plan(plan_id)

        cols = ["id", "travel_plan_id"] + [
            f for f in LOCATION_FIELDS if f in data and data[f] is not None
        ]
        vals = [location_id, plan_id] + [
            data[f] for f in LOCATION_FIELDS if f in data and data[f] is not None
        ]
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
        new_plan = cur.fetchone()
        location["plan_version"] = new_plan["version"]

        return location

def get_location(plan_id: str, location_id: str) -> dict | None:
    with sharding.get_cursor_for(plan_id) as cur:
        cur.execute("SELECT * FROM locations WHERE id = %s", (location_id,))
        return cur.fetchone()


def update_location(location_id: str, data: dict, expected_version: int) -> dict:
    with sharding.get_cursor_for(location_id, commit=True) as cur:
        cur.execute(
            """SELECT l.travel_plan_id, tp.version AS plan_version
               FROM locations l
               JOIN travel_plans tp ON tp.id = l.travel_plan_id
               WHERE l.id = %s
               FOR UPDATE OF tp""",
            (location_id,),
        )
        row = cur.fetchone()

        if not row:
            raise ApiError("Location not found", 404)

        plan_id = row["travel_plan_id"]

        if row["plan_version"] != expected_version:
            raise ApiError(
                "Version conflict", 409,
                details={"expected": expected_version, "actual": row["plan_version"]},
            )

        fields = {k: v for k, v in data.items()
                  if k in LOCATION_FIELDS and v is not None}
        if not fields:
            raise ApiError("Nothing to update", 400)

        set_clause = ", ".join(f"{k} = %({k})s" for k in fields)
        params = {**fields, "id": location_id, "plan_id": plan_id}

        try:
            cur.execute(
                f"""WITH updated AS (
                        UPDATE locations SET {set_clause}
                        WHERE id = %(id)s
                        RETURNING *
                    ),
                    bumped AS (
                        UPDATE travel_plans
                        SET version = version + 1, updated_at = NOW()
                        WHERE id = %(plan_id)s
                        RETURNING version
                    )
                    SELECT u.*, b.version AS plan_version
                    FROM updated u, bumped b""",
                params,
            )
            return cur.fetchone()
        except Exception as e:
            if "unique_plan_order" in str(e):
                raise ApiError("visit_order already taken in this plan", 409)
            raise


def delete_location(location_id: str, expected_version: int) -> None:
    with sharding.get_cursor_for(location_id, commit=True) as cur:
        cur.execute(
            """SELECT l.travel_plan_id, tp.version AS plan_version
               FROM locations l
               JOIN travel_plans tp ON tp.id = l.travel_plan_id
               WHERE l.id = %s
               FOR UPDATE OF tp""",
            (location_id,),
        )
        row = cur.fetchone()

        if not row:
            raise ApiError("Location not found", 404)

        if row["plan_version"] != expected_version:
            raise ApiError(
                "Version conflict", 409,
                details={"expected": expected_version, "actual": row["plan_version"]},
            )

        cur.execute(
            """WITH deleted AS (
                   DELETE FROM locations WHERE id = %s RETURNING id
               )
               UPDATE travel_plans
               SET version = version + 1, updated_at = NOW()
               WHERE id = %s""",
            (location_id, row["travel_plan_id"]),
        )

def plan_exists(plan_id: str) -> bool:
    try:
        with sharding.get_cursor_for(plan_id) as cur:
            cur.execute("SELECT 1 FROM travel_plans WHERE id = %s", (plan_id,))
            return cur.fetchone() is not None
    except Exception:
        return False


def location_exists(location_id: str) -> bool:
    try:
        with sharding.get_cursor_for(location_id) as cur:
            cur.execute("SELECT 1 FROM locations WHERE id = %s", (location_id,))
            return cur.fetchone() is not None
    except Exception:
        return False