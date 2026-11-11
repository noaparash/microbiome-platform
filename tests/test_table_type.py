"""What kind of table was uploaded (profiler.check_table): the rules that decide whether MIPMLP should run.

A real case (2026-11-10, run a1534bb2): 1,506 samples × 64 selected taxa, relative abundances of a subset
(values 0–1, 41% exact zeros, samples adding up to 0.002–1.0, four samples with one taxon at exactly 1.0,
names such as 'g__Bifidobacterium_388775'). It was taken for an already preprocessed table and MIPMLP was
skipped. It is *partial relative abundances*: a type of its own, never "preprocessed".
"""

import numpy as np
import pandas as pd
import pytest

from microplatform.core.inputs import sort_uploads
from microplatform.core.preprocessing import preprocess
from microplatform.core.profiler import (
    MANY_ZEROS, TABLE_TYPE_NAMES, check_table, profile_counts, read_table,
)
from microplatform.examples import EXAMPLE_COUNTS

EVIDENCE = {"min", "max", "negative_values", "zero_fraction", "whole_number_fraction", "row_sum_min",
            "row_sum_max", "samples_adding_up_to_1", "samples", "columns", "columns_with_sub_pca_ending",
            "columns_with_mean_about_0"}


@pytest.fixture(scope="module")
def counts() -> pd.DataFrame:
    raw = pd.read_csv(EXAMPLE_COUNTS, dtype=str)
    values = raw.iloc[:-1, 1:].astype(float)
    values.columns = raw.iloc[-1, 1:].tolist()  # lineages as names
    return values


@pytest.fixture(scope="module")
def mipmlp_output() -> pd.DataFrame:
    return preprocess(read_table(EXAMPLE_COUNTS)).table


def partial_shares(counts: pd.DataFrame) -> pd.DataFrame:
    """Like the real case: shares of 40 selected taxa (of 263), so samples add up to different totals
    (at most 1); two samples hold one taxon only (exactly 1.0); names end in database IDs."""
    shares = counts.div(counts.sum(axis=1), axis=0).iloc[:, :40].copy()
    shares.iloc[0] = 0.0
    shares.iloc[0, 3] = 1.0
    shares.iloc[1] = 0.0
    shares.iloc[1, 5] = 1.0
    shares.columns = [f"{c.rstrip(';')}_{388775 + i}" for i, c in enumerate(shares.columns)]
    return shares


# --- one test per type -------------------------------------------------------------------------

def test_read_counts(counts):
    check = check_table(counts)
    assert check.type == "counts" and "whole numbers" in check.sentence


@pytest.mark.parametrize("scale", [1, 100])
def test_full_relative_abundances_as_shares_or_percentages(counts, scale):
    assert check_table(counts.div(counts.sum(axis=1), axis=0) * scale).type == "relative"


def test_partial_relative_abundances_the_real_case(counts):
    shares = partial_shares(counts)
    check = check_table(shares)
    assert check.type == "partial_relative", check.sentence
    ev = check.evidence
    assert ev["negative_values"] == 0 and ev["max"] == 1.0 and ev["row_sum_max"] <= 1 + 1e-9
    assert ev["zero_fraction"] >= MANY_ZEROS and ev["row_sum_min"] < 0.5
    assert ev["columns_with_sub_pca_ending"] == 0  # '_388775' is a database ID, not sub-PCA's '_0'
    assert check.sentence.startswith("Your table looks like relative abundances of a subset of taxa")
    assert "exactly 0" in check.sentence and "never above 1" in check.sentence


def test_mipmlp_output_is_preprocessed_by_negatives_and_names(mipmlp_output):
    check = check_table(mipmlp_output)
    assert check.type == "preprocessed"
    assert any("negative" in r for r in check.reasons) and any("sub-PCA index" in r for r in check.reasons)
    assert any("mean of about 0" in r for r in check.reasons)  # MIPMLP z-scores within sub-PCA: supporting


def test_sub_pca_names_alone_mark_a_table_preprocessed(mipmlp_output):
    shifted = mipmlp_output - mipmlp_output.min().min()  # no negatives left, MIPMLP's names kept
    check = check_table(shifted)
    assert check.type == "preprocessed" and check.evidence["negative_values"] == 0
    assert check.evidence["columns_with_sub_pca_ending"] >= 0.5 * shifted.shape[1]


def test_database_id_endings_are_not_sub_pca(counts):
    named = counts.copy()
    named.columns = [f"{c.rstrip(';')}_{100000 + i}" for i, c in enumerate(counts.columns)]
    assert check_table(named).type == "counts"


def test_a_few_short_endings_are_not_enough(counts):
    named = counts.copy()
    named.columns = [f"{c}_0" if i < 10 else c for i, c in enumerate(counts.columns)]  # 10 of 263
    assert check_table(named).type == "counts"


def test_a_column_mean_of_zero_never_decides_alone():
    """A non-negative column has mean 0 only when it is all zeros, and constant columns are not counted,
    so 'mean about 0' can only accompany negatives; here it is reported, the negatives decide."""
    rng = np.random.default_rng(0)
    z = pd.DataFrame(rng.normal(size=(30, 5)))
    z = (z - z.mean()) / z.std()
    check = check_table(z)
    assert check.type == "preprocessed" and check.evidence["columns_with_mean_about_0"] == 5
    zeros = pd.DataFrame(np.zeros((5, 3))).assign(x=[0.1, 0.2, 0.3, 0.2, 0.1])
    assert check_table(zeros).evidence["columns_with_mean_about_0"] == 0


@pytest.mark.parametrize("table", [
    pd.DataFrame({"a": [0.3, 0.2, 0.1], "b": [0.4, 0.3, 0.2]}),  # 0–1, sums ≤ 1, but no zeros
    pd.DataFrame({"a": [1.3, 0.0, 2.1], "b": [0.4, 3.3, 0.0]}),  # e.g. log10(count + 1): above 1
    pd.DataFrame({"a": [30.5, 0.0, 10.2], "b": [40.1, 50.3, 0.0]}),  # partial percentages
])
def test_everything_else_is_unclear(table):
    check = check_table(table)
    assert check.type == "unclear" and check.sentence.startswith("We can't tell")


def test_the_first_rule_that_applies_wins(counts):
    with_negative = counts.copy()
    with_negative.iloc[0, 0] = -1  # whole numbers, but a negative one: not counts
    assert check_table(with_negative).type == "preprocessed"


# --- the evidence and the profile --------------------------------------------------------------

def test_every_check_carries_all_the_evidence(counts, mipmlp_output):
    for table in (counts, partial_shares(counts), mipmlp_output, pd.DataFrame({"a": [0.3], "b": [0.4]})):
        check = check_table(table)
        assert set(check.evidence) == EVIDENCE and check.type in TABLE_TYPE_NAMES


def test_the_profile_carries_the_check_using_the_lineages(counts):
    """Uploaded as the real file was (lineages as column names, no taxonomy row), the profile's check
    sees the lineages, and the names' database IDs do not count as sub-PCA."""
    shares = partial_shares(counts)
    shares.insert(0, "ID", [f"s{i}" for i in range(len(shares))])
    upload = sort_uploads([("0_fixed_ordered_n_all_otu_sub_pca_log_tax_7.csv",
                            shares.to_csv(index=False).encode())])
    profile = profile_counts(upload.counts)
    assert profile.table_check.type == "partial_relative"
    assert profile_counts(read_table(EXAMPLE_COUNTS)).table_check.type == "counts"
