"""Group tests on the diversity figures (reports/diversity_stats.py), checked against the libraries themselves."""

import json
import warnings

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from scipy.spatial.distance import pdist, squareform
from statsmodels.stats.multitest import multipletests

from microplatform.core.preprocessing import CANONICAL
from microplatform.core.profiler import count_matrix, profile_labels, read_table
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.reports import diversity_stats as ds
from microplatform.reports.figures import ellipse_outline, export, to_plotly
from microplatform.reports.overview import DESCRIPTIVE, EXPLORATORY, overview_figures


def _groups(sizes: dict[str, int]) -> pd.Series:
    labels = [g for g, n in sizes.items() for _ in range(n)]
    return pd.Series(labels, index=[f"s{i}" for i in range(len(labels))], name="group")


# --- marks and effect sizes ------------------------------------------------------------------------

@pytest.mark.parametrize(("p", "mark"), [(0.0009, "***"), (0.001, "**"), (0.0099, "**"), (0.01, "*"),
                                          (0.0499, "*"), (0.05, "ns"), (0.7, "ns"), (np.nan, "n/a")])
def test_stars_as_in_the_reference(p, mark):
    assert ds.stars(p) == mark


def test_cohens_d_uses_the_pooled_standard_deviation():
    a, b = np.array([1.0, 2, 3, 4, 5]), np.array([2.0, 4, 6, 8])
    pooled = np.sqrt((4 * np.var(a, ddof=1) + 3 * np.var(b, ddof=1)) / 7)
    assert ds.cohens_d(a, b) == pytest.approx((a.mean() - b.mean()) / pooled)
    assert np.isnan(ds.cohens_d(np.ones(4), np.ones(4)))  # no spread: undefined, not infinite


# --- alpha diversity -------------------------------------------------------------------------------

def test_two_normal_groups_get_a_t_test_and_skewed_ones_mann_whitney():
    rng = np.random.default_rng(1)
    groups = _groups({"a": 30, "b": 30})
    quantiles = stats.norm.ppf((np.arange(30) + 0.5) / 30)  # textbook-normal values: Shapiro-Wilk passes
    normal = np.r_[5 + quantiles, 6 + rng.permutation(quantiles)]
    skewed = rng.exponential(1, 60) ** 3
    values = pd.DataFrame({"Normal": normal, "Skewed": skewed}, index=groups.index)
    table = ds.alpha_tests(values, groups, ["a", "b"]).set_index("measure")
    a, b = normal[:30], normal[30:]
    assert table.loc["Normal", "test"] == "Student's t-test"
    assert table.loc["Normal", "p_value"] == pytest.approx(stats.ttest_ind(a, b).pvalue)
    assert table.loc["Skewed", "test"] == "Mann-Whitney U"
    assert table.loc["Skewed", "p_value"] == pytest.approx(
        stats.mannwhitneyu(skewed[:30], skewed[30:], alternative="two-sided").pvalue)
    # Benjamini-Hochberg over the figure's pairwise tests (both measures), as the reference does.
    assert table["p_fdr"].tolist() == pytest.approx(multipletests(table["p_value"], method="fdr_bh")[1].tolist())
    assert table.loc["Normal", "cohens_d"] == pytest.approx(ds.cohens_d(a, b))
    assert set(table["significance"]) <= {"***", "**", "*", "ns"}


def test_more_groups_get_an_overall_test_and_every_pair():
    rng = np.random.default_rng(2)
    groups = _groups({"a": 20, "b": 20, "c": 20})
    values = pd.DataFrame({"M": rng.normal(0, 1, 60) + np.repeat([0, 0.5, 1.5], 20)}, index=groups.index)
    table = ds.alpha_tests(values, groups, ["a", "b", "c"])
    assert table["comparison"].tolist() == ["overall", "a vs b", "a vs c", "b vs c"]
    overall = table.iloc[0]
    assert overall["test"] == "One-way ANOVA"
    assert overall["p_value"] == pytest.approx(stats.f_oneway(*[values["M"][groups == g] for g in "abc"]).pvalue)
    pairs = table.iloc[1:]
    assert pairs["p_fdr"].tolist() == pytest.approx(multipletests(pairs["p_value"], method="fdr_bh")[1].tolist())
    marks = ds.brackets(table, ["a", "b", "c"])
    assert marks[0] == ("M", "a", "c", f"ANOVA {overall['significance']}")  # the overall test spans all groups
    assert len(marks) == 4


def test_non_normal_groups_get_kruskal_wallis_and_many_groups_only_the_overall_bracket():
    rng = np.random.default_rng(3)
    names = list("abcdef")
    groups = _groups({g: 10 for g in names})
    values = pd.DataFrame({"M": rng.exponential(1, 60) ** 3}, index=groups.index)
    table = ds.alpha_tests(values, groups, names)
    assert table.iloc[0]["test"] == "Kruskal-Wallis" and len(table) == 1 + 15
    assert [label for *_, label in ds.brackets(table, names)] == [f"Kruskal-Wallis {table.iloc[0]['significance']}"]


def test_groups_too_small_to_test_are_left_out():
    groups = _groups({"a": 10, "b": 2, "c": 10})
    values = pd.DataFrame({"M": np.arange(22, dtype=float)}, index=groups.index)
    table = ds.alpha_tests(values, groups, ["a", "b", "c"])
    assert set(table["group_a"]) | set(table["group_b"]) == {"a", "c"}  # b has fewer than MIN_PER_GROUP
    assert ds.alpha_tests(values, _groups({"a": 20, "b": 2}), ["a", "b"]) is None


