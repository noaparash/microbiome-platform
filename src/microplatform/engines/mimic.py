"""miMic as an engine: "Find bacteria that differ between groups".

Runs the authors' ``apply_mimic`` unchanged, fed from the shared ``Dataset``
(see docs/tool-inputs.he.md). The adapter:

- ``processed`` = ``Dataset.features`` for the labelled samples. miMic's own
  preprocessing is ``MIPMLP.preprocess(raw, taxnomy_group="sub PCA")``, which is
  exactly our canonical setting, so this is what miMic would compute itself
  (tests/test_reproduction.py proves the results are identical).
- ``tag`` = the labels as a one-column table. Binary labels are coded 0/1,
  because miMic compares ``tag == 0`` with ``tag == 1`` and crashes on words.
- the test follows the label type: binary → "man" (Mann-Whitney), continuous →
  "corr" (Spearman). Categorical labels are refused: in mimic-da 1.0.1 the
  "category" mode crashes ("'numpy.ndarray' object has no attribute 'unique'").
- it runs inside ``work_dir``, because miMic always writes .pkl files into the
  current folder.

miMic's own figures are drawn by the authors' plot mode, unchanged (``_authors_plots``,
seed 42): the cladogram (the headline) and the RP vs SP plot (``tax_vs_rp_sp_anova_p``,
after the bars). The significant-taxa bars are drawn through ``reports.figures``; the
a-priori p-values are in the summary and the ``apriori_test`` table. The authors' full
bundle (their tables and every diagnostic plot, several seeds) is made by
``engines/mimic_authors.py``, outside the website.
"""

from __future__ import annotations

import contextlib
import io
import logging
import math
import os
import shutil
import warnings
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from microplatform.core.contract import RANK_SEPARATOR, Dataset
from microplatform.core.errors import UserFacingError
from microplatform.engines.base import Engine, EngineResult
from microplatform.engines.labels import native_tag
from microplatform.reports.figures import Figure, RenderedFigure

log = logging.getLogger(__name__)

# The authors' defaults, recorded with every result.
THRESHOLD_P = 0.05
SISTER_CORRECTION = "fdr_bh"
CORRECT_FIRST = True
EVALS = {"binary": "man", "continuous": "corr"}  # miMic's names for its tests
TOP_TAXA = 25  # shown in the figure; the table lists all of them

# miMic's own names for the rows of the a-priori test (its first row is the tree's root).
_LEVELS = ["Root", "Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"]
_TOOL_FILES = ("df_corrs.pkl", "miMic&Utest.pkl", "u_test_without_mimic.pkl")
LEAF_ONLY = "leaf test only"  # found only by the plain per-leaf test (the authors' u_test_without_mimic)


