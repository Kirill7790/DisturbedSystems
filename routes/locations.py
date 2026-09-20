from flask import Blueprint, jsonify, request
from pydantic import ValidationError
import schemas, models
from errors import ApiError

locations_bp = Blueprint("locations", __name__, url_prefix="/api")

def _pydantic_errors(e: ValidationError):
    return [{"loc": ".".join(map(str, err["loc"])), "msg": err["msg"]}
            for err in e.errors()]

@locations_bp.post("/travel-plans/<uuid:plan_id>/locations")
def add_location(plan_id):
    if not models.plan_exists(str(plan_id)):
        raise ApiError("Travel plan not found", 404)

    body = request.get_json(force=True) or {}
    version = body.pop("version", None)
    if version is None:
        raise ApiError(
            "Validation error",
            400,
            details=[{"loc": "version", "msg": "version is required for optimistic locking"}],
        )

    try:
        data = schemas.LocationCreate(**body)
    except ValidationError as e:
        raise ApiError("Validation error", 400, _pydantic_errors(e))

    result = models.add_location(str(plan_id), data.model_dump(exclude_unset=True), version)
    return jsonify(result), 201

@locations_bp.put("/locations/<uuid:location_id>")
def update_location(location_id):
    if not models.location_exists(str(location_id)):
        raise ApiError("Location not found", 404)

    try:
        data = schemas.LocationUpdate(**request.get_json(force=True))
    except ValidationError as e:
        raise ApiError("Validation error", 400, _pydantic_errors(e))

    updated = models.update_location(
        str(location_id), data.model_dump(exclude_unset=True), data.version
    )
    return jsonify(updated), 200

@locations_bp.delete("/locations/<uuid:location_id>")
def delete_location(location_id):
    version = request.args.get("version", type=int)
    if version is None:
        raise ApiError("version query param is required", 400)
    models.delete_location(str(location_id), version)
    return "", 204