"""Flask web app. Start it with ``flask --app microplatform.web run``.

Analyses run in the background (see microplatform.jobs). ``JOBS`` chooses who
works through the queue:

    "thread"    a worker thread inside the website (default; right for one computer)
    "external"  a separate worker process: ``python -m microplatform.worker`` (for a server)
    "inline"    immediately, inside the request (for tests)

Set ``MICROPLATFORM_JOBS`` to choose. Email notifications switch on when the
SMTP settings are in the environment (see microplatform.notify).
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, flash, redirect, request, url_for

from microplatform.jobs import Worker
from microplatform.notify import EmailNotifier, EmailSettings


def create_app(test_config: dict | None = None) -> Flask:
    instance = Path(os.environ.get("MICROPLATFORM_INSTANCE", Path.cwd() / "instance")).resolve()
    app = Flask(__name__, instance_path=str(instance))
    app.config.from_mapping(
        # A random key is fine for local use. Set one in the environment when deploying.
        SECRET_KEY=os.environ.get("MICROPLATFORM_SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=100 * 1024 * 1024,  # 100 MB per upload
        RUNS_DIR=instance / "runs",
        CACHE_DIR=instance / "cache",
        JOBS=os.environ.get("MICROPLATFORM_JOBS", "thread"),
        EMAIL=EmailSettings.from_env(),  # None: email notifications are off
    )
    if test_config:
        app.config.update(test_config)
    if app.config["JOBS"] not in ("thread", "external", "inline"):
        raise ValueError(f"JOBS must be 'thread', 'external' or 'inline', not {app.config['JOBS']!r}")

    email = app.config["EMAIL"]
    app.extensions["microplatform.notifier"] = app.config.get("NOTIFIER") or (EmailNotifier(email) if email else None)
    if app.config["JOBS"] == "thread":
        worker = Worker(app.config["RUNS_DIR"], app.config["CACHE_DIR"], app.extensions["microplatform.notifier"])
        worker.start_thread()
        app.extensions["microplatform.worker"] = worker

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
