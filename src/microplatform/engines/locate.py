"""LOCATE as an engine: "Link bacteria to metabolites" (not enabled yet).

LOCATE (Shtossel et al., Microbiome 2024) learns a latent representation Z of
the microbiome that predicts metabolite levels. The published package,
LOCATE-model 0.0.3, pins torch 1.13, pytorch-lightning 1.8, numpy 1.21 and
pandas 1.3. Those install only on Python 3.7-3.10, and the model uses
Lightning 1.x's two-optimizer training API, which Lightning 2 removed, so it
cannot run in the platform's Python 3.13 environment (verified: Lightning 2.6
raises "Training with multiple optimizers is only supported with manual
optimization").

So the authors' code runs unchanged in its own environment, as a separate
process: this engine writes the inputs as CSV into the run's work folder, runs
``locate_runner.py`` with the interpreter named in ``MICROPLATFORM_LOCATE_PYTHON``,
and reads the outputs back. The other tools never share that environment. If a
Lightning-2-compatible LOCATE becomes available, point the setting at the main
interpreter; nothing else changes.

Inputs, as the paper prepares them:
- microbiome: the shared table with one declared variation, a z-score per
  feature (``z_scoring="col"``): MIPMLP sub-PCA at species level, log10(x + 0.1),
  then z-scored, as in the paper's Methods;
- metabolites: relative → log → z-score per metabolite (``core/metabolites.py``;
  the log base and pseudocount are still to be confirmed by the authors).

As micrOS does: one ``train_test_split(test_size=0.2)``; the test samples also
serve as ``LOCATE_training``'s validation set (used for early stopping), and the
authors' default hyperparameters are used. Prediction quality is the Spearman
correlation per metabolite on the test samples (the paper's measure).

Not registered in ``ENGINES`` until the environment is installed and the
reproduction test passes on a real paired dataset (see docs/tool-inputs.he.md).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from microplatform.core.contract import Dataset
from microplatform.core.errors import UserFacingError
from microplatform.core.metabolites import LOCATE_METABOLITES, MIN_PAIRED, prepare_metabolites
from microplatform.core.preprocessing import CANONICAL
from microplatform.engines.base import Engine, EngineResult
from microplatform.reports.figures import Figure

PYTHON_SETTING = "MICROPLATFORM_LOCATE_PYTHON"
RUNNER = Path(__file__).with_name("locate_runner.py")
SEED = 42
TEST_SIZE = 0.2  # micrOS's default and the paper's 80/20
TIMEOUT_SECONDS = 6 * 60 * 60
TOP = 20  # metabolites shown in the figure
OUTPUTS = ("Z_train", "Z_val", "pred_train", "pred_val")


class LocateUnavailable(UserFacingError):
    """LOCATE's own environment is not set up on this computer."""


