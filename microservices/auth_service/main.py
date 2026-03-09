"""main.py – Flask application entry point for auth-service microservice.

Task 4 AC1: Flask application initialises without errors at /health route.
Task 4 AC3: Environment configurations parameterised via config.py.
"""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify

from .config import get_config
from .controllers.LoginController import login_bp


def create_app(config=None) -> Flask:
    """Application factory."""
    app = Flask(__name__)

    cfg = config or get_config()
    app.config.from_object(cfg)

    # Logging
    logging.basicConfig(
        level=logging.DEBUG if app.config.get("DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Blueprints
    app.register_blueprint(login_bp)

    # Health check (Task 4 AC1)
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "auth-service"}), 200

    return app


app = create_app()

if __name__ == "__main__":
    cfg = get_config()
    app.run(
        host=cfg.AUTH_SERVICE_HOST,
        port=cfg.AUTH_SERVICE_PORT,
    )
