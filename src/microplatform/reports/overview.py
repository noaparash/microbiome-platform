"""Data overview: the standard figures that describe a microbiome dataset, made with every analysis.

They describe; they do not test. A difference between groups seen here is not a
finding (that is what the tools are for), and every caption says so.

Everything here is computed from the **raw counts** (``Dataset.raw_counts``), never from
the log-transformed table the tools use:

    composition_bars   one stacked bar per sample, % of its reads per taxon (+ an average bar per group)
    composition_pie    the average composition (one pie per group, if there are groups)
    alpha_diversity    Shannon index and richness per sample, as boxes per group with every sample shown
    beta_pcoa          PCoA of Bray-Curtis distances between samples (on relative abundance)
    taxa_per_sample    row sparsity: how many taxa each sample contains
    taxa_prevalence    column sparsity: in how many samples each taxon appears

Composition is shown at a readable rank (phylum by default): the ``top_n`` most
abundant taxa get a colour each (Okabe-Ito, colour-blind safe), the rest are summed as
"Other". A taxon has the same colour in the bars and the pies; a group has the same
colour in the diversity boxes and the PCoA.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform

from microplatform.core.contract import LABEL_COLUMN, RANK_SEPARATOR, LabelKind
from microplatform.core.preprocessing import PreprocessSettings
from microplatform.core.profiler import RANKS, _strip_prefix
from microplatform.reports.figures import OTHER, Figure, group_colors, taxa_prevalence, taxon_colors

RANK_DEFAULT = "phylum"
TOP_TAXA = 7  # one colour each (the Okabe-Ito palette has 7 besides black); the rest are "Other"
UNASSIGNED = "Unassigned"  # no name at the chosen rank
NO_LABEL = "No label"  # samples the labels file does not mention
ALL_SAMPLES = "All samples"  # the one group when there are no labels
AVERAGES = "Average per group"  # the composition figure's last block of bars
GROUPABLE: tuple[LabelKind, ...] = ("binary", "categorical")  # a continuous label has no groups
MIN_ORDINATION = 3  # samples needed for a PCoA map
DESCRIPTIVE = "Descriptive only, not a statistical test."
SHANNON = "Shannon index"
RICHNESS = "Richness (taxa observed)"
# Every figure of the overview, in page order (the PCoA is left out when it cannot be drawn).
FIGURE_NAMES = ("composition_bars", "composition_pie", "alpha_diversity", "beta_pcoa", "taxa_per_sample",
                "taxa_prevalence")
PLURAL = {"kingdom": "kingdoms", "phylum": "phyla", "class": "classes", "order": "orders",
          "family": "families", "genus": "genera", "species": "species"}

__all__ = ["overview_figures", "relative_abundance", "alpha_diversity", "bray_curtis_pcoa", "sample_groups"]


def overview_figures(
    counts: pd.DataFrame,
    settings: PreprocessSettings,
    labels: pd.Series | None = None,
    label_kind: LabelKind | None = None,
    rank: str = RANK_DEFAULT,
    top_n: int = TOP_TAXA,
) -> list[Figure]:
    """The data overview from the raw counts (samples × taxa, columns named by lineage).

    With two-group or categorical ``labels``, samples are grouped by label. Samples
    without any reads are left out of the composition, diversity and PCoA figures (and
    the captions say how many). The PCoA needs at least 3 such samples.
    """
    with_reads = counts.loc[counts.sum(axis=1) > 0]
    grouped = label_kind in GROUPABLE and labels is not None
    groups = sample_groups(with_reads.index, labels if grouped else None)
    percent = relative_abundance(with_reads, rank, top_n)
    taxa = tuple(taxon_colors(percent.columns).items())
    colors = tuple(group_colors(_ordered(groups)).items())
    dropped = len(counts) - len(with_reads)
    left_out = f" {dropped:,} sample{'s' if dropped != 1 else ''} without reads {'are' if dropped != 1 else 'is'} left out." if dropped else ""
    figures = [
        _composition_bars(percent, groups if grouped else None, rank, taxa, left_out),
        _composition_pie(percent, groups if grouped else None, rank, taxa),
        _alpha_figure(with_reads, groups, colors, left_out),
    ]
    if len(with_reads) >= MIN_ORDINATION:
        pcoa = _beta_figure(with_reads, groups if grouped else None, colors, left_out)
        if pcoa is not None:
            figures.append(pcoa)
    prevalence = taxa_prevalence(counts, settings, section="overview")
    return figures + [_taxa_per_sample(counts), replace(prevalence, caption=f"{prevalence.caption} {DESCRIPTIVE}")]


# --- the numbers ------------------------------------------------------------------------

def relative_abundance(counts: pd.DataFrame, rank: str = RANK_DEFAULT, top_n: int = TOP_TAXA) -> pd.DataFrame:
    """Samples × taxa at ``rank``, in % of each sample's reads (each row adds up to 100).

    Columns: the ``top_n`` most abundant taxa on average, most abundant first, then
    "Other" (the rest summed), if there is a rest. Samples without reads are left out.
    """
    level = RANKS.index(rank)
    names = [_name_at(lineage, level) for lineage in counts.columns]
    totals = counts.sum(axis=1)
    counts = counts.loc[totals > 0]
    per_taxon = counts.T.groupby(names).sum().T
    percent = per_taxon.div(totals.loc[counts.index], axis=0) * 100
    order = list(percent.mean().sort_values(ascending=False, kind="stable").index)
    named = [t for t in order if t != OTHER]  # a taxon really called "Other" joins the rest
    top = named[:top_n]
    out = percent[top].copy()
    if len(order) > len(top):
        out[OTHER] = percent.drop(columns=top).sum(axis=1)
    return out


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


def _name_at(lineage: str, level: int) -> str:
    """The taxon's name at one rank of its lineage ('k__Bacteria;p__Firmicutes;…', 1 → 'Firmicutes')."""
    parts = str(lineage).split(RANK_SEPARATOR)
    name = _strip_prefix(parts[level]) if len(parts) > level else ""
    return name or UNASSIGNED


