"""GIMIC as an engine: "See how samples group".

Runs the authors' code from the ``samba-metric`` package unchanged (see
docs/tool-inputs.he.md), exactly as their published example does:

    images, bact_names, ordered_df = micro2matrix(processed, folder, save=False)
    dm = build_SAMBA_distance_matrix(folder, imgs=images, ordered_df=ordered_df,
                                     bact_names=bact_names, class_=False)   # SAM metric, FFT cut-off 0.8

``processed`` is ``Dataset.features``. How bacteria are grouped is an option
(decided with the lab, 2026-10-22):

- "sub PCA" (default): the shared table every tool uses; the paper's method.
- "mean": how GIMIC's published example runs (``MIPMLP.preprocess(df)``
  defaults). A declared exception in the data contract, shown on the results page.

The map uses the same UMAP call as the authors' ``plot_umap``
(``umap.UMAP(metric="precomputed")``) with a fixed seed, so it is the same on
every run. Their ``plot_umap`` itself is not used: it hard-codes two groups
named "Control"/"Condition" and opens a plot window.
"""

from __future__ import annotations

import contextlib
import io
import os
import warnings
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from microplatform.core.contract import ID_COLUMN, Dataset
from microplatform.engines.base import Engine, EngineOption, EngineResult
from microplatform.core.preprocessing import CANONICAL, PreprocessSettings
from microplatform.reports.figures import Figure

METRIC = "sam"  # the authors' default: spectral angle between smoothed images
CUTOFF = 0.8  # the authors' default FFT cut-off
UMAP_SEED = 42
GROUPING_DEFAULT = "sub PCA"  # the single internal switch for the default grouping

GROUPINGS = {
    "sub PCA": "Sub-PCA: the same table as every other tool (the method in the GIMIC paper). Recommended.",
    "mean": "Mean: as in GIMIC's published example code. Only GIMIC uses this grouping.",
}


