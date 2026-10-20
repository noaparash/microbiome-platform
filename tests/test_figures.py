import io
import json
import re
import zipfile

import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core.preprocessing import CANONICAL
from microplatform.core.profiler import count_matrix, read_table
from microplatform.examples import EXAMPLE_COUNTS
from microplatform.reports.figures import (
    FORMATS,
    PLOTLY_JS,
    export,
    load_manifest,
    preprocessing_figures,
    to_plotly,
)


@pytest.fixture(scope="module")
def figures():
    return preprocessing_figures(count_matrix(read_table(EXAMPLE_COUNTS)), CANONICAL)


@pytest.fixture(scope="module")
def exported(figures, tmp_path_factory):
    out = tmp_path_factory.mktemp("figures")
    return out, export(figures, out)


def test_reads_per_sample(figures):
    reads = figures[0]
    assert reads.name == "reads_per_sample" and reads.log_y
    assert len(reads.data) == 40
    assert reads.data["reads"].is_monotonic_decreasing


def test_prevalence_marks_the_mipmlp_cut_off(figures):
    prevalence = figures[1]
    assert len(prevalence.data) == 263
    assert prevalence.data["prevalence_percent"].between(0, 100).all()
    assert prevalence.marker[0] == CANONICAL.rare_bacteria_threshold * 100


def test_every_format_is_written(exported):
    out, figs = exported
    for fig in figs:
        for fmt in (*FORMATS, "json"):
            assert (out / fig.files[fmt]).stat().st_size > 0


def test_data_csv_is_exactly_what_is_plotted(figures, exported):
    out, _ = exported
    for fig in figures:
        pd.testing.assert_frame_equal(pd.read_csv(out / f"{fig.name}.csv"), fig.data, check_dtype=False)


def test_svg_text_stays_editable(exported):
    out, _ = exported
    assert "<text" in (out / "reads_per_sample.svg").read_text(encoding="utf-8")


def test_interactive_html_works_offline(exported):
    out, _ = exported
    html = (out / "taxa_prevalence.html").read_text(encoding="utf-8")
    assert not re.search(r"<script[^>]*\bsrc=", html)  # nothing loaded from outside
    assert "Plotly.newPlot" in html and len(html) > 1_000_000  # plotly.js is embedded


def test_manifest_round_trip(exported):
    out, figs = exported
    assert load_manifest(out) == figs
    assert load_manifest(out / "missing") == []


def test_plotly_figure_has_log_axis_and_marker(figures):
    assert to_plotly(figures[0]).layout.yaxis.type == "log"
    assert to_plotly(figures[1]).layout.shapes  # the cut-off line


def test_plotly_js_is_bundled():
    assert PLOTLY_JS.is_file()


# --- through the workflow ------------------------------------------------------

@pytest.fixture(scope="module")
def finished_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("runs")
    run = workflows.start_example_run(root)
    workflows.run_goal(run, "preprocess", cache_dir=root / "cache")
    return run


def test_preprocessing_produces_figures(finished_run):
    assert [f.name for f in workflows.describe(finished_run).figures] == ["reads_per_sample", "taxa_prevalence"]


def test_figure_files_cannot_escape_the_run(finished_run):
    assert finished_run.figure_file("reads_per_sample.png") is not None
    # "figures.json.." matters on Windows, which silently drops trailing dots.
    for name in ("../meta.json", "..\\meta.json", ".hidden", "nope.png", "figures.json..",
                 "READS_PER_SAMPLE.PNG"):
        assert finished_run.figure_file(name) is None


def test_bundle_has_everything(finished_run):
    with zipfile.ZipFile(io.BytesIO(workflows.build_bundle(finished_run))) as zf:
        names = set(zf.namelist())
        assert {"README.txt", "record.json", "results/processed_table.csv",
                "inputs/counts.csv", "inputs/labels.csv"} <= names
        for fig in ("reads_per_sample", "taxa_prevalence"):
            assert {f"figures/{fig}.{fmt}" for fmt in FORMATS} <= names
        assert not any(n.endswith(".json") and n.startswith("figures/") for n in names)
        assert json.loads(zf.read("record.json"))["tool"] == "MIPMLP"
        assert finished_run.id in zf.read("README.txt").decode()
