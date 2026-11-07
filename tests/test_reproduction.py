"""Reproduction tests: each engine gives exactly what the original tool gives.

For every engine, run the authors' tool the way their own example does, on
their example data, and check that our engine's result is identical. This
proves the adapter feeds the original tool faithfully (see docs/tool-inputs.he.md).
Every new engine must add its test here.
"""

import warnings
from pathlib import Path

import MIPMLP
import numpy as np
import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core.inputs import sort_uploads
from microplatform.core.preprocessing import CANONICAL
from microplatform.examples import EXAMPLE_COUNTS

MIMIC_EXAMPLE = Path(__file__).parent / "data" / "mimic_example"  # the authors' files, unchanged
GIMIC_EXAMPLE = Path(__file__).parent / "data" / "gimic_example"  # the authors' files, unchanged


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
    # Read back exactly what miMic wrote (pandas' default reader can be off in the last digit).
    return selected, pd.read_csv(folder / "df_corrs.csv", index_col=0, float_precision="round_trip")


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


# --- GIMIC (mean mode, as its published example runs) ------------------------------------

@pytest.mark.slow
def test_gimic_mean_mode_reproduces_the_authors_example_exactly(tmp_path):
    """SAMBA's example_use.py: MIPMLP.preprocess(df) (defaults: mean) → micro2matrix → SAMBA distances.

    GIMIC's distances are deterministic, so the match must be exact. About 4 minutes.
    """
    from microplatform.engines.gimic import load_gimic

    micro2matrix, build_SAMBA_distance_matrix = load_gimic()
    df = pd.read_csv(GIMIC_EXAMPLE / "for_preprocess.csv")
    with warnings.catch_warnings(), pytest.MonkeyPatch.context() as mp:
        warnings.simplefilter("ignore")
        mp.chdir(tmp_path)
        processed = MIPMLP.preprocess(df)
        array_of_imgs, bact_names, ordered_df = micro2matrix(processed, "example_data/2D_images", save=False)
        theirs = build_SAMBA_distance_matrix("example_data/2D_images", imgs=array_of_imgs, ordered_df=ordered_df,
                                             bact_names=bact_names, class_=False)

    files = [(p.name, p.read_bytes()) for p in (GIMIC_EXAMPLE / "for_preprocess.csv", GIMIC_EXAMPLE / "tag.csv")]
    run = workflows.start_run(tmp_path / "runs", sort_uploads(files))
    workflows.run_goal(run, "group", tmp_path / "cache", {"grouping": "mean"})
    ours = run.table("distance_matrix").set_index("ID")

    ours.index = ours.index.astype(str)
    theirs.index, theirs.columns = theirs.index.astype(str), theirs.columns.astype(str)
    assert theirs.shape == (257, 257)
    pd.testing.assert_frame_equal(ours, theirs, check_names=False, check_exact=True)
    assert run.engine_record()["record"]["grouping"] == "mean"


# --- iMic (same seed, within the tolerance recorded on 2026-10-22, before any run) -------

PROBABILITY_TOLERANCE = 1e-4
AUC_TOLERANCE = 0.005


@pytest.fixture(scope="module")
def imic_theirs(tmp_path_factory):
    """MIPMLP's documented usage: micro2matrix(df, folder) then apply_iMic(tag, folder), seed 42.

    Run twice: once exactly as published (plain CNN), and once with the CNN observed so the
    probabilities its own predict() computes can be read. Labels are in the counts table's order.
    """
    import numpy as np
    import pytorch_lightning as pl

    from microplatform.engines.imic import load_imic, recording_cnn

    mipmlp, apply_iMic, _, _ = load_imic()
    work = tmp_path_factory.mktemp("imic_authors")
    df = pd.read_csv(MIMIC_EXAMPLE / "for_process.csv")
    tag = pd.read_csv(MIMIC_EXAMPLE / "tag.csv", index_col=0)[["Tag"]]
    tag.index = tag.index.astype(str)
    tag = tag.loc[df["ID"].iloc[:-1].astype(str)]  # the counts table's order
    with warnings.catch_warnings(), pytest.MonkeyPatch.context() as mp:
        warnings.simplefilter("ignore")
        mp.chdir(work)
        (work / "images").mkdir()
        mipmlp.micro2matrix(df, "images")
        pl.seed_everything(42, workers=True)
        plain = apply_iMic(tag, "images")
        observed_cnn = recording_cnn(mipmlp.CNN)
        mp.setattr(mipmlp, "CNN", observed_cnn)
        pl.seed_everything(42, workers=True)
        observed = apply_iMic(tag, "images")
    images = {p.stem: np.load(p, allow_pickle=True) for p in (work / "images").glob("*.npy")}
    return plain, observed, observed_cnn.instances[-1].recorded_proba[1], images


