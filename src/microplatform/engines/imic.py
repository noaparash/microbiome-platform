"""iMic as an engine: "Predict the outcome from the microbiome".

The lab's clean code base, micrOS (github.com/louzounlab/micrOS), runs iMic by
calling ``MIPMLP.apply_iMic`` from the MIPMLP package; it has no iMic code of its
own. So the authors' code used here is MIPMLP's, unchanged:

- images: ``MIPMLP.micro2matrix(features, folder, mipmlp=False)`` from the shared
  table (iMic's own re-processing off; micrOS's GIMIC-package ``micro2matrix`` makes
  identical images);
- the network, training and prediction: ``MIPMLP.CNN`` via the authors'
  ``run_iMic``, with ``load_data_2d_train_test`` and ``apply_iMic``'s own default
  hyperparameters (read from ``apply_iMic`` itself, never re-typed).

``apply_iMic`` is 6 lines of glue around those pieces. It returns only rounded
0/1 predictions and no sample IDs, so the adapter repeats that glue with a CNN
subclass that only *records* the probabilities the authors' ``predict`` computes.
tests/test_reproduction.py proves the result equals calling ``apply_iMic``.

Faithful to the published code, recorded with every result:
- the split is ``train_test_split(..., test_size=0.2)`` seeded via
  ``pytorch_lightning.seed_everything(42)``; it follows row order (the counts table's);
- predictions are made with the network still in training mode (dropout on),
  as in the published code;
- the published code would crash on a GPU (``Trainer(gpus=1)``, removed in
  Lightning 2), so it is steered onto its CPU path.
"""

from __future__ import annotations

import contextlib
import copy
import inspect
import io
import logging
import os
import warnings
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from microplatform.core.contract import Dataset
from microplatform.core.errors import UserFacingError
from microplatform.engines.base import Engine, EngineResult
from microplatform.engines.labels import native_tag
from microplatform.reports.figures import Figure

SEED = 42
TEST_SIZE = 0.2  # apply_iMic's default
IMAGES = "imic_images"  # relative: the authors' loader first tries "../<folder>", which must not exist
ORDERED_TABLE = "0_fixed_ordered_n_all_otu_sub_pca_log_tax_7.csv"  # the file name apply_iMic reads
SMALL_TEST_SET = 30


def load_imic():
    """The authors' pieces. MIPMLP loads PyTorch first, which must precede Qt on Windows."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    import MIPMLP
    from MIPMLP.example_code_run_imic import apply_iMic, load_data_2d_train_test, run_iMic

    return MIPMLP, apply_iMic, load_data_2d_train_test, run_iMic


def default_params() -> dict:
    """apply_iMic's own default hyperparameters (a fresh copy: it changes 'input_dim' in place)."""
    _, apply_iMic, _, _ = load_imic()
    return copy.deepcopy(inspect.signature(apply_iMic).parameters["params"].default)


def recording_cnn(cnn_class):
    """A subclass of the authors' CNN that records each predict() call's probabilities; nothing else differs.

    Always wraps the authors' original class, even if given an already-recording one,
    so probabilities are never recorded twice.
    """
    while getattr(cnn_class, "_records_proba", False):
        cnn_class = cnn_class.__bases__[0]

    class RecordingCNN(cnn_class):
        _records_proba = True
        instances: list = []

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.recorded_proba = []
            type(self).instances.append(self)

        def predict(self, loader):
            predictions = super().predict(loader)
            self.recorded_proba.append(list(self.proba))
            return predictions

    RecordingCNN.instances = []
    return RecordingCNN


class ImicEngine(Engine):
    name = "iMic"
    goal = "predict"
    requires = frozenset({"counts", "labels"})

    def run(self, data: Dataset, work_dir: Path, choices: dict[str, str] | None = None) -> EngineResult:
        if data.labels is None or data.label_kind != "binary":
            raise UserFacingError(
                "iMic can predict a two-group label only (for now).",
                "Use a labels file with exactly two groups, for example case/control.",
            )
        tag, coding = native_tag(data.labels, data.label_kind)  # labelled samples, counts-table order
        if tag[tag.columns[0]].value_counts().min() < 5:
            raise UserFacingError("Each group needs at least 5 samples to train and test iMic.",
                                  "Add samples to the smaller group.")
        features = data.features.loc[tag.index]
        params = default_params()
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

        with contextlib.chdir(work_dir), _quiet():  # the tool writes lightning_logs into the current folder
            (work_dir / IMAGES).mkdir(exist_ok=True)  # micro2matrix does not create it
            mipmlp, _, _, _ = load_imic()
            mipmlp.micro2matrix(features, IMAGES, mipmlp=False)
            with _cpu_path() as device:
                found = fit_and_predict(tag, IMAGES, params)

        test, train = found["test"], found["train"]
        predictions = _predictions(train, test, coding)
        metrics = _metrics(test)
        return EngineResult(
            summary=_summary(len(train), len(test), metrics, coding),
            figures=[f for f in (_roc_figure(test),) if f],
            tables={"predictions": predictions, "test_metrics": pd.DataFrame([metrics])},
            highlight=("predictions", "Predictions (test samples first)"),
            record={
                "tool": "iMic", "package": "MIPMLP", "version": version("MIPMLP"),
                "source": "micrOS calls MIPMLP.apply_iMic; this engine uses the same MIPMLP code",
                "images": "MIPMLP.micro2matrix(features, folder, mipmlp=False)",
                "seed": SEED, "test_size": TEST_SIZE, "split_order": "counts table",
                "hyperparameters": {k: v for k, v in params.items()}, "device": device,
                "prediction_mode": "as published: network left in training mode (dropout on) when predicting",
                "label_coding": coding, "samples": len(tag),
            },
        )


