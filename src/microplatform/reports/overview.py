"""Data overview: the standard figures that describe a microbiome dataset, made with every analysis.

Mostly they describe. When the samples form groups, the two diversity figures add the lab's
group tests (``reports/diversity_stats.py``): alpha diversity gets significance brackets, beta
diversity PERMANOVA, PERMDISP and 95% ellipses. Those tests are exploratory: computed on the
uploaded data, not corrected across the report, and not a tool's finding; their captions say so
(``EXPLORATORY``). Every other caption says the figure is descriptive (``DESCRIPTIVE``).

Everything here is computed from the **user's own table** (``Dataset.raw_counts``: counts or
relative abundances), never from the log-transformed table the tools use:

    composition_bars   phylum composition in the lab's fig_1B style (``reports/composition.py``):
                       one stacked bar per sample, and the mean of all samples beside them
    composition_pie    the average composition (one pie per group, if there are groups)
    composition_violin optional (``split_violin=True``, two groups only): per phylum, group A
                       against group B as the two halves of a violin
    alpha_diversity    Shannon index and richness per sample, as boxes per group with every sample shown
                       (with groups: tests between groups, brackets, a CSV of the tests)
    beta_pcoa          PCoA of Bray-Curtis distances between samples (on relative abundance)
                       (with groups: PERMANOVA, η², PERMDISP, 95% ellipses, a CSV of the tests)
    taxa_per_sample    row sparsity: how many taxa each sample contains
    taxa_prevalence    column sparsity: in how many samples each taxon appears

Composition is shown at phylum level: the 12 phyla with the highest mean get a colour each
(``palette="lab"``, the lab's look, by default; ``palette="colorblind"`` for a colour-blind-safer
set), the rest are summed as "Other" in grey. A phylum has the same colour in every
composition figure and every dataset; a group has the same colour in the diversity boxes,
the PCoA and the violins.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform

from microplatform.core.contract import LABEL_COLUMN, LabelKind
from microplatform.core.preprocessing import PreprocessSettings
from microplatform.core.profiler import value_kind
from microplatform.reports import composition, diversity_stats
from microplatform.reports.composition import PALETTE_DEFAULT, TOP_PHYLA, CompositionError
from microplatform.reports.figures import OTHER, Figure, group_colors, taxa_prevalence

NO_LABEL = "No label"  # samples the labels file does not mention
ALL_SAMPLES = "All samples"  # the one group when there are no labels
GROUPABLE: tuple[LabelKind, ...] = ("binary", "categorical")  # a continuous label has no groups
MIN_ORDINATION = 3  # samples needed for a PCoA map
DESCRIPTIVE = "Descriptive only, not a statistical test."
EXPLORATORY = ("Exploratory: tests on the uploaded data, not corrected across this report, and not a "
               "tool's finding.")
ELLIPSE = 0.95  # the share of a group's points its ellipse holds (normal theory)
SHANNON = "Shannon index"
RICHNESS = "Richness (taxa observed)"
# Every figure of the overview, in page order (the PCoA is left out when it cannot be drawn).
FIGURE_NAMES = ("composition_bars", "composition_pie", "alpha_diversity", "beta_pcoa", "taxa_per_sample",
                "taxa_prevalence")
VIOLIN = "composition_violin"  # only with split_violin=True and two groups, right after the pie

__all__ = ["overview_figures", "alpha_diversity", "bray_curtis_pcoa", "sample_groups"]

OVERVIEW_UNAVAILABLE = ("The descriptive overview is not drawn for this table: it has negative values (it is "
                        "already log-transformed or z-scored), and composition, diversity and distances between "
                        "samples need abundances.")


def overview_figures(
    counts: pd.DataFrame,
    settings: PreprocessSettings,
    labels: pd.Series | None = None,
    label_kind: LabelKind | None = None,
    dataset: str | None = None,
    palette: str = PALETTE_DEFAULT,
    split_violin: bool = False,
    top_n: int = TOP_PHYLA,
) -> list[Figure]:
    """The data overview from the user's table (samples × taxa, columns named by lineage).

    With two-group or categorical ``labels``, samples are grouped by label. Samples
    without any reads are left out of the composition, diversity and PCoA figures (and
    the captions say how many). The PCoA needs at least 3 such samples.

    ``dataset`` names the composition figure (its bold heading); ``palette`` is "lab"
    (default) or "colorblind"; ``split_violin`` adds the per-phylum split violins when the
    samples form two groups. A table that cannot be shown as relative abundance (e.g.
    already log-transformed, with negative values) gets no composition figures.
    A table with negative values (already log-transformed or z-scored, e.g. MIPMLP output used as it
    is) gets no overview at all: composition, diversity and Bray-Curtis distances need abundances,
    and would be wrong on such values (the page says why: ``OVERVIEW_UNAVAILABLE``).
    """
    if (counts.to_numpy() < 0).any():
        return []
    with_reads = counts.loc[counts.sum(axis=1) > 0]
    grouped = label_kind in GROUPABLE and labels is not None
    groups = sample_groups(with_reads.index, labels if grouped else None)
    colors = tuple(group_colors(_ordered(groups)).items())
    dropped = len(counts) - len(with_reads)
    left_out = f" {dropped:,} sample{'s' if dropped != 1 else ''} without reads {'are' if dropped != 1 else 'is'} left out." if dropped else ""
    figures = _composition_figures(with_reads, groups if grouped else None, dataset, palette, split_violin,
                                   top_n, left_out)
    figures.append(_alpha_figure(with_reads, groups, colors, left_out, tested=grouped))
    if len(with_reads) >= MIN_ORDINATION:
        pcoa = _beta_figure(with_reads, groups if grouped else None, colors, left_out)
        if pcoa is not None:
            figures.append(pcoa)
    prevalence = taxa_prevalence(counts, settings, section="overview")
    return figures + [_taxa_per_sample(counts), replace(prevalence, caption=f"{prevalence.caption} {DESCRIPTIVE}")]


# --- the numbers ------------------------------------------------------------------------

def alpha_diversity(counts: pd.DataFrame) -> pd.DataFrame:
    """Per sample: Shannon index (natural log, on each sample's proportions) and richness (taxa with a count > 0)."""
    proportions = counts.div(counts.sum(axis=1), axis=0)
    logs = np.log(proportions.where(proportions > 0))  # 0 · log 0 counts as 0
    shannon = -(proportions * logs).sum(axis=1, min_count=0)
    return pd.DataFrame({SHANNON: shannon, RICHNESS: (counts > 0).sum(axis=1)}, index=counts.index)


def bray_curtis_pcoa(counts: pd.DataFrame, axes: int = 2) -> tuple[pd.DataFrame, np.ndarray] | None:
    """PCoA (classical multidimensional scaling) of Bray-Curtis distances on relative abundance.

    Returns the samples' coordinates on the first ``axes`` axes (``PCo1``…) and the share of
    the variation each axis shows (out of all positive eigenvalues), or None if the samples
    do not differ at all. Each axis's sign is fixed (largest coordinate positive), so the
    map is the same every time.
    """
    relative = counts.div(counts.sum(axis=1), axis=0).to_numpy()
    distances = squareform(pdist(relative, metric="braycurtis"))
    n = len(distances)
    centre = np.eye(n) - 1 / n
    inner = -0.5 * centre @ (distances ** 2) @ centre
    values, vectors = np.linalg.eigh(inner)
    order = np.argsort(values)[::-1]
    values, vectors = values[order], vectors[:, order]
    positive = values[values > 1e-12]
    if len(positive) == 0:
        return None
    k = min(axes, len(positive))
    coords = vectors[:, :k] * np.sqrt(values[:k])
    coords *= np.sign(coords[np.abs(coords).argmax(axis=0), range(k)])
    table = pd.DataFrame(coords, index=counts.index, columns=[f"PCo{i + 1}" for i in range(k)])
    return table, values[:k] / positive.sum()


def sample_groups(samples: pd.Index, labels: pd.Series | None) -> pd.Series:
    """Each sample's group from its label ("Tag 1" for numbers; "No label" if it has none).

    Without labels, every sample is in one group, "All samples".
    """
    def name(value) -> str:
        if pd.isna(value):
            return NO_LABEL
        if isinstance(value, str):
            return value
        return f"{LABEL_COLUMN} {value:g}"
    if labels is None:
        return pd.Series(ALL_SAMPLES, index=samples, name="group")
    return pd.Series([name(v) for v in labels.reindex(samples)], index=samples, name="group")


def _ordered(groups: pd.Series) -> list[str]:
    """Group names sorted, with "No label" last."""
    named = sorted(g for g in groups.unique() if g != NO_LABEL)
    return named + ([NO_LABEL] if NO_LABEL in set(groups) else [])


# --- the figures ------------------------------------------------------------------------

def _composition_figures(counts: pd.DataFrame, groups: pd.Series | None, dataset: str | None, palette: str,
                         split_violin: bool, top_n: int, left_out: str) -> list[Figure]:
    """Bars and pie (and the split violins if asked), sharing one colour per phylum; none if not possible."""
    try:
        percent, removed = composition.phylum_percent(counts)
    except CompositionError:
        return []
    top = composition.top_phyla(percent, top_n)
    colors = composition.phylum_colors(top.columns, palette)
    gone = removed["samples_dropped"]
    notes = left_out
    if removed["unassigned_percent"] >= 0.05:
        notes += (f" Abundance with no phylum (on average {removed['unassigned_percent']:.1f}% of a sample) is "
                  "left out before the shares are computed.")
    if gone:
        notes += f" {gone:,} sample{'s' if gone != 1 else ''} with nothing at phylum level {'are' if gone != 1 else 'is'} left out."
    figures = [composition.composition_figure(top, colors, dataset, notes, DESCRIPTIVE),
               _composition_pie(top, groups.loc[top.index] if groups is not None else None, colors)]
    if split_violin and groups is not None:
        labelled = groups.loc[top.index]
        labelled = labelled[labelled != NO_LABEL]
        violin = composition.split_violin_figure(
            percent.loc[labelled.index], labelled, list(top.columns),
            group_colors(_ordered(labelled)), DESCRIPTIVE)
        if violin is not None:
            figures.append(violin)
    return figures


def _composition_pie(percent: pd.DataFrame, groups: pd.Series | None, colors: dict[str, str]) -> Figure:
    rank = "phylum"
    if groups is None:
        data = pd.DataFrame({rank: percent.columns, "percent": percent.mean().round(4).to_numpy()})
        title, over = f"Average composition ({rank})", "all samples"
    else:
        means = percent.groupby(groups).mean().loc[_ordered(groups)]
        data = (means.stack(future_stack=True).round(4).rename("percent")
                .rename_axis(["group", rank]).reset_index())
        title, over = f"Average composition per group ({rank})", "the samples of each group"
    rest = f", with the rest summed as {OTHER}" if OTHER in percent.columns else ""
    return Figure(
        name="composition_pie",
        title=title,
        caption=f"The average share of each {rank} over {over} (each sample counts equally)"
                f"{rest}. Relative abundance from the uploaded table; the colours match the bars. {DESCRIPTIVE}",
        data=data, kind="pie", x=rank, y="percent", x_label="", y_label="",
        group_by="group" if groups is not None else None, colors=tuple(colors.items()),
        hover="%{label}: %{value:.1f}%<extra>%{fullData.name}</extra>",
        section="overview",
    )


def _alpha_figure(counts: pd.DataFrame, groups: pd.Series, colors: tuple, left_out: str,
                  tested: bool = False) -> Figure:
    alpha = alpha_diversity(counts)
    ordered = _ordered(groups)
    order = {g: i for i, g in enumerate(ordered)}
    wide = alpha.assign(group=groups).rename_axis("sample").reset_index()
    wide = wide.sort_values("group", key=lambda g: g.map(order), kind="stable")
    data = wide.melt(id_vars=["sample", "group"], var_name="measure", value_name="value")
    data["value"] = data["value"].round(6)
    labelled = groups[groups != NO_LABEL]
    table = diversity_stats.alpha_tests(alpha.loc[labelled.index], labelled, ordered) if tested else None
    if value_kind(counts) == "counts":
        caption = ("Each point is one sample; the box spans the middle half of the samples and the line is the "
                   "median. Shannon index (natural log) grows with both the number of taxa and how evenly "
                   "reads are spread among them; richness counts the taxa with at least one read. Computed on "
                   "the raw counts without rarefaction, so a deeper-sequenced sample tends to show more taxa.")
    else:  # relative abundances: there are no reads to speak of
        caption = ("Each point is one sample; the box spans the middle half of the samples and the line is the "
                   "median. Shannon index (natural log) grows with both the number of taxa and how evenly "
                   "the abundance is spread among them; richness counts the taxa above zero. Computed on the "
                   "uploaded values; richness still depends on how deeply each sample was sequenced, which "
                   "this table (not read counts) does not show.")
    if table is None:
        too_few = (f" Groups are not compared: fewer than two groups have {diversity_stats.MIN_PER_GROUP} or more "
                   "samples.") if tested else ""
        return Figure(
            name="alpha_diversity", title="Diversity within each sample (alpha diversity)",
            caption=f"{caption}{too_few}{left_out} {DESCRIPTIVE}",
            data=data, kind="box", x="group", y="value", x_label="", y_label="Value",
            group_by="group", facet="measure", label="sample", colors=colors,
            hover="%{text}: %{y:.3g}<extra></extra>", section="overview",
        )
    tests = sorted(set(table["test"]))
    per_panel = tuple((m, ", ".join(dict.fromkeys(table.loc[table["measure"] == m, "test"])))
                      for m in dict.fromkeys(table["measure"]))
    shown = len(set(table["group_a"]) - {"all groups"} | set(table["group_b"]) - {""})
    pairs_note = ("Every pair is marked." if shown <= diversity_stats.MAX_BRACKETS else
                  "Only the overall test is marked; every pair is in the tests CSV.")
    return Figure(
        name="alpha_diversity",
        title="Diversity within each sample (alpha diversity)",
        caption=f"{caption} Groups are compared per measure: Shapiro-Wilk in each group decides the test "
                f"(normal in every group: t-test or ANOVA; otherwise Mann-Whitney U or Kruskal-Wallis; here: "
                f"{', '.join(tests)}). Brackets show Benjamini-Hochberg (FDR) corrected p-values: *** < 0.001, "
                f"** < 0.01, * < 0.05, ns otherwise. {pairs_note} Cohen's d and every p-value are in the tests "
                f"CSV. Richness depends on sequencing depth here, so a richness difference can reflect "
                f"depth.{left_out} {EXPLORATORY}",
        data=data, kind="box", x="group", y="value", x_label="", y_label="Value",
        group_by="group", facet="measure", label="sample", colors=colors,
        hover="%{text}: %{y:.3g}<extra></extra>", section="overview",
        brackets=diversity_stats.brackets(table, ordered), panel_titles=per_panel, stats=table,
    )


def _beta_figure(counts: pd.DataFrame, groups: pd.Series | None, colors: tuple, left_out: str) -> Figure | None:
    found = bray_curtis_pcoa(counts)
    if found is None:
        return None
    coords, explained = found
    if coords.shape[1] < 2:
        coords["PCo2"] = 0.0
        explained = np.append(explained, 0.0)
    data = coords.round(6).rename_axis("sample").reset_index()
    if groups is not None:
        data.insert(1, "group", groups.loc[coords.index].to_numpy())
        order = {g: i for i, g in enumerate(_ordered(groups))}
        data = data.sort_values("group", key=lambda g: g.map(order), kind="stable").reset_index(drop=True)
    base = ("Each point is one sample; samples close together have similar compositions. The map is a "
            "principal coordinates analysis (PCoA) of Bray-Curtis distances on relative abundance; each "
            "axis says how much of the variation it shows.")
    figure = dict(
        name="beta_pcoa", title="How similar samples are (beta diversity, PCoA)",
        data=data, kind="scatter", x="PCo1", y="PCo2",
        x_label=f"PCo1 ({explained[0]:.1%} of variation)", y_label=f"PCo2 ({explained[1]:.1%} of variation)",
        color_by="group" if groups is not None else None, label="sample", colors=colors,
        hover="%{text}<br>PCo1 %{x:.3f}, PCo2 %{y:.3f}<extra></extra>", section="overview",
    )
    labelled = groups[groups != NO_LABEL] if groups is not None else None
    table = (diversity_stats.beta_tests(counts.loc[labelled.index], labelled, _ordered(labelled))
             if labelled is not None and len(labelled) else None)
    if table is None:
        too_few = (" Points are coloured by group. Groups are not tested: fewer than two groups have "
                   f"{diversity_stats.MIN_PER_GROUP} or more samples.") if groups is not None else ""
        return Figure(caption=f"{base}{too_few}{left_out} {DESCRIPTIVE}", **figure)
    row = table.iloc[0]
    p_text = _p(row["p_value"], diversity_stats.PERMUTATIONS)
    spread = ("the groups also differ in spread (PERMDISP p < 0.05), so part of the PERMANOVA result may come "
              "from spread rather than position" if row["permdisp_p"] < diversity_stats.ALPHA else
              "no difference in spread was found (PERMDISP p ≥ 0.05), so PERMANOVA's assumption of equal spread "
              "looks reasonable")
    return Figure(
        caption=f"{base} Points are coloured by group; each dashed ellipse is where about {ELLIPSE:.0%} of a "
                f"group's points would fall if they were normally distributed. PERMANOVA (scikit-bio, "
                f"{diversity_stats.PERMUTATIONS} permutations, seed {diversity_stats.SEED}) tests whether the "
                f"groups' compositions differ: pseudo-F = {row['pseudo_F']:.2f}, p {p_text}; η² = "
                f"{row['eta_squared_pcoa']:.1%} of the variation on all PCoA axes lies between groups "
                f"(PERMANOVA R² = {row['permanova_R2']:.1%}). PERMDISP (distance to each group's spatial "
                f"median): F = {row['permdisp_F']:.2f}, p {_p(row['permdisp_p'], diversity_stats.PERMUTATIONS)}; "
                f"{spread}.{left_out} {EXPLORATORY}",
        subtitle=f"PERMANOVA (Bray-Curtis): pseudo-F = {row['pseudo_F']:.2f}, p {p_text} · "
                 f"η² = {row['eta_squared_pcoa']:.1%}",
        ellipses=ELLIPSE, stats=table, **figure,
    )


def _p(p: float, permutations: int) -> str:
    """A permutation p-value as text: "= 0.012", or "≤ 0.001" at the smallest it can be."""
    floor = 1 / (permutations + 1)
    return f"≤ {floor:.3f}" if p <= floor else f"= {p:.3f}"


def _taxa_per_sample(counts: pd.DataFrame) -> Figure:
    detected = (counts > 0).sum(axis=1)
    data = pd.DataFrame({"sample": detected.index, "taxa_detected": detected.to_numpy(),
                         "percent_of_taxa": (detected / counts.shape[1] * 100).round(2).to_numpy()})
    median = float(detected.median())
    return Figure(
        name="taxa_per_sample",
        title="How many taxa each sample contains (row sparsity)",
        caption=f"For each sample, how many of the table's {counts.shape[1]:,} taxa it contains (a count above "
                "0); every other taxon is a zero in that sample's row. A sample far below the rest may have "
                f"failed sequencing. {DESCRIPTIVE}",
        data=data, kind="histogram", x="taxa_detected", y=None, x_range=None,
        x_label="Taxa detected in a sample", y_label="Number of samples",
        marker=(median, f"median {median:,.0f}"),
        hover="%{x} taxa: %{y} samples<extra></extra>",
        section="overview",
    )