@pytest.fixture(scope="module")
def imic_ours(tmp_path_factory):
    root = tmp_path_factory.mktemp("imic_ours")
    files = [(p.name, p.read_bytes()) for p in (MIMIC_EXAMPLE / "for_process.csv", MIMIC_EXAMPLE / "tag.csv")]
    run = workflows.start_run(root / "runs", sort_uploads(files))
    workflows.run_goal(run, "predict", root / "cache")
    return run


def _ours_test(run):
    predictions = run.table("predictions")
    return predictions[predictions["set"] == "test"].reset_index(drop=True)


@pytest.mark.slow
def test_imic_images_are_identical(imic_theirs, imic_ours):
    import numpy as np

    _, _, _, theirs = imic_theirs
    folder = imic_ours.path / "work" / "imic" / "imic_images"
    ours = {p.stem: np.load(p, allow_pickle=True) for p in folder.glob("*.npy")}
    assert set(ours) == set(theirs)
    assert len(set(ours) - {"bact_names"}) == 257  # one image per sample, plus the taxon names
    assert all(np.array_equal(ours[k], theirs[k]) for k in ours)


@pytest.mark.slow
def test_imic_split_hyperparameters_and_predicted_groups_are_identical(imic_theirs, imic_ours):
    from microplatform.engines.imic import default_params, load_imic

    plain, observed, _, _ = imic_theirs
    ours = _ours_test(imic_ours)
    coding = imic_ours.engine_record()["record"]["label_coding"]
    to_code = {v: int(k) for k, v in coding.items()}
    # The same test samples in the same order: their labels match ours position by position.
    assert list(plain["y_test"]) == [to_code[str(g)] for g in ours["true_group"]]
    assert list(plain["pred_test"]) == [to_code[str(g)] for g in ours["predicted_group"]]
    assert list(observed["pred_test"]) == list(plain["pred_test"])  # observing changes nothing
    _, apply_iMic, _, _ = load_imic()
    recorded = imic_ours.engine_record()["record"]["hyperparameters"]
    published = default_params()
    assert {k: v for k, v in recorded.items() if k != "input_dim"} == \
        {k: v for k, v in published.items() if k != "input_dim"}


@pytest.mark.slow
def test_imic_probabilities_and_auc_within_the_recorded_tolerance(imic_theirs, imic_ours):
    import numpy as np
    from sklearn.metrics import roc_auc_score

    plain, _, their_proba, _ = imic_theirs
    ours = _ours_test(imic_ours)
    proba_column = next(c for c in ours.columns if c.startswith("probability_of_"))
    diff = np.abs(np.asarray(their_proba) - ours[proba_column].to_numpy())
    assert diff.max() <= PROBABILITY_TOLERANCE, f"largest probability difference {diff.max():.2e}"
    their_auc = roc_auc_score(plain["y_test"], their_proba)
    our_auc = imic_ours.table("test_metrics")["auc"].iloc[0]
    assert abs(their_auc - our_auc) <= AUC_TOLERANCE


@pytest.mark.slow
def test_imic_two_runs_with_the_same_seed_agree(imic_ours, tmp_path):
    files = [(p.name, p.read_bytes()) for p in (MIMIC_EXAMPLE / "for_process.csv", MIMIC_EXAMPLE / "tag.csv")]
    again = workflows.start_run(tmp_path / "runs", sort_uploads(files))
    workflows.run_goal(again, "predict", tmp_path / "cache")
    first, second = _ours_test(imic_ours), _ours_test(again)
    pd.testing.assert_frame_equal(first, second, check_exact=False, atol=PROBABILITY_TOLERANCE, rtol=0)


