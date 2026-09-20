from flask import Blueprint, jsonify, request
from pydantic import ValidationError
import schemas, models
from errors import ApiError

plans_bp = Blueprint("plans", __name__, url_prefix="/api/travel-plans")

def _pydantic_errors(e: ValidationError):
    return [{"loc": ".".join(map(str, err["loc"])), "msg": err["msg"]}
            for err in e.errors()]

@plans_bp.get("")
def list_plans():
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        raise ApiError("Invalid pagination params", 400)

    is_public = request.args.get("is_public")
    is_public = None if is_public is None else is_public.lower() == "true"

    rows, total = models.list_plans(limit, offset, is_public)
    return jsonify({
        "items": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }), 200

@plans_bp.post("")
def create_plan():
    try:
        data = schemas.PlanCreate(**request.get_json(force=True))
    except ValidationError as e:
        raise ApiError("Validation error", 400, _pydantic_errors(e))
    plan = models.create_plan(data.model_dump())
    return jsonify(plan), 201

@plans_bp.get("/<uuid:plan_id>")
def get_plan(plan_id):
    plan = models.get_plan(str(plan_id))
    if not plan:
        raise ApiError("Travel plan not found", 404)
    return jsonify(plan), 200

@plans_bp.put("/<uuid:plan_id>")
def update_plan(plan_id):
    try:
        data = schemas.PlanUpdate(**request.get_json(force=True))
    except ValidationError as e:
        raise ApiError("Validation error", 400, _pydantic_errors(e))
    plan = models.update_plan(str(plan_id), data.model_dump(exclude_unset=True),
                              data.version)
    return jsonify(plan), 200

@plans_bp.delete("/<uuid:plan_id>")
def delete_plan(plan_id):
    models.delete_plan(str(plan_id))
    return "", 204