def _ordered(groups: pd.Series) -> list[str]:
    """Group names sorted, with "No label" last."""
    named = sorted(g for g in groups.unique() if g != NO_LABEL)
    return named + ([NO_LABEL] if NO_LABEL in set(groups) else [])


# --- the figures ------------------------------------------------------------------------

def _composition_bars(percent: pd.DataFrame, groups: pd.Series | None, rank: str,
                      colors: tuple, left_out: str) -> Figure:
    lead = percent.columns[0]
    if groups is None:
        data = _long(percent.sort_values(lead, ascending=False, kind="stable"), rank, group=None)
    else:
        blocks = [_long(percent.loc[groups == g].sort_values(lead, ascending=False, kind="stable"), rank, group=g)
                  for g in _ordered(groups)]
        means = percent.groupby(groups).mean().loc[_ordered(groups)]
        means.index = [f"{g} average" for g in means.index]
        data = pd.concat([*blocks, _long(means, rank, group=AVERAGES)], ignore_index=True)
    named = len([t for t in percent.columns if t != OTHER])
    rest = f"; the rest are summed as {OTHER}" if OTHER in percent.columns else ""
    order = (f"Samples are grouped by label and sorted by the most abundant {rank}; the last bars are each "
             "group's average composition." if groups is not None else
             f"Samples are sorted by the most abundant {rank}.")
    return Figure(
        name="composition_bars",
        title=f"Composition of each sample ({rank})",
        caption=f"Each bar is one sample: the share of its reads from each {rank}, adding up to 100%. "
                f"The {named} most abundant {PLURAL[rank]} have a colour{rest}. {order} Relative abundance "
                f"from the raw counts, not the log-transformed table the tools use.{left_out} {DESCRIPTIVE}",
        data=data, kind="stacked", x="sample", y="percent", color_by=rank,
        x_label="Samples by group" if groups is not None else "Samples", y_label="Relative abundance (%)",
        group_by="group" if groups is not None else None, summary=(AVERAGES,) if groups is not None else (),
        colors=colors, hover="%{customdata[0]}<br>%{fullData.name}: %{y:.1f}%<extra></extra>",
        section="overview",
    )


def _long(percent: pd.DataFrame, rank: str, group: str | None) -> pd.DataFrame:
    """Wide (bars × taxa) to long rows: sample, [group,] taxon, percent; bar by bar, taxa in column order."""
    rows = (percent.stack(future_stack=True).round(4).rename("percent")
            .rename_axis(["sample", rank]).reset_index())
    if group is not None:
        rows.insert(1, "group", group)
    return rows


def _composition_pie(percent: pd.DataFrame, groups: pd.Series | None, rank: str, colors: tuple) -> Figure:
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
        caption=f"The average share of reads from each {rank} over {over} (each sample counts equally)"
                f"{rest}. Relative abundance from the raw counts; the colours match the bars. {DESCRIPTIVE}",
        data=data, kind="pie", x=rank, y="percent", x_label="", y_label="",
        group_by="group" if groups is not None else None, colors=colors,
        hover="%{label}: %{value:.1f}%<extra>%{fullData.name}</extra>",
        section="overview",
    )


def _alpha_figure(counts: pd.DataFrame, groups: pd.Series, colors: tuple, left_out: str) -> Figure:
    alpha = alpha_diversity(counts)
    order = {g: i for i, g in enumerate(_ordered(groups))}
    wide = alpha.assign(group=groups).rename_axis("sample").reset_index()
    wide = wide.sort_values("group", key=lambda g: g.map(order), kind="stable")
    data = wide.melt(id_vars=["sample", "group"], var_name="measure", value_name="value")
    data["value"] = data["value"].round(6)
    return Figure(
        name="alpha_diversity",
        title="Diversity within each sample (alpha diversity)",
        caption="Each point is one sample; the box spans the middle half of the samples and the line is the "
                "median. Shannon index (natural log) grows with both the number of taxa and how evenly "
                "reads are spread among them; richness counts the taxa with at least one read. Computed on "
                "the raw counts without rarefaction, so a deeper-sequenced sample tends to show more taxa."
                f"{left_out} {DESCRIPTIVE}",
        data=data, kind="box", x="group", y="value", x_label="", y_label="Value",
        group_by="group", facet="measure", label="sample", colors=colors,
        hover="%{text}: %{y:.3g}<extra></extra>",
        section="overview",
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
    by_group = (" Points are coloured by group; groups that sit apart differ in composition, but only a "
                "test (such as PERMANOVA) can say whether that is more than chance.") if groups is not None else ""
    return Figure(
        name="beta_pcoa",
        title="How similar samples are (beta diversity, PCoA)",
        caption="Each point is one sample; samples close together have similar compositions. The map is a "
                "principal coordinates analysis (PCoA) of Bray-Curtis distances on relative abundance; each "
                f"axis says how much of the variation it shows.{by_group}{left_out} {DESCRIPTIVE}",
        data=data, kind="scatter", x="PCo1", y="PCo2",
        x_label=f"PCo1 ({explained[0]:.1%} of variation)", y_label=f"PCo2 ({explained[1]:.1%} of variation)",
        color_by="group" if groups is not None else None, label="sample", colors=colors,
        hover="%{text}<br>PCo1 %{x:.3f}, PCo2 %{y:.3f}<extra></extra>",
        section="overview",
    )


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
