"""Flask web app. Start it with ``flask --app microplatform.web run``."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, flash, redirect, request, url_for


def create_app(test_config: dict | None = None) -> Flask:
    instance = Path(os.environ.get("MICROPLATFORM_INSTANCE", Path.cwd() / "instance")).resolve()
    app = Flask(__name__, instance_path=str(instance))
    app.config.from_mapping(
        # A random key is fine for local use. Set one in the environment when deploying.
        SECRET_KEY=os.environ.get("MICROPLATFORM_SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=100 * 1024 * 1024,  # 100 MB per upload
        RUNS_DIR=instance / "runs",
        CACHE_DIR=instance / "cache",
    )
    if test_config:
        app.config.update(test_config)

    from microplatform.web import views

    app.register_blueprint(views.bp)

    @app.errorhandler(413)
    def too_large(_error):
        limit = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        flash(f"That upload is larger than {limit} MB.", "error")
        return redirect(url_for("main.index"))

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.endpoint == "static":
            response.cache_control.max_age = 3600
        return response

    return app
