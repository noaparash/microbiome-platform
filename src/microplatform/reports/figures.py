"""Figures: one description, three renderings, and always the data behind it.

A ``Figure`` holds the exact table that is plotted plus how to draw it.
``export`` writes, for each figure:

    <name>.png    for slides and documents (200 dpi; composition figures 300 dpi)
    <name>.svg    vector, with editable text (for Illustrator or Inkscape)
    <name>.html   interactive (hover, zoom); standalone and works offline
    <name>.json   the interactive figure, for embedding in the results page
    <name>.csv    the underlying data, so the figure can be re-made or edited
    <name>_tests.csv   the statistical tests shown on the figure, if any (``Figure.stats``)

Every engine draws through this module, so all results look and download alike. The one
exception is a figure drawn by a tool's own plotting code (``RenderedFigure``, e.g. miMic's
cladogram): ``export_rendered`` copies its SVG and PNG unchanged and adds the HTML page and the CSV.
"""

from __future__ import annotations

import html
import json
import shutil
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
from microplatform.core.profiler import value_kind

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
# Taxa in composition figures take their colours from one global map, reports/composition.py.
OTHER = "Other"
BOX_LINE = "#3f4a4a"  # box outlines and medians

# Interactive files: plotly.js shows a "Share chart" button by default, which uploads the
# plot's data to Chart Studio online. Uploads may be clinical, so it is always off.
PLOTLY_CONFIG = {"displaylogo": False, "showSendToCloud": False, "responsive": True}

Kind = Literal["bar", "histogram", "barh", "column", "scatter", "line", "stacked", "pie", "box", "composition",
               "violin"]