# --- beta diversity --------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def example():
    counts = count_matrix(read_table(EXAMPLE_COUNTS))
    labels = profile_labels(read_table(EXAMPLE_TAGS, index_col=0), list(counts.index))
    groups = labels.values.map(lambda v: f"Tag {v:g}").reindex(counts.index)
    return counts, labels, groups


def test_permanova_and_permdisp_are_scikit_bio_on_bray_curtis_of_relative_abundance(example):
    from skbio import DistanceMatrix
    from skbio.stats.distance import permanova, permdisp
    from skbio.stats.ordination import pcoa

    counts, _, groups = example
    row = ds.beta_tests(counts, groups, ["Tag 0", "Tag 1"]).iloc[0]
    relative = counts.div(counts.sum(axis=1), axis=0)
    dm = DistanceMatrix(squareform(pdist(relative.to_numpy(), "braycurtis")), ids=list(counts.index))
    frame = groups.rename("group").to_frame()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        direct = permanova(dm, frame, column="group", permutations=999, seed=ds.SEED)
        ordination = pcoa(dm, method="eigh", dimensions=len(counts))
        dispersion = permdisp(ordination, frame, column="group", test="median", permutations=999, seed=ds.SEED)
    assert row["pseudo_F"] == pytest.approx(float(direct["test statistic"]))
    assert row["p_value"] == pytest.approx(float(direct["p-value"]))
    assert row["permdisp_F"] == pytest.approx(float(dispersion["test statistic"]))
    assert row["permutations"] == 999 and row["permdisp_centre"] == "spatial median"
    # The same every time (seeded permutations).
    assert ds.beta_tests(counts, groups, ["Tag 0", "Tag 1"]).iloc[0]["p_value"] == row["p_value"]


def test_eta_squared_is_between_over_total_and_equals_r2_for_euclidean_distances():
    from skbio import DistanceMatrix
    from skbio.stats.distance import permanova
    from skbio.stats.ordination import pcoa

    rng = np.random.default_rng(0)
    x = rng.normal(size=(30, 4))
    x[:15] += 0.8
    groups = _groups({"a": 15, "b": 15})
    dm = DistanceMatrix(squareform(pdist(x)), ids=list(groups.index))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        coords = pcoa(dm, method="eigh", dimensions=30).samples
        f = float(permanova(dm, groups.to_frame(), column="group", seed=1)["test statistic"])
    assert ds.eta_squared(coords, groups) == pytest.approx(f / (f + 28))  # R² = F(k−1) / (F(k−1) + n − k)


def test_beta_tests_need_two_groups_with_enough_samples(example):
    counts, _, _ = example
    assert ds.beta_tests(counts, pd.Series("x", index=counts.index), ["x"]) is None


# --- the ellipse -----------------------------------------------------------------------------------

def test_the_95_percent_ellipse_holds_about_95_percent_of_normal_points():
    rng = np.random.default_rng(4)
    points = rng.multivariate_normal([1, -2], [[2, 1.2], [1.2, 1]], size=20000)
    ex, ey = ellipse_outline(points[:, 0], points[:, 1], 0.95)
    from matplotlib.path import Path as Outline
    inside = Outline(np.column_stack([ex, ey])).contains_points(points).mean()
    assert inside == pytest.approx(0.95, abs=0.01)
    assert ellipse_outline([0, 1], [0, 1], 0.95) is None  # fewer than 3 points


# --- on the figures --------------------------------------------------------------------------------

def test_the_figures_carry_the_tests_and_say_they_are_exploratory(example, tmp_path):
    counts, labels, _ = example
    figs = {f.name: f for f in overview_figures(counts, CANONICAL, labels.values, labels.kind)}
    alpha, beta = figs["alpha_diversity"], figs["beta_pcoa"]
    assert alpha.caption.endswith(EXPLORATORY) and beta.caption.endswith(EXPLORATORY)
    assert alpha.brackets and dict(alpha.panel_titles) and beta.ellipses == 0.95
    assert "PERMANOVA" in beta.subtitle and "PERMDISP" in beta.caption and "η²" in beta.caption
    exported = {e.name: e for e in export([alpha, beta], tmp_path)}
    for name in ("alpha_diversity", "beta_pcoa"):
        assert exported[name].files["tests"] == f"{name}_tests.csv"
        pd.testing.assert_frame_equal(pd.read_csv(tmp_path / f"{name}_tests.csv"), figs[name].stats,
                                      check_dtype=False)
    # The interactive versions draw the same brackets and ellipses.
    boxes = to_plotly(alpha)
    paths = [s for s in boxes.layout.shapes if s.type == "path"]
    assert len(paths) == len(alpha.brackets)
    assert all(s.fillcolor == "rgba(0,0,0,0)" for s in paths)  # a bracket is a line: plotly would fill it
    scatter = json.loads(to_plotly(beta).to_json())
    assert sum(t.get("name", "").endswith(" ellipse") for t in scatter["data"]) == 2
    # Without groups: the plain descriptive figures, and no stale tests file left behind.
    plain = {f.name: f for f in overview_figures(counts, CANONICAL)}
    exported = {e.name: e for e in export([plain["alpha_diversity"], plain["beta_pcoa"]], tmp_path)}
    assert plain["alpha_diversity"].caption.endswith(DESCRIPTIVE) and plain["beta_pcoa"].ellipses is None
    assert "tests" not in exported["alpha_diversity"].files
    assert not (tmp_path / "alpha_diversity_tests.csv").exists()
