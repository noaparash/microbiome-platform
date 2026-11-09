"""miMic's full standard output bundle, made by the authors' own code from end to end.

The website's engine (``engines/mimic.py``) runs only miMic's test step and draws its own
figures. This module runs the whole published pipeline, exactly as the authors' README does:

1. ``apply_mimic(folder, tag, mode="test", processed=..., apply_samba=True, save=True)``:
   ``samba.micro2matrix`` builds the iMic images, then the a-priori nested ANOVA (or GLM) and
   the post-hoc tests along the taxonomy tree. With ``save=True`` the authors write their own
   result tables into ``folder``: ``df_corrs.csv`` (every significant taxon), ``miMic&Utest.csv``
   (found by both the tree path and the leaf test), ``u_test_without_mimic.csv`` and
   ``just_mimic.csv``.
2. ``apply_mimic(folder, tag, mode="plot", tax=<start level>, samba_output=...)``: their
   diagnostic plots (``tax_vs_rp_sp_anova_p.png``, ``rsp_vs_beta.png``, ``hist.png``,
   ``corrs_within_family.png``, ``interaction.png``) and their cladogram
   (``correlations_tree.svg``), written to ``plots/``. The SP counts come from re-running the
   tests on shuffled labels (``np.random.shuffle``), so they depend on the random seed.

Nothing statistical is reimplemented and the authors' package is never modified. mimic-da
1.0.1 was written for older libraries, so ``compatible()`` makes four small, scoped
adjustments for the libraries installed here (Python 3.13), each restoring the behaviour the
authors' code was written against, plus some for running without a screen and for presentation
(file formats, a stand-in font, legible tree labels). They are listed in
``ADJUSTMENTS`` and recorded with every run.

Run it: ``python -m microplatform.engines.mimic_authors processed.csv tag.csv out_dir``.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import random
import shutil
import sys
import types
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from microplatform.core.contract import LABEL_COLUMN
from microplatform.core.errors import UserFacingError
from microplatform.core.profiler import _label_kind
from microplatform.engines.labels import native_tag
from microplatform.engines.mimic import EVALS, SISTER_CORRECTION, THRESHOLD_P, CORRECT_FIRST, load_mimic

SEED = 42  # the fixed seed of the main result
EXTRA_SEEDS = (0, 1, 2, 3)  # more runs, so that the seed's effect is visible
THRESHOLD_EDGE = 0.5  # the authors' default edge threshold of the interaction plot
COLORFUL = True  # the authors' default: colour the tree and the family plot by family
IMAGES = "images"  # the folder handed to miMic (iMic images and the authors' tables)
PLOTS = "plots"  # where miMic's plot mode always writes (relative to the current folder)
TABLES = ("df_corrs.csv", "miMic&Utest.csv", "u_test_without_mimic.csv", "just_mimic.csv")
TREE_FORMATS = ("svg", "png", "pdf")
TREE_PNG_MM, TREE_PNG_DPI = 180, 300  # the PNG's size: as the lab's reference tree (2,125 px square)
TREE_LABEL_SCALE = 4  # miMic's leaf labels (100 pt) are ~4 px tall at that size; 400 pt reads clearly
TREE_ARC_SPAN = 360  # ete3's default 359° leaves a cut-out wedge where the circle should close
RP_SP_FIGURE = "tax_vs_rp_sp_anova_p"  # miMic's RP vs SP plot (plot_rp_sp_anova_p), in plots/
AUTHORS_FONT = "Times New Roman"  # what miMic's diagnostic plots ask for
FONT_STAND_IN = "Nimbus Roman"  # its metric-compatible clone (URW), on Linux servers without it

ADJUSTMENTS = {
    "kstest": "SciPy 1.18 raises TypeError on kstest(x, 'norm', args=(loc, scale)); miMic calls it only "
              "to print a normality check while drawing hist.png. It is run as the documented equivalent "
              "kstest(x, norm(loc, scale).cdf), which gives the same result.",
    "get_cmap": "matplotlib 3.9 removed cm.get_cmap(name); miMic uses it for the family colours. It is "
                "served by matplotlib.colormaps[name], the same colormap.",
    "index_truth": "NumPy 2.2 made `if <empty array>:` an error; miMic's cladogram drawer tests "
                   "`if index != None:` and relied on the old result (empty -> False, one element -> its "
                   "value). Inside the drawer only, that comparison gives the old result.",
    "tree_formats": "miMic renders correlations_tree.svg with ete3; the same tree and style are also "
                    "rendered by ete3 to .png (180 mm wide at 300 dpi, as the lab's reference tree) and .pdf "
                    "(inside the drawer only).",
    "tree_legibility": "Presentation only, in the cladogram drawer: the leaf labels are drawn 4x larger "
                       "(400 pt instead of miMic's 100 pt; miMic's large -log10(p) markers make the tree so "
                       "wide that 100 pt labels are ~4 px tall at 180 mm) and the circle is closed (arc "
                       "360°, ete3's default 359° leaves a wedge cut out). The tree, the taxa, the markers' "
                       "sizes, shapes and colours are miMic's.",
    "rp_sp_formats": "miMic saves its RP vs SP plot (tax_vs_rp_sp_anova_p) as .png only; the same matplotlib "
                     "figure is also saved as .svg, right after miMic saves it.",
    "font": "miMic's diagnostic plots ask for Times New Roman. Where it is not installed (the Linux server), "
            "its metric-compatible clone Nimbus Roman is used instead of matplotlib's default sans-serif. "
            "matplotlib's settings are restored after the run (miMic changes them globally).",
    "no_window": "miMic opens the tree in an interactive window (ete3 show) before saving it; without a "
                 "screen that window is skipped (the saved files are unchanged).",
    "offscreen": "Qt draws offscreen (QT_QPA_PLATFORM=offscreen), as miMic forces the Qt5Agg backend.",
}


def run_bundle(processed: pd.DataFrame, tags: pd.DataFrame, out_dir: str | Path, seed: int = SEED) -> dict:
    """Run the authors' miMic test and plot modes on ``processed`` + ``tags`` in ``out_dir``.

    ``processed`` is a MIPMLP-processed table (samples × taxa); ``tags`` has the labels in a
    ``Tag`` column (one differently named column is accepted). Returns the run's record.
    """
    tag, coding, test, processed = _prepare(processed, tags)
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / IMAGES).mkdir(parents=True)
    apply_mimic, _ = load_mimic()
    log = io.StringIO()
    with compatible() as seen, contextlib.chdir(out_dir), contextlib.redirect_stdout(log):
        random.seed(seed)
        _numpy().random.seed(seed)
        start, samba_output = apply_mimic(
            IMAGES, tag, eval=test, sis=SISTER_CORRECTION, correct_first=CORRECT_FIRST, mode="test",
            threshold_p=THRESHOLD_P, processed=processed, apply_samba=True, save=True,
        )
        if start != "nosignificant":
            apply_mimic(
                IMAGES, tag, eval=test, sis=SISTER_CORRECTION, correct_first=CORRECT_FIRST, mode="plot",
                tax=start, threshold_p=THRESHOLD_P, THRESHOLD_edge=THRESHOLD_EDGE, colorful=COLORFUL,
                samba_output=samba_output, save=False,
            )
        _close_figures()
    (out_dir / "mimic_log.txt").write_text(log.getvalue(), encoding="utf-8")
    if seen.get("rp_sp") is not None:
        seen["rp_sp"].to_csv(out_dir / "rp_sp.csv", index_label="level")
    # Everything but the iMic images (one file per sample); the authors' tables sit beside them.
    files = sorted(str(p.relative_to(out_dir)).replace("\\", "/") for p in out_dir.rglob("*")
                   if p.is_file() and (p.suffix == ".csv" or not p.is_relative_to(out_dir / IMAGES)))
    return {
        "seed": seed, "eval": test, "label_coding": coding, "samples": len(tag),
        "taxa": processed.shape[1], "post_hoc_start": str(start), "files": files,
        "sha256": {f: _sha256(out_dir / f) for f in files},
    }


def run(processed_csv: str | Path, tag_csv: str | Path, out_dir: str | Path,
        seeds: tuple[int, ...] = (SEED, *EXTRA_SEEDS)) -> dict:
    """The whole bundle: one run per seed under ``seeds/seed_<n>/``, plus the first seed once more
    (``seed_<n>_repeat``: does the same seed give the same files?). The first seed's tables and
    plots are also copied to ``out_dir`` itself. Writes and returns ``run.json``."""
    out_dir = Path(out_dir)
    processed = pd.read_csv(processed_csv, index_col=0)  # as in the authors' README
    tags = pd.read_csv(tag_csv, index_col=0)
    runs = [run_bundle(processed, tags, out_dir / "seeds" / f"seed_{s}", s) for s in seeds]
    repeat = run_bundle(processed, tags, out_dir / "seeds" / f"seed_{seeds[0]}_repeat", seeds[0])
    main = out_dir / "seeds" / f"seed_{seeds[0]}"
    for name in TABLES:
        if (main / IMAGES / name).exists():
            shutil.copy2(main / IMAGES / name, out_dir / name)
    if (out_dir / PLOTS).exists():
        shutil.rmtree(out_dir / PLOTS)
    if (main / PLOTS).exists():
        shutil.copytree(main / PLOTS, out_dir / PLOTS)
    for extra in ("rp_sp.csv", "mimic_log.txt"):
        if (main / extra).exists():
            shutil.copy2(main / extra, out_dir / extra)
    record = {
        "tool": "miMic", "package": "mimic-da", "version": version("mimic-da"),
        "samba-metric": version("samba-metric"), "MIPMLP": version("MIPMLP"),
        "python": sys.version.split()[0],
        "libraries": {n: version(n) for n in ("numpy", "pandas", "scipy", "matplotlib", "statsmodels",
                                                "ete3", "PyQt5", "networkx")},
        "inputs": {Path(p).name: _sha256(Path(p)) for p in (processed_csv, tag_csv)},
        "settings": {"eval": runs[0]["eval"], "sis": SISTER_CORRECTION, "correct_first": CORRECT_FIRST,
                     "threshold_p": THRESHOLD_P, "THRESHOLD_edge": THRESHOLD_EDGE, "colorful": COLORFUL,
                     "apply_samba": True},
        "calls": CALLS, "adjustments": ADJUSTMENTS,
        "main_seed": seeds[0], "seeds": list(seeds), "runs": runs, "repeat_of_main_seed": repeat,
        # Byte-for-byte comparisons. PDFs are left out: they embed their creation time.
        "same_in_every_seed": _compared(runs, same=True),
        "differs_between_seeds": _compared(runs, same=False),
        "differs_on_repeat_of_main_seed": _compared([runs[0], repeat], same=False),
    }
    (out_dir / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


# Which of the authors' functions make each output (recorded with every run).
CALLS = {
    "iMic images (images/*.npy, bact_names.npy)": "samba.micro2matrix, called by apply_mimic(mode='test', "
                                                  "apply_samba=True, save=True)",
    "a-priori test": "mimic_da.miMic_test.apply_nested_anova (inside apply_mimic)",
    "df_corrs.csv, miMic&Utest.csv, u_test_without_mimic.csv, just_mimic.csv":
        "mimic_da.apply_mimic(mode='test', save=True) -> calculate_all_imgs_tag_corr",
    "plots/tax_vs_rp_sp_anova_p.png": "apply_mimic(mode='plot') -> plot_rp_sp_anova_p",
    "plots/rsp_vs_beta.png": "apply_mimic(mode='plot') -> calculate_rsp",
    "plots/hist.png, plots/corrs_within_family.png": "apply_mimic(mode='plot') -> calculate_all_imgs_tag_corr"
                                                     "(mode='plot')",
    "plots/interaction.png": "calculate_all_imgs_tag_corr(mode='plot') -> build_interactions",
    "plots/correlations_tree.svg/.png/.pdf": "calculate_all_imgs_tag_corr(mode='plot') -> creare_tree_view "
                                             "(ete3 TreeNode.render)",
    "rp_sp.csv": "the RP/SP table apply_mimic(mode='plot') passes to calculate_rsp",
}


@contextlib.contextmanager
def compatible():
    """The ``ADJUSTMENTS``, applied to miMic's module only for the duration of a run."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    load_mimic()
    import ete3
    import matplotlib
    import matplotlib.pyplot  # noqa: F401  (rp_sp_plot saves the current figure)
    import mimic_da.miMic_test as mt
    from scipy import stats

    seen: dict = {}
    saved = {"stats": mt.stats, "cm": mt.cm, "creare_tree_view": mt.creare_tree_view,
             "calculate_rsp": mt.calculate_rsp, "plot_rp_sp_anova_p": mt.plot_rp_sp_anova_p, "mpl": mt.mpl}
    show, render, index_ne = ete3.TreeNode.show, ete3.TreeNode.render, pd.Index.__ne__
    text_face = mt.TextFace

    class Stats(types.ModuleType):
        def __getattr__(self, name):
            return getattr(stats, name)

        @staticmethod
        def kstest(rvs, cdf, args=(), **kwargs):
            if isinstance(cdf, str) and args:
                return stats.kstest(rvs, getattr(stats, cdf)(*args).cdf, **kwargs)
            return stats.kstest(rvs, cdf, args=args, **kwargs)

    class Colormaps(types.ModuleType):
        def __getattr__(self, name):
            return getattr(saved["cm"], name)

        @staticmethod
        def get_cmap(name=None, lut=None):
            cmap = matplotlib.colormaps[name]
            return cmap.resampled(lut) if lut is not None else cmap

    from matplotlib import font_manager

    installed = {f.name for f in font_manager.fontManager.ttflist}

    class Matplotlib(types.ModuleType):
        def __getattr__(self, name):
            return getattr(saved["mpl"], name)

        @staticmethod
        def rc(group, **kwargs):
            if (group == "font" and kwargs.get("family") == AUTHORS_FONT and AUTHORS_FONT not in installed
                    and FONT_STAND_IN in installed):
                kwargs["family"] = FONT_STAND_IN
            return saved["mpl"].rc(group, **kwargs)

    def rp_sp_plot(df, mixed, save):
        seen["rp_sp_plotted"] = (df.copy(), mixed)
        out = saved["plot_rp_sp_anova_p"](df, mixed, save)
        # The figure miMic just saved as .png; no date and fixed element ids, so the same run gives the same file.
        with matplotlib.rc_context({"svg.hashsalt": RP_SP_FIGURE}):
            matplotlib.pyplot.gcf().savefig(f"{save}/{RP_SP_FIGURE}.svg", metadata={"Date": None})
        return out

    def old_truth(self, other):
        result = index_ne(self, other)
        if other is None:
            if result.size > 1:
                raise ValueError("The truth value of an array with more than one element is ambiguous.")
            return bool(result.size and result[0])
        return result

    def render_formats(self, file_name, *args, tree_style=None, **kwargs):
        if tree_style is not None:
            tree_style = deepcopy(tree_style)
            tree_style.arc_span = TREE_ARC_SPAN
        out = render(self, file_name, *args, tree_style=deepcopy(tree_style), **kwargs)
        stem, _, ext = str(file_name).rpartition(".")
        for other in TREE_FORMATS:
            if other == ext:
                continue
            # The PNG at a printable size: without a width, ete3 uses the SVG's own units as pixels
            # (73,630 px square on a 64-taxon tree). 180 mm at 300 dpi = the reference's 2,125 px.
            size = dict(w=TREE_PNG_MM, units="mm", dpi=TREE_PNG_DPI) if other == "png" else {}
            render(self, f"{stem}.{other}", *args, tree_style=deepcopy(tree_style), **{**kwargs, **size})
        return out

    def legible_text(text, fsize=10, **kwargs):
        return text_face(text, fsize=fsize * TREE_LABEL_SCALE, **kwargs)

    def tree_view(*args, **kwargs):
        pd.Index.__ne__, ete3.TreeNode.render, mt.TextFace = old_truth, render_formats, legible_text
        try:
            return saved["creare_tree_view"](*args, **kwargs)
        finally:
            pd.Index.__ne__, ete3.TreeNode.render, mt.TextFace = index_ne, render, text_face

    def rsp(df, save):
        seen["rp_sp"] = df.copy()
        return saved["calculate_rsp"](df, save)

    mt.stats, mt.cm, mt.mpl = Stats("stats"), Colormaps("cm"), Matplotlib("matplotlib")
    mt.creare_tree_view, mt.calculate_rsp, mt.plot_rp_sp_anova_p = tree_view, rsp, rp_sp_plot
    ete3.TreeNode.show = lambda self, *a, **k: None
    try:
        with matplotlib.rc_context():  # miMic sets fonts globally (mpl.rc); restore them afterwards
            yield seen
    finally:
        for name, value in saved.items():
            setattr(mt, name, value)
        ete3.TreeNode.show, ete3.TreeNode.render, pd.Index.__ne__ = show, render, index_ne


