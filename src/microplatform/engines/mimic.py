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

The headline figure is miMic's own cladogram, drawn by the authors' code (the
final call of their plot mode; see ``_cladogram``). The significant-taxa bars and
the a-priori test are drawn through ``reports.figures``. The authors' full bundle
(their tables and every diagnostic plot) is made by ``engines/mimic_authors.py``,
outside the website.
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

        hits = _significant_taxa(work_dir, start, data.label_kind, coding)
        apriori = _apriori_table(levels)
        tree = _cladogram(work_dir, images, samba_output, tag, start, test, hits, data.label_kind, coding)
        return EngineResult(
            summary=_summary(start, hits, apriori, data.label_kind, coding),
            rendered=[tree] if tree else [],
            figures=[f for f in (_taxa_figure(hits, data.label_kind, coding), _apriori_figure(apriori)) if f],
            tables={"significant_taxa": hits, "apriori_test": apriori},
            highlight=("significant_taxa", "Most significant taxa") if not hits.empty else None,
            record={
                "tool": "miMic", "package": "mimic-da", "version": version("mimic-da"),
                "test": {"man": "Mann-Whitney (binary)", "corr": "Spearman (continuous)"}[test],
                "eval": test, "threshold_p": THRESHOLD_P, "sister_correction": SISTER_CORRECTION,
                "correct_first": CORRECT_FIRST, "samples": len(tag), "label_coding": coding,
                "post_hoc_start": str(start), "significant_taxa": len(hits),
                "cladogram": (CLADOGRAM_CALL if tree else "not drawn (no significant taxa)"),
            },
        )


# miMic's cladogram is drawn by the authors' own code: the last call of ``apply_mimic(mode="plot")``,
# which goes on to ``creare_tree_view``. The rest of plot mode (16 more test passes on real and shuffled
# labels) only feeds its other diagnostic plots, so it is skipped; the tree is the same (tests/
# test_reproduction.py compares it byte for byte with the authors' whole plot mode).
CLADOGRAM_CALL = ("mimic_da.miMic_test.calculate_all_imgs_tag_corr(mode='plot', colorful=True) -> "
                  "creare_tree_view (ete3), unchanged, with engines/mimic_authors.ADJUSTMENTS; matplotlib "
                  "draws without a screen (Agg)")


def _cladogram(work_dir: Path, images: Path, samba_output, tag: pd.DataFrame, start, test: str,
               hits: pd.DataFrame, kind: str, coding: dict) -> RenderedFigure | None:
    """miMic's own correlation cladogram (``plots/correlations_tree.svg``), or None if nothing is significant."""
    if start == "nosignificant" or hits.empty:
        return None
    import mimic_da.miMic_test as mt

    from microplatform.engines.mimic_authors import COLORFUL, THRESHOLD_EDGE, compatible  # (imports this module)

    plots = work_dir / "plots"
    shutil.rmtree(plots, ignore_errors=True)
    import matplotlib.pyplot as plt

    backend = plt.get_backend()
    plt.switch_backend("Agg")  # the authors' plot mode opens windows (plt.show); here it only saves files
    try:
        with compatible(), contextlib.chdir(work_dir), _quiet():
            mt.calculate_all_imgs_tag_corr(
                samba_output, str(images), tag, start, eval=test, sis=SISTER_CORRECTION,
                correct_first=CORRECT_FIRST, mode="plot", threshold_p=THRESHOLD_P,
                THRESHOLD_edge=THRESHOLD_EDGE, shuffle=False, colorful=COLORFUL,
            )
    finally:
        plt.close("all")
        with contextlib.suppress(Exception):
            plt.switch_backend(backend)
    svg, png = plots / "correlations_tree.svg", plots / "correlations_tree.png"
    if not svg.exists() or not png.exists():
        log.warning("miMic did not draw its cladogram in %s", plots)
        return None
    if kind == "binary":
        colours = f"blue: higher in '{coding['1']}', red: higher in '{coding['0']}'"
    else:
        colours = "blue: increases with the label, red: decreases with it"
    return RenderedFigure(
        name="mimic_cladogram",
        title="miMic's cladogram: where on the taxonomy tree the groups differ",
        caption=("Drawn by miMic itself (mimic-da's own tree drawing, unchanged). The taxonomy tree of the "
                 f"significant taxa; each node's size grows with -log10(p), and its colour gives the direction ("
                 f"{colours}). Shape: sphere = found by both miMic's tree test and the leaf test, circle = the "
                 "tree test only, square = the leaf test only. The background shows each taxon's family. "
                 "Data (CSV): the significant taxa, as in the table below."),
        svg=svg, png=png, data=hits,
    )


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
            found_by = "leaf test only"
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


def _summary(start, hits: pd.DataFrame, apriori: pd.DataFrame, kind: str, coding: dict) -> list[str]:
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
        lines.append(f"No taxa differ significantly (p < {THRESHOLD_P:g}).")
    else:
        counts = hits["direction"].value_counts()
        parts = ", ".join(f"{n} {d}" for d, n in counts.items())
        lines.append(f"{len(hits)} taxa are significant (p < {THRESHOLD_P:g}): {parts}.")
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


def _apriori_figure(apriori: pd.DataFrame) -> Figure | None:
    if apriori.empty:
        return None
    return Figure(
        name="mimic_apriori_test", title="Is the label linked to the microbiome?",
        caption="miMic's first step tests each taxonomic level as a whole (nested ANOVA, or GLM for "
                "continuous labels). Bars above the line are significant; the post-hoc tests start only then.",
        data=apriori, kind="column", x="level", y="minus_log10_p",
        x_label="Taxonomic level", y_label="−log10(p)", hline=(-math.log10(THRESHOLD_P), f"p = {THRESHOLD_P:g}"),
        section="findings", hover="%{x}: −log10(p) = %{y:.2f}<extra></extra>",
    )


@contextlib.contextmanager
def _quiet():
    """miMic prints progress and warnings; keep them out of the application's output."""
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        yield
