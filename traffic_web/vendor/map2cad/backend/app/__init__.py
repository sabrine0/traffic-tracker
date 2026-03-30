import logging
import os
import sys

from flask import Flask
from flask_cors import CORS
from app.config import DevelopmentConfig, ProductionConfig, TestingConfig
from app.errors import register_error_handlers

CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)

    env = os.environ.get("FLASK_ENV", "development")
    app.config.from_object(CONFIG_MAP.get(env, DevelopmentConfig))

    if config:
        app.config.update(config)

    # Logging to stdout for Docker
    if not app.debug:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    # CORS
    origins = app.config.get("CORS_ORIGIN", "*")
    if isinstance(origins, str) and "," in origins:
        origins = [o.strip() for o in origins.split(",")]
    CORS(app, origins=origins)

    register_error_handlers(app)

    from app.routes.health import health_bp
    from app.routes.export import export_bp
    app.register_blueprint(health_bp)
    app.register_blueprint(export_bp)

    return app
