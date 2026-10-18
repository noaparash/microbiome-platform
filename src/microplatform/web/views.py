"""Pages: upload → analysis (profile + one button) → results on the same page."""

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

from microplatform.core.preprocessing import CANONICAL, PreprocessError, preprocess
from microplatform.core.profiler import (
    ProfileError,
    is_counts_table,
    profile_counts,
    profile_labels,
    read_table,
)
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.web import runs

bp = Blueprint("main", __name__)

ALLOWED_SUFFIXES = {".csv", ".tsv", ".txt"}

# Shown on the home page. Becomes the engine registry once engines exist.
TOOLS = [
    ("MIPMLP", "Prepares raw counts for every other tool", "available"),
    ("miMic", "Which bacteria differ between my groups?", "next"),
    ("iMic", "What predicts my outcome?", "planned"),
    ("GIMIC", "How do my samples group?", "planned"),
    ("LOCATE", "How do my bacteria relate to metabolites?", "planned"),
]


class UploadError(Exception):
    pass


@bp.app_template_filter("short_taxon")
def short_taxon(name: str) -> str:
    """'Bacteria;...;Actinomycetaceae_0;;;' -> 'Actinomycetaceae_0'."""
    parts = [p for p in str(name).split(";") if p.strip()]
    return parts[-1] if parts else str(name)


@bp.get("/")
def index():
    return render_template("index.html", tools=TOOLS)


@bp.post("/upload")
def upload():
    files = [f for f in request.files.getlist("files") if f and f.filename]
    try:
        (counts_name, counts), labels = _sort_uploads(files)
    except UploadError as exc:
        flash(str(exc), "error")
        return redirect(url_for(".index"))
    labels_name, labels_table = labels if labels else (None, None)
    run = runs.create(current_app.config["RUNS_DIR"], counts_name, counts, labels_name, labels_table)
    return redirect(url_for(".analysis", run_id=run.id))


@bp.post("/example")
def example():
    run = runs.create(
        current_app.config["RUNS_DIR"],
        "Example dataset (miMic authors)",
        read_table(EXAMPLE_COUNTS),
        EXAMPLE_TAGS.name,
        read_table(EXAMPLE_TAGS, index_col=0),
    )
    return redirect(url_for(".analysis", run_id=run.id))


@bp.get("/runs/<run_id>")
def analysis(run_id: str):
    run = _get_run(run_id)
    profile = profile_counts(run.counts())

    label_profile, label_error = None, None
    labels = run.labels()
    if labels is not None:
        try:
            label_profile = profile_labels(labels, profile.sample_ids)
        except ProfileError as exc:
            label_error = str(exc)

    record = run.record()
    return render_template(
        "analysis.html",
        run=run,
        meta=run.meta(),
        profile=profile,
        labels=label_profile,
        label_error=label_error,
        settings=CANONICAL,
        record=record,
        preview=run.processed_preview() if record else None,
    )


@bp.post("/runs/<run_id>/preprocess")
def run_preprocess(run_id: str):
    run = _get_run(run_id)
    try:
        result = preprocess(run.counts(), cache_dir=current_app.config["CACHE_DIR"])
    except PreprocessError as exc:
        flash(str(exc), "error")
        return redirect(url_for(".analysis", run_id=run.id))
    run.save_result(result)
    return redirect(url_for(".analysis", run_id=run.id, _anchor="results"))


@bp.get("/runs/<run_id>/download")
def download(run_id: str):
    run = _get_run(run_id)
    if not run.processed_file.exists():
        abort(404)
    stem = Path(run.meta()["counts_name"]).stem.replace(" ", "_")
    return send_file(
        run.processed_file,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{stem}_mipmlp.csv",
    )


def _get_run(run_id: str) -> runs.Run:
    run = runs.load(current_app.config["RUNS_DIR"], run_id)
    if run is None:
        abort(404)
    return run


def _sort_uploads(files) -> tuple[tuple[str, object], tuple[str, object] | None]:
    """Work out which upload is the counts table and which (if any) is the labels file."""
    if not files:
        raise UploadError("Choose a counts table to upload.")
    if len(files) > 2:
        raise UploadError("Upload at most two files: a counts table and, optionally, a labels file.")

    counts = labels = None
    for f in files:
        if Path(f.filename).suffix.lower() not in ALLOWED_SUFFIXES:
            raise UploadError(f"'{f.filename}' is not a CSV or TSV file.")
        try:
            table = read_table(io.BytesIO(f.read()))
        except ProfileError as exc:
            raise UploadError(f"'{f.filename}': {exc}") from exc

        if is_counts_table(table):
            if counts is not None:
                raise UploadError("Both files look like counts tables. Upload one counts table at a time.")
            counts = (f.filename, table)
        else:
            if labels is not None:
                raise UploadError(
                    "Neither file has a 'taxonomy' row, so no counts table was found."
                )
            labels = (f.filename, table.set_index(table.columns[0]))

    if counts is None:
        raise UploadError(
            "No counts table found. A counts table has samples as rows and a final row named 'taxonomy'."
        )
    return counts, labels
