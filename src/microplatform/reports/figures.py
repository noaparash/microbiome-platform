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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import matplotlib
import matplotlib.ticker
import pandas as pd
import plotly
import plotly.graph_objects as go
from matplotlib.figure import Figure as MplFigure
from matplotlib.patches import Patch

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

# Interactive files: plotly.js shows a "Share chart" button by default, which uploads the
# plot's data to Chart Studio online. Uploads may be clinical, so it is always off.
PLOTLY_CONFIG = {"displaylogo": False, "showSendToCloud": False, "responsive": True}

Kind = Literal["bar", "histogram", "barh", "column", "scatter", "line"]
Section = Literal["quality", "findings"]


@dataclass(frozen=True)
class Figure:
    """What to plot and how.

    bar        one unlabelled bar per row (e.g. per sample), value in ``y``
    histogram  distribution of ``x`` between 0 and 100
    barh       one labelled horizontal bar per row: label ``y``, value ``x``, coloured by ``color_by``
    column     one labelled vertical bar per row: label ``x``, value ``y``
    scatter    one point per row at (``x``, ``y``), coloured by ``color_by``; ``label`` names each point
    line       a line through (``x``, ``y``) in row order; ``diagonal`` adds the 0→1 reference line
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


@dataclass(frozen=True)
class ExportedFigure:
    """What a results page needs: the text and the file name for each format."""

    name: str
    title: str
    caption: str
    files: dict[str, str]  # format → file name inside the figures folder
    section: Section = "quality"
    tall: bool = False  # one row per item (e.g. per taxon): needs the full width and more height


# --- the figures for preprocessing ---------------------------------------------

def preprocessing_figures(counts: pd.DataFrame, settings: PreprocessSettings) -> list[Figure]:
    """Quality-check figures from the raw counts (samples × taxa, see ``Dataset.raw_counts``)."""
    return [_reads_per_sample(counts), _taxa_prevalence(counts, settings)]


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


def _taxa_prevalence(counts: pd.DataFrame, settings: PreprocessSettings) -> Figure:
    prevalence = (counts > 0).mean(axis=0) * 100
    data = pd.DataFrame({"taxon": prevalence.index, "prevalence_percent": prevalence.round(2).to_numpy()})
    threshold = settings.rare_bacteria_threshold * 100
    return Figure(
        name="taxa_prevalence",
        title="How widespread each bacterium is",
        caption="For each bacterium, the share of samples it appears in. Most microbiome "
                f"data is sparse; MIPMLP drops bacteria found in fewer than {threshold:g}% of samples.",
        data=data, kind="histogram", x="prevalence_percent", y=None,
        x_label="Present in % of samples", y_label="Number of bacteria",
        marker=(threshold, f"{threshold:g}% cut-off"),
        hover="%{x}%: %{y} bacteria<extra></extra>",
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
            fig.section, tall=fig.kind == "barh",
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


# --- static rendering (matplotlib) ----------------------------------------------------

def _group_colors(fig: Figure) -> tuple[list[str], list[tuple[str, str]]]:
    """Per-row colours and the legend entries, for figures coloured by a group column."""
    if not fig.color_by:
        return [ACCENT] * len(fig.data), []
    groups = list(dict.fromkeys(fig.data[fig.color_by]))
    lookup = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}
    return [lookup[g] for g in fig.data[fig.color_by]], [(str(g), lookup[g]) for g in groups]


def _write_static(fig: Figure, out_dir: Path) -> None:
    # The object-oriented matplotlib API (no pyplot) is safe inside a web server.
    height = max(3.5, 0.26 * len(fig.data) + 1.4) if fig.kind == "barh" else 4
    with matplotlib.rc_context({"svg.fonttype": "none", "font.size": 10}):
        mpl = MplFigure(figsize=(7, height), layout="constrained")
        ax = mpl.add_subplot()
        if fig.kind == "bar":
            ax.bar(range(len(fig.data)), fig.data[fig.y], color=ACCENT, width=0.85)
            ax.set_xticks([])
            ax.set_xlim(-0.6, len(fig.data) - 0.4)
            ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
        elif fig.kind == "histogram":
            ax.hist(fig.data[fig.x], bins=20, range=(0, 100), color=ACCENT, edgecolor="white")
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
        for fmt in ("png", "svg"):
            mpl.savefig(out_dir / f"{fig.name}.{fmt}", dpi=200)


# --- interactive rendering (plotly) ----------------------------------------------------

def to_plotly(fig: Figure) -> go.Figure:
    out = go.Figure()
    if fig.kind == "bar":
        out.add_trace(go.Bar(x=fig.data[fig.x], y=fig.data[fig.y], marker_color=ACCENT,
                             hovertemplate=fig.hover))
    elif fig.kind == "histogram":
        out.add_trace(go.Histogram(x=fig.data[fig.x], xbins={"start": 0, "end": 100, "size": 5},
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
        bargap=0.05 if fig.kind in ("bar", "histogram") else 0.25, height=height,
        legend={"orientation": "h", "y": -0.15},
    )
    if fig.kind == "bar":
        out.update_xaxes(showticklabels=False)
    if fig.log_y:
        out.update_yaxes(type="log")
    return out
