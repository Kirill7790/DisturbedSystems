from .plans import plans_bp
from .locations import locations_bp

def register_routes(app):
    app.register_blueprint(plans_bp)
    app.register_blueprint(locations_bp)