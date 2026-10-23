"""The GIMIC engine: both groupings, the contained exception, outputs and determinism."""

import numpy as np
import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core.contract import ContractError, check_settings
from microplatform.core.inputs import InputError, sort_uploads
from microplatform.core.preprocessing import CANONICAL
from microplatform.engines.gimic import GROUPING_DEFAULT, GimicEngine, load_gimic
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS

ENGINE = GimicEngine()


# --- the option and the contract's exception ---------------------------------------------

def test_sub_pca_is_the_default_grouping():
    assert GROUPING_DEFAULT == "sub PCA"
    assert ENGINE.resolve(None) == {"grouping": "sub PCA"}
    assert ENGINE.settings_for(ENGINE.resolve(None)) == CANONICAL  # the shared table, unchanged


def test_mean_grouping_changes_only_the_grouping():
    settings = ENGINE.settings_for(ENGINE.resolve({"grouping": "mean"}))
    assert settings == CANONICAL.with_changes(taxonomy_group="mean")


@pytest.mark.parametrize("choices", [{"grouping": "sum"}, {"cutoff": "0.5"}])
def test_unknown_choices_are_refused_with_a_reason(choices):
    with pytest.raises(InputError) as info:
        ENGINE.resolve(choices)
    assert info.value.fix


def test_mean_is_allowed_for_gimic_only():
    mean = CANONICAL.with_changes(taxonomy_group="mean")
    check_settings(mean, "GIMIC")  # the declared exception
    for other in (None, "MIPMLP", "miMic", "iMic"):
        with pytest.raises(ContractError):
            check_settings(mean, other)
    with pytest.raises(ContractError):  # only the listed value, not any grouping
        check_settings(CANONICAL.with_changes(taxonomy_group="sum"), "GIMIC")


# --- running it ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("cache")


def _run(root, cache, choices=None, labels=True):
    files = [(EXAMPLE_COUNTS.name, EXAMPLE_COUNTS.read_bytes())]
    if labels:
        files.append((EXAMPLE_TAGS.name, EXAMPLE_TAGS.read_bytes()))
    run = workflows.start_run(root, sort_uploads(files))
    workflows.run_goal(run, "group", cache, choices)
    return run


@pytest.fixture(scope="module")
def sub_pca_run(tmp_path_factory, cache):
    return _run(tmp_path_factory.mktemp("subpca"), cache)


def test_distances_are_a_proper_distance_matrix(sub_pca_run):
    dm = sub_pca_run.table("distance_matrix").set_index("ID")
    dm.index = dm.index.astype(str)
    assert dm.shape == (40, 40) and list(dm.index) == list(dm.columns)
    values = dm.to_numpy()
    assert np.allclose(values, values.T) and np.allclose(np.diag(values), 0) and (values >= 0).all()


def test_sub_pca_mode_uses_the_shared_table_and_the_authors_functions(sub_pca_run, cache):
    """In sub-PCA mode GIMIC's distances are the authors' functions applied to the shared table."""
    data = workflows.build_dataset(sub_pca_run, CANONICAL, cache)[0]
    micro2matrix, build = load_gimic()
    imgs, names, ordered = micro2matrix(data.features, "unused", save=False)
    theirs = build("unused", imgs=imgs, ordered_df=ordered, bact_names=names, class_=False)
    ours = sub_pca_run.table("distance_matrix").set_index("ID")
    ours.index, theirs.index, theirs.columns = ours.index.astype(str), theirs.index.astype(str), theirs.columns.astype(str)
    pd.testing.assert_frame_equal(ours, theirs, check_names=False, check_exact=True)


def test_outputs_and_summary(sub_pca_run):
    engine = sub_pca_run.engine_record()
    assert engine["tool"] == "GIMIC" and engine["choices"] == {"grouping": "sub PCA"}
    assert set(engine["tables"]) == {"distance_matrix", "map_coordinates", "group_distances"}
    assert any("sub-PCA" in line and "same table" in line for line in engine["summary"])
    assert any("not a statistical test" in line for line in engine["summary"])
    groups = sub_pca_run.table("group_distances")
    assert list(groups["comparison"]) == ["within '0'", "within '1'", "between groups"]
    assert groups["pairs"].sum() == 40 * 39 // 2
    assert workflows.describe(sub_pca_run).representation_note is None  # shared table: nothing to flag


def test_the_map_is_the_same_on_every_run(sub_pca_run, tmp_path, cache):
    again = _run(tmp_path, cache)
    pd.testing.assert_frame_equal(sub_pca_run.table("map_coordinates"), again.table("map_coordinates"))


def test_mean_mode_is_labelled_as_the_exception(tmp_path, cache):
    run = _run(tmp_path, cache, {"grouping": "mean"})
    view = workflows.describe(run)
    assert view.record["settings"]["taxonomy_group"] == "mean"
    assert "taxonomy group 'mean'" in view.representation_note and "'sub PCA'" in view.representation_note
    assert any("published example" in line and "not on exactly the same" in line for line in view.engine["summary"])


def test_without_labels_there_is_a_map_but_no_group_comparison(tmp_path, cache):
    run = _run(tmp_path, cache, labels=False)
    assert set(run.engine_record()["tables"]) == {"distance_matrix", "map_coordinates"}
    assert set(run.table("map_coordinates")["group"]) == {"all samples"}