def load_gimic():
    """Import GIMIC (the samba package) after PyTorch, which must load before Qt on Windows."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    import MIPMLP  # noqa: F401  (PyTorch first)
    from samba import build_SAMBA_distance_matrix, micro2matrix

    return micro2matrix, build_SAMBA_distance_matrix


class GimicEngine(Engine):
    name = "GIMIC"
    goal = "group"
    requires = frozenset({"counts"})
    options = (EngineOption("grouping", "How bacteria are grouped", GROUPINGS, GROUPING_DEFAULT),)

    def settings_for(self, choices: dict[str, str]) -> PreprocessSettings:
        return CANONICAL.with_changes(taxonomy_group=choices["grouping"])

    def run(self, data: Dataset, work_dir: Path, choices: dict[str, str] | None = None) -> EngineResult:
        choices = self.resolve(choices)
        micro2matrix, build_distances = load_gimic()
        work_dir = Path(work_dir)
        images = work_dir / "images"
        images.mkdir(parents=True, exist_ok=True)

        with contextlib.chdir(work_dir), _quiet():
            imgs, bact_names, ordered_df = micro2matrix(data.features, str(images), save=False)
            dm = build_distances(str(images), metric=METRIC, cutoff=CUTOFF, imgs=imgs,
                                 ordered_df=ordered_df, bact_names=bact_names, class_=False)
        dm.index = dm.index.astype(str)
        dm.columns = dm.columns.astype(str)

        groups = _groups(data, dm.index)
        coords = _umap(dm)
        tables = {"distance_matrix": dm.rename_axis(ID_COLUMN).reset_index()}
        figures = []
        if coords is not None:
            coords["group"] = (groups.reindex(coords["sample"]).fillna("no label").to_numpy()
                               if groups is not None else "all samples")
            coords = coords.sort_values(["group", "sample"], kind="stable").reset_index(drop=True)  # tidy legend
            tables["map_coordinates"] = coords
            figures.append(_map_figure(coords, groups is not None))
        separation = _separation(dm, groups) if groups is not None else None
        if separation is not None:
            tables["group_distances"] = separation
            figures.append(_separation_figure(separation))

        return EngineResult(
            highlight=("group_distances", "Average distances, in numbers") if separation is not None else None,
            summary=_summary(dm, choices["grouping"], separation),
            notes=_notes(choices["grouping"], coords is not None),
            figures=figures,
            tables=tables,
            record={
                "tool": "GIMIC", "package": "samba-metric", "version": version("samba-metric"),
                "grouping": choices["grouping"], "metric": METRIC, "fft_cutoff": CUTOFF,
                "samples": len(dm), "map": f"umap.UMAP(metric='precomputed', random_state={UMAP_SEED})",
            },
        )


def _groups(data: Dataset, samples: pd.Index) -> pd.Series | None:
    """Labels for colouring, as text; None without labels or for a continuous label."""
    if data.labels is None or data.label_kind == "continuous":
        return None
    return data.labels.reindex(samples).dropna().astype(str)


def _umap(dm: pd.DataFrame) -> pd.DataFrame | None:
    """2-D map from the distances (the authors' UMAP call, plus a seed). None if too few samples."""
    n = len(dm)
    if n < 5:
        return None
    import umap

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = umap.UMAP(metric="precomputed", random_state=UMAP_SEED, n_neighbors=min(15, n - 1))
        xy = model.fit_transform(dm.to_numpy())
    return pd.DataFrame({"sample": dm.index, "map_1": xy[:, 0], "map_2": xy[:, 1]})


def _separation(dm: pd.DataFrame, groups: pd.Series) -> pd.DataFrame | None:
    """Average GIMIC distance within each group and between groups (descriptive, no test)."""
    groups = groups[groups.index.isin(dm.index)]
    if groups.nunique() < 2:
        return None
    rows = []
    values = dm.loc[groups.index, groups.index].to_numpy()
    upper = np.triu(np.ones_like(values, dtype=bool), k=1)
    for g in sorted(groups.unique()):
        mask = (groups == g).to_numpy()
        pair = np.outer(mask, mask) & upper
        if pair.any():
            rows.append({"comparison": f"within '{g}'", "mean_distance": float(values[pair].mean()), "pairs": int(pair.sum())})
    between = np.not_equal.outer(groups.to_numpy(), groups.to_numpy()) & upper
    rows.append({"comparison": "between groups", "mean_distance": float(values[between].mean()), "pairs": int(between.sum())})
    return pd.DataFrame(rows)


def _summary(dm, grouping: str, separation) -> list[str]:
    lines = [f"GIMIC distances were computed between all {len(dm):,} samples "
             f"(spectral angle between FFT-smoothed images, cut-off {CUTOFF:g})."]
    if grouping != "mean":
        lines.append("Bacteria were grouped with sub-PCA: the same table the other tools use (the paper's method).")
    if separation is not None:
        within = separation[separation["comparison"] != "between groups"]["mean_distance"].mean()
        between = float(separation.loc[separation["comparison"] == "between groups", "mean_distance"].iloc[0])
        lines.append(f"Samples are on average {between / within:.2f}× as far from other groups as from their own "
                     f"(between {between:.3g}, within {within:.3g}). Above 1 means groups are more alike inside "
                     "than across; this is a description, not a statistical test.")
    return lines


def _notes(grouping: str, has_map: bool) -> list[str]:
    notes = []
    if grouping == "mean":
        notes.append("Bacteria were grouped by their mean, as in GIMIC's published example. Every other "
                     "tool uses sub-PCA (the shared table), so these distances are not on exactly the same "
                     "representation as the other tools' results.")
    if has_map:
        notes.append("The map places similar samples close together; it is for viewing — the distances themselves "
                     "are in the table.")
    return notes


def _map_figure(coords: pd.DataFrame, coloured: bool) -> Figure:
    return Figure(
        name="gimic_map", title="Map of the samples (UMAP of GIMIC distances)",
        caption="Each point is a sample, placed so that samples with similar microbiomes (a small GIMIC "
                "distance) lie close together" + (", coloured by label" if coloured else "") + ". Use it to see "
                "groups and outliers: the axes have no units, and distances on the map are only approximate "
                "(the exact ones are in the distance matrix download). Descriptive only, not a statistical test.",
        details=f"UMAP of the GIMIC distance matrix (umap.UMAP(metric='precomputed', random_state={UMAP_SEED})); "
                "GIMIC distance = the spectral angle between FFT-smoothed iMic images (samba-metric).",
        data=coords, kind="scatter", x="map_1", y="map_2", x_label="Map dimension 1",
        y_label="Map dimension 2", color_by="group" if coloured else None, label="sample",
        hover="%{text}<extra></extra>", section="findings",
    )


def _separation_figure(separation: pd.DataFrame) -> Figure:
    return Figure(
        name="gimic_group_distances", title="Distances within and between groups",
        caption="The average GIMIC distance between two samples from the same group, and between two samples "
                "from different groups. If 'between groups' is clearly higher than 'within', samples are more "
                "alike inside their group than across groups. Descriptive only, not a statistical test.",
        details="Means over all pairs of samples (each pair once); the number of pairs is in the data CSV.",
        data=separation, kind="column", x="comparison", y="mean_distance", x_label="",
        y_label="Average GIMIC distance", hover="%{x}: %{y:.3g}<extra></extra>", section="findings",
    )


@contextlib.contextmanager
def _quiet():
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        yield
