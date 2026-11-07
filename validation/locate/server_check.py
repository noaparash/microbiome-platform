"""LOCATE re-validation on another machine, under the approved V2 rule (SERVER-peptibase10-PLAN.md).

    python validation/locate/server_check.py run SEED OUT_DIR      # one seed: score + predictions
    python validation/locate/server_check.py summarize OUT_DIR      # the rule, over seeds 10-29

The original's scores (A) and the laptop product's (C) come from
tests/data/locate_reference/v2_scores.csv; nothing of the original is re-run.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
E2 = ROOT / "validation" / "locate" / "data" / "E2"
REFERENCE = ROOT / "tests" / "data" / "locate_reference"
SEEDS = range(10, 30)
T90 = 1.729  # t(0.95, 19): the two-sided 90% interval with 20 seeds, as in V2
MARGIN = 0.02


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(E2 / f"{name}.csv", index_col=0, float_precision="round_trip")


def run(seed: int, out: Path) -> None:
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    sys.path.insert(0, str(Path(__file__).parent))
    from compare_v2 import mean_test_spearman  # the V2 score, unchanged
    from microplatform.engines.locate import fit_and_predict

    import torch

    out.mkdir(parents=True, exist_ok=True)
    measured = read("Y_val")
    os.chdir(tempfile.mkdtemp())  # LOCATE writes its logs into the current folder
    result = fit_and_predict(read("X_train"), read("Y_train"), read("X_val"), measured, seed=seed)
    pred = result["pred_val"]
    pred.to_csv(out / f"pred_val_seed{seed}.csv", float_format="%.9g")
    (out / f"seed{seed}.json").write_text(json.dumps({
        "seed": seed, "epochs": int(result["epochs"]), "score": mean_test_spearman(pred, measured),
        "torch": torch.__version__, "threads": torch.get_num_threads(), "machine": platform.node(),
    }), encoding="utf-8")


def summarize(out: Path) -> str:
    runs = pd.DataFrame([json.loads((out / f"seed{s}.json").read_text()) for s in SEEDS]).set_index("seed")
    recorded = pd.read_csv(REFERENCE / "v2_scores.csv").set_index("seed")
    table = runs.join(recorded)
    table["d"] = table["score"] - table["A"]
    table["vs_laptop"] = table["score"] - table["C"]
    mean, sd = float(table["d"].mean()), float(table["d"].std(ddof=1))
    half = T90 * sd / np.sqrt(len(table))
    low, high = mean - half, mean + half
    verdict = "PASS" if -MARGIN <= low and high <= MARGIN else "FAIL"
    direction = ("systematically lower" if high < 0 else "systematically higher" if low > 0
                 else "no systematic direction")
    lines = [
        f"Machine: {runs['machine'].iloc[0]}; torch {runs['torch'].iloc[0]}; {runs['threads'].iloc[0]} threads per run.",
        f"Verdict: {verdict}. d = server − original: mean {mean:+.4f}, 90% CI [{low:+.4f}, {high:+.4f}] "
        f"(margin ±{MARGIN}); {direction} (lower in {(table['d'] < 0).sum()} of {len(table)} seeds).",
        f"Mean test Spearman: original {table['A'].mean():.4f}, laptop product {table['C'].mean():.4f}, "
        f"server {table['score'].mean():.4f}. Server − laptop: mean {table['vs_laptop'].mean():+.4f}, "
        f"largest |difference| {table['vs_laptop'].abs().max():.4f}.",
        "",
        "| Seed | Epochs | Spearman original (A) | laptop (C) | server | d = server − A | server − laptop |",
        "|---|---|---|---|---|---|---|",
    ]
    for seed, row in table.iterrows():
        lines.append(f"| {seed} | {row['epochs']} | {row['A']:.4f} | {row['C']:.4f} | {row['score']:.4f} | "
                     f"{row['d']:+.4f} | {row['vs_laptop']:+.4f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    command, *rest = sys.argv[1:]
    if command == "run":
        run(int(rest[0]), Path(rest[1]))
    else:
        print(summarize(Path(rest[0])))
