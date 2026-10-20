"""Figures: one description, three renderings, and always the data behind it.

A ``Figure`` holds the exact table that is plotted plus how to draw it.
``export`` writes, for each figure:

    <name>.png    for slides and documents (200 dpi)
    <name>.svg    vector, with editable text (for Illustrator or Inkscape)
    <name>.html   interactive (hover, zoom); standalone and works offline
    <name>.json   the interactive figure, for embedding in the results page
    <name>.csv    the underlying data, so the figure can be re-made or edited
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
ACCENT = "#1f7a5c"
MARKER = "#b42318"


@dataclass(frozen=True)
class Figure:
    name: str  # file stem, e.g. "reads_per_sample"
    title: str
    caption: str  # one plain-language sentence on how to read it
    data: pd.DataFrame
    kind: Literal["bar", "histogram"]
    x: str  # column of ``data`` on the x axis
    y: str | None  # column on the y axis (bar charts only)
    x_label: str
    y_label: str
    marker: tuple[float, str] | None = None  # vertical reference line: (x, label)
    log_y: bool = False


@dataclass(frozen=True)
class ExportedFigure:
    """What a results page needs: the text and the file name for each format."""

    name: str
    title: str
    caption: str
    files: dict[str, str]  # format → file name inside the figures folder


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
    )


# --- rendering -------------------------------------------------------------------------

def export(figures: list[Figure], out_dir: Path) -> list[ExportedFigure]:
    """Write every format of every figure, plus a manifest the results page reads."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    for fig in figures:
        fig.data.to_csv(out_dir / f"{fig.name}.csv", index=False)
        _write_static(fig, out_dir)
        interactive = to_plotly(fig)
        interactive.write_html(out_dir / f"{fig.name}.html", include_plotlyjs=True, full_html=True)
        (out_dir / f"{fig.name}.json").write_text(interactive.to_json(), encoding="utf-8")
        exported.append(ExportedFigure(
            fig.name, fig.title, fig.caption, {f: f"{fig.name}.{f}" for f in (*FORMATS, "json")},
        ))
    (out_dir / "figures.json").write_text(
        json.dumps([asdict(e) for e in exported], indent=2), encoding="utf-8"
    )
    return exported


def load_manifest(figures_dir: Path) -> list[ExportedFigure]:
    manifest = Path(figures_dir) / "figures.json"
    if not manifest.exists():
        return []
    return [ExportedFigure(**e) for e in json.loads(manifest.read_text(encoding="utf-8"))]


def _write_static(fig: Figure, out_dir: Path) -> None:
    # The object-oriented matplotlib API (no pyplot) is safe inside a web server.
    with matplotlib.rc_context({"svg.fonttype": "none", "font.size": 10}):
        mpl = MplFigure(figsize=(7, 4), layout="constrained")
        ax = mpl.add_subplot()
        if fig.kind == "bar":
            ax.bar(range(len(fig.data)), fig.data[fig.y], color=ACCENT, width=0.85)
            ax.set_xticks([])
            ax.set_xlim(-0.6, len(fig.data) - 0.4)
            if fig.log_y:
                ax.set_yscale("log")
            ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
        else:
            ax.hist(fig.data[fig.x], bins=20, range=(0, 100), color=ACCENT, edgecolor="white")
        if fig.marker:
            ax.axvline(fig.marker[0], color=MARKER, linestyle="--", linewidth=1)
            ax.annotate(fig.marker[1], (fig.marker[0], 1), xycoords=("data", "axes fraction"),
                        xytext=(4, -4), textcoords="offset points", va="top", color=MARKER)
        ax.set_title(fig.title, loc="left", fontweight="bold")
        ax.set_xlabel(fig.x_label)
        ax.set_ylabel(fig.y_label)
        ax.spines[["top", "right"]].set_visible(False)
        for fmt in ("png", "svg"):
            mpl.savefig(out_dir / f"{fig.name}.{fmt}", dpi=200)


def to_plotly(fig: Figure) -> go.Figure:
    if fig.kind == "bar":
        trace = go.Bar(
            x=fig.data[fig.x], y=fig.data[fig.y], marker_color=ACCENT,
            hovertemplate="%{x}<br>%{y:,.0f} reads<extra></extra>",
        )
    else:
        trace = go.Histogram(
            x=fig.data[fig.x], xbins={"start": 0, "end": 100, "size": 5}, marker_color=ACCENT,
            hovertemplate="%{x}%: %{y} bacteria<extra></extra>",
        )
    out = go.Figure(trace)
    if fig.marker:
        out.add_vline(x=fig.marker[0], line_dash="dash", line_color=MARKER,
                      annotation_text=fig.marker[1], annotation_font_color=MARKER)
    out.update_layout(
        title={"text": fig.title, "x": 0, "xanchor": "left"},
        xaxis_title=fig.x_label, yaxis_title=fig.y_label,
        template="simple_white", margin={"l": 60, "r": 20, "t": 50, "b": 50},
        bargap=0.05,
    )
    if fig.kind == "bar":
        out.update_xaxes(showticklabels=False)
    if fig.log_y:
        out.update_yaxes(type="log")
    return out
