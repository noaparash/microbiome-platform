"""Apply PROTOCOL.md's checks to the runs and write RESULTS.md. Run in the platform's environment:
python validation/locate/compare.py [reference folder]

The tolerances are PROTOCOL.md's, fixed before any run; they are not parameters.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).parent
REFERENCE = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\noapa\code\locate-reference")
EXAMPLES, SEEDS = ("E1", "E2"), range(5)
TABLES = ("pred_val", "pred_train", "Z_val", "Z_train")

V1_TOLERANCE = 1e-6          # A vs B: predictions and Z
V2_IDENTICAL = 1e-4          # A vs C, tier "identical": predictions
V2_RUN_SCC = 0.02            # A vs C, tier "equivalent": per run, |difference in mean test Spearman|
V2_MEAN_SCC = 0.01           # A vs C, tier "equivalent": |average of those differences| over all runs


def load(setup: str, example: str, seed: int) -> dict:
    folder = REFERENCE / "runs" / setup / example / f"seed{seed}"
    run = {name: pd.read_csv(folder / f"{name}.csv", index_col=0, float_precision="round_trip") for name in TABLES}
    run["info"] = json.loads((folder / "run.json").read_text())
    return run


def max_difference(a: dict, b: dict, names=TABLES) -> float:
    return max(float(np.abs(a[n].to_numpy() - b[n].to_numpy()).max()) for n in names)


def mean_test_scc(run: dict, measured: pd.DataFrame) -> float:
    pred = run["pred_val"].loc[measured.index]
    rho = [spearmanr(measured[c], pred[c])[0] for c in measured.columns]
    return float(np.nanmean(rho))


def main() -> None:
    rows = []
    for example in EXAMPLES:
        measured = pd.read_csv(HERE / "data" / example / "Y_val.csv", index_col=0, float_precision="round_trip")
        for seed in SEEDS:
            a, b, c = (load(s, example, seed) for s in "ABC")
            rows.append({
                "example": example, "seed": seed,
                "epochs_A": a["info"]["epochs"], "epochs_B": b["info"]["epochs"], "epochs_C": c["info"]["epochs"],
                "max_diff_AB": max_difference(a, b),
                "max_diff_AC_pred": max_difference(a, c, ("pred_val", "pred_train")),
                "scc_A": mean_test_scc(a, measured), "scc_B": mean_test_scc(b, measured),
                "scc_C": mean_test_scc(c, measured),
                "mode_A": a["info"]["mode_at_prediction"], "mode_C": c["info"]["mode_at_prediction"],
            })
    table = pd.DataFrame(rows)
    table["scc_diff_AC"] = table["scc_C"] - table["scc_A"]

    table["V1"] = (table["epochs_A"] == table["epochs_B"]) & (table["max_diff_AB"] <= V1_TOLERANCE)
    table["V2_identical"] = (table["epochs_A"] == table["epochs_C"]) & (table["max_diff_AC_pred"] <= V2_IDENTICAL)
    table["V2_equivalent"] = table["scc_diff_AC"].abs() <= V2_RUN_SCC
    mean_shift = float(table["scc_diff_AC"].mean())

    v1 = bool(table["V1"].all())
    v2_identical = bool(table["V2_identical"].all())
    v2_equivalent = bool((table["V2_identical"] | table["V2_equivalent"]).all()) and abs(mean_shift) <= V2_MEAN_SCC
    v2 = v2_identical or v2_equivalent
    versions = {s: load(s, "E1", 0)["info"] for s in "ABC"}

    lines = [
        "# LOCATE on Python 3.13: validation results",
        "",
        "Produced by `validation/locate/compare.py` with the tolerances in PROTOCOL.md (fixed before the runs).",
        "",
        "| Setup | Python | torch | Lightning | numpy | pandas |",
        "|---|---|---|---|---|---|",
        *[f"| {s} | {v['python']} | {v['torch']} | {v['lightning']} | {v['numpy']} | {v['pandas']} |"
          for s, v in versions.items()],
        "",
        f"- **V1, the conversion (A vs B): {'PASS' if v1 else 'FAIL'}** (same epochs, max difference ≤ {V1_TOLERANCE:g})",
        f"- **V2, the product (A vs C): {'PASS' if v2 else 'FAIL'}** — tier "
        f"{'identical' if v2_identical else 'equivalent' if v2_equivalent else 'none'} "
        f"(average Spearman shift C − A: {mean_shift:+.4f}; limit ±{V2_MEAN_SCC})",
        "",
        "| Example | Seed | Epochs A / B / C | max diff A–B | max diff A–C | mean test Spearman A / B / C | V1 | V2 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in table.itertuples():
        tier = "identical" if r.V2_identical else "equivalent" if r.V2_equivalent else "no"
        lines.append(f"| {r.example} | {r.seed} | {r.epochs_A} / {r.epochs_B} / {r.epochs_C} | {r.max_diff_AB:.2e} | "
                     f"{r.max_diff_AC_pred:.2e} | {r.scc_A:.4f} / {r.scc_B:.4f} / {r.scc_C:.4f} | "
                     f"{'pass' if r.V1 else 'FAIL'} | {tier} |")
    modes = sorted(set(table["mode_A"]) | set(table["mode_C"]))
    lines += ["", f"Model mode at prediction (A and C): {', '.join(modes)}."]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
