"""LOCATE as an engine: "Link bacteria to metabolites".

LOCATE (Shtossel et al., Microbiome 2024) learns a latent representation Z of
the microbiome that predicts metabolite levels. The published package,
LOCATE-model 0.0.3, needs Python 3.7-3.10 and Lightning 1.x. The platform uses
``locate_lightning2`` (in this repository): the authors' model with only the
changes Lightning 2 requires, validated against the original in
validation/locate/ (PROTOCOL.md: V1′ bit-identical, V2 equivalent) and against
the paper's published figures on two public datasets (FRANZOSA.md, YACHIDA.md).

Inputs, as the paper prepares them:
- microbiome: the shared table with one declared variation, a z-score per
  feature (``z_scoring="col"``): MIPMLP sub-PCA at species level, log10(x + 0.1),
  then z-scored, as in the paper's Methods;
- metabolites: relative → log → z-score per metabolite (``core/metabolites.py``;
  the paper gives neither the log base nor the pseudocount, so these are reconstructed and
  recorded as unconfirmed).

As micrOS does: one ``train_test_split(test_size=0.2)``; the test samples also
serve as ``LOCATE_training``'s validation set (used for early stopping), and the
authors' default hyperparameters are used. The authors' two calls,
``LOCATE_training`` then ``LOCATE_predict``, run unchanged after every random
seed is fixed. Prediction quality is the Spearman correlation per metabolite on
the test samples (the paper's measure). The summary reports this one run
honestly and says how the paper's figures were built (best of 16 runs).
"""

from __future__ import annotations

import contextlib
import io
import logging
import random
import warnings
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from microplatform.core.contract import Dataset
from microplatform.core.errors import UserFacingError
from microplatform.core.metabolites import LOCATE_METABOLITES, MIN_PAIRED, prepare_metabolites
from microplatform.core.preprocessing import CANONICAL
from microplatform.engines.base import Engine, EngineResult
from microplatform.reports.figures import Figure

SEED = 42
TEST_SIZE = 0.2  # micrOS's default and the paper's 80/20
TOP = 20  # metabolites shown in the figure


def fit_and_predict(X_train: pd.DataFrame, Y_train: pd.DataFrame, X_val: pd.DataFrame, Y_val: pd.DataFrame,
                    seed: int = SEED) -> dict:
    """The authors' two calls, after fixing every random seed. Runs in the current folder.

    ``LOCATE_predict`` returns predictions without sample IDs; they are re-attached in X's order.
    """
    import pytorch_lightning as pl
    import torch
    from locate_lightning2 import LOCATE_predict, LOCATE_training

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    pl.seed_everything(seed)
    model = LOCATE_training(X_train, Y_train, X_val, Y_val)
    mode = "training" if model.training else "evaluation"
    Z_val, pred_val = LOCATE_predict(model, X_val, Y_val.columns)
    Z_train, pred_train = LOCATE_predict(model, X_train, Y_train.columns)
    pred_val.index, pred_train.index = X_val.index, X_train.index
    return {"Z_val": Z_val, "Z_train": Z_train, "pred_val": pred_val, "pred_train": pred_train,
            "epochs": int(model.current_epoch), "mode_at_prediction": mode}


class LocateEngine(Engine):
    name = "LOCATE"
    goal = "metabolites"
    requires = frozenset({"counts", "metabolites"})
    preprocessing = CANONICAL.with_changes(z_scoring="col")  # the paper z-scores each taxon after the log

    def run(self, data: Dataset, work_dir: Path, choices: dict[str, str] | None = None) -> EngineResult:
        from sklearn.model_selection import train_test_split

        import locate_lightning2

        if data.metabolites is None:
            raise UserFacingError("LOCATE needs a metabolite table.",
                                  "Add a table with one row per sample and one column per metabolite.")
        paired = [s for s in data.features.index if s in set(data.metabolites.index)]  # counts-table order
        if len(paired) < MIN_PAIRED:
            raise UserFacingError(f"Only {len(paired)} samples have both microbiome and metabolite data; "
                                  f"LOCATE needs at least {MIN_PAIRED}.",
                                  "Check that both tables use the same sample IDs.")
        X = data.features.loc[paired]
        Y, prepared = prepare_metabolites(data.metabolites.loc[paired], LOCATE_METABOLITES)
        train, test = train_test_split(paired, test_size=TEST_SIZE, random_state=SEED)

        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.chdir(work_dir), _quiet():  # training writes lightning_logs/ into the current folder
            out = fit_and_predict(X.loc[train], Y.loc[train], X.loc[test], Y.loc[test])

        scores = metabolite_scores(Y.loc[test], out["pred_val"])
        return EngineResult(
            summary=_summary(len(train), len(test), scores, prepared),
            notes=_notes(prepared),
            figures=[f for f in (_scores_figure(scores),) if f],
            tables={
                "metabolite_scores": scores,
                "predicted_metabolites_test": out["pred_val"].rename_axis("sample").reset_index(),
                "latent_representation": _latent(out["Z_train"], out["Z_val"]),
            },
            highlight=("metabolite_scores", "Best-predicted metabolites"),
            record={
                "tool": "LOCATE", "package": "locate_lightning2", "version": locate_lightning2.__version__,
                "based_on": locate_lightning2.BASED_ON,
                "environment": {"torch": version("torch"), "pytorch-lightning": version("pytorch-lightning")},
                "hyperparameters": "LOCATE_training's defaults",
                "seed": SEED, "test_size": TEST_SIZE, "split_order": "counts table",
                "validation": "the test samples (as micrOS); LOCATE uses them for early stopping",
                "epochs": out["epochs"],
                "prediction_mode": f"as published: LOCATE_predict right after training (model in "
                                   f"{out['mode_at_prediction']} mode)",
                "metabolites": prepared, "paired_samples": len(paired),
                "score": "Spearman correlation per metabolite, measured vs predicted, on the test samples",
            },
        )