def fit_and_predict(tag: pd.DataFrame, folder: str, params: dict) -> dict:
    """apply_iMic's glue (MIPMLP 1.2.19, example_code_run_imic.py), keeping sample IDs and probabilities.

    Same calls in the same order, so the random numbers are drawn exactly as in apply_iMic.
    """
    import pytorch_lightning as pl
    import torch
    from sklearn.model_selection import train_test_split
    from torch.utils import data as data_modul

    mipmlp, _, load_data_2d_train_test, run_iMic = load_imic()
    pl.seed_everything(SEED, workers=True)

    otu = pd.read_csv(f"{folder}/{ORDERED_TABLE}", index_col=0)
    o_train, o_test, t_train, t_test = train_test_split(otu, tag, test_size=TEST_SIZE)
    X_train, X_test, y_train, y_test = load_data_2d_train_test(folder, t_train, t_test, params)
    train_dataset = data_modul.TensorDataset(torch.tensor(X_train), torch.tensor(y_train))
    test_dataset = data_modul.TensorDataset(torch.tensor(X_test), torch.tensor(y_test))

    model_class = recording_cnn(mipmlp.CNN)
    pred_train, pred_test = run_iMic(train_dataset, test_dataset, model_class, params)
    proba_train, proba_test = model_class.instances[-1].recorded_proba  # run_iMic predicts train, then test

    def part(t, y, pred, proba):
        return pd.DataFrame({"sample": t.index.astype(str), "label": np.asarray(y).astype(int),
                             "probability": proba, "predicted": np.asarray(pred).astype(int)})

    return {"train": part(t_train, y_train, pred_train, proba_train),
            "test": part(t_test, y_test, pred_test, proba_test)}


@contextlib.contextmanager
def _cpu_path():
    """The published code's GPU branch uses Trainer(gpus=1), removed in Lightning 2: use its CPU branch."""
    import torch

    if not torch.cuda.is_available():
        yield "cpu"
        return
    original = torch.cuda.is_available
    torch.cuda.is_available = lambda: False
    try:
        yield "cpu (a GPU was present; the published GPU branch fails on Lightning 2)"
    finally:
        torch.cuda.is_available = original


def _predictions(train: pd.DataFrame, test: pd.DataFrame, coding: dict) -> pd.DataFrame:
    rows = pd.concat([test.assign(set="test"), train.assign(set="train")], ignore_index=True)
    return pd.DataFrame({
        "sample": rows["sample"], "set": rows["set"],
        "true_group": rows["label"].astype(str).map(coding),
        "probability_of_" + _slug(coding["1"]): rows["probability"],
        "predicted_group": rows["predicted"].astype(str).map(coding),
    })


def _metrics(test: pd.DataFrame) -> dict:
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score

    y, p, pred = test["label"], test["probability"], test["predicted"]
    both = y.nunique() == 2
    return {
        "test_samples": len(test),
        "auc": float(roc_auc_score(y, p)) if both else float("nan"),
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)) if both else float("nan"),
    }


def _summary(n_train: int, n_test: int, metrics: dict, coding: dict) -> list[str]:
    lines = []
    if set(coding.values()) != {"0", "1"}:
        lines.append(f"The two groups were coded 0 = '{coding['0']}' and 1 = '{coding['1']}'.")
    lines.append(f"iMic was trained on {n_train} samples and tested on {n_test} it had not seen "
                 f"(a {round((1 - TEST_SIZE) * 100)}/{round(TEST_SIZE * 100)} split, seed {SEED}).")
    if np.isnan(metrics["auc"]):
        lines.append("The test samples all belong to one group, so an AUC cannot be computed.")
    else:
        lines.append(f"Test AUC = {metrics['auc']:.3f} (0.5 is chance, 1 is perfect), from the predicted "
                     f"probabilities; accuracy {metrics['accuracy']:.0%}, balanced accuracy "
                     f"{metrics['balanced_accuracy']:.0%}.")
    if n_test < SMALL_TEST_SET:
        lines.append(f"Only {n_test} test samples: treat this AUC as a rough estimate.")
    lines.append("This is one random split; another split would give a somewhat different number.")
    return lines


def _roc_figure(test: pd.DataFrame) -> Figure | None:
    from sklearn.metrics import auc, roc_curve

    if test["label"].nunique() < 2:
        return None
    fpr, tpr, _ = roc_curve(test["label"], test["probability"])
    data = pd.DataFrame({"false_positive_rate": fpr, "true_positive_rate": tpr})
    return Figure(
        name="imic_roc", title=f"ROC curve on the test samples (AUC {auc(fpr, tpr):.3f})",
        caption="How well iMic's probabilities separate the two groups on samples it had not seen. "
                "The dashed line is chance; the closer the curve to the top-left, the better.",
        data=data, kind="line", x="false_positive_rate", y="true_positive_rate",
        x_label="False positive rate", y_label="True positive rate", diagonal=True, section="findings",
        hover="FPR %{x:.2f}, TPR %{y:.2f}<extra></extra>",
    )


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(text)).strip("_") or "group_1"


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