# --- LOCATE ------------------------------------------------------------------------------------
# The product runs locate_lightning2 (the authors' LOCATE converted to Lightning 2). Its faithfulness
# to the original was established in validation/locate/ against the original LOCATE in a Python 3.10
# reference environment (never shipped): PROTOCOL.md (fixed in advance, with Amendment 1),
# RESULTS.md (V1': the conversion is bit-identical) and RESULTS-V2.md (V2: the product passes the
# approved equivalence rule). The evidence is saved in tests/data/locate_reference/ (RULE.md).
# Still to come, V3: against the authors' own results on a real paired dataset.
LOCATE_REFERENCE = Path(__file__).parent / "data" / "locate_reference"
LOCATE_EXAMPLE = Path(__file__).parents[1] / "validation" / "locate" / "data" / "E2"


def test_locate_product_passes_the_approved_rule_against_the_original():
    """V2 as approved: the 90% CI of mean(C - A) over seeds 10-29 lies within ±0.02."""
    import math

    scores = pd.read_csv(LOCATE_REFERENCE / "v2_scores.csv")
    assert list(scores["seed"]) == list(range(10, 30))
    d = scores["C"] - scores["A"]
    half = 1.729 * d.std(ddof=1) / math.sqrt(len(d))
    assert -0.02 <= d.mean() - half and d.mean() + half <= 0.02


def _platform() -> str:
    import platform

    return f"{platform.system()}-{platform.machine()}".lower()


def _exact_reference(seed: int) -> tuple[Path, Path]:
    """This platform's recorded predictions: the laptop's (Windows, the V2 evidence) or one re-validated
    under the same rule on another platform (``platforms/<os>-<cpu>/``, e.g. the lab server)."""
    if _platform() == "windows-amd64":
        return LOCATE_REFERENCE / f"C_pred_val_seed{seed}.csv", LOCATE_REFERENCE / f"C_run_seed{seed}.json"
    folder = LOCATE_REFERENCE / "platforms" / _platform()
    if not folder.exists():
        pytest.skip(f"No LOCATE reference recorded for {_platform()}: different processors round differently, "
                    "so re-validate there first (validation/locate/server_check.py, the approved V2 rule).")
    return folder / f"pred_val_seed{seed}.csv", folder / f"seed{seed}.json"


def test_locate_on_other_platforms_passed_the_same_rule():
    """Every platform with its own exact reference also passed V2's rule against the original (A)."""
    import math

    original = pd.read_csv(LOCATE_REFERENCE / "v2_scores.csv").set_index("seed")["A"]
    for scores_file in sorted((LOCATE_REFERENCE / "platforms").glob("*/v2_scores.csv")):
        scores = pd.read_csv(scores_file).set_index("seed")["score"]
        assert list(scores.index) == list(range(10, 30)), scores_file
        d = scores - original
        half = 1.729 * d.std(ddof=1) / math.sqrt(len(d))
        assert -0.02 <= d.mean() - half and d.mean() + half <= 0.02, scores_file


@pytest.mark.slow
@pytest.mark.parametrize("seed", [10, 11, 12])
def test_locate_product_still_gives_its_validated_output(seed, tmp_path, monkeypatch):
    """The product is deterministic on a given platform; any change (e.g. a library upgrade, or another
    processor) means: re-validate first. Each platform keeps its own recorded predictions."""
    import json

    from microplatform.engines.locate import fit_and_predict

    predictions, run_info = _exact_reference(seed)
    read = lambda name: pd.read_csv(LOCATE_EXAMPLE / f"{name}.csv", index_col=0, float_precision="round_trip")
    monkeypatch.chdir(tmp_path)  # the tool writes lightning_logs/ into the current folder
    out = fit_and_predict(read("X_train"), read("Y_train"), read("X_val"), read("Y_val"), seed=seed)
    saved = pd.read_csv(predictions, index_col=0, float_precision="round_trip")
    info = json.loads(run_info.read_text())
    assert out["epochs"] == info["epochs"]
    # LOCATE computes in float32; the file keeps 9 significant digits, which recover each float32 exactly.
    np.testing.assert_array_equal(out["pred_val"].to_numpy(dtype="float32"), saved.to_numpy().astype("float32"))
