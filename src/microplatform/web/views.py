"""Routes only: each one calls the package and renders the answer.

No business logic lives here (see "Package-first" in CLAUDE.md).
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from microplatform import CANONICAL, TOOLS, __version__, jobs, runs, workflows
from microplatform.apidoc import api_reference
from microplatform.core.contract import ALLOWED_VARIATIONS, short_feature_name
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import sort_uploads
from microplatform.examples import DOWNLOADS, EXAMPLE_SOURCE
from microplatform.reports.figures import MEDIA_TYPES, PLOTLY_JS
from microplatform.router.goals import GOALS, get_goal, requirement_text

bp = Blueprint("main", __name__)


bp.add_app_template_filter(short_feature_name, "short_taxon")


@bp.get("/")
def index():
    chosen = get_goal(request.args.get("goal"))
    return render_template(
        "index.html", goals=GOALS, chosen=chosen,
        needs=requirement_text(chosen) if chosen else None,
    )


@bp.post("/upload")
def upload():
    goal = request.form.get("goal") or None
    files = [(f.filename, f.read()) for f in request.files.getlist("files") if f and f.filename]
    try:
        run = workflows.start_run(_runs_dir(), sort_uploads(files), requested_goal=goal)
    except UserFacingError as exc:
        _flash_error(exc)
        return redirect(url_for(".index", goal=goal))
    return redirect(url_for(".analysis", run_id=run.id))


@bp.post("/example")
def example():
    run = workflows.start_example_run(_runs_dir(), requested_goal=request.form.get("goal") or None)
    return redirect(url_for(".analysis", run_id=run.id))


@bp.post("/runs/<run_id>/labels")
def add_labels(run_id: str):
    run = _get_run(run_id)
    upload = request.files.get("file")
    try:
        if not upload or not upload.filename:
            raise UserFacingError("No file was chosen.", "Choose a labels file to add.")
        workflows.add_labels(run, upload.filename, upload.read())
    except UserFacingError as exc:
        _flash_error(exc)
    return redirect(url_for(".analysis", run_id=run.id, _anchor="plan"))


@bp.get("/example")
def example_page():
    counts, labels = workflows.example_overview()
    return render_template("example.html", counts=counts, labels=labels, source=EXAMPLE_SOURCE)


@bp.get("/methods")
def methods():
    status = {goal.tool: goal.status for goal in GOALS}
    return render_template("methods.html", tools=TOOLS, status=status, settings=CANONICAL,
                           allowed=sorted(ALLOWED_VARIATIONS))


@bp.get("/docs")
def docs():
    return render_template("docs.html", api=api_reference(), version=__version__)


@bp.get("/about")
def about():
    return render_template("about.html", tools=TOOLS, version=__version__)


@bp.get("/downloads/<name>")
def download_file(name: str):
    """Format templates and the example dataset."""
    if name not in DOWNLOADS:
        abort(404)
    return send_file(DOWNLOADS[name], mimetype="text/csv", as_attachment=True, download_name=name)


@bp.get("/runs/<run_id>")
def analysis(run_id: str):
    return render_template("analysis.html", view=workflows.describe(_get_run(run_id)),
                           email_enabled=_notifier() is not None)


@bp.post("/runs/<run_id>/run")
def run_goal(run_id: str):
    """Queue the chosen goal; the page then follows the run until its results are ready."""
    run = _get_run(run_id)
    goal = request.form.get("goal", "")
    # Advanced settings arrive as "<goal>:<option>" fields; the package validates them.
    choices = {key.split(":", 1)[1]: value for key, value in request.form.items() if key.startswith(f"{goal}:")}
    try:
        jobs.submit(run, goal, email=request.form.get("email"),
                    results_url=_public_url(url_for(".analysis", run_id=run.id)),
                    email_enabled=_notifier() is not None, choices=choices)
    except UserFacingError as exc:
        _flash_error(exc)
        return redirect(url_for(".analysis", run_id=run.id, _anchor="plan"))
    if current_app.config["JOBS"] == "inline":
        jobs.run_now(run, current_app.config["CACHE_DIR"], _notifier())
    return redirect(url_for(".analysis", run_id=run.id, _anchor="results"))


@bp.get("/runs/<run_id>/download")
def download(run_id: str):
    run = _get_run(run_id)
    if not run.processed_file.exists():
        abort(404)
    return send_file(
        run.processed_file, mimetype="text/csv", as_attachment=True,
        download_name=f"{_stem(run)}_mipmlp.csv",
    )


@bp.get("/runs/<run_id>/figures/<name>")
def figure_file(run_id: str, name: str):
    path = _get_run(run_id).figure_file(name)
    if path is None:
        abort(404)
    return send_file(path, mimetype=MEDIA_TYPES.get(path.suffix),
                     as_attachment=request.args.get("download") == "1")


@bp.get("/runs/<run_id>/tables/<name>")
def table_file(run_id: str, name: str):
    path = _get_run(run_id).table_file(name)
    if path is None:
        abort(404)
    return send_file(path, mimetype="text/csv", as_attachment=True,
                     download_name=f"{_stem(_get_run(run_id))}_{name}")


@bp.get("/runs/<run_id>/bundle")
def bundle(run_id: str):
    run = _get_run(run_id)
    return send_file(
        io.BytesIO(workflows.build_bundle(run)), mimetype="application/zip",
        as_attachment=True, download_name=f"{_stem(run)}_results.zip",
    )


@bp.get("/vendor/plotly.min.js")
def plotly_js():
    """Served locally so interactive figures work without internet access."""
    return send_file(PLOTLY_JS, mimetype="text/javascript", max_age=86400)


def _stem(run: runs.Run) -> str:
    return Path(run.meta()["counts_name"]).stem.replace(" ", "_")


def _runs_dir() -> Path:
    return current_app.config["RUNS_DIR"]


def _get_run(run_id: str) -> runs.Run:
    run = runs.load(_runs_dir(), run_id)
    if run is None:
        abort(404)
    return run


def _notifier():
    return current_app.extensions.get("microplatform.notifier")


def _public_url(path: str) -> str:
    """The run's results link as users will open it (behind a proxy, set MICROPLATFORM_PUBLIC_URL)."""
    base = current_app.config.get("PUBLIC_URL") or os.environ.get("MICROPLATFORM_PUBLIC_URL") or request.host_url
    return base.rstrip("/") + path


def _flash_error(exc: UserFacingError) -> None:
    flash({"message": exc.message, "fix": exc.fix}, "error")
