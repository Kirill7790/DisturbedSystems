from flask import jsonify
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 400, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def register_error_handlers(app):

    @app.errorhandler(ApiError)
    def handle_api_error(e):
        body = {"error": e.message}
        if e.details:
            body["details"] = e.details
        return jsonify(body), e.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(e):
        return jsonify({"error": e.name, "details": e.description}), e.code

    @app.errorhandler(Exception)
    def handle_unexpected():
        return jsonify({"error": "Internal server error"}), 500