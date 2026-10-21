"""Reproduction tests: each engine gives exactly what the original tool gives.

For every engine, run the authors' tool the way their own example does, on
their example data, and check that our engine's result is identical. This
proves the adapter feeds the original tool faithfully (see docs/tool-inputs.he.md).
Every new engine must add its test here.
"""

import warnings
from pathlib import Path

import MIPMLP
import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core.inputs import sort_uploads
from microplatform.core.preprocessing import CANONICAL
from microplatform.examples import EXAMPLE_COUNTS

MIMIC_EXAMPLE = Path(__file__).parent / "data" / "mimic_example"  # the authors' files, unchanged


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return workflows.start_example_run(tmp_path_factory.mktemp("runs"))


# --- MIPMLP ------------------------------------------------------------------------

def test_mipmlp_matches_the_authors_call(run, tmp_path):
    """miMic's own preprocessing is MIPMLP.preprocess(raw, taxnomy_group="sub PCA")."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        theirs = MIPMLP.preprocess(pd.read_csv(EXAMPLE_COUNTS), taxnomy_group="sub PCA")

    ours = workflows.build_dataset(run, CANONICAL, tmp_path)[0].features

    pd.testing.assert_index_equal(ours.columns, theirs.columns)
    assert list(ours.index) == [str(i) for i in theirs.index]
    pd.testing.assert_frame_equal(ours, theirs, check_names=False, check_index_type=False)


# --- miMic ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mimic_theirs(tmp_path_factory):
    """miMic exactly as the authors' example_use.py runs it (test mode, save=True)."""
    from microplatform.engines.mimic import load_mimic

    apply_mimic, _ = load_mimic()
    work = tmp_path_factory.mktemp("authors")
    folder = work / "2D_images"
    folder.mkdir()
    df = pd.read_csv(MIMIC_EXAMPLE / "for_process.csv")
    tag = pd.read_csv(MIMIC_EXAMPLE / "tag.csv", index_col=0)
    with pytest.MonkeyPatch.context() as mp, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mp.chdir(work)  # miMic writes .pkl files into the current folder
        processed = apply_mimic(folder=str(folder), tag=tag, mode="preprocess", preprocess=True,
                                rawData=df, taxnomy_group="sub PCA")
        selected, _ = apply_mimic(str(folder), tag, eval="man", threshold_p=0.05, processed=processed,
                                  apply_samba=True, save=True)
    return selected, pd.read_csv(folder / "df_corrs.csv", index_col=0)


@pytest.fixture(scope="module")
def mimic_ours(tmp_path_factory):
    """Our engine, through the normal workflow, on the same two files."""
    root = tmp_path_factory.mktemp("ours")
    files = [(p.name, p.read_bytes()) for p in (MIMIC_EXAMPLE / "for_process.csv", MIMIC_EXAMPLE / "tag.csv")]
    run = workflows.start_run(root / "runs", sort_uploads(files))
    workflows.run_goal(run, "differ", cache_dir=root / "cache")
    return run.engine_record(), run.table("significant_taxa")


def test_mimic_finds_exactly_the_authors_taxa(mimic_theirs, mimic_ours):
    _, theirs = mimic_theirs
    _, ours = mimic_ours
    assert len(theirs) > 0, "the authors' example should find significant taxa"
    assert sorted(ours["taxon"]) == sorted(theirs.index)


def test_mimic_scores_and_p_values_are_identical(mimic_theirs, mimic_ours):
    _, theirs = mimic_theirs
    _, ours = mimic_ours
    ours = ours.set_index("taxon").loc[theirs.index]
    pd.testing.assert_series_equal(ours["p"], theirs["p"], check_names=False, check_exact=True)
    pd.testing.assert_series_equal(ours["statistic"], theirs["scc"], check_names=False, check_exact=True)


def test_mimic_starts_the_post_hoc_test_at_the_same_level(mimic_theirs, mimic_ours):
    selected, _ = mimic_theirs
    record, _ = mimic_ours
    assert record["record"]["post_hoc_start"] == str(selected)
    assert record["record"]["eval"] == "man"