def metabolite_scores(measured: pd.DataFrame, predicted: pd.DataFrame) -> pd.DataFrame:
    """Spearman correlation between measured and predicted levels, per metabolite (the paper's measure)."""
    from scipy.stats import spearmanr

    predicted = predicted.loc[measured.index]
    rows = []
    for name in measured.columns:
        rho, p = spearmanr(measured[name], predicted[name])
        rows.append({"metabolite": str(name), "spearman": float(rho), "p": float(p)})
    return pd.DataFrame(rows).sort_values("spearman", ascending=False, na_position="last").reset_index(drop=True)


def _latent(z_train: pd.DataFrame, z_val: pd.DataFrame) -> pd.DataFrame:
    z = pd.concat([z_val.assign(set="test"), z_train.assign(set="train")])
    z.columns = [c if c == "set" else f"z{int(c) + 1}" for c in z.columns]
    return z.rename_axis("sample").reset_index()[["sample", "set", *[c for c in z.columns if c != "set"]]]


def _summary(n_train: int, n_test: int, scores: pd.DataFrame, prepared: dict) -> list[str]:
    rho = scores["spearman"].dropna()
    lines = [
        f"LOCATE learned from {n_train:,} samples with both microbiome and metabolite data and was tested on "
        f"{n_test:,} it had not seen ({round((1 - TEST_SIZE) * 100)}% for training, "
        f"{round(TEST_SIZE * 100)}% for testing, seed {SEED}).",
        f"Across {len(rho):,} metabolites, the median Spearman correlation between measured and predicted "
        f"levels on the test samples is {rho.median():.2f}; {int((rho > 0).sum()):,} are predicted better "
        "than chance would suggest (correlation above 0)." if len(rho) else
        "No metabolite varied enough in the test samples to score the predictions.",
    ]
    if prepared["left_out_constant"]:
        lines.append(f"{prepared['left_out_constant']:,} metabolites were the same in every sample and were left out.")
    return lines


def _notes(prepared: dict) -> list[str]:
    """How to read the scores; honest single-run reporting comes first (validation/locate/PROTOCOL.md)."""
    notes = [
        "These scores come from one training run, which is what to expect in practice. The LOCATE paper's "
        "per-dataset figures show, for each metabolite, the best of 16 runs; on two of the paper's public "
        "datasets (FRANZOSA and YACHIDA) that raised the median correlation by about 0.13, so the published "
        "figures look better than a single run.",
        "As in micrOS, the test samples also decided when training stopped, so these scores may be "
        "slightly optimistic.",
    ]
    settings = prepared["settings"]
    if not settings["confirmed"]:
        notes.append("The paper does not give two details of its metabolite preparation (the log base and the "
                     "value added before the log for zeros); the platform uses a reconstruction (log base "
                     f"{settings['log_base']:g}, {settings['pseudocount']:g} added), recorded with these results.")
    return notes


def _scores_figure(scores: pd.DataFrame) -> Figure | None:
    top = scores.dropna(subset=["spearman"]).head(TOP)
    if top.empty:
        return None
    return Figure(
        name="locate_metabolite_scores", title="Best-predicted metabolites",
        caption=f"Spearman correlation between measured and predicted levels on the test samples, for the "
                f"{len(top)} best-predicted metabolites. 0 means no relation, 1 a perfect ranking. "
                "Every metabolite is in the table download.",
        data=top.iloc[::-1].reset_index(drop=True), kind="barh", x="spearman", y="metabolite",
        x_label="Spearman correlation (test samples)", y_label="", section="findings",
        hover="%{y}: %{x:.2f}<extra></extra>",
    )


@contextlib.contextmanager
def _quiet():
    """Training prints progress bars and model summaries; keep them out of the application's output."""
    loggers = [logging.getLogger(n) for n in ("lightning.pytorch", "pytorch_lightning", "lightning")]
    levels = [lg.level for lg in loggers]
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        for lg in loggers:
            lg.setLevel(logging.ERROR)
        try:
            yield
        finally:
            for lg, level in zip(loggers, levels):
                lg.setLevel(level)
