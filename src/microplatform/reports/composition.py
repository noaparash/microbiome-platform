"""Phylum composition, in the lab's figure style (the fig_1B scripts in references/composition/).

From the user's own abundance table (counts or already relative, never the log-transformed
table the tools use):

1. **Phylum table** (``phylum_percent``): each column's phylum is read from its lineage
   (``k__Bacteria;p__Firmicutes;…``; ``;``, ``|`` and ``,`` all separate ranks). A table that
   lists every rank (MetaPhlAn: ``k__…``, ``k__…|p__…``, ``k__…|p__…|c__…``) uses only its
   phylum rows, so nothing is counted twice. Columns with no phylum (``Bacteria``, ``Archaea``,
   ``Unassigned``, ``Unclassified``) are dropped, phyla are summed, samples that are left
   with nothing are dropped, and every sample is re-normalized to 100%. Values must be finite
   and not negative.
2. **Top phyla** (``top_phyla``): the ``TOP_PHYLA`` phyla with the highest mean over all
   samples, most abundant first; the rest are summed as "Other", drawn last in grey.
3. **Colours** (``phylum_colors``): one colour per phylum, the same in every panel, figure and
   dataset. Common gut phyla have a fixed slot (``KNOWN_PHYLA``; old and new names share it),
   so Firmicutes looks the same in every run; other phyla take the next free colour.
   ``palette="lab"`` (the default) is the lab's look, tab20 + Set3 + Pastel1;
   ``palette="colorblind"`` is a colour-blind-safer set of 12 hues.
4. **Figures**: ``composition_figure`` (left: one stacked bar per sample, sorted by Firmicutes
   if present, else by the top phylum; right: the mean of all samples) and, only when asked
   and the samples form two groups, ``split_violin_figure`` (per phylum: group A on the left
   half, group B on the right, medians marked).
"""

from __future__ import annotations

import re

import pandas as pd
from matplotlib import colormaps
from matplotlib.colors import to_hex

from microplatform.core.errors import UserFacingError
from microplatform.reports.figures import OTHER, Figure

TOP_PHYLA = 12
OTHER_GREY = "#BDBDBD"
MEAN = "Mean"  # the right panel's one bar
DROPPED = ("Bacteria", "Archaea", "Unassigned", "Unclassified")  # no phylum: left out (case-insensitive)
SORT_BY = ("Firmicutes", "Bacillota")  # the same phylum, old and new name

def _not_grey(color: str) -> bool:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b) > 16


PALETTES = {
    # The lab's look: matplotlib's tab20, then Set3, then Pastel1 (as in the fig_1B scripts), without
    # their greys, which would read as "Other".
    "lab": tuple(c for name in ("tab20", "Set3", "Pastel1") for c in map(to_hex, colormaps[name].colors)
                 if _not_grey(c)),
    # Colour-blind safer, 12 hues: Okabe-Ito (without black) + five of Paul Tol's muted/dark hues.
    # No 12-colour set is safe for everyone; neighbours in a stack differ in lightness too.
    "colorblind": ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442",
                   "#332288", "#882255", "#999933", "#117733", "#661100"),
}
PALETTE_DEFAULT = "lab"
# Fixed colour slots, in the usual order of abundance in gut samples, so that a phylum keeps its
# colour across datasets. Each entry lists one phylum's names (older name first, then current ones).
KNOWN_PHYLA = (
    ("Firmicutes", "Bacillota"), ("Bacteroidetes", "Bacteroidota"), ("Proteobacteria", "Pseudomonadota"),
    ("Actinobacteria", "Actinobacteriota", "Actinomycetota"), ("Verrucomicrobia", "Verrucomicrobiota"),
    ("Euryarchaeota", "Methanobacteriota"), ("Tenericutes", "Mycoplasmatota"), ("Fusobacteria", "Fusobacteriota"),
    ("Cyanobacteria", "Cyanobacteriota"), ("Spirochaetes", "Spirochaetota"), ("Synergistetes", "Synergistota"),
    ("Lentisphaerae", "Lentisphaerota"), ("Desulfobacterota",), ("Campylobacterota",),
    ("Patescibacteria", "Saccharibacteria", "TM7"), ("Chloroflexi", "Chloroflexota"),
    ("Elusimicrobia", "Elusimicrobiota"), ("Deferribacteres", "Deferribacterota"),
    ("Planctomycetes", "Planctomycetota"), ("Acidobacteria", "Acidobacteriota"),
)
_SLOT = {name.lower(): i for i, names in enumerate(KNOWN_PHYLA) for name in names}
_RANKS = re.compile(r"\s*[;|,]\s*")
_PREFIX = re.compile(r"^[a-z]__")

