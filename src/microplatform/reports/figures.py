"""Figures: one description, three renderings, and always the data behind it.

A ``Figure`` holds the exact table that is plotted plus how to draw it.
``export`` writes, for each figure:

    <name>.png    for slides and documents (200 dpi)
    <name>.svg    vector, with editable text (for Illustrator or Inkscape)
    <name>.html   interactive (hover, zoom); standalone and works offline
    <name>.json   the interactive figure, for embedding in the results page
    <name>.csv    the underlying data, so the figure can be re-made or edited

Every engine draws through this module, so all results look and download alike.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import matplotlib
import matplotlib.ticker
import numpy as np
import pandas as pd
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from matplotlib.figure import Figure as MplFigure
from matplotlib.patches import Patch, Rectangle

from microplatform.core.preprocessing import PreprocessSettings

# Shipped with plotly; the website serves it so interactive figures work offline.
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"

FORMATS = ("png", "svg", "html", "csv")

# Explicit media types: the operating system's guesses differ (Windows calls CSV "Excel").
MEDIA_TYPES = {
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".html": "text/html",
    ".csv": "text/csv",
    ".json": "application/json",
}
ACCENT = "#0f766e"  # the site's teal
CONTRAST = "#b45309"  # the second group, distinguishable from teal (also for colour blindness)
MARKER = "#b42318"
# Groups beyond two: distinct hues that stay apart for common colour blindness.
PALETTE = (ACCENT, CONTRAST, "#6d28d9", "#0369a1", "#be185d", "#4d7c0f", "#57534e")
# Taxa in composition figures: the Okabe-Ito palette (Okabe & Ito 2008), designed to stay apart for every
# common colour blindness and widely used in journals; mid-tones, so they read on light and dark pages.
TAXON_PALETTE = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442")
OTHER = "Other"
OTHER_COLOR = "#BBBBBB"
BOX_LINE = "#3f4a4a"  # box outlines and medians

# Interactive files: plotly.js shows a "Share chart" button by default, which uploads the
# plot's data to Chart Studio online. Uploads may be clinical, so it is always off.
PLOTLY_CONFIG = {"displaylogo": False, "showSendToCloud": False, "responsive": True}

Kind = Literal["bar", "histogram", "barh", "column", "scatter", "line", "stacked", "pie", "box"]
Section = Literal["quality", "findings", "overview"]


@dataclass(frozen=True)
class Figure:
    """What to plot and how.

    bar        one unlabelled bar per row (e.g. per sample), value in ``y``
    histogram  distribution of ``x``, between ``x_range`` (0 to 100 by default; None: the data's range)
    barh       one labelled horizontal bar per row: label ``y``, value ``x``, coloured by ``color_by``
    column     one labelled vertical bar per row: label ``x``, value ``y``
    scatter    one point per row at (``x``, ``y``), coloured by ``color_by``; ``label`` names each point
    line       a line through (``x``, ``y``) in row order; ``diagonal`` adds the 0→1 reference line
    stacked    one stacked bar per distinct ``x`` (in row order), segments ``y`` coloured by ``color_by``;
               bars are set in blocks by ``group_by``, and rows whose ``group_by`` is in ``summary``
               form a last block (e.g. one average bar per group)
    pie        shares ``y`` of each ``x``; one pie per value of ``group_by`` if given
    box        a box per value of ``group_by`` with every point of ``y`` on it; one panel per ``facet`` value

    ``colors`` fixes the colour of each value (of ``color_by``, of the pie's ``x``, or of the box's
    ``group_by``), so a taxon or a group keeps one colour across figures.
    """

    name: str  # file stem, e.g. "reads_per_sample"
    title: str
    caption: str  # one plain-language sentence on how to read it
    data: pd.DataFrame
    kind: Kind
    x: str
    y: str | None
    x_label: str
    y_label: str
    marker: tuple[float, str] | None = None  # vertical reference line: (x, label)
    hline: tuple[float, str] | None = None  # horizontal reference line: (y, label)
    log_y: bool = False
    diagonal: bool = False  # line: dashed y = x reference (e.g. chance on a ROC curve)
    color_by: str | None = None  # barh, scatter: a column with the groups to colour by
    label: str | None = None  # scatter: a column naming each point (shown on hover)
    hover: str | None = None  # plotly hovertemplate
    section: Section = "quality"
    x_range: tuple[float, float] | None = (0, 100)  # histogram: the binned range (None: the data's own)
    group_by: str | None = None  # stacked: blocks of bars; pie: one pie per group
    summary: tuple[str, ...] = ()  # stacked: the group_by values that form the last block
    facet: str | None = None  # box: one panel per value of this column (each with its own y axis)
    colors: tuple[tuple[str, str], ...] = ()  # (value, colour) pairs; see above


@dataclass(frozen=True)
class ExportedFigure:
    """What a results page needs: the text and the file name for each format."""

    name: str
    title: str
    caption: str
    files: dict[str, str]  # format → file name inside the figures folder
    section: Section = "quality"
    tall: bool = False  # one row per item (e.g. per taxon): needs the full width and more height
    wide: bool = False  # many bars side by side, or several pies: needs the full width


# --- the figures for preprocessing ---------------------------------------------

def preprocessing_figures(counts: pd.DataFrame, settings: PreprocessSettings) -> list[Figure]:
    """Quality-check figures from the raw counts (samples × taxa, see ``Dataset.raw_counts``).

    How widespread each taxon is (``taxa_prevalence``) is part of the data overview (``reports/overview.py``).
    """
    return [_reads_per_sample(counts)]


def _reads_per_sample(counts: pd.DataFrame) -> Figure:
    reads = counts.sum(axis=1).sort_values(ascending=False)
    data = pd.DataFrame({"sample": reads.index, "reads": reads.to_numpy()})
    return Figure(
        name="reads_per_sample",
        title="Sequencing depth per sample",
        caption="Total reads in each sample, sorted, on a log scale. A sample far above or "
                "below the rest may be contaminated or a failed sequencing run.",
        data=data, kind="bar", x="sample", y="reads",
        x_label="Samples (sorted by depth)", y_label="Total reads (log scale)", log_y=True,
        hover="%{x}<br>%{y:,.0f} reads<extra></extra>",
    )


def taxa_prevalence(counts: pd.DataFrame, settings: PreprocessSettings, section: Section = "quality") -> Figure:
    """Column sparsity: the share of samples each taxon appears in, with MIPMLP's rare-taxa cut-off."""
    prevalence = (counts > 0).mean(axis=0) * 100
    data = pd.DataFrame({"taxon": prevalence.index, "prevalence_percent": prevalence.round(2).to_numpy()})
    threshold = settings.rare_bacteria_threshold * 100
    return Figure(
        name="taxa_prevalence",
        title="How widespread each taxon is (column sparsity)",
        caption="For each taxon, the share of samples it appears in. Most microbiome "
                f"data is sparse; MIPMLP drops taxa found in fewer than {threshold:g}% of samples.",
        data=data, kind="histogram", x="prevalence_percent", y=None,
        x_label="Present in % of samples", y_label="Number of taxa",
        marker=(threshold, f"{threshold:g}% cut-off"),
        hover="%{x}%: %{y} taxa<extra></extra>",
        section=section,
    )


# --- export ------------------------------------------------------------------------

def export(figures: list[Figure], out_dir: Path) -> list[ExportedFigure]:
    """Write every format of every figure, and add them to the folder's manifest.

    Figures already in the manifest with the same name are replaced; others are kept,
    so preprocessing and an engine can both export into one run.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    for fig in figures:
        fig.data.to_csv(out_dir / f"{fig.name}.csv", index=False)
        _write_static(fig, out_dir)
        interactive = to_plotly(fig)
        interactive.write_html(out_dir / f"{fig.name}.html", include_plotlyjs=True, full_html=True,
                               config=PLOTLY_CONFIG)
        (out_dir / f"{fig.name}.json").write_text(interactive.to_json(), encoding="utf-8")
        exported.append(ExportedFigure(
            fig.name, fig.title, fig.caption, {f: f"{fig.name}.{f}" for f in (*FORMATS, "json")},
            fig.section, tall=fig.kind == "barh", wide=_is_wide(fig),
        ))
    names = {e.name for e in exported}
    kept = [e for e in load_manifest(out_dir) if e.name not in names]
    (out_dir / "figures.json").write_text(
        json.dumps([asdict(e) for e in kept + exported], indent=2), encoding="utf-8"
    )
    return exported


def load_manifest(figures_dir: Path) -> list[ExportedFigure]:
    manifest = Path(figures_dir) / "figures.json"
    if not manifest.exists():
        return []
    return [ExportedFigure(**e) for e in json.loads(manifest.read_text(encoding="utf-8"))]


def _is_wide(fig: Figure) -> bool:
    if fig.kind == "stacked":
        return True
    if fig.kind == "box":
        return fig.facet is not None and fig.data[fig.facet].nunique() > 1
    return fig.kind == "pie" and fig.group_by is not None and fig.data[fig.group_by].nunique() > 1


def _values(fig: Figure, column: str | None) -> list:
    return list(dict.fromkeys(fig.data[column])) if column else [None]


# --- composition figures: shared layout --------------------------------------------------

def taxon_colors(taxa) -> dict[str, str]:
    """A colour per taxon, in the given order (most abundant first); "Other" is always grey."""
    named = [t for t in dict.fromkeys(taxa) if t != OTHER]
    colors = {t: TAXON_PALETTE[i % len(TAXON_PALETTE)] for i, t in enumerate(named)}
    return colors | {OTHER: OTHER_COLOR}


def group_colors(groups) -> dict[str, str]:
    """A colour per group, in the given order: the site's group colours (as in every other figure)."""
    return {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(dict.fromkeys(groups))}


def _color_map(fig: Figure, column: str) -> dict[str, str]:
    """The figure's fixed colours, or colours by order of appearance."""
    if fig.colors:
        return dict(fig.colors)
    return taxon_colors(fig.data[column]) if fig.kind in ("stacked", "pie") else group_colors(fig.data[column])


def _stacked_layout(fig: Figure) -> tuple[dict[str, tuple[float, float]], list[tuple[float, str]]]:
    """Where each bar goes and how wide it is (blocks by group, a gap between blocks), and the axis labels.

    Bars of the ``summary`` block are wider and labelled one by one (they are few; labels wrap
    onto lines); other blocks get one label in their middle (they may hold hundreds of samples).
    """
    bars: dict[str, tuple[float, float]] = {}
    ticks: list[tuple[float, str]] = []
    data = fig.data
    groups = _values(fig, fig.group_by)
    blocks = [g for g in groups if g not in fig.summary] + [g for g in groups if g in fig.summary]
    regular = data.loc[~data[fig.group_by].isin(fig.summary), fig.x].nunique() if fig.group_by else 0
    gap = max(1.0, 0.04 * regular)
    wide = max(5.0, 0.1 * regular)  # a summary bar: wide enough for its label
    at = -0.5
    for i, group in enumerate(blocks):
        if i:
            at += gap
        members = list(dict.fromkeys(data[fig.x] if group is None else data.loc[data[fig.group_by] == group, fig.x]))
        width = wide if group in fig.summary else 1.0
        for bar in members:
            bars[bar] = (at + width / 2, width * (0.85 if group in fig.summary else 1.0))
            if group in fig.summary:
                ticks.append((at + width / 2, "\n".join(textwrap.wrap(str(bar), 12))))
            at += width
        if group is not None and group not in fig.summary:
            ticks.append((at - len(members) / 2, f"{group}\n(n={len(members)})"))
    return bars, ticks


def _ink(color: str) -> str:
    """Black or white text, whichever reads better on ``color`` (WCAG relative luminance)."""
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return "#000000" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.18 else "#ffffff"


def _pie_groups(fig: Figure) -> list[tuple[str | None, pd.DataFrame]]:
    if not fig.group_by:
        return [(None, fig.data)]
    return [(g, fig.data[fig.data[fig.group_by] == g]) for g in dict.fromkeys(fig.data[fig.group_by])]


# --- static rendering (matplotlib) ----------------------------------------------------

def _group_colors(fig: Figure) -> tuple[list[str], list[tuple[str, str]]]:
    """Per-row colours and the legend entries, for figures coloured by a group column."""
    if not fig.color_by:
        return [ACCENT] * len(fig.data), []
    groups = list(dict.fromkeys(fig.data[fig.color_by]))
    lookup = _color_map(fig, fig.color_by)
    return [lookup[g] for g in fig.data[fig.color_by]], [(str(g), lookup[g]) for g in groups]


def _write_static(fig: Figure, out_dir: Path) -> None:
    # The object-oriented matplotlib API (no pyplot) is safe inside a web server.
    height = max(3.5, 0.26 * len(fig.data) + 1.4) if fig.kind == "barh" else 4
    width = 10 if _is_wide(fig) else 7
    with matplotlib.rc_context({"svg.fonttype": "none", "font.size": 10}):
        mpl = MplFigure(figsize=(width, height), layout="constrained")
        if fig.kind == "pie":
            _write_pies(fig, mpl, out_dir)
            return
        if fig.kind == "box":
            _write_boxes(fig, mpl, out_dir)
            return
        ax = mpl.add_subplot()
        if fig.kind == "stacked":
            bars, ticks = _stacked_layout(fig)
            x = [center for center, _ in bars.values()]
            widths = [width for _, width in bars.values()]
            bottom = pd.Series(0.0, index=list(bars))
            for taxon, color in _color_map(fig, fig.color_by).items():
                rows = fig.data[fig.data[fig.color_by] == taxon]
                if rows.empty:
                    continue
                heights = rows.set_index(fig.x)[fig.y].reindex(bottom.index, fill_value=0)
                ax.bar(x, heights, bottom=bottom, width=widths, color=color, label=taxon, linewidth=0)
                bottom += heights
            ax.set_xticks([t for t, _ in ticks], [label for _, label in ticks])
            ax.tick_params(axis="x", length=0)
            ax.set_xlim(-0.5, max(c + w / 2 for c, w in bars.values()) + 0.5)
            ax.set_ylim(0, 100)
            handles, labels = ax.get_legend_handles_labels()  # listed top to bottom, as stacked
            ax.legend(handles[::-1], labels[::-1], frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1),
                      title=fig.color_by.capitalize())
        elif fig.kind == "bar":
            ax.bar(range(len(fig.data)), fig.data[fig.y], color=ACCENT, width=0.85)
            ax.set_xticks([])
            ax.set_xlim(-0.6, len(fig.data) - 0.4)
            ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
        elif fig.kind == "histogram":
            ax.hist(fig.data[fig.x], bins=20, range=fig.x_range, color=ACCENT, edgecolor="white")
        elif fig.kind == "barh":
            colors, legend = _group_colors(fig)
            rows = range(len(fig.data))
            ax.barh(rows, fig.data[fig.x], color=colors, height=0.75)
            ax.set_yticks(rows, fig.data[fig.y])
            ax.invert_yaxis()  # first row on top
            ax.axvline(0, color="#8a9a9a", linewidth=0.8)
            if legend:
                ax.legend(handles=[Patch(color=c, label=g) for g, c in legend], frameon=False,
                          loc="lower right")
        elif fig.kind == "scatter":
            colors, legend = _group_colors(fig)
            ax.scatter(fig.data[fig.x], fig.data[fig.y], c=colors, s=28, alpha=0.85, edgecolors="white",
                       linewidths=0.5)
            if legend:
                ax.legend(handles=[Patch(color=c, label=g) for g, c in legend], frameon=False)
        elif fig.kind == "line":
            ax.plot(fig.data[fig.x], fig.data[fig.y], color=ACCENT, linewidth=2)
            if fig.diagonal:
                ax.plot([0, 1], [0, 1], color="#8a9a9a", linestyle="--", linewidth=1)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1.02)
                ax.set_aspect("equal")
        else:  # column
            ax.bar(fig.data[fig.x].astype(str), fig.data[fig.y], color=ACCENT, width=0.7)
        if fig.log_y:
            ax.set_yscale("log")
        if fig.marker:
            ax.axvline(fig.marker[0], color=MARKER, linestyle="--", linewidth=1)
            ax.annotate(fig.marker[1], (fig.marker[0], 1), xycoords=("data", "axes fraction"),
                        xytext=(4, -4), textcoords="offset points", va="top", color=MARKER,
                        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 1.5})
        if fig.hline:
            ax.axhline(fig.hline[0], color=MARKER, linestyle="--", linewidth=1)
            ax.annotate(fig.hline[1], (0, fig.hline[0]), xycoords=("axes fraction", "data"),
                        xytext=(4, 4), textcoords="offset points", ha="left", color=MARKER)
        ax.set_title(fig.title, loc="left", fontweight="bold")
        ax.set_xlabel(fig.x_label)
        ax.set_ylabel(fig.y_label)
        ax.spines[["top", "right"]].set_visible(False)
        _save(mpl, fig, out_dir)


