"""V2, as approved (PROTOCOL.md, "V2 rule: APPROVED"): the product (C) vs the original as published (A),
on E2 with the new seeds 10-29. Writes RESULTS-V2.md. Run in the platform's environment:
python validation/locate/compare_v2.py

The rule is fixed in PROTOCOL.md; nothing here is a parameter.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from scipy.stats import t as student_t

HERE = Path(__file__).parent
REFERENCE = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\noapa\code\locate-reference")
EXAMPLE, SEEDS = "E2", range(10, 30)
T_95_19 = 1.729  # t(0.95, df = 19), as recorded in PROTOCOL.md
MARGIN = 0.02


def run(setup: str, seed: int) -> tuple[pd.DataFrame, dict]:
    folder = REFERENCE / "runs-v2" / setup / EXAMPLE / f"seed{seed}"
    info = json.loads((folder / "run.json").read_text())
    expected = {"A": ("original", "1.13.0+cpu"), "C": ("lightning2", "2.14.1+cpu")}[setup]
    if (info["impl"], info["torch"], info.get("lstsq")) != (*expected, "default"):
        raise SystemExit(f"{setup} seed {seed}: {info['impl']}, torch {info['torch']}, lstsq {info.get('lstsq')} "
                         f"is not the setup V2 requires")
    return pd.read_csv(folder / "pred_val.csv", index_col=0, float_precision="round_trip"), info


def mean_test_spearman(pred: pd.DataFrame, measured: pd.DataFrame) -> float:
    pred = pred.loc[measured.index]
    return float(np.nanmean([spearmanr(measured[c], pred[c])[0] for c in measured.columns]))


def main() -> None:
    assert len(SEEDS) == 20 and abs(student_t.ppf(0.95, 19) - T_95_19) < 5e-4  # the recorded constant is right
    measured = pd.read_csv(HERE / "data" / EXAMPLE / "Y_val.csv", index_col=0, float_precision="round_trip")
    rows = []
    for seed in SEEDS:
        (pa, ia), (pc, ic) = run("A", seed), run("C", seed)
        a, c = mean_test_spearman(pa, measured), mean_test_spearman(pc, measured)
        rows.append({"seed": seed, "epochs_A": ia["epochs"], "epochs_C": ic["epochs"], "A": a, "C": c, "d": c - a})
    table = pd.DataFrame(rows)
    mean, sd = float(table["d"].mean()), float(table["d"].std(ddof=1))
    half = T_95_19 * sd / math.sqrt(len(table))
    low, high = mean - half, mean + half
    passed = -MARGIN <= low and high <= MARGIN
    direction = ("systematically lower" if high < 0 else "systematically higher" if low > 0
                 else "no systematic direction")
    versions = {s: run(s, SEEDS[0])[1] for s in "AC"}

    lines = [
        "# LOCATE on Python 3.13: V2, the product vs the original (approved rule)",
        "",
        "Rule (PROTOCOL.md, approved and recorded before running): E2, new seeds 10-29; d = mean test Spearman(C) "
        "− mean test Spearman(A); pass if the 90% confidence interval of the mean of d lies within ±0.02.",
        "",
        "| Setup | Python | torch | Lightning | numpy | pandas |",
        "|---|---|---|---|---|---|",
        *[f"| {s} {'(original, as published)' if s == 'A' else '(the product)'} | {v['python']} | {v['torch']} | "
          f"{v['lightning']} | {v['numpy']} | {v['pandas']} |" for s, v in versions.items()],
        "",
        f"## Verdict: **{'PASS' if passed else 'FAIL'}**",
        "",
        f"- Mean difference d (C − A): **{mean:+.4f}**; 90% confidence interval **[{low:+.4f}, {high:+.4f}]** "
        f"(margin ±{MARGIN}).",
        f"- Direction: **{direction}**. C was lower in {int((table['d'] < 0).sum())} of 20 seeds and higher in "
        f"{int((table['d'] > 0).sum())}.",
        f"- Mean test Spearman: A {table['A'].mean():.4f}, C {table['C'].mean():.4f}. "
        f"Spread of d across seeds (SD): {sd:.4f}.",
        "",
        "| Seed | Epochs A | Epochs C | Spearman A | Spearman C | d = C − A |",
        "|---|---|---|---|---|---|",
        *[f"| {r.seed} | {r.epochs_A} | {r.epochs_C} | {r.A:.4f} | {r.C:.4f} | {r.d:+.4f} |" for r in table.itertuples()],
    ]
    (HERE / "RESULTS-V2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
