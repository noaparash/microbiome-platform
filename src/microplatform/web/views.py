"""Routes only: each one calls the package and renders the answer.

No business logic lives here (see "Package-first" in CLAUDE.md).
"""

from __future__ import annotations

import io
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

from microplatform import runs, workflows
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import sort_uploads
from microplatform.examples import TEMPLATES
from microplatform.reports.figures import MEDIA_TYPES, PLOTLY_JS
from microplatform.router.goals import GOALS

bp = Blueprint("main", __name__)


@bp.app_template_filter("short_taxon")
def short_taxon(name: str) -> str:
    """'Bacteria;...;Actinomycetaceae_0;;;' -> 'Actinomycetaceae_0'."""
    parts = [p for p in str(name).split(";") if p.strip()]
    return parts[-1] if parts else str(name)


@bp.get("/")
def index():
    return render_template("index.html", goals=GOALS)


@bp.post("/upload")
def upload():
    files = [(f.filename, f.read()) for f in request.files.getlist("files") if f and f.filename]
    try:
        run = workflows.start_run(_runs_dir(), sort_uploads(files))
    except UserFacingError as exc:
        _flash_error(exc)
        return redirect(url_for(".index"))
    return redirect(url_for(".analysis", run_id=run.id))


@bp.post("/example")
def example():
    run = workflows.start_example_run(_runs_dir())
    return redirect(url_for(".analysis", run_id=run.id))


@bp.get("/templates/<name>")
def template_file(name: str):
    if name not in TEMPLATES:
        abort(404)
    return send_file(TEMPLATES[name], mimetype="text/csv", as_attachment=True, download_name=name)


@bp.get("/runs/<run_id>")
def analysis(run_id: str):
    return render_template("analysis.html", view=workflows.describe(_get_run(run_id)))


@bp.post("/runs/<run_id>/run")
def run_goal(run_id: str):
    run = _get_run(run_id)
    try:
        workflows.run_goal(run, request.form.get("goal", ""), current_app.config["CACHE_DIR"])
    except UserFacingError as exc:
        _flash_error(exc)
        return redirect(url_for(".analysis", run_id=run.id))
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


def _flash_error(exc: UserFacingError) -> None:
    flash({"message": exc.message, "fix": exc.fix}, "error")
