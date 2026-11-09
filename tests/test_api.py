"""The package's public API, its generated reference, and the tool references."""

import io
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

import microplatform as mp
from microplatform import workflows
from microplatform.apidoc import api_reference
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.reports.overview import FIGURE_NAMES as OVERVIEW
from microplatform.references import TOOLS, get_tool
from microplatform.router.goals import GOALS


ROOT = Path(__file__).parents[1]

# The public API as released in 0.3.0 (0.2.0 + ``metabolites`` in analyze), plus, unreleased and in
# CHANGELOG.md: ``preprocessing`` in analyze and ``as_is`` in build_dataset (both last, with defaults,
# so earlier calls still work). If this test fails, the API changed: make sure it was meant to,
# record it in CHANGELOG.md (Added / Changed / Removed), then update this.
API_0_3 = {
    "analyze": "mp.analyze(counts: str | Path, labels: str | Path | None = None, goal: str | None = None, "
               "out_dir: str | Path = 'microplatform-runs', cache_dir: str | Path | None = None, "
               "options: dict | None = None, metabolites: str | Path | None = None, "
               "preprocessing: str | None = None) -> RunView",
    "read_table": "mp.read_table(source: str | IO, **kwargs) -> DataFrame",
    "profile_counts": "mp.profile_counts(raw: DataFrame) -> CountsProfile",
    "profile_labels": "mp.profile_labels(tags: DataFrame, sample_ids: list[str]) -> LabelProfile",
    "preprocess": "mp.preprocess(raw: DataFrame, settings: PreprocessSettings = CANONICAL, "
                  "cache_dir: Path | None = None) -> PreprocessResult",
    "PreprocessSettings": "mp.PreprocessSettings(taxonomy_level: int = 7, taxonomy_group: Literal['sub PCA', "
                          "'mean', 'sum'] = 'sub PCA', epsilon: float = 0.1, normalization: Literal['log', "
                          "'relative'] = 'log', z_scoring: Literal['No', 'row', 'col', 'both'] = 'No', "
                          "rare_bacteria_threshold: float = 0.01)",
    "CANONICAL": "mp.CANONICAL",
    "sort_uploads": "mp.sort_uploads(files: list[tuple[str, bytes]]) -> Inputs",
    "start_run": "mp.start_run(root: Path, inputs: Inputs, requested_goal: str | None = None) -> Run",
    "describe": "mp.describe(run: Run) -> RunView",
    "run_goal": "mp.run_goal(run: Run, goal_id: str, cache_dir: Path | None = None, "
                "choices: dict | None = None) -> None",
    "build_dataset": "mp.build_dataset(run: Run, settings: PreprocessSettings = CANONICAL, "
                     "cache_dir: Path | None = None, engine: str | None = None, as_is: bool = False) "
                     "-> tuple[Dataset, PreprocessResult]",
    "Dataset": "mp.Dataset(features: DataFrame, settings: PreprocessSettings, raw_counts: DataFrame, "
               "labels: Series | None = None, label_kind: LabelKind | None = None, "
               "metabolites: DataFrame | None = None, engine: str | None = None)",
    "UserFacingError": "mp.UserFacingError(message: str, fix: str = '')",
    "GOALS": "mp.GOALS",
    "TOOLS": "mp.TOOLS",
}


def test_the_public_api_is_unchanged_since_the_release():
    assert {e.name: e.signature for e in api_reference()} == API_0_3
    assert mp.CANONICAL == mp.PreprocessSettings()  # the default settings are the paper's


def test_one_version_everywhere():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == mp.__version__
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # The newest released entry comes first (an "Unreleased" section may sit above it).
    assert re.search(r"^## \[(\d[^\]]*)\]", changelog, re.M).group(1) == mp.__version__


def test_citation_file_is_complete():
    yaml = pytest.importorskip("yaml")
    cff = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert cff["cff-version"] == "1.2.0" and cff["type"] == "software"
    assert cff["version"] == mp.__version__ and cff["title"] and cff["message"]
    assert cff["authors"] and all("name" in a or "family-names" in a for a in cff["authors"])
    # Every tool's paper is referenced, from the single source of citations.
    assert {r["doi"] for r in cff["references"]} == {t.paper.doi for t in TOOLS}


def test_the_package_does_not_need_the_website():
    """`pip install microplatform` (without [web]) must be enough to import and use the package."""
    code = ("import sys, microplatform as mp; "
            "assert 'flask' not in sys.modules, 'importing the package loaded Flask'")
    subprocess.run([sys.executable, "-c", code], check=True, timeout=300)
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert not any(d.lower().startswith("flask") for d in pyproject["project"]["dependencies"])


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
    # With labels, the recommended task is miMic (its own cladogram first); data-quality figures come with every run.
    assert view.engine["tool"] == "miMic"
    assert {f.name for f in view.figures} == {"reads_per_sample", "mimic_cladogram", "mimic_significant_taxa",
                                               "mimic_apriori_test", *OVERVIEW}


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
