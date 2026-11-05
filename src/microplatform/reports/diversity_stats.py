"""Group comparisons for the diversity figures, as in the lab's reference analysis.

The reference is louzounlab/Early-Pregnancy-Oral-Microbiome (``Analysis/alpha_diversity.py`` and
``Analysis/beta_diversity_diff_control_gdm_time.py``). Run only when the samples form groups.

Alpha diversity (``alpha_tests``), per measure (Shannon, richness):
    the test is chosen by normality: Shapiro-Wilk per group (p > 0.05 in every group compared:
    parametric). Two groups: Student's t-test or Mann-Whitney U. More groups: an overall one-way
    ANOVA or Kruskal-Wallis, plus every pair. Benjamini-Hochberg (FDR) correction over all pairwise
    tests of the figure (both measures, as the reference does) and, separately, over the overall
    tests. Cohen's d (pooled SD) for each pair.

Beta diversity (``beta_tests``), on Bray-Curtis distances between relative abundances:
    PERMANOVA (scikit-bio, 999 permutations, fixed seed): pseudo-F and p; η² = between-group / total
    sum of squares on all PCoA axes (the reference's effect size); PERMANOVA's own R²; and PERMDISP
    (scikit-bio, distances to each group's spatial median, on a PCoA with all axes) to show whether
    the groups differ in spread, which PERMANOVA cannot tell apart from a difference in location.

All of these are exploratory: computed on the uploaded data and not corrected across the report.
"""

from __future__ import annotations

import warnings
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import pdist, squareform
from statsmodels.stats.multitest import multipletests

ALPHA = 0.05  # the normality cut-off and the significance level of the stars
MIN_PER_GROUP = 3  # a group needs this many samples to be tested (and for Shapiro-Wilk)
PERMUTATIONS = 999
SEED = 42  # PERMANOVA and PERMDISP draw permutations: the same result every time
MAX_BRACKETS = 4  # with more groups, the figure shows only the overall test (every pair is in the CSV)
TESTS = {"t": "Student's t-test", "mw": "Mann-Whitney U", "anova": "One-way ANOVA", "kw": "Kruskal-Wallis"}

__all__ = ["alpha_tests", "beta_tests", "stars", "eta_squared"]


def stars(p: float) -> str:
    """The reference's significance marks: *** < 0.001, ** < 0.01, * < 0.05, otherwise ns."""
    if p is None or not np.isfinite(p):
        return "n/a"
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"


def testable_groups(groups: pd.Series) -> list[str]:
    """Groups with enough samples to test, in the given (sorted) order."""
    sizes = groups.value_counts()
    return [g for g in dict.fromkeys(groups) if sizes[g] >= MIN_PER_GROUP]


# --- alpha diversity -----------------------------------------------------------------------------

def alpha_tests(values: pd.DataFrame, groups: pd.Series, order: list[str]) -> pd.DataFrame | None:
    """One row per test: for each measure (column of ``values``), the overall test (more than two
    groups) and every pair. ``groups`` gives each sample's group; ``order`` the groups' order.

    None when fewer than two groups have ``MIN_PER_GROUP`` samples.
    """
    names = [g for g in order if g in testable_groups(groups)]
    if len(names) < 2:
        return None
    rows = []
    for measure in values.columns:
        by_group = {g: values.loc[groups[groups == g].index, measure].dropna().to_numpy(float) for g in names}
        normal_p = {g: _shapiro(v) for g, v in by_group.items()}
        normal = {g: np.isfinite(p) and p > ALPHA for g, p in normal_p.items()}
        if len(names) > 2:
            parametric = all(normal.values())
            statistic, p = (stats.f_oneway if parametric else stats.kruskal)(*by_group.values())
            rows.append({"measure": measure, "comparison": "overall", "group_a": "all groups", "group_b": "",
                         "n_a": sum(len(v) for v in by_group.values()), "n_b": np.nan,
                         "test": TESTS["anova" if parametric else "kw"], "statistic": float(statistic),
                         "p_value": float(p), "cohens_d": np.nan,
                         "shapiro_p_a": np.nan, "shapiro_p_b": np.nan})
        for a, b in combinations(names, 2):
            va, vb = by_group[a], by_group[b]
            parametric = normal[a] and normal[b]
            if parametric:
                statistic, p = stats.ttest_ind(va, vb)
            else:
                statistic, p = stats.mannwhitneyu(va, vb, alternative="two-sided")
            rows.append({"measure": measure, "comparison": f"{a} vs {b}", "group_a": a, "group_b": b,
                         "n_a": len(va), "n_b": len(vb), "test": TESTS["t" if parametric else "mw"],
                         "statistic": float(statistic), "p_value": float(p), "cohens_d": cohens_d(va, vb),
                         "shapiro_p_a": normal_p[a], "shapiro_p_b": normal_p[b]})
    table = pd.DataFrame(rows)
    table.insert(table.columns.get_loc("p_value") + 1, "p_fdr", np.nan)
    for overall in (True, False):
        rows_of = (table["comparison"] == "overall") == overall
        table.loc[rows_of, "p_fdr"] = _fdr(table.loc[rows_of, "p_value"])
    table.insert(table.columns.get_loc("p_fdr") + 1, "significance", table["p_fdr"].map(stars))
    table.insert(table.columns.get_loc("cohens_d") + 1, "effect_size", table["cohens_d"].map(_effect))
    return table


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """(mean a − mean b) / pooled standard deviation (sample variances, n − 1), as in the reference."""
    na, nb = len(a), len(b)
    pooled = np.sqrt(((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1)) / (na + nb - 2))
    return float((np.mean(a) - np.mean(b)) / pooled) if pooled > 0 else np.nan