def _save(mpl: MplFigure, fig: Figure, out_dir: Path) -> None:
    for fmt in ("png", "svg"):
        mpl.savefig(out_dir / f"{fig.name}.{fmt}", dpi=200)


def _write_pies(fig: Figure, mpl: MplFigure, out_dir: Path) -> None:
    groups = _pie_groups(fig)
    colors = _color_map(fig, fig.x)
    axes = mpl.subplots(1, len(groups), squeeze=False)[0]
    for ax, (group, rows) in zip(axes, groups):
        # A percentage on each slice big enough to hold it; the CSV has every value.
        _, _, percents = ax.pie(
            rows[fig.y], colors=[colors[t] for t in rows[fig.x]], startangle=90, counterclock=False,
            wedgeprops={"linewidth": 1, "edgecolor": "white"}, pctdistance=0.72, textprops={"fontsize": 9},
            autopct=lambda pct: f"{pct:.0f}%" if pct >= 5 else "")
        for text, taxon in zip(percents, rows[fig.x]):
            text.set_color(_ink(colors[taxon]))
        ax.set_aspect("equal")
        if group is not None:
            ax.set_title(str(group))
    mpl.suptitle(fig.title, x=0.02, ha="left", fontweight="bold")
    mpl.legend(handles=[Patch(color=c, label=t) for t, c in colors.items() if t in set(fig.data[fig.x])],
               frameon=False, loc="outside right center", title=fig.x.capitalize())
    _save(mpl, fig, out_dir)


