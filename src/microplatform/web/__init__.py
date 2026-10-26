"""Flask web app.

Locally: ``flask --app microplatform.web run``. On a server: gunicorn with the
entry point ``microplatform.web.wsgi:app`` (see docs/deployment.he.md).

Analyses run in the background (see microplatform.jobs). ``JOBS`` chooses who
works through the queue:

    "thread"    a worker thread inside the website (default locally; right for one computer)
    "external"  queue only: a separate worker process, ``python -m microplatform.worker`` (servers)
    "inline"    immediately, inside the request (for tests)

All settings come from environment variables (on a server, one file outside Git;
see deploy/microplatform.env.example):

    MICROPLATFORM_INSTANCE       where uploads, results and the cache are stored
    MICROPLATFORM_SECRET_KEY     signs session cookies (required on a server)
    MICROPLATFORM_JOBS           thread | external | inline
    MICROPLATFORM_MAX_UPLOAD_MB  largest upload accepted (default 100)
    MICROPLATFORM_PUBLIC_URL     the address users open (for results links in emails)
    MICROPLATFORM_TRUST_PROXY    1 behind a reverse proxy (nginx) that terminates HTTPS
    MICROPLATFORM_COOKIE_SECURE  1 to send cookies over HTTPS only
    MICROPLATFORM_SMTP_*         optional email (see microplatform.notify)
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, flash, redirect, request, url_for

from microplatform.jobs import Worker
from microplatform.notify import EmailNotifier, EmailSettings


def _flag(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes", "on")


def create_app(test_config: dict | None = None) -> Flask:
    instance = Path(os.environ.get("MICROPLATFORM_INSTANCE", Path.cwd() / "instance")).resolve()
    app = Flask(__name__, instance_path=str(instance))
    app.config.from_mapping(
        # A random key is fine for local use; a server must set one (see wsgi.py).
        SECRET_KEY=os.environ.get("MICROPLATFORM_SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=int(os.environ.get("MICROPLATFORM_MAX_UPLOAD_MB", "100")) * 1024 * 1024,
        RUNS_DIR=instance / "runs",
        CACHE_DIR=instance / "cache",
        JOBS=os.environ.get("MICROPLATFORM_JOBS", "thread"),
        EMAIL=EmailSettings.from_env(),  # None: email notifications are off
        PUBLIC_URL=os.environ.get("MICROPLATFORM_PUBLIC_URL") or None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_flag("MICROPLATFORM_COOKIE_SECURE"),
    )
    if test_config:
        app.config.update(test_config)
    if app.config["JOBS"] not in ("thread", "external", "inline"):
        raise ValueError(f"JOBS must be 'thread', 'external' or 'inline', not {app.config['JOBS']!r}")

    if _flag("MICROPLATFORM_TRUST_PROXY"):
        # Behind nginx: take the scheme and host from its headers, so links are https://<host>/…
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.endpoint == "static":
            response.cache_control.max_age = 3600
        else:
            # Pages may show clinical results: never keep them in shared or browser caches.
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    return app
