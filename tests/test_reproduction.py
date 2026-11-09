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


def _taxonomy_as_column_names(path: Path) -> bytes:
    """The authors' combined file re-expressed as "taxonomy in the column names": each column is
    named by its lineage (the text of the taxonomy row) and the taxonomy row is removed."""
    import csv
    import io

    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
    taxonomy = next(r for r in rows if r[0].strip().lower() == "taxonomy")
    body = [r for r in rows[1:] if r is not taxonomy]
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([[rows[0][0], *taxonomy[1:]], *body])
    return out.getvalue().encode()


def _features(tmp_path, name, content):
    run = workflows.start_run(tmp_path / f"runs-{name}", sort_uploads([(name, content)]))
    # Each side gets its own empty cache: a shared cache would hand back the other side's table.
    return workflows.build_dataset(run, CANONICAL, tmp_path / f"cache-{name}")[0].features


@pytest.mark.parametrize("example", [
    EXAMPLE_COUNTS,
    pytest.param(MIMIC_EXAMPLE / "for_process.csv", marks=pytest.mark.slow),  # all 257 samples
], ids=["example-40", "authors-257"])
def test_taxonomy_in_column_names_gives_the_same_preprocessed_table(tmp_path, example):
    """Faithfulness of the "taxonomy in the column names" layout: the authors' example in that
    layout gives exactly the preprocessed table of the combined (taxonomy row) file."""
    headers = _taxonomy_as_column_names(example)
    assert b"\ntaxonomy," not in headers.lower()
    combined = _features(tmp_path, "combined.csv", example.read_bytes())
    from_headers = _features(tmp_path, "headers.csv", headers)
    assert sort_uploads([("headers.csv", headers)]).counts_layout == "headers"
    pd.testing.assert_frame_equal(from_headers, combined)  # exact: same columns, samples and values


def test_a_repeated_lineage_in_the_column_names_is_kept_as_written(tmp_path):
    """Two columns with the same lineage (pandas would rename the second '….1'): both layouts still
    give the same preprocessed table. The authors' example has none, so one is made here."""
    import csv
    import io

    rows = list(csv.reader(io.StringIO(EXAMPLE_COUNTS.read_text(encoding="utf-8"))))
    for row in (rows[0], next(r for r in rows if r[0] == "taxonomy")):
        row[2] = row[1]  # the second bacteria column takes the first one's lineage
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    combined_file = tmp_path / "repeated.csv"
    combined_file.write_text(out.getvalue(), encoding="utf-8")
    combined = _features(tmp_path, "combined.csv", combined_file.read_bytes())
    from_headers = _features(tmp_path, "headers.csv", _taxonomy_as_column_names(combined_file))
    pd.testing.assert_frame_equal(from_headers, combined)


# --- miMic's cladogram: the authors' own drawing ---------------------------------------------

def test_mimic_cladogram_is_the_authors_own_tree(run, tmp_path):
    """The engine draws miMic's cladogram with the last call of the authors' plot mode only. On the
    same table and labels, its SVG is byte for byte the one the authors' whole plot mode
    (engines/mimic_authors.py, apply_mimic(mode="plot")) writes."""
    from microplatform.engines import mimic_authors

    workflows.run_goal(run, "differ", tmp_path / "cache")
    ours = run.figures_dir / "mimic_cladogram.svg"
    assert ours.exists() and run.figure_file("mimic_cladogram.png") is not None
    from PIL import Image

    with Image.open(run.figures_dir / "mimic_cladogram.png") as png:  # printable, as the lab's reference
        assert 2000 <= max(png.size) <= 2200, png.size  # 180 mm at 300 dpi (it was once 73,630 px square)
    svg = ours.read_text()
    # miMic's own 100 pt labels; markers capped (TREE_MARKER_MAX), so the tree is no longer stretched by
    # 2,000-unit markers (the SVG was ~67,000 units wide on the 1,506-sample case).
    assert 'font-size="100pt"' in svg and 'font-size="400pt"' not in svg
    import re
    radii = [float(r) for r in re.findall(r'<circle[^>]* r="([0-9.]+)"', svg)]
    assert radii and max(radii) <= mimic_authors.TREE_MARKER_MAX / 2 + 0.5, max(radii)
    shown = [f.name for f in workflows.describe(run).findings]
    assert shown[0] == "mimic_cladogram"  # the headline figure, before the bars
    assert shown[-1] == "mimic_rp_sp"  # the authors' RP vs SP check, after the bars
    assert "mimic_apriori_test" not in shown  # replaced by the authors' own figure

    features = workflows.build_dataset(run, CANONICAL, tmp_path / "cache")[0]
    tags = features.labels.to_frame()
    mimic_authors.run_bundle(features.features.loc[tags.index], tags, tmp_path / "authors")
    theirs = tmp_path / "authors" / "plots" / "correlations_tree.svg"
    assert ours.read_bytes() == theirs.read_bytes()
    # miMic's RP vs SP check: its own drawing ships unchanged (byte for byte the authors'
    # plot_rp_sp_anova_p, same seed), and the platform's redraw shows exactly miMic's numbers.
    for ext in ("png", "svg"):
        mine = (run.figures_dir / f"mimic_rp_sp_original.{ext}").read_bytes()
        assert mine == (tmp_path / "authors" / "plots" / f"tax_vs_rp_sp_anova_p.{ext}").read_bytes(), ext
    redrawn = pd.read_csv(run.figures_dir / "mimic_rp_sp.csv")
    authors = pd.read_csv(tmp_path / "authors" / "rp_sp.csv")
    for series, column in (("Real labels (RP)", "RP"), ("Shuffled labels (SP)", "SP")):
        assert redrawn.loc[redrawn["labels"] == series, "significant_leaves"].tolist() == authors[column].tolist()


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
    read = lambda name: pd.read_csv(folder / name, index_col=0, float_precision="round_trip")  # noqa: E731
    return selected, read("df_corrs.csv"), read("just_mimic.csv"), read("u_test_without_mimic.csv")