def _draw_box(ax, x: float, values: np.ndarray, width: float = 0.55) -> None:
    """A Tukey box (quartiles, median, whiskers to the furthest point within 1.5 × IQR), as plotly draws it.

    Drawn from plain shapes: matplotlib's own boxplot (``Axes.bxp``) stops PyTorch from loading
    afterwards on Windows (WinError 1114 in c10.dll), and the tools load PyTorch after the overview.
    """
    if len(values) == 0:
        return
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    reach = 1.5 * (q3 - q1)
    low, high = values[values >= q1 - reach].min(), values[values <= q3 + reach].max()
    line = {"color": BOX_LINE, "linewidth": 1, "zorder": 2}
    ax.add_patch(Rectangle((x - width / 2, q1), width, q3 - q1, fill=False, edgecolor=BOX_LINE, linewidth=1,
                           zorder=2))
    ax.plot([x - width / 2, x + width / 2], [median, median], **(line | {"linewidth": 1.8}))
    for end, edge in ((low, q1), (high, q3)):
        ax.plot([x, x], [end, edge], **line)
        ax.plot([x - width / 4, x + width / 4], [end, end], **line)


def _write_boxes(fig: Figure, mpl: MplFigure, out_dir: Path) -> None:
    panels = _values(fig, fig.facet)
    groups = _values(fig, fig.group_by)
    colors = _color_map(fig, fig.group_by) if fig.group_by else {None: ACCENT}
    rng = np.random.default_rng(0)  # the same jitter every time
    axes = mpl.subplots(1, len(panels), squeeze=False)[0]
    for ax, panel in zip(axes, panels):
        rows = fig.data if panel is None else fig.data[fig.data[fig.facet] == panel]
        values = [rows[fig.y] if g is None else rows.loc[rows[fig.group_by] == g, fig.y] for g in groups]
        for i, v in enumerate(values):
            _draw_box(ax, i, v.to_numpy(dtype=float))
        for i, (group, v) in enumerate(zip(groups, values)):
            ax.scatter(i + rng.uniform(-0.17, 0.17, len(v)), v, s=16, color=colors[group], alpha=0.8,
                       edgecolors="white", linewidths=0.4, zorder=3)
        ax.set_xticks(range(len(groups)), [f"{g}\n(n={len(v)})" if g is not None else f"n={len(v)}"
                                           for g, v in zip(groups, values)])
        ax.set_xlim(-0.6, len(groups) - 0.4)
        ax.set_ylabel(panel if panel is not None else fig.y_label)
        ax.set_xlabel(fig.x_label)
        ax.spines[["top", "right"]].set_visible(False)
    mpl.suptitle(fig.title, x=0.02, ha="left", fontweight="bold")
    _save(mpl, fig, out_dir)


