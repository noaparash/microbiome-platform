"""The package's public API, its generated reference, and the tool references."""

import io
import zipfile

import microplatform as mp
from microplatform import workflows
from microplatform.apidoc import api_reference
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.references import TOOLS, get_tool
from microplatform.router.goals import GOALS


def test_every_public_name_is_documented():
    entries = {e.name: e for e in api_reference()}
    assert set(entries) == set(mp.__all__)
    for entry in entries.values():
        assert entry.summary, f"mp.{entry.name} needs a docstring"
        assert "'" not in entry.signature.split("=")[0], entry.signature  # no quoted types


def test_analyze_runs_a_whole_analysis_without_the_website(tmp_path):
    view = mp.analyze(EXAMPLE_COUNTS, EXAMPLE_TAGS, out_dir=tmp_path / "runs",
                      cache_dir=tmp_path / "cache")
    assert view.run.status == "done"
    assert view.record["output_features"] > 0
    assert (view.run.path / "processed.csv").exists()
    assert {f.name for f in view.figures} == {"reads_per_sample", "taxa_prevalence"}


def test_every_goal_has_a_tool_reference():
    assert {t.name for t in TOOLS} == {g.tool for g in GOALS}
    for tool in TOOLS:
        assert tool.paper.doi.startswith("10.") and tool.paper.url.startswith("https://doi.org/")
        assert tool.method and tool.code_url.startswith("https://")


def test_results_zip_cites_from_the_single_source(tmp_path):
    view = mp.analyze(EXAMPLE_COUNTS, out_dir=tmp_path / "runs", cache_dir=tmp_path / "cache")
    with zipfile.ZipFile(io.BytesIO(workflows.build_bundle(view.run))) as zf:
        readme = zf.read("README.txt").decode()
    assert get_tool("MIPMLP").paper.citation in readme


def test_example_overview():
    counts, labels = workflows.example_overview()
    assert counts.n_samples == 40 and labels.kind == "binary"
