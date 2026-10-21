"""The miMic engine: label coding, direction of effects, refusals and housekeeping."""

import subprocess
import sys

import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core.contract import LABEL_COLUMN, RANK_SEPARATOR, Dataset
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import sort_uploads
from microplatform.core.preprocessing import CANONICAL
from microplatform.engines.mimic import MimicEngine, display_name, native_tag
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS


# --- the adapter's small pieces -------------------------------------------------------

def test_binary_word_labels_are_coded_0_1_in_sorted_order():
    labels = pd.Series(["sick", "healthy", "sick"], index=["a", "b", "c"], name=LABEL_COLUMN)
    tag, coding = native_tag(labels, "binary")
    assert tag[LABEL_COLUMN].tolist() == [1, 0, 1]
    assert coding == {"0": "healthy", "1": "sick"}


def test_numeric_0_1_labels_are_unchanged():
    labels = pd.Series([1, 0, 1], index=["a", "b", "c"], name=LABEL_COLUMN)
    tag, coding = native_tag(labels, "binary")
    assert tag[LABEL_COLUMN].tolist() == [1, 0, 1] and coding == {"0": "0", "1": "1"}


def test_continuous_labels_stay_numbers():
    labels = pd.Series([0.5, 2, 7.25], index=["a", "b", "c"], name=LABEL_COLUMN)
    tag, coding = native_tag(labels, "continuous")
    assert tag[LABEL_COLUMN].tolist() == [0.5, 2.0, 7.25] and coding == {}


@pytest.mark.parametrize(("taxon", "name"), [
    ("k__Bacteria;p__Firmicutes;c__Bacilli;o__Lactobacillales;f__Streptococcaceae;g__Streptococcus_0",
     "Streptococcus_0"),
    ("k__Bacteria;p__Bacteroidetes;c__Bacteroidia;o__Bacteroidales;f__Bacteroidaceae;g__Bacteroides;s__caccae_0",
     "Bacteroides caccae_0"),
    ("k__Bacteria;p__Bacteroidetes;c__Bacteroidia;o__Bacteroidales;f__Rikenellaceae_0", "Rikenellaceae_0"),
])
def test_display_names(taxon, name):
    assert display_name(taxon) == name


def test_categorical_labels_are_refused_with_a_reason(tmp_path):
    features = pd.DataFrame({"x": [0.1, 0.2, 0.3]}, index=pd.Index(["a", "b", "c"], name="ID"))
    labels = pd.Series([0, 1, 2], index=features.index, name=LABEL_COLUMN)
    data = Dataset(features, CANONICAL, features, labels, "categorical")
    with pytest.raises(UserFacingError, match="three or more groups") as info:
        MimicEngine().run(data, tmp_path)
    assert "Combine your groups into two" in info.value.fix


# --- end to end on the example --------------------------------------------------------

@pytest.fixture(scope="module")
def numeric_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("numeric")
    run = workflows.start_example_run(root / "runs")
    workflows.run_goal(run, "differ", cache_dir=root / "cache")
    return run


def test_effect_direction_matches_the_data(numeric_run):
    """A positive miMic score means 'higher in group 1' — checked against the processed values."""
    hits = numeric_run.table("significant_taxa")
    features = pd.read_csv(numeric_run.processed_file, index_col=0)
    tags = pd.read_csv(EXAMPLE_TAGS, index_col=0)[LABEL_COLUMN]
    by_lineage = {_lineage(c): c for c in features.columns}
    checked = 0
    for _, hit in hits.iterrows():
        column = by_lineage.get(_lineage(hit["taxon"]))
        if column is None:
            continue  # internal tree nodes are averages over several features, not one column
        diff = features.loc[tags[tags == 1].index.astype(str), column].mean() - \
            features.loc[tags[tags == 0].index.astype(str), column].mean()
        assert (diff > 0) == (hit["statistic"] > 0) == hit["direction"].endswith("'1'")
        checked += 1
    assert checked >= 3


def _lineage(name: str) -> tuple[str, ...]:
    """The named ranks of a taxon, with or without 'g__'-style prefixes: comparable across tools."""
    ranks = (part.strip().split("__", 1)[-1] for part in name.split(RANK_SEPARATOR))
    return tuple(r for r in ranks if r)


def test_word_labels_give_the_same_results_with_named_groups(numeric_run, tmp_path):
    words = pd.read_csv(EXAMPLE_TAGS, index_col=0)
    words[LABEL_COLUMN] = words[LABEL_COLUMN].map({0: "control", 1: "case"})
    files = [(EXAMPLE_COUNTS.name, EXAMPLE_COUNTS.read_bytes()), ("labels.csv", words.to_csv().encode())]
    run = workflows.start_run(tmp_path / "runs", sort_uploads(files))
    workflows.run_goal(run, "differ", cache_dir=tmp_path / "cache")

    # Sorted order: 'case' < 'control', so case = 0 and control = 1 — the reverse of the numbers.
    record = run.engine_record()
    assert record["record"]["label_coding"] == {"0": "case", "1": "control"}
    assert any("coded 0 = 'case' and 1 = 'control'" in line for line in record["summary"])
    ours, before = run.table("significant_taxa").set_index("taxon"), numeric_run.table("significant_taxa").set_index("taxon")
    assert sorted(ours.index) == sorted(before.index)
    pd.testing.assert_series_equal(ours["p"], before.loc[ours.index, "p"])
    assert all(d in ("higher in 'case'", "higher in 'control'") for d in ours["direction"])


def test_results_zip_has_the_mimic_tables_and_citation(numeric_run):
    import io
    import zipfile

    from microplatform.references import get_tool

    with zipfile.ZipFile(io.BytesIO(workflows.build_bundle(numeric_run))) as zf:
        names = set(zf.namelist())
        readme = zf.read("README.txt").decode()
    assert {"results/significant_taxa.csv", "results/apriori_test.csv", "analysis.json",
            "figures/mimic_significant_taxa.svg", "figures/mimic_apriori_test.csv"} <= names
    assert get_tool("miMic").paper.citation in readme and get_tool("MIPMLP").paper.citation in readme
    assert "Findings" in readme and "taxa are significant" in readme


def test_mimic_never_writes_into_the_current_folder(tmp_path, monkeypatch):
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    run = workflows.start_example_run(tmp_path / "runs")
    workflows.run_goal(run, "differ", cache_dir=tmp_path / "cache")
    assert list(here.iterdir()) == []  # its .pkl files went to the run's work folder
    assert (run.path / "work" / "mimic" / "df_corrs.pkl").exists()


def test_loading_mimic_keeps_pytorch_working():
    """On Windows, Qt (via ete3) loaded before PyTorch breaks PyTorch; load_mimic orders them."""
    code = "from microplatform.engines.mimic import load_mimic; load_mimic(); import torch; print(torch.ones(1).item())"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-500:]
    assert result.stdout.strip().endswith("1.0")