# --- interactive rendering (plotly) ----------------------------------------------------

def to_plotly(fig: Figure) -> go.Figure:
    if fig.kind == "pie":
        return _plotly_pies(fig)
    if fig.kind == "box":
        return _plotly_boxes(fig)
    out = go.Figure()
    if fig.kind == "stacked":
        bars, ticks = _stacked_layout(fig)
        for taxon, color in _color_map(fig, fig.color_by).items():
            rows = fig.data[fig.data[fig.color_by] == taxon]
            if rows.empty:
                continue
            out.add_trace(go.Bar(x=[bars[b][0] for b in rows[fig.x]], width=[bars[b][1] for b in rows[fig.x]],
                                 y=rows[fig.y], name=taxon, marker={"color": color, "line": {"width": 0}},
                                 customdata=rows[[fig.x]], hovertemplate=fig.hover))
        out.update_layout(barmode="stack")
        out.update_xaxes(tickmode="array", tickvals=[t for t, _ in ticks],
                         ticktext=[label.replace("\n", "<br>") for _, label in ticks], ticks="")
        out.update_yaxes(range=[0, 100])
    elif fig.kind == "bar":
        out.add_trace(go.Bar(x=fig.data[fig.x], y=fig.data[fig.y], marker_color=ACCENT,
                             hovertemplate=fig.hover))
    elif fig.kind == "histogram":
        low, high = fig.x_range or (None, None)
        bins = {"start": low, "end": high, "size": (high - low) / 20} if fig.x_range else None
        out.add_trace(go.Histogram(x=fig.data[fig.x], xbins=bins, nbinsx=None if bins else 20,
                                   marker_color=ACCENT, hovertemplate=fig.hover))
    elif fig.kind == "barh":
        _, legend = _group_colors(fig)
        groups = legend or [(None, ACCENT)]
        for group, color in groups:
            rows = fig.data if group is None else fig.data[fig.data[fig.color_by].astype(str) == group]
            out.add_trace(go.Bar(x=rows[fig.x], y=rows[fig.y], orientation="h", marker_color=color,
                                 name=group or "", hovertemplate=fig.hover, showlegend=group is not None))
        out.update_yaxes(autorange="reversed", categoryorder="array", categoryarray=list(fig.data[fig.y]))
    elif fig.kind == "scatter":
        _, legend = _group_colors(fig)
        for group, color in legend or [(None, ACCENT)]:
            rows = fig.data if group is None else fig.data[fig.data[fig.color_by].astype(str) == group]
            out.add_trace(go.Scatter(
                x=rows[fig.x], y=rows[fig.y], mode="markers", name=group or "",
                marker={"color": color, "size": 8, "opacity": 0.85, "line": {"color": "white", "width": 0.5}},
                text=rows[fig.label] if fig.label else None, hovertemplate=fig.hover,
                showlegend=group is not None,
            ))
    elif fig.kind == "line":
        out.add_trace(go.Scatter(x=fig.data[fig.x], y=fig.data[fig.y], mode="lines",
                                 line={"color": ACCENT, "width": 2}, hovertemplate=fig.hover, showlegend=False))
        if fig.diagonal:
            out.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", hoverinfo="skip", showlegend=False,
                                     line={"color": "#8a9a9a", "width": 1, "dash": "dash"}))
            out.update_xaxes(range=[0, 1])
            out.update_yaxes(range=[0, 1.02])
    else:  # column
        out.add_trace(go.Bar(x=fig.data[fig.x].astype(str), y=fig.data[fig.y], marker_color=ACCENT,
                             hovertemplate=fig.hover))
    if fig.marker:
        # A light box behind the label keeps it readable where it crosses a bar.
        out.add_vline(x=fig.marker[0], line_dash="dash", line_color=MARKER,
                      annotation_text=fig.marker[1], annotation_font_color=MARKER,
                      annotation_bgcolor="rgba(255,255,255,0.85)")
    if fig.hline:
        out.add_hline(y=fig.hline[0], line_dash="dash", line_color=MARKER, annotation_position="top left",
                      annotation_text=fig.hline[1], annotation_font_color=MARKER)
    height = max(360, 22 * len(fig.data) + 120) if fig.kind == "barh" else None
    out.update_layout(
        title={"text": fig.title, "x": 0, "xanchor": "left"},
        xaxis_title=fig.x_label, yaxis_title=fig.y_label,
        template="simple_white", margin={"l": 60, "r": 20, "t": 50, "b": 50},
        bargap={"bar": 0.05, "histogram": 0.05, "stacked": 0}.get(fig.kind, 0.25), height=height,
        # Stacked: the legend lists taxa top to bottom in the order they are stacked, beside the bars.
        legend=({"traceorder": "reversed", "title": {"text": fig.color_by.capitalize()}} if fig.kind == "stacked"
                # Group legends sit above the plot, clear of the axis title below.
                else {"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom"}),
    )
    if fig.kind == "bar":
        out.update_xaxes(showticklabels=False)
    if fig.log_y:
        out.update_yaxes(type="log")
    return out