def _prepare(processed: pd.DataFrame, tags: pd.DataFrame) -> tuple[pd.DataFrame, dict, str, pd.DataFrame]:
    """Labels as miMic needs them, for the samples that have both (in the table's order), the test
    for the label type, and the table for those samples."""
    if LABEL_COLUMN not in tags.columns:
        if tags.shape[1] != 1:
            raise UserFacingError(f"The labels table needs a column named '{LABEL_COLUMN}'.",
                                  f"Name the label column '{LABEL_COLUMN}'.")
        tags = tags.rename(columns={tags.columns[0]: LABEL_COLUMN})
    processed, tags = processed.copy(), tags.copy()
    processed.index, tags.index = processed.index.astype(str), tags.index.astype(str)
    for name, table in (("abundance table", processed), ("labels", tags)):
        if table.index.duplicated().any():
            raise UserFacingError(f"The {name} has repeated sample IDs.", "Give every sample one row.")
    numbers = processed.apply(pd.to_numeric, errors="coerce")
    if numbers.isna().any().any() or not numbers.abs().lt(float("inf")).all().all():
        raise UserFacingError("The abundance table must hold numbers only (no gaps or infinities).",
                              "Use MIPMLP's processed output as it is.")
    labels = tags[LABEL_COLUMN].dropna()
    labels = labels[labels.index.isin(processed.index)]
    labels = labels.loc[[i for i in processed.index if i in labels.index]]
    kind = _label_kind(labels)
    if kind not in EVALS:
        raise UserFacingError("miMic's test for three or more groups is broken in mimic-da 1.0.1.",
                              "Use two groups or a continuous label.")
    tag, coding = native_tag(labels.rename(LABEL_COLUMN), kind)
    return tag, coding, EVALS[kind], numbers.loc[tag.index]


def _compared(runs: list[dict], same: bool) -> list[str]:
    names = sorted(set().union(*(r["sha256"] for r in runs)))
    return [f for f in names if not f.endswith(".pdf")
            and (len({r["sha256"].get(f) for r in runs}) == 1) == same]


def _numpy():
    import numpy

    return numpy


def _close_figures() -> None:
    import matplotlib.pyplot as plt

    plt.close("all")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("processed", help="MIPMLP-processed table (CSV, first column = sample IDs)")
    parser.add_argument("tag", help="labels (CSV, first column = sample IDs, a 'Tag' column)")
    parser.add_argument("out_dir")
    parser.add_argument("--seeds", type=int, nargs="+", default=[SEED, *EXTRA_SEEDS],
                        help="the first is the main result")
    args = parser.parse_args(argv)
    record = run(args.processed, args.tag, args.out_dir, tuple(args.seeds))
    print(json.dumps({k: record[k] for k in ("version", "seeds", "same_in_every_seed",
                                             "differs_between_seeds")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