def load_mimic():
    """Import miMic safely.

    On Windows, PyTorch fails to load if Qt (pulled in by ete3) is loaded first,
    so MIPMLP (which loads PyTorch) is imported before miMic. Qt and matplotlib
    are set to draw without a screen.

    miMic's module runs ``matplotlib.use('Qt5Agg')`` when imported. On a Linux server
    without a screen, matplotlib refuses that ("headless") and the import fails. miMic
    needs Qt5Agg only to show windows (``plt.show``), never to save its figures, so
    there the screen-less backend is kept; with a screen, the call goes through as before.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("MPLBACKEND", "Agg")
    import MIPMLP  # noqa: F401  (PyTorch first)
    import matplotlib

    use = matplotlib.use

    def use_unless_headless(backend, *args, **kwargs):
        try:
            return use(backend, *args, **kwargs)
        except ImportError as exc:
            if "headless" not in str(exc):
                raise
            log.info("No screen: keeping matplotlib's %s backend instead of %s.", matplotlib.get_backend(), backend)

    matplotlib.use = use_unless_headless  # only while miMic's module is first imported
    try:
        from mimic_da import apply_mimic
        from mimic_da.miMic_test import apply_nested_anova
    finally:
        matplotlib.use = use

    return apply_mimic, apply_nested_anova


class MimicEngine(Engine):
    name = "miMic"
    goal = "differ"
    requires = frozenset({"counts", "labels"})

    def run(self, data: Dataset, work_dir: Path, choices: dict[str, str] | None = None) -> EngineResult:
        if data.labels is None:
            raise UserFacingError("miMic needs a labels file.", "Add a labels file in the Plan step.")
        if data.label_kind not in EVALS:
            raise UserFacingError(
                "miMic can compare two groups or test a continuous label, but not three or more groups yet.",
                "Combine your groups into two (for example, each group against the rest), "
                "or use a continuous label.",
            )
        tag, coding = native_tag(data.labels, data.label_kind)
        features = data.features.loc[tag.index]
        test = EVALS[data.label_kind]
        apply_mimic, apply_nested_anova = load_mimic()

        work_dir = Path(work_dir)
        images = work_dir / "images"
        images.mkdir(parents=True, exist_ok=True)
        for leftover in _TOOL_FILES:
            (work_dir / leftover).unlink(missing_ok=True)

        with contextlib.chdir(work_dir), _quiet():
            start, samba_output = apply_mimic(
                str(images), tag, eval=test, sis=SISTER_CORRECTION, correct_first=CORRECT_FIRST,
                threshold_p=THRESHOLD_P, processed=features, apply_samba=True, save=False,
            )
            levels = apply_nested_anova(samba_output, str(images), tag, mode="plot", eval=test,
                                        threshold_p=THRESHOLD_P)

        found = _significant_taxa(work_dir, start, data.label_kind, coding)
        # miMic's result is its tree test (the authors' just_mimic.csv). Taxa that only the plain leaf
        # test finds (their u_test_without_mimic.csv) are the baseline miMic is compared with: kept apart.
        hits = found[found["found_by"] != LEAF_ONLY].reset_index(drop=True)
        leaf_only = found[found["found_by"] == LEAF_ONLY].reset_index(drop=True)
        apriori = _apriori_table(levels)
        drawn = _authors_plots(work_dir, images, samba_output, tag, start, test, found, data.label_kind, coding)
        return EngineResult(
            summary=_summary(start, hits, leaf_only, apriori, data.label_kind, coding, test),
            rendered=drawn,
            figures=[f for f in (_taxa_figure(hits, data.label_kind, coding),) if f],
            tables={"significant_taxa": hits, "leaf_test_only": leaf_only, "apriori_test": apriori},
            highlight=("significant_taxa", "Most significant taxa (miMic)") if not hits.empty else None,
            record={
                "tool": "miMic", "package": "mimic-da", "version": version("mimic-da"),
                "test": {"man": "Mann-Whitney (binary)", "corr": "Spearman (continuous)"}[test],
                "eval": test, "threshold_p": THRESHOLD_P, "sister_correction": SISTER_CORRECTION,
                "correct_first": CORRECT_FIRST, "samples": len(tag), "label_coding": coding,
                "post_hoc_start": str(start), "significant_taxa": len(hits), "leaf_test_only": len(leaf_only),
                "authors_plots": (PLOT_CALL if drawn else "not drawn (no significant taxa)"),
                "plot_seed": PLOT_SEED,
            },
        )


# miMic's own figures are drawn by the authors' own code: their whole plot mode,
# ``apply_mimic(mode="plot")``, exactly as engines/mimic_authors.py runs it (seed 42). It re-runs the tree
# test from every starting level on the real labels (RP) and on shuffled labels (SP), draws the RP vs SP
# plot (``plot_rp_sp_anova_p``) and finally the cladogram (``creare_tree_view``). The SP counts depend on
# the seed; the cladogram and the tables do not. tests/test_reproduction.py compares both figures byte for
# byte with mimic_authors.run_bundle.
PLOT_SEED = 42
PLOT_CALL = ("mimic_da.apply_mimic(mode='plot') (seed 42): plot_rp_sp_anova_p -> plots/tax_vs_rp_sp_anova_p.png "
             "and calculate_all_imgs_tag_corr(mode='plot', colorful=True) -> creare_tree_view (ete3), unchanged, "
             "with engines/mimic_authors.ADJUSTMENTS; matplotlib draws without a screen (Agg)")


def _authors_plots(work_dir: Path, images: Path, samba_output, tag: pd.DataFrame, start, test: str,
                   hits: pd.DataFrame, kind: str, coding: dict) -> list[RenderedFigure]:
    """miMic's cladogram and its RP vs SP plot, drawn by the authors' plot mode (none if nothing is significant)."""
    if start == "nosignificant" or hits.empty:
        return []
    import random

    import numpy as np
    from mimic_da import apply_mimic

    from microplatform.engines.mimic_authors import COLORFUL, RP_SP_FIGURE, THRESHOLD_EDGE, compatible

    plots = work_dir / "plots"
    shutil.rmtree(plots, ignore_errors=True)
    import matplotlib.pyplot as plt

    backend = plt.get_backend()
    plt.switch_backend("Agg")  # the authors' plot mode opens windows (plt.show); here it only saves files
    try:
        with compatible() as seen, contextlib.chdir(work_dir), _quiet():
            random.seed(PLOT_SEED)
            np.random.seed(PLOT_SEED)
            apply_mimic(
                str(images), tag, eval=test, sis=SISTER_CORRECTION, correct_first=CORRECT_FIRST, mode="plot",
                tax=start, threshold_p=THRESHOLD_P, THRESHOLD_edge=THRESHOLD_EDGE, colorful=COLORFUL,
                samba_output=samba_output, save=False,
            )
    finally:
        plt.close("all")
        with contextlib.suppress(Exception):
            plt.switch_backend(backend)
    drawn = []
    svg, png = plots / "correlations_tree.svg", plots / "correlations_tree.png"
    if svg.exists() and png.exists():
        if kind == "binary":
            colours = f"blue: higher in '{coding['1']}', red: higher in '{coding['0']}'"
        else:
            colours = "blue: increases with the label, red: decreases with it"
        drawn.append(RenderedFigure(
            name="mimic_cladogram",
            title="miMic's cladogram: where on the taxonomy tree the groups differ",
            caption=("Drawn by miMic itself (mimic-da's own tree drawing; for legibility only, the labels are "
                     "4x larger and the circle is closed). The taxonomy tree of the "
                     f"significant taxa; each node's size grows with -log10(p), and its colour gives the direction ("
                     f"{colours}). Shape: sphere = found by both miMic's tree test and the leaf test, circle = the "
                     "tree test only, square = the leaf test only (not miMic's result; listed separately). The "
                     "background shows each taxon's family. Data (CSV): every taxon on the tree, with what found it "
                     "(column found_by)."),
            svg=svg, png=png, data=hits,
        ))
    else:
        log.warning("miMic did not draw its cladogram in %s", plots)
    svg, png = plots / f"{RP_SP_FIGURE}.svg", plots / f"{RP_SP_FIGURE}.png"
    if svg.exists() and png.exists() and "rp_sp_plotted" in seen:
        table, mixed = seen["rp_sp_plotted"]
        drawn.append(RenderedFigure(
            name="mimic_rp_sp", lead=False, wide=False,
            title="miMic's check: real vs shuffled labels per starting level",
            caption=("Drawn by miMic itself (mimic-da's plot_rp_sp_anova_p, unchanged). For each taxonomic level "
                     "the tree test could start from, the number of significant leaves with the real labels (RP, "
                     "blue) and with shuffled labels (SP, red; few or none means the findings are not chance). "
                     f"Grey: the levels the a-priori test passed, down to the start level used ({mixed}). Log "
                     "scale; a bar of 0 is not drawn. SP depends on the shuffle (seed 42). Data (CSV): RP and SP "
                     "per level (the a-priori p-values are in the apriori_test table)."),
            svg=svg, png=png, data=_rp_sp_table(table, mixed),
        ))
    else:
        log.warning("miMic did not draw its RP vs SP plot in %s", plots)
    return drawn


def _rp_sp_table(table: pd.DataFrame, mixed: str) -> pd.DataFrame:
    """miMic's RP/SP counts with the level names its plot shows (1-7 = Kingdom..Species, 8 = its combined level).

    miMic passes its a-priori p-values in the same table, but indexed from the root (1 = root), one level off
    from RP/SP (1 = kingdom); its plot does not draw them. They are left out here: the ``apriori_test`` table
    has them, correctly labelled."""
    names = [*_LEVELS[:8], mixed]  # _LEVELS[0] is the root (level 0)
    out = table[["RP", "SP"]].copy()
    out.insert(0, "starting_taxonomy", [names[int(i)] if 0 <= int(i) <= 8 else str(i) for i in out.index])
    return out.reset_index(drop=True)


def display_name(taxon: str) -> str:
    """'k__Bacteria;…;g__Bacteroides;s__caccae_0' → 'Bacteroides caccae_0'."""
    ranks = [p.strip() for p in str(taxon).split(RANK_SEPARATOR)]
    named = [(p[0], p.split("__", 1)[1]) if "__" in p else ("", p) for p in ranks if p]
    named = [(r, n) for r, n in named if n]
    if not named:
        return str(taxon)
    if named[-1][0] == "s" and len(named) > 1 and named[-2][0] == "g":
        return f"{named[-2][1]} {named[-1][1]}"
    return named[-1][1]


def _significant_taxa(work_dir: Path, start, kind: str, coding: dict) -> pd.DataFrame:
    columns = ["taxon", "name", "statistic", "p", "direction", "found_by"]
    if start == "nosignificant" or not (work_dir / "df_corrs.pkl").exists():
        return pd.DataFrame(columns=columns)
    corrs = pd.read_pickle(work_dir / "df_corrs.pkl")
    both = _index_of(work_dir / "miMic&Utest.pkl")
    leaf_only = _index_of(work_dir / "u_test_without_mimic.pkl")
    rows = []
    for taxon, row in corrs.iterrows():
        if kind == "binary":
            direction = f"higher in '{coding['1']}'" if row["scc"] > 0 else f"higher in '{coding['0']}'"
        else:
            direction = "increases with the label" if row["scc"] > 0 else "decreases with the label"
        if start == "noAnova" or taxon in leaf_only:
            found_by = LEAF_ONLY
        elif taxon in both:
            found_by = "tree path and leaf test"
        else:
            found_by = "tree path"
        rows.append([taxon, display_name(taxon), float(row["scc"]), float(row["p"]), direction, found_by])
    return pd.DataFrame(rows, columns=columns).sort_values("p", kind="stable").reset_index(drop=True)


def _index_of(path: Path) -> set:
    return set(pd.read_pickle(path).index) if path.exists() else set()


def _apriori_table(levels: pd.DataFrame) -> pd.DataFrame:
    p = pd.to_numeric(levels["nested-p"], errors="coerce").dropna()
    names = [_LEVELS[i - 1] if 0 < i <= len(_LEVELS) else f"Level {i}" for i in p.index]
    return pd.DataFrame({
        "level": names,
        "p": p.to_numpy(),
        "minus_log10_p": [-math.log10(max(v, 1e-300)) for v in p],
        "significant": p.to_numpy() < THRESHOLD_P,
    })


def _summary(start, hits: pd.DataFrame, leaf_only: pd.DataFrame, apriori: pd.DataFrame, kind: str,
             coding: dict, test: str) -> list[str]:
    lines = []
    if coding and set(coding.values()) != {"0", "1"}:
        lines.append(f"The two groups were coded 0 = '{coding['0']}' and 1 = '{coding['1']}'.")
    first = apriori[apriori["significant"]].head(1)
    if not first.empty:
        lines.append(
            f"The a-priori test found the label linked to the microbiome "
            f"(nested test p = {first['p'].iloc[0]:.3g} at the {first['level'].iloc[0].lower()} level), "
            "so miMic followed significant paths down the taxonomy tree."
        )
    else:
        lines.append("The a-priori test found no link at any taxonomic level, so only the leaf-level test was applied.")
    if hits.empty:
        lines.append(f"miMic's tree test found no significant taxa (p < {THRESHOLD_P:g}).")
    else:
        counts = hits["direction"].value_counts()
        parts = ", ".join(f"{n} {d}" for d, n in counts.items())
        lines.append(f"{len(hits)} taxa are significant by miMic's tree test (p < {THRESHOLD_P:g}): {parts}.")
    if not leaf_only.empty:
        plain = {"man": "a Mann-Whitney test", "corr": "a Spearman correlation"}.get(test, "a plain test")
        lines.append(f"Testing each leaf on its own ({plain}, without the tree) found {len(leaf_only)} more "
                     f"{'taxon' if len(leaf_only) == 1 else 'taxa'} that miMic's tree test did not. They are not "
                     "miMic's result and are not counted above; they are listed separately (\"leaf test only\"), "
                     "as in the authors' own output.")
    return lines


def _taxa_figure(hits: pd.DataFrame, kind: str, coding: dict) -> Figure | None:
    if hits.empty:
        return None
    top = hits.head(TOP_TAXA)[["name", "statistic", "p", "direction", "taxon"]]
    shown = f"the {len(top)} most significant" if len(hits) > TOP_TAXA else "all"
    if kind == "binary":
        x_label = f"miMic score (positive = higher in '{coding['1']}')"
        title = "Bacteria that differ between the groups"
    else:
        x_label = "Spearman correlation with the label"
        title = "Bacteria linked to the label"
    return Figure(
        name="mimic_significant_taxa", title=title,
        caption=f"Significant taxa from miMic ({shown} of {len(hits)}), most significant at the top, "
                "coloured by direction. The full list is in the table download.",
        data=top, kind="barh", x="statistic", y="name", x_label=x_label, y_label="",
        color_by="direction", section="findings",
        hover="%{y}<br>score %{x:.3g}<extra></extra>",
    )


@contextlib.contextmanager
def _quiet():
    """miMic prints progress and warnings; keep them out of the application's output."""
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        yield