def _plotly_pies(fig: Figure) -> go.Figure:
    out = go.Figure()
    groups = _pie_groups(fig)
    colors = _color_map(fig, fig.x)
    width = 1 / len(groups)
    for i, (group, rows) in enumerate(groups):
        out.add_trace(go.Pie(
            labels=rows[fig.x], values=rows[fig.y], sort=False, direction="clockwise", rotation=0,
            marker={"colors": [colors[t] for t in rows[fig.x]], "line": {"color": "white", "width": 1}},
            domain={"x": [i * width + 0.02, (i + 1) * width - 0.02], "y": [0, 0.9]},
            title={"text": str(group) if group is not None else ""}, textposition="inside",
            # A percentage only on slices big enough to hold it (as in the PNG); hover shows every value.
            texttemplate=["%{percent:.0%}" if share >= 5 else "" for share in rows[fig.y] / rows[fig.y].sum() * 100],
            insidetextorientation="horizontal", insidetextfont={"color": [_ink(colors[t]) for t in rows[fig.x]]},
            hovertemplate=fig.hover, name=str(group or ""),
        ))
    out.update_layout(title={"text": fig.title, "x": 0, "xanchor": "left"}, template="simple_white",
                      margin={"l": 20, "r": 20, "t": 50, "b": 20}, legend={"title": {"text": fig.x.capitalize()}})
    return out