__all__ = ["phylum_percent", "top_phyla", "phylum_colors", "composition_figure", "split_violin_figure"]


class CompositionError(UserFacingError):
    """The table cannot be shown as relative abundance (e.g. negative, log-transformed values)."""


def phylum_percent(table: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Samples × phyla in % (each row adds up to 100), and what was left out.

    ``table`` is samples × taxa, columns named by lineage, values counts or relative abundances.
    The second value says how many samples had nothing at phylum level (dropped) and the mean
    share of each sample's total that had no phylum (``unassigned_percent``).
    """
    values = table.apply(pd.to_numeric, errors="coerce")
    array = values.to_numpy(dtype=float)
    if not (pd.notna(array).all() and abs(array).max(initial=0) < float("inf")) or (array < 0).any():
        raise CompositionError(
            "Composition needs finite, non-negative abundances (counts or relative abundances).",
            "Upload the raw counts or relative abundances, not a log-transformed table.",
        )
    ranks = [_ranks(c) for c in values.columns]
    if _all_ranks(ranks):  # MetaPhlAn style: keep the phylum rows only
        keep = [i for i, r in enumerate(ranks) if r and r[-1].startswith("p__")]
    else:
        keep = list(range(len(ranks)))
    names = [_phylum(ranks[i]) for i in keep]
    phylum = values.iloc[:, keep].T.groupby(names, sort=False).sum().T
    totals = values.sum(axis=1) if not _all_ranks(ranks) else phylum.sum(axis=1)
    phylum = phylum.drop(columns=[c for c in phylum.columns if str(c).lower() in {d.lower() for d in DROPPED}])
    assigned = phylum.sum(axis=1)
    valid = assigned > 0
    unassigned = (1 - assigned[valid] / totals[valid]).clip(lower=0).mean() * 100 if valid.any() else 0.0
    phylum = phylum.loc[valid]
    if phylum.empty:
        raise CompositionError("No sample has any abundance at phylum level.",
                               "Check that the column names hold the taxonomy (k__…;p__…).")
    percent = phylum.div(phylum.sum(axis=1), axis=0) * 100
    return percent, {"samples_dropped": int((~valid).sum()), "unassigned_percent": float(unassigned)}


def top_phyla(percent: pd.DataFrame, top_n: int = TOP_PHYLA) -> pd.DataFrame:
    """The ``top_n`` phyla by mean over all samples (most abundant first), then "Other" (the rest)."""
    order = list(percent.mean().sort_values(ascending=False, kind="stable").index)
    named = [p for p in order if p != OTHER][:top_n]
    out = percent[named].copy()
    rest = [p for p in percent.columns if p not in named]
    if rest:
        out[OTHER] = percent[rest].sum(axis=1)
    return out


def phylum_colors(phyla, palette: str = PALETTE_DEFAULT) -> dict[str, str]:
    """One colour per phylum (in the given order); "Other" is always grey.

    Known phyla keep their fixed slot; other phyla take the next free colour (after the fixed
    slots in the lab palette, so they never borrow a known phylum's colour).
    """
    if palette not in PALETTES:
        raise ValueError(f"palette must be one of {sorted(PALETTES)}")
    colors = PALETTES[palette]
    named = [p for p in dict.fromkeys(phyla) if p != OTHER]
    slots: dict[str, int] = {}
    for p in named:
        slot = _SLOT.get(str(p).lower())
        if slot is not None and slot < len(colors) and slot not in slots.values():
            slots[p] = slot
    start = len(KNOWN_PHYLA) if len(colors) > len(KNOWN_PHYLA) + len(named) else 0
    free = [i for i in range(start, len(colors)) if i not in slots.values()] + \
           [i for i in range(start) if i not in slots.values()]
    for p in named:
        if p not in slots:
            slots[p] = free.pop(0) if free else len(slots) % len(colors)
    return {p: colors[slots[p]] for p in named} | {OTHER: OTHER_GREY}


def sort_samples(top: pd.DataFrame) -> pd.DataFrame:
    """Samples by Firmicutes (most first) if present, else by the most abundant phylum."""
    lead = next((p for p in top.columns if p in SORT_BY), top.columns[0])
    return top.sort_values(lead, ascending=False, kind="stable")


def composition_figure(top: pd.DataFrame, colors: dict[str, str], dataset: str | None = None,
                       left_out: str = "", descriptive: str = "") -> Figure:
    """Left: one stacked bar per sample; right: the mean of all samples. ``top`` from ``top_phyla``."""
    ordered = sort_samples(top)
    lead = next((p for p in ordered.columns if p in SORT_BY), ordered.columns[0])
    mean = ordered.mean().to_frame(MEAN).T
    rows = pd.concat([ordered, mean]).stack(future_stack=True).round(4).rename("percent")
    data = rows.rename_axis(["sample", "phylum"]).reset_index()
    data.insert(0, "panel", ["Average" if s == MEAN else "Samples" for s in data["sample"]])
    named = len([p for p in top.columns if p != OTHER])
    rest = f"; the rest are summed as {OTHER} (grey)" if OTHER in top.columns else ""
    return Figure(
        name="composition_bars",
        title="Composition of each sample (phylum)",
        caption=f"Left: each bar is one sample, the share of its abundance from each phylum, adding up to "
                f"100%. Right: the mean of all samples. The {named} phyla with the highest mean have a colour"
                f"{rest}. Samples are sorted by {lead} (most first). Relative abundance from the uploaded "
                f"table, collapsed to phylum, not the log-transformed table the tools use.{left_out} {descriptive}",
        data=data, kind="composition", x="sample", y="percent", color_by="phylum",
        x_label="Samples", y_label="Relative abundance (%)", summary=(MEAN,),
        colors=tuple(colors.items()), suptitle=dataset,
        hover="%{x}<br>%{fullData.name}: %{y:.1f}%<extra></extra>", section="overview",
    )


def split_violin_figure(percent: pd.DataFrame, groups: pd.Series, phyla: list[str],
                        colors: dict[str, str], descriptive: str = "") -> Figure | None:
    """Per phylum, the samples' % in group A (left half) and group B (right half); None unless two groups."""
    names = sorted(set(groups.loc[percent.index]))  # group A (left half) first, as in the other figures
    if len(names) != 2:
        return None
    long = percent[[p for p in phyla if p != OTHER]].assign(group=groups.loc[percent.index])
    data = (long.rename_axis("sample").reset_index()
            .melt(id_vars=["sample", "group"], var_name="phylum", value_name="percent"))
    data = data.sort_values("group", key=lambda g: g.map({n: i for i, n in enumerate(names)}), kind="stable")
    data = data.reset_index(drop=True)
    data["percent"] = data["percent"].round(4)
    return Figure(
        name="composition_violin",
        title=f"Phylum abundance by group ({names[0]} vs {names[1]})",
        caption=f"For each of the most abundant phyla, the spread of its share across samples: {names[0]} on "
                f"the left half, {names[1]} on the right; the line is the median. {descriptive}",
        data=data, kind="violin", x="phylum", y="percent", group_by="group",
        x_label="", y_label="Relative abundance (%)", colors=tuple(colors.items()),
        hover="%{x}<br>%{y:.1f}%<extra>%{fullData.name}</extra>", section="overview",
    )


def _ranks(column) -> list[str]:
    return [p for p in _RANKS.split(str(column).strip()) if p]


def _all_ranks(ranks: list[list[str]]) -> bool:
    """True for a table that lists every rank, as MetaPhlAn does: every clade's parent is a column too.

    (A 16S table where some taxa are named only down to their phylum is not one: their
    deeper relatives have no column per parent.)
    """
    seen = {tuple(r) for r in ranks}
    deeper = [r for r in ranks if len(r) > 1]
    return bool(deeper) and all(tuple(r[:-1]) in seen for r in deeper)


def _phylum(ranks: list[str]) -> str:
    """The phylum's name: the ``p__`` rank, else the second rank (after the kingdom); "Unassigned" if none."""
    tagged = [r for r in ranks if r.startswith("p__")]
    if tagged:
        name = _PREFIX.sub("", tagged[0])
    elif len(ranks) > 1 and not any(_PREFIX.match(r) for r in ranks):
        name = ranks[1]
    elif len(ranks) == 1:
        name = _PREFIX.sub("", ranks[0])  # a lone name: a phylum, or e.g. "Bacteria" (dropped)
    else:
        name = ""
    return name.strip() or "Unassigned"