@dataclass(frozen=True)
class LocateBackend:
    """Runs locate_runner.py with LOCATE's own interpreter, in a clean environment."""

    python: str
    extra_paths: tuple[str, ...] = ()  # put on that interpreter's import path (used by the tests)
    timeout: float = TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> LocateBackend:
        python = os.environ.get(PYTHON_SETTING, "").strip()
        if not python or not Path(python).is_file():
            raise LocateUnavailable(
                "LOCATE is not installed on this server yet.",
                f"An administrator needs to create LOCATE's environment and set {PYTHON_SETTING} "
                "(see docs/tool-inputs.he.md, LOCATE).",
            )
        return cls(python)

    def run(self, work_dir: Path, tables: dict[str, pd.DataFrame], params: dict, seed: int) -> dict:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        for name, table in tables.items():
            table.to_csv(work_dir / f"{name}.csv")
        (work_dir / "job.json").write_text(json.dumps({"seed": seed, "params": params}), encoding="utf-8")
        script = work_dir / "run_locate.py"  # run from the work folder: nothing else is importable next to it
        shutil.copyfile(RUNNER, script)

        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
        if self.extra_paths:
            env["PYTHONPATH"] = os.pathsep.join(self.extra_paths)
        env.setdefault("MPLBACKEND", "Agg")
        try:
            done = subprocess.run([self.python, "-s", str(script), str(work_dir)], cwd=work_dir, env=env,
                                  capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            raise UserFacingError(f"LOCATE did not finish within {self.timeout / 3600:.0f} hours.",
                                  "Try fewer samples or metabolites, or ask an administrator.") from exc
        (work_dir / "locate.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
        if done.returncode != 0:
            raise RuntimeError(f"LOCATE failed (exit {done.returncode}); see locate.log. "
                               f"Last lines: {done.stderr.strip()[-800:]}")
        read = {name: pd.read_csv(work_dir / f"{name}.csv", index_col=0, float_precision="round_trip")
                for name in OUTPUTS}
        for table in read.values():
            table.index = table.index.astype(str)
        read["environment"] = json.loads((work_dir / "environment.json").read_text(encoding="utf-8"))
        return read


class LocateEngine(Engine):
    name = "LOCATE"
    goal = "metabolites"
    requires = frozenset({"counts", "metabolites"})
    preprocessing = CANONICAL.with_changes(z_scoring="col")  # the paper z-scores each taxon after the log

    def __init__(self, backend: LocateBackend | None = None) -> None:
        self._backend = backend  # None: read MICROPLATFORM_LOCATE_PYTHON when it runs

    def run(self, data: Dataset, work_dir: Path, choices: dict[str, str] | None = None) -> EngineResult:
        from sklearn.model_selection import train_test_split

        backend = self._backend or LocateBackend.from_env()
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

        out = backend.run(Path(work_dir), {"X_train": X.loc[train], "Y_train": Y.loc[train],
                                           "X_val": X.loc[test], "Y_val": Y.loc[test]}, params={}, seed=SEED)
        scores = metabolite_scores(Y.loc[test], out["pred_val"])
        env = out["environment"]
        return EngineResult(
            summary=_summary(len(train), len(test), scores, prepared),
            figures=[f for f in (_scores_figure(scores),) if f],
            tables={
                "metabolite_scores": scores,
                "predicted_metabolites_test": out["pred_val"].rename_axis("sample").reset_index(),
                "latent_representation": _latent(out["Z_train"], out["Z_val"]),
            },
            highlight=("metabolite_scores", "Best-predicted metabolites"),
            record={
                "tool": "LOCATE", "package": "LOCATE-model", "version": env.get("LOCATE-model", "unknown"),
                "environment": {k: env.get(k) for k in ("python", "torch", "pytorch-lightning", "numpy", "pandas")},
                "hyperparameters": env.get("hyperparameters", {}),
                "seed": SEED, "test_size": TEST_SIZE, "split_order": "counts table",
                "validation": "the test samples (as micrOS); LOCATE uses them for early stopping",
                "prediction_mode": f"as published: LOCATE_predict right after training (model in "
                                   f"{env.get('model_mode_at_prediction', 'unknown')} mode)",
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
        rho, p = spearmanr(measured[name], predicted[str(name)])
        rows.append({"metabolite": str(name), "spearman": float(rho), "p": float(p)})
    return pd.DataFrame(rows).sort_values("spearman", ascending=False, na_position="last").reset_index(drop=True)


def _latent(z_train: pd.DataFrame, z_val: pd.DataFrame) -> pd.DataFrame:
    z = pd.concat([z_val.assign(set="test"), z_train.assign(set="train")])
    z.columns = [c if c == "set" else f"z{int(c) + 1}" for c in z.columns]
    return z.rename_axis("sample").reset_index()[["sample", "set", *[c for c in z.columns if c != "set"]]]


def _summary(n_train: int, n_test: int, scores: pd.DataFrame, prepared: dict) -> list[str]:
    rho = scores["spearman"].dropna()
    lines = [
        f"LOCATE learned from {n_train} samples with both microbiome and metabolite data and was tested on "
        f"{n_test} it had not seen ({round((1 - TEST_SIZE) * 100)}% for training, "
        f"{round(TEST_SIZE * 100)}% for testing, seed {SEED}).",
        f"Across {len(rho)} metabolites, the median Spearman correlation between measured and predicted "
        f"levels on the test samples is {rho.median():.2f}; {int((rho > 0).sum())} are predicted better "
        "than chance would suggest (correlation above 0)." if len(rho) else
        "No metabolite varied enough in the test samples to score the predictions.",
        "As in micrOS, the test samples also decided when training stopped, so these scores may be "
        "slightly optimistic.",
    ]
    if prepared["left_out_constant"]:
        lines.append(f"{prepared['left_out_constant']} metabolites were the same in every sample and were left out.")
    if not prepared["settings"]["confirmed"]:
        lines.append("The metabolite preparation (log base and the value added before the log) is provisional "
                     "until the LOCATE authors confirm it.")
    return lines


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
