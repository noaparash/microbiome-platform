import io
from pathlib import Path

import pandas as pd
import pytest

from microplatform.core.profiler import (
    ProfileError,
    profile_counts,
    profile_labels,
    read_table,
)

DATA = Path(__file__).parent / "data"
TAX = "k__Bacteria;p__Firmicutes;c__Bacilli;o__Lactobacillales;f__Lactobacillaceae;g__Lactobacillus;s__"


def make_counts(rows: dict[str, list], taxonomy: list[str] | None = None) -> pd.DataFrame:
    """Build a table in the shared format: ID column, one row per sample, taxonomy row last."""
    n_taxa = len(next(iter(rows.values())))
    records = [[sid, *vals] for sid, vals in rows.items()]
    if taxonomy is not None:
        records.append(["taxonomy", *taxonomy])
    return pd.DataFrame(records, columns=["ID", *[f"asv{i}" for i in range(n_taxa)]])


@pytest.fixture(scope="module")
def example():
    counts = read_table(DATA / "example_counts.csv")
    tags = read_table(DATA / "example_tag.csv", index_col=0)
    return counts, tags


# --- real example data -------------------------------------------------------

def test_example_counts_profile(example):
    p = profile_counts(example[0])
    assert p.ok
    assert (p.n_samples, p.n_taxa) == (40, 263)
    assert p.has_taxonomy
    assert p.value_kind == "counts"
    assert p.taxonomy_depth == 6  # genus is named for most taxa; species only for a minority
    assert 0 < p.rank_coverage["species"] < 0.5
    assert 0.5 < p.zero_fraction < 1
    assert "taxonomy" not in p.sample_ids


def test_example_labels_profile(example):
    counts, tags = example
    lp = profile_labels(tags, profile_counts(counts).sample_ids)
    assert lp.ok
    assert lp.column == "Tag"
    assert lp.kind == "binary"
    assert lp.class_counts == {"0": 20, "1": 20}
    assert lp.missing == []


def test_summary_is_plain_language(example):
    text = " ".join(profile_counts(example[0]).summary())
    assert "40 samples" in text and "263" in text and "genus" in text


# --- reading files -------------------------------------------------------------

def test_reads_tab_separated():
    tsv = io.StringIO(f"ID\tasv0\na\t5\ntaxonomy\t{TAX}\n")
    assert read_table(tsv).shape == (2, 2)


def test_semicolons_in_taxonomy_do_not_split_columns():
    csv = io.StringIO(f"ID,asv0,asv1\na,1,2\ntaxonomy,{TAX},{TAX}\n")
    assert read_table(csv).shape == (2, 3)


def test_reads_tab_separated_labels_with_index():
    tsv = io.StringIO("\tTag\na\t1\nb\t0\n")
    assert read_table(tsv, index_col=0)["Tag"].tolist() == [1, 0]


def test_reads_uploaded_bytes():
    upload = io.BytesIO(f"ID,asv0\na,5\ntaxonomy,{TAX}\n".encode())
    assert read_table(upload).shape == (2, 2)


def test_unreadable_file_raises_friendly_error():
    with pytest.raises(ProfileError):
        read_table(io.StringIO(""))


# --- counts problems ----------------------------------------------------------

def test_missing_taxonomy_row_is_an_error():
    p = profile_counts(make_counts({"a": [1, 2], "b": [3, 4]}))
    assert not p.ok
    assert any("taxonomy" in i.message for i in p.issues)


def test_non_numeric_values_are_an_error():
    p = profile_counts(make_counts({"a": [1, "x"], "b": [3, 4]}, [TAX, TAX]))
    assert not p.ok


def test_duplicate_sample_ids_are_an_error():
    df = make_counts({"a": [1, 2]}, [TAX, TAX])
    df = pd.concat([df.iloc[:1], df]).reset_index(drop=True)
    assert not profile_counts(df).ok


def test_wrong_id_column_name_is_only_a_warning():
    df = make_counts({f"s{i}": [i, 1] for i in range(12)}, [TAX, TAX]).rename(columns={"ID": "sample"})
    p = profile_counts(df)
    assert p.ok
    assert any(i.level == "warning" and "'ID'" in i.message for i in p.issues)


@pytest.mark.parametrize(
    ("rows", "kind"),
    [
        ({"a": [1, 3], "b": [0, 7]}, "counts"),
        ({"a": [0.25, 0.75], "b": [0.5, 0.5]}, "relative"),
        ({"a": [25.0, 75.0], "b": [50.5, 49.5]}, "relative"),
        ({"a": [-1.2, 0.4], "b": [0.3, 2.1]}, "transformed"),
    ],
)
def test_value_kind(rows, kind):
    assert profile_counts(make_counts(rows, [TAX, TAX])).value_kind == kind


# --- labels -----------------------------------------------------------------------

@pytest.mark.parametrize(
    ("values", "kind"),
    [
        (["sick", "healthy"] * 6, "binary"),
        ([0, 1, 2] * 4, "categorical"),
        (["a", "b", "c"] * 4, "categorical"),
        ([i * 0.37 for i in range(12)], "continuous"),
        (list(range(12)), "continuous"),  # more distinct integers than MAX_CATEGORIES
    ],
)
def test_label_kind(values, kind):
    ids = [f"s{i}" for i in range(len(values))]
    assert profile_labels(pd.DataFrame({"Tag": values}, index=ids), ids).kind == kind


def test_unlabelled_samples_are_reported():
    ids = [f"s{i}" for i in range(12)]
    tags = pd.DataFrame({"Tag": [0, 1] * 5}, index=ids[:10])
    lp = profile_labels(tags, ids)
    assert lp.ok
    assert lp.missing == ["s10", "s11"]


def test_single_unnamed_label_column_is_accepted():
    ids = ["a", "b", "c", "d"]
    lp = profile_labels(pd.DataFrame({"disease": [0, 1, 0, 1]}, index=ids), ids)
    assert lp.column == "disease"


def test_label_with_one_value_is_an_error():
    ids = ["a", "b", "c"]
    assert not profile_labels(pd.DataFrame({"Tag": [1, 1, 1]}, index=ids), ids).ok


def test_labels_matching_no_sample_is_an_error():
    lp = profile_labels(pd.DataFrame({"Tag": [0, 1]}, index=["x", "y"]), ["a", "b"])
    assert not lp.ok