HIGH_DPI = 300  # composition figures, as in the lab's own figure scripts
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
    composition  two panels (5:1): one stacked bar per distinct ``x`` (in row order), segments ``y``
               coloured by ``color_by`` in ``colors`` order; rows whose ``x`` is in ``summary`` form
               the right panel ("Average"); legend below; ``suptitle`` above (the lab's fig_1B style)
    violin     per ``x``, the spread of ``y``: the first ``group_by`` value as the left half of a
               violin, the second as the right half, medians marked

    ``colors`` fixes the colour of each value (of ``color_by``, of the pie's ``x``, or of the box's
    ``group_by``), so a taxon or a group keeps one colour across figures.

    Statistics on a figure: ``brackets`` (box) are significance bars between two groups of a
    panel; ``panel_titles`` (box) name each panel's test; ``ellipses`` (scatter) draws, for each
    colour group of at least 3 points, the normal-theory ellipse holding that share of its points;
    ``subtitle`` is a line under the title; ``stats`` is the table of tests, saved beside the data.
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
    suptitle: str | None = None  # composition: a bold heading above both panels (e.g. the dataset's name)
    subtitle: str | None = None  # a line under the title (e.g. a test's result)
    brackets: tuple[tuple[str | None, str, str, str], ...] = ()  # box: (panel, group, group, label)
    panel_titles: tuple[tuple[str, str], ...] = ()  # box: (panel, title), e.g. the test used
    ellipses: float | None = None  # scatter: coverage of each group's ellipse (e.g. 0.95)
    stats: pd.DataFrame | None = None  # the tests behind the figure, written as <name>_tests.csv


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
    rendered: bool = False  # drawn by a tool's own plotting code (RenderedFigure): no interactive plotly version


@dataclass
class RenderedFigure:
    """A figure drawn by a tool's own plotting code, not by us (e.g. miMic's cladogram).

    Its SVG and PNG are copied unchanged; the export adds a standalone HTML page that shows the SVG,
    and ``data`` as the CSV (what the figure shows). It is never redrawn.
    """

    name: str
    title: str
    caption: str
    svg: Path
    png: Path
    data: pd.DataFrame
    section: Section = "findings"
    lead: bool = True  # first among the figures (the headline); False: after the figures we draw
    wide: bool = True  # takes the whole row; False for a small plot (shown at its own size)


# --- the figures for preprocessing ---------------------------------------------

def preprocessing_figures(counts: pd.DataFrame, settings: PreprocessSettings) -> list[Figure]:
    """Quality-check figures from the raw counts (samples × taxa, see ``Dataset.raw_counts``).

    How widespread each taxon is (``taxa_prevalence``) is part of the data overview (``reports/overview.py``).
    Sequencing depth exists only for read counts: for relative abundances (each sample adds up to the
    same total) or transformed values, ``reads_per_sample`` is not made (the same rule as the data
    check, ``profiler.value_kind``; the page shows ``CountsProfile.depth_note`` instead).
    """
    return [_reads_per_sample(counts)] if value_kind(counts) == "counts" else []


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
        files = {f: f"{fig.name}.{f}" for f in (*FORMATS, "json")}
        stats_file = out_dir / f"{fig.name}_tests.csv"
        if fig.stats is not None:
            fig.stats.to_csv(stats_file, index=False)
            files["tests"] = stats_file.name
        else:
            stats_file.unlink(missing_ok=True)  # a re-run without groups must not keep old tests
        _write_static(fig, out_dir)
        interactive = to_plotly(fig)
        interactive.write_html(out_dir / f"{fig.name}.html", include_plotlyjs=True, full_html=True,
                               config=PLOTLY_CONFIG)
        (out_dir / f"{fig.name}.json").write_text(interactive.to_json(), encoding="utf-8")
        exported.append(ExportedFigure(
            fig.name, fig.title, fig.caption, files, fig.section, tall=fig.kind == "barh", wide=_is_wide(fig),
        ))
    _add_to_manifest(exported, out_dir)
    return exported


def export_rendered(figures: list[RenderedFigure], out_dir: Path) -> list[ExportedFigure]:
    """Copy each tool-drawn figure's SVG and PNG unchanged, write its data CSV and an HTML page showing
    the SVG, and add them to the folder's manifest (first among the figures when ``lead``: the headline;
    otherwise after the others)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    for fig in figures:
        shutil.copyfile(fig.svg, out_dir / f"{fig.name}.svg")
        shutil.copyfile(fig.png, out_dir / f"{fig.name}.png")
        fig.data.to_csv(out_dir / f"{fig.name}.csv", index=False)
        svg = Path(fig.svg).read_text(encoding="utf-8")
        svg = svg[svg.index("<svg"):] if "<svg" in svg else svg  # inline: drop the XML declaration
        (out_dir / f"{fig.name}.html").write_text(
            "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{html.escape(fig.title)}</title>"
            "<style>body{margin:16px;font-family:Arial,sans-serif;color:#0f2e33;background:#fff}"
            "svg{max-width:100%;height:auto}p{max-width:60rem}</style></head><body>"
            f"<h1>{html.escape(fig.title)}</h1><p>{html.escape(fig.caption)}</p>{svg}</body></html>\n",
            encoding="utf-8")
        files = {f: f"{fig.name}.{f}" for f in ("png", "svg", "html", "csv")}
        exported.append(ExportedFigure(fig.name, fig.title, fig.caption, files, fig.section, wide=fig.wide,
                                       rendered=True))
    leads = {f.name for f in figures if f.lead}
    _add_to_manifest([e for e in exported if e.name in leads], out_dir, first=True)
    _add_to_manifest([e for e in exported if e.name not in leads], out_dir)
    return exported


def _add_to_manifest(exported: list[ExportedFigure], out_dir: Path, first: bool = False) -> None:
    """Replace figures of the same name in the manifest and keep the others."""
    names = {e.name for e in exported}
    kept = [e for e in load_manifest(out_dir) if e.name not in names]
    ordered = exported + kept if first else kept + exported
    (out_dir / "figures.json").write_text(json.dumps([asdict(e) for e in ordered], indent=2), encoding="utf-8")


def load_manifest(figures_dir: Path) -> list[ExportedFigure]:
    manifest = Path(figures_dir) / "figures.json"
    if not manifest.exists():
        return []
    return [ExportedFigure(**e) for e in json.loads(manifest.read_text(encoding="utf-8"))]


def _is_wide(fig: Figure) -> bool:
    if fig.kind in ("stacked", "composition", "violin"):
        return True
    if fig.kind == "box":
        return fig.facet is not None and fig.data[fig.facet].nunique() > 1
    return fig.kind == "pie" and fig.group_by is not None and fig.data[fig.group_by].nunique() > 1


def _values(fig: Figure, column: str | None) -> list:
    return list(dict.fromkeys(fig.data[column])) if column else [None]


# --- composition figures: shared layout --------------------------------------------------

def taxon_colors(taxa) -> dict[str, str]:
    """The global phylum→colour map (``composition.phylum_colors``, lab palette); "Other" grey and last.

    The one place per-taxon colours come from, so a figure built without explicit ``colors``
    still matches every other composition figure.
    """
    from microplatform.reports.composition import phylum_colors  # it imports this module

    return phylum_colors(taxa)


def group_colors(groups) -> dict[str, str]:
    """A colour per group, in the given order: the site's group colours (as in every other figure)."""
    return {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(dict.fromkeys(groups))}


def _color_map(fig: Figure, column: str) -> dict[str, str]:
    """The figure's fixed colours, or colours by order of appearance."""
    if fig.colors:
        return dict(fig.colors)
    return (taxon_colors(fig.data[column]) if fig.kind in ("stacked", "pie", "composition")
            else group_colors(fig.data[column]))


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
    if fig.kind in ("composition", "violin"):
        with matplotlib.rc_context({"svg.fonttype": "none"}):
            (_write_composition if fig.kind == "composition" else _write_violin)(fig, out_dir)
        return
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
            for group, color, (ex, ey) in _ellipses(fig):
                ax.plot(ex, ey, color=color, linestyle="--", linewidth=1.5, alpha=0.8)
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
        if fig.subtitle:
            mpl.suptitle(fig.title, x=0.02, ha="left", fontweight="bold")
            ax.set_title(fig.subtitle, loc="left", fontsize=9)
        else:
            ax.set_title(fig.title, loc="left", fontweight="bold")
        ax.set_xlabel(fig.x_label)
        ax.set_ylabel(fig.y_label)
        ax.spines[["top", "right"]].set_visible(False)
        _save(mpl, fig, out_dir)


def ellipse_outline(x, y, coverage: float, points: int = 120) -> tuple[np.ndarray, np.ndarray] | None:
    """The normal-theory ellipse that holds ``coverage`` of the points (x, y), as an outline.

    Its centre is the mean, its shape the covariance, and its size the chi-square quantile with
    2 degrees of freedom (95%: 2.45 standard deviations). None with fewer than 3 points or no spread.
    """
    from scipy.stats import chi2

    xy = np.column_stack([np.asarray(x, float), np.asarray(y, float)])
    if len(xy) < 3:
        return None
    values, vectors = np.linalg.eigh(np.cov(xy, rowvar=False))
    if not np.all(np.isfinite(values)) or values.max() <= 0:
        return None
    radius = np.sqrt(chi2.ppf(coverage, df=2))
    angle = np.linspace(0, 2 * np.pi, points)
    circle = np.vstack([np.cos(angle), np.sin(angle)])
    outline = vectors @ (np.sqrt(np.clip(values, 0, None))[:, None] * circle) * radius
    centre = xy.mean(axis=0)
    return outline[0] + centre[0], outline[1] + centre[1]


def _ellipses(fig: Figure) -> list[tuple[str, str, tuple[np.ndarray, np.ndarray]]]:
    """(group, colour, outline) for each colour group of a scatter that gets an ellipse."""
    if not fig.ellipses or not fig.color_by:
        return []
    lookup = _color_map(fig, fig.color_by)
    out = []
    for group in dict.fromkeys(fig.data[fig.color_by]):
        rows = fig.data[fig.data[fig.color_by] == group]
        outline = ellipse_outline(rows[fig.x], rows[fig.y], fig.ellipses)
        if outline is not None:
            out.append((str(group), lookup[group], outline))
    return out


def _bracket_levels(fig: Figure, panel, groups: list) -> list[tuple[int, int, str, int]]:
    """The panel's brackets as (from index, to index, label, level): short spans low, wide ones above,
    and a bracket whose label names a test (an overall test, e.g. "Kruskal-Wallis **") on top."""
    where = {g: i for i, g in enumerate(groups)}
    found = [(where[a], where[b], label) for p, a, b, label in fig.brackets
             if p == panel and a in where and b in where]
    found.sort(key=lambda bracket: (" " in bracket[2], abs(bracket[1] - bracket[0]), bracket[0]))
    return [(min(a, b), max(a, b), label, level) for level, (a, b, label) in enumerate(found)]


def _save(mpl: MplFigure, fig: Figure, out_dir: Path, dpi: int = 200, tight: bool = False) -> None:
    for fmt in ("png", "svg"):
        mpl.savefig(out_dir / f"{fig.name}.{fmt}", dpi=dpi, bbox_inches="tight" if tight else None)


def _write_composition(fig: Figure, out_dir: Path) -> None:
    """The lab's fig_1B layout: samples (left, 5 parts) and their mean (right, 1 part), legend below."""
    colors = _color_map(fig, fig.color_by)
    wide = fig.data.pivot(index=fig.x, columns=fig.color_by, values=fig.y)
    order = [t for t in colors if t in wide.columns]
    bars = list(dict.fromkeys(fig.data[fig.x]))
    samples = wide.loc[[b for b in bars if b not in fig.summary], order]
    means = wide.loc[[b for b in bars if b in fig.summary], order]
    mpl = MplFigure(figsize=(16, 6))
    ax_samples, ax_mean = mpl.subplots(1, 2, gridspec_kw={"width_ratios": [5, 1]})
    for ax, table in ((ax_samples, samples), (ax_mean, means)):
        bottom = np.zeros(len(table))
        for taxon in order:
            values = table[taxon].fillna(0).to_numpy()
            ax.bar(range(len(table)), values, bottom=bottom, width=0.9, color=colors[taxon], edgecolor="none",
                   label=taxon)
            bottom += values
        ax.set_ylim(0, 100)
        ax.spines[["top", "right"]].set_visible(False)
    ax_samples.set_ylabel(fig.y_label, fontsize=12)
    ax_samples.set_xticks([])
    ax_samples.set_xlim(-0.6, len(samples) - 0.4)
    ax_samples.set_title(f"Samples (n={len(samples):,})", fontsize=13)
    ax_mean.set_xticks(range(len(means)), list(means.index), fontsize=11)
    ax_mean.set_title("Average", fontsize=13)
    ax_mean.spines["left"].set_visible(False)
    ax_mean.yaxis.set_visible(False)
    mpl.legend(handles=[Rectangle((0, 0), 1, 1, color=colors[t], label=t) for t in order], loc="lower center",
               bbox_to_anchor=(0.5, -0.12), ncol=4, frameon=False, fontsize=9)
    mpl.suptitle(fig.suptitle or fig.title, fontsize=16, fontweight="bold")
    mpl.tight_layout(rect=[0, 0.12, 1, 1])
    _save(mpl, fig, out_dir, dpi=HIGH_DPI, tight=True)


def _write_violin(fig: Figure, out_dir: Path) -> None:
    """Split violins as in the lab's fig_1B scripts: one group's half on the left, the other's on the right."""
    taxa = list(dict.fromkeys(fig.data[fig.x]))
    groups = list(dict.fromkeys(fig.data[fig.group_by]))[:2]
    colors = _color_map(fig, fig.group_by)
    mpl = MplFigure(figsize=(max(14, len(taxa) * 0.8), 7))
    ax = mpl.add_subplot()
    for i, taxon in enumerate(taxa):
        for group, keep in zip(groups, (np.minimum, np.maximum)):
            values = fig.data.loc[(fig.data[fig.x] == taxon) & (fig.data[fig.group_by] == group), fig.y].dropna()
            if len(values) < 2 or values.nunique() < 2:  # a violin needs a spread
                continue
            parts = ax.violinplot([values.to_numpy()], positions=[i], widths=0.8, showmeans=False,
                                  showmedians=True, showextrema=False)
            for body in parts["bodies"]:
                body.set_facecolor(colors[group])
                body.set_edgecolor("black")
                body.set_alpha(0.7)
                verts = body.get_paths()[0].vertices
                verts[:, 0] = keep(verts[:, 0], i)
            median = parts["cmedians"]
            median.set_color("black")
            median.set_linewidth(1.2)
            # The median line spans only its own half.
            median.set_segments([np.column_stack([keep(s[:, 0], i), s[:, 1]]) for s in median.get_segments()])
    ax.set_xticks(range(len(taxa)), taxa, rotation=45, ha="right")
    ax.set_ylabel(fig.y_label)
    ax.set_title(fig.title, loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(handles=[Patch(facecolor=colors[g], edgecolor="black", label=g) for g in groups], frameon=False)
    mpl.tight_layout()
    _save(mpl, fig, out_dir, dpi=HIGH_DPI, tight=True)


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
        levels = _bracket_levels(fig, panel, groups)
        if levels:
            low, high = float(rows[fig.y].min()), float(rows[fig.y].max())
            step = (high - low or 1.0) * 0.09
            for a, b, label, level in levels:
                y = high + step * (level + 0.6)
                ax.plot([a, a, b, b], [y - step * 0.25, y, y, y - step * 0.25], color=BOX_LINE, linewidth=1)
                ax.text((a + b) / 2, y, label, ha="center", va="bottom", fontsize=9, color=BOX_LINE,
                        fontweight="normal" if label.endswith("ns") else "bold")
            ax.set_ylim(top=high + step * (len(levels) + 1.2))
        titles = dict(fig.panel_titles)
        if panel in titles:
            ax.set_title(titles[panel], fontsize=9, loc="left")
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
    if fig.kind == "composition":
        return _plotly_composition(fig)
    if fig.kind == "violin":
        return _plotly_violin(fig)
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
        for group, color, (ex, ey) in _ellipses(fig):
            out.add_trace(go.Scatter(x=ex, y=ey, mode="lines", hoverinfo="skip", showlegend=False,
                                     line={"color": color, "width": 1.5, "dash": "dash"}, name=f"{group} ellipse"))
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
        title={"text": _title(fig), "x": 0, "xanchor": "left"},
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


def _title(fig: Figure) -> str:
    """The interactive title: the title, and the subtitle as a smaller second line."""
    return f"{fig.title}<br><sup>{fig.subtitle}</sup>" if fig.subtitle else fig.title


def _plotly_composition(fig: Figure) -> go.Figure:
    colors = _color_map(fig, fig.color_by)
    bars = list(dict.fromkeys(fig.data[fig.x]))
    samples = [b for b in bars if b not in fig.summary]
    out = make_subplots(rows=1, cols=2, column_widths=[5 / 6, 1 / 6], shared_yaxes=True, horizontal_spacing=0.02,
                        subplot_titles=(f"Samples (n={len(samples):,})", "Average"))
    for taxon, color in colors.items():
        rows = fig.data[fig.data[fig.color_by] == taxon]
        if rows.empty:
            continue
        for col, part in ((1, rows[~rows[fig.x].isin(fig.summary)]), (2, rows[rows[fig.x].isin(fig.summary)])):
            out.add_trace(go.Bar(x=part[fig.x], y=part[fig.y], name=taxon, legendgroup=taxon, showlegend=col == 1,
                                 marker={"color": color, "line": {"width": 0}}, hovertemplate=fig.hover),
                          row=1, col=col)
    out.update_xaxes(categoryorder="array", categoryarray=samples, showticklabels=False, ticks="", row=1, col=1)
    out.update_xaxes(ticks="", row=1, col=2)
    out.update_yaxes(range=[0, 100], title_text=fig.y_label, row=1, col=1)
    out.update_yaxes(range=[0, 100], visible=False, row=1, col=2)
    out.update_layout(
        title={"text": fig.suptitle or fig.title, "x": 0.5, "xanchor": "center"}, barmode="stack", bargap=0.1,
        template="simple_white", margin={"l": 60, "r": 20, "t": 70, "b": 20},
        legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": -0.04, "yanchor": "top"},
        meta={"panels": "side by side"},  # app.js: keep the Average beside the samples, also on phones
    )
    return out


def _plotly_violin(fig: Figure) -> go.Figure:
    groups = list(dict.fromkeys(fig.data[fig.group_by]))[:2]
    colors = _color_map(fig, fig.group_by)
    out = go.Figure()
    for group, side in zip(groups, ("negative", "positive")):
        rows = fig.data[fig.data[fig.group_by] == group]
        out.add_trace(go.Violin(x=rows[fig.x], y=rows[fig.y], name=str(group), side=side, legendgroup=str(group),
                                fillcolor=colors[group], line={"color": "black", "width": 1}, opacity=0.7,
                                points=False, box={"visible": True, "width": 0.15}, meanline={"visible": False},
                                spanmode="hard", hovertemplate=fig.hover))
    out.update_layout(title={"text": fig.title, "x": 0, "xanchor": "left"}, violinmode="overlay",
                      template="simple_white", yaxis_title=fig.y_label, margin={"l": 60, "r": 20, "t": 50, "b": 80},
                      legend={"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom"})
    out.update_xaxes(tickangle=-45)
    return out


def _plotly_boxes(fig: Figure) -> go.Figure:
    panels = _values(fig, fig.facet)
    groups = _values(fig, fig.group_by)
    colors = _color_map(fig, fig.group_by) if fig.group_by else {None: ACCENT}
    titles = dict(fig.panel_titles)
    out = make_subplots(rows=1, cols=len(panels), horizontal_spacing=0.12,
                        subplot_titles=[titles.get(p, "") for p in panels] if titles else None)
    for annotation in out.layout.annotations:  # panel titles: small, left-aligned, as in the PNG
        annotation.update(font={"size": 11})
    for col, panel in enumerate(panels, start=1):
        rows = fig.data if panel is None else fig.data[fig.data[fig.facet] == panel]
        names = []
        for group in groups:
            members = rows if group is None else rows[rows[fig.group_by] == group]
            names.append(f"{group} (n={len(members)})" if group is not None else f"n={len(members)}")
            out.add_trace(go.Box(
                y=members[fig.y], name=names[-1],
                boxpoints="all", jitter=0.45, pointpos=0, text=members[fig.label] if fig.label else None,
                marker={"color": colors[group], "size": 6, "opacity": 0.8, "line": {"color": "white", "width": 0.5}},
                line={"color": BOX_LINE, "width": 1}, fillcolor="rgba(0,0,0,0)", hovertemplate=fig.hover,
                showlegend=False,
            ), row=1, col=col)
        out.update_yaxes(title_text=panel if panel is not None else fig.y_label, row=1, col=col)
        out.update_xaxes(title_text=fig.x_label, row=1, col=col)
        levels = _bracket_levels(fig, panel, groups)
        if levels:
            low, high = float(rows[fig.y].min()), float(rows[fig.y].max())
            step = (high - low or 1.0) * 0.09
            axis = "" if col == 1 else str(col)
            for a, b, label, level in levels:
                y = high + step * (level + 0.6)
                out.add_shape(type="path", path=_bracket_path(a, b, y, step * 0.25),
                              xref=f"x{axis}", yref=f"y{axis}", line={"color": BOX_LINE, "width": 1},
                              fillcolor="rgba(0,0,0,0)")  # a line, not a filled shape
                out.add_annotation(x=(a + b) / 2, y=y, text=label, showarrow=False, yanchor="bottom",
                                   xref=f"x{axis}", yref=f"y{axis}", font={"color": BOX_LINE, "size": 11})
            out.update_yaxes(range=[low - step, high + step * (len(levels) + 1.2)], row=1, col=col)
    out.update_layout(title={"text": _title(fig), "x": 0, "xanchor": "left"}, template="simple_white",
                      margin={"l": 60, "r": 20, "t": 50, "b": 50})
    return out


def _bracket_path(a: int, b: int, y: float, drop: float) -> str:
    """An SVG path for a significance bracket between two boxes (by position: 0, 1, … on a category axis)."""
    return f"M {a},{y - drop} L {a},{y} L {b},{y} L {b},{y - drop}"
