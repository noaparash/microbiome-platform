import pandas as pd
import pytest

from microplatform.core.preprocessing import (
    CANONICAL,
    PreprocessError,
    cache_key,
    preprocess,
)
from microplatform.core.profiler import read_table
from microplatform.examples import EXAMPLES_DIR as DATA



@pytest.fixture(scope="module")
def raw():
    return read_table(DATA / "example_counts.csv")


@pytest.fixture(scope="module")
def result(raw):
    return preprocess(raw)


# --- the canonical run ------------------------------------------------------------

def test_one_row_per_sample(raw, result):
    sample_ids = raw["ID"].iloc[:-1].astype(str).tolist()
    assert sorted(result.table.index.astype(str)) == sorted(sample_ids)


def test_output_is_clean_numbers(result):
    assert 0 < result.n_features <= result.n_input_taxa == 263
    assert not result.table.isna().any().any()
    assert all(pd.api.types.is_float_dtype(t) for t in result.table.dtypes)


def test_input_is_not_modified(raw):
    before = raw.copy()
    preprocess(raw)
    pd.testing.assert_frame_equal(raw, before)


def test_record_is_reproducible(result):
    rec = result.record()
    assert rec["tool"] == "MIPMLP"
    assert rec["mipmlp_version"]
    assert rec["settings"]["taxonomy_group"] == "sub PCA"
    assert rec["output_features"] == result.n_features


def test_summary_is_plain_language(result):
    text = " ".join(result.summary())
    assert "263 taxa" in text and "species" in text


def test_leaves_no_stray_files(raw, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    preprocess(raw)
    assert list(tmp_path.iterdir()) == []


# --- settings and variations ---------------------------------------------------

def test_settings_use_mipmlp_spelling():
    kwargs = CANONICAL.to_mipmlp_kwargs()
    assert kwargs["taxnomy_group"] == "sub PCA"
    assert kwargs["pca"] == (0, "PCA") and kwargs["plot"] is False


def test_variation_does_not_change_canonical():
    genus = CANONICAL.with_changes(taxonomy_level=6)
    assert genus.taxonomy_level == 6
    assert CANONICAL.taxonomy_level == 7


def test_genus_level_gives_no_more_features_than_species(raw, result):
    genus = preprocess(raw, CANONICAL.with_changes(taxonomy_level=6))
    assert genus.n_features <= result.n_features


def test_first_column_need_not_be_called_id(raw, result):
    renamed = preprocess(raw.rename(columns={"ID": "sample"}))
    assert renamed.n_features == result.n_features


# --- caching ---------------------------------------------------------------------------

def test_second_run_comes_from_cache(raw, tmp_path):
    first = preprocess(raw, cache_dir=tmp_path)
    second = preprocess(raw, cache_dir=tmp_path)
    assert (first.from_cache, second.from_cache) == (False, True)
    pd.testing.assert_frame_equal(first.table, second.table)
    assert len(list(tmp_path.glob("*.json"))) == 1  # settings saved next to the cached table


def test_cache_key_depends_on_settings_and_data(raw):
    key = cache_key(raw, CANONICAL)
    assert key == cache_key(raw.copy(), CANONICAL)
    assert key != cache_key(raw, CANONICAL.with_changes(z_scoring="col"))
    changed = raw.copy()
    changed.iloc[0, 1] = int(changed.iloc[0, 1]) + 1
    assert key != cache_key(changed, CANONICAL)


# --- bad input ---------------------------------------------------------------------------

def test_invalid_table_gives_user_message(raw):
    without_taxonomy = raw.iloc[:-1]
    with pytest.raises(PreprocessError, match="taxonomy"):
        preprocess(without_taxonomy)