@pytest.fixture(scope="module")
def mimic_ours(tmp_path_factory):
    """Our engine, through the normal workflow, on the same two files."""
    root = tmp_path_factory.mktemp("ours")
    files = [(p.name, p.read_bytes()) for p in (MIMIC_EXAMPLE / "for_process.csv", MIMIC_EXAMPLE / "tag.csv")]
    run = workflows.start_run(root / "runs", sort_uploads(files))
    workflows.run_goal(run, "differ", cache_dir=root / "cache")
    both = pd.concat([run.table("significant_taxa"), run.table("leaf_test_only")], ignore_index=True)
    return run.engine_record(), both, run.table("significant_taxa"), run.table("leaf_test_only")


def test_mimic_finds_exactly_the_authors_taxa(mimic_theirs, mimic_ours):
    """miMic's own result = the authors' just_mimic.csv; the leaf-test-only taxa = their
    u_test_without_mimic.csv; together = their df_corrs.csv. The headline counts miMic's only."""
    _, theirs, just_mimic, leaf_only = mimic_theirs
    record, ours, our_mimic, our_leaf_only = mimic_ours
    assert len(theirs) > 0, "the authors' example should find significant taxa"
    assert sorted(ours["taxon"]) == sorted(theirs.index)
    assert sorted(our_mimic["taxon"]) == sorted(just_mimic.index)
    assert sorted(our_leaf_only["taxon"]) == sorted(leaf_only.index)
    assert record["record"]["significant_taxa"] == len(just_mimic)
    assert f"{len(just_mimic)} taxa are significant by miMic's tree test" in " ".join(record["summary"])


def test_mimic_scores_and_p_values_are_identical(mimic_theirs, mimic_ours):
    _, theirs, _, _ = mimic_theirs
    _, ours, _, _ = mimic_ours
    ours = ours.set_index("taxon").loc[theirs.index]
    pd.testing.assert_series_equal(ours["p"], theirs["p"], check_names=False, check_exact=True)
    pd.testing.assert_series_equal(ours["statistic"], theirs["scc"], check_names=False, check_exact=True)


def test_mimic_starts_the_post_hoc_test_at_the_same_level(mimic_theirs, mimic_ours):
    selected, _, _, _ = mimic_theirs
    record, _, _, _ = mimic_ours
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
    """Every platform with its own exact reference passed V2's rule against the original (A), on the
    seeds its plan names (``scores.csv``: seed, A, S; e.g. the lab server: Amendment 2, seeds 30-69)."""
    import math

    from scipy.stats import t as student_t

    folders = sorted((LOCATE_REFERENCE / "platforms").glob("*/"))
    assert folders, "the lab server's reference is recorded"
    for folder in folders:
        scores = pd.read_csv(folder / "scores.csv")
        assert len(scores) >= 20 and scores["seed"].is_unique, folder
        d = scores["S"] - scores["A"]
        half = student_t.ppf(0.95, len(d) - 1) * d.std(ddof=1) / math.sqrt(len(d))
        assert -0.02 <= d.mean() - half and d.mean() + half <= 0.02, folder


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