def _plotly_boxes(fig: Figure) -> go.Figure:
    panels = _values(fig, fig.facet)
    groups = _values(fig, fig.group_by)
    colors = _color_map(fig, fig.group_by) if fig.group_by else {None: ACCENT}
    out = make_subplots(rows=1, cols=len(panels), horizontal_spacing=0.12)
    for col, panel in enumerate(panels, start=1):
        rows = fig.data if panel is None else fig.data[fig.data[fig.facet] == panel]
        for group in groups:
            members = rows if group is None else rows[rows[fig.group_by] == group]
            out.add_trace(go.Box(
                y=members[fig.y], name=f"{group} (n={len(members)})" if group is not None else f"n={len(members)}",
                boxpoints="all", jitter=0.45, pointpos=0, text=members[fig.label] if fig.label else None,
                marker={"color": colors[group], "size": 6, "opacity": 0.8, "line": {"color": "white", "width": 0.5}},
                line={"color": BOX_LINE, "width": 1}, fillcolor="rgba(0,0,0,0)", hovertemplate=fig.hover,
                showlegend=False,
            ), row=1, col=col)
        out.update_yaxes(title_text=panel if panel is not None else fig.y_label, row=1, col=col)
        out.update_xaxes(title_text=fig.x_label, row=1, col=col)
    out.update_layout(title={"text": fig.title, "x": 0, "xanchor": "left"}, template="simple_white",
                      margin={"l": 60, "r": 20, "t": 50, "b": 50})
    return out