def _effect(d: float) -> str:
    if not np.isfinite(d):
        return ""
    d = abs(d)
    return "negligible" if d < 0.2 else "small" if d < 0.5 else "medium" if d < 0.8 else "large"


def _shapiro(values: np.ndarray) -> float:
    """Shapiro-Wilk p, or NaN when it cannot be computed (fewer than 3 values, or all equal)."""
    if len(values) < 3 or np.ptp(values) == 0:
        return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(stats.shapiro(values).pvalue)


def _fdr(p: pd.Series) -> np.ndarray:
    if p.empty:
        return np.array([])
    corrected = np.full(len(p), np.nan)
    ok = p.notna().to_numpy()
    if ok.any():
        corrected[ok] = multipletests(p[ok].to_numpy(), method="fdr_bh")[1]
    return corrected


def brackets(table: pd.DataFrame, order: list[str]) -> tuple[tuple[str, str, str, str], ...]:
    """What the box figure draws above the boxes: (measure, from group, to group, label).

    Every pair (FDR-corrected marks, ns included) when there are at most ``MAX_BRACKETS`` groups;
    with more groups, only the overall test, spanning all of them.
    """
    out = []
    groups = [g for g in order if g in set(table["group_a"]) | set(table["group_b"])]
    for _, row in table.iterrows():
        if row["comparison"] == "overall":
            out.append((row["measure"], groups[0], groups[-1], f"{_short(row['test'])} {row['significance']}"))
        elif len(groups) <= MAX_BRACKETS:
            out.append((row["measure"], row["group_a"], row["group_b"], row["significance"]))
    return tuple(out)


def _short(test: str) -> str:
    return {"One-way ANOVA": "ANOVA"}.get(test, test)


# --- beta diversity ------------------------------------------------------------------------------

def beta_tests(counts: pd.DataFrame, groups: pd.Series, order: list[str]) -> pd.DataFrame | None:
    """PERMANOVA, η² and PERMDISP for the groups with enough samples (one row), or None.

    ``counts`` holds the samples with reads; Bray-Curtis is computed on their relative abundance,
    as for the PCoA map.
    """
    from skbio import DistanceMatrix
    from skbio.stats.distance import permanova, permdisp
    from skbio.stats.ordination import pcoa

    names = [g for g in order if g in testable_groups(groups)]
    if len(names) < 2:
        return None
    members = groups[groups.isin(names)]
    table = counts.loc[members.index]
    relative = table.div(table.sum(axis=1), axis=0).to_numpy()
    distances = squareform(pdist(relative, metric="braycurtis"))
    if not np.any(distances):
        return None
    ids = [str(i) for i in members.index]
    dm = DistanceMatrix(distances, ids=ids)
    grouping = pd.Series(members.astype(str).to_numpy(), index=ids, name="group")
    frame = grouping.to_frame()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # negative eigenvalues of Bray-Curtis: expected, not an error
        result = permanova(dm, frame, column="group", permutations=PERMUTATIONS, seed=SEED)
        ordination = pcoa(dm, method="eigh", dimensions=len(ids))  # every axis, not only the first 10
        dispersion = permdisp(ordination, frame, column="group", test="median", permutations=PERMUTATIONS,
                              seed=SEED)
    n, k = len(ids), len(names)
    f = float(result["test statistic"])
    return pd.DataFrame([{
        "test": "PERMANOVA", "distance": "Bray-Curtis on relative abundance", "groups": ", ".join(names),
        "n_samples": n, "permutations": PERMUTATIONS, "seed": SEED,
        "pseudo_F": f, "p_value": float(result["p-value"]),
        "eta_squared_pcoa": eta_squared(ordination.samples, grouping),
        "permanova_R2": f * (k - 1) / (f * (k - 1) + (n - k)),
        "permdisp_F": float(dispersion["test statistic"]), "permdisp_p": float(dispersion["p-value"]),
        "permdisp_centre": "spatial median",
    }])


def eta_squared(coords: pd.DataFrame, groups: pd.Series) -> float:
    """Between-group / total sum of squares over all PCoA axes (the reference's R²-like effect size)."""
    x = coords.loc[groups.index].to_numpy(float)
    mean = x.mean(axis=0)
    total = float(((x - mean) ** 2).sum())
    between = sum(len(rows) * float(((x[rows].mean(axis=0) - mean) ** 2).sum())
                  for rows in (np.flatnonzero(groups.to_numpy() == g) for g in pd.unique(groups)))
    return between / total if total > 0 else np.nan
