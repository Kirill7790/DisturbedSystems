from flask import Flask, jsonify
from config import Config
from errors import register_error_handlers
from routes import register_routes
import sharding
from datetime import date, datetime
from flask.json.provider import DefaultJSONProvider
import json

class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json = CustomJSONProvider(app)
    app.json.sort_keys = False
    app.json.ensure_ascii = False

    register_routes(app)
    register_error_handlers(app)

    @app.get("/api/health")
    def health():
        try:
            with sharding.get_cursor_for_shard("0") as cur:
                cur.execute("SELECT 1")
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            print(f"Health check failed: {e}")
            return jsonify({"status": "unavailable"}), 503

    @app.after_request
    def add_security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Content-Security-Policy"] = "default-src 'none'"
        return resp

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=False)