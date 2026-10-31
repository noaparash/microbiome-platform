"""Amendment 1 (PROTOCOL.md): V1' verdict, and the original's own spread next to C (information only).
Writes RESULTS.md. Run in the platform's environment: python validation/locate/compare_amended.py"""

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
V1_TOLERANCE = 1e-6  # V1's tolerance, unchanged
A_RUNS = ("runs", "runs-A-repeat2", "runs-A-repeat3")  # the original, as published, three times


def load(folder: str, setup: str, example: str, seed: int) -> dict:
    path = REFERENCE / folder / setup / example / f"seed{seed}"
    run = {n: pd.read_csv(path / f"{n}.csv", index_col=0, float_precision="round_trip") for n in TABLES}
    run["info"] = json.loads((path / "run.json").read_text())
    return run


def max_difference(a: dict, b: dict, names=TABLES) -> float:
    return max(float(np.abs(a[n].to_numpy() - b[n].to_numpy()).max()) for n in names)


def mean_test_scc(run: dict, measured: pd.DataFrame) -> float:
    pred = run["pred_val"].loc[measured.index]
    return float(np.nanmean([spearmanr(measured[c], pred[c])[0] for c in measured.columns]))


def main() -> None:
    v1_rows, spread_rows = [], []
    for example in EXAMPLES:
        measured = pd.read_csv(HERE / "data" / example / "Y_val.csv", index_col=0, float_precision="round_trip")
        for seed in SEEDS:
            a, b = load("runs-gels", "A", example, seed), load("runs-gels", "B", example, seed)
            for run in (a, b):  # V1' is only meaningful if the run really used the repeatable lstsq
                if run["info"].get("lstsq") != "gels (test only)":
                    raise SystemExit(f"{example} seed {seed}: run used lstsq={run['info'].get('lstsq')!r}, "
                                     "not the repeatable driver V1' requires; re-run with -Gels")
            diff = max_difference(a, b)
            v1_rows.append({"example": example, "seed": seed, "epochs_A": a["info"]["epochs"],
                            "epochs_B": b["info"]["epochs"], "max_diff": diff,
                            "pass": a["info"]["epochs"] == b["info"]["epochs"] and diff <= V1_TOLERANCE,
                            "lstsq": (a["info"]["lstsq"], b["info"]["lstsq"])})
            originals = [load(f, "A", example, seed) for f in A_RUNS]
            c = load("runs", "C", example, seed)
            scc_a = [mean_test_scc(r, measured) for r in originals]
            spread_rows.append({
                "example": example, "seed": seed,
                "epochs_A": "/".join(str(r["info"]["epochs"]) for r in originals), "epochs_C": c["info"]["epochs"],
                "scc_A": scc_a, "scc_C": mean_test_scc(c, measured),
                "A_vs_A_max_diff": max(max_difference(originals[0], r, ("pred_val",)) for r in originals[1:]),
            })
    v1 = pd.DataFrame(v1_rows)
    v1_pass = bool(v1["pass"].all())
    sp = pd.DataFrame(spread_rows)
    sp["A_range"] = sp["scc_A"].map(lambda s: max(s) - min(s))
    sp["C_minus_A_mean"] = sp["scc_C"] - sp["scc_A"].map(np.mean)
    sp["C_within_A_range"] = [min(a) <= c <= max(a) for a, c in zip(sp["scc_A"], sp["scc_C"])]
    versions = {s: load("runs", s, "E1", 0)["info"] for s in "ABC"}

    lines = [
        "# LOCATE on Python 3.13: validation results (Amendment 1)",
        "",
        "Run 1, as first written, failed: see RESULTS-run1.md and PROTOCOL.md, Amendment 1.",
        "",
        "A first V1′ batch was invalid: a bug in run_all.ps1 dropped the `--gels` option, so those runs used",
        "the default (unrepeatable) lstsq (their run.json says `lstsq: default`). It was fixed, the comparison",
        "now refuses runs without the setting, and V1′ was re-run. The tolerance is unchanged.",
        "",
        "| Setup | Python | torch | Lightning | numpy | pandas |",
        "|---|---|---|---|---|---|",
        *[f"| {s} | {v['python']} | {v['torch']} | {v['lightning']} | {v['numpy']} | {v['pandas']} |"
          for s, v in versions.items()],
        "",
        f"## V1′, the conversion (A vs B, both with lstsq driver='gels', test only): **{'PASS' if v1_pass else 'FAIL'}**",
        "",
        f"Tolerance (V1's, unchanged): the same epochs and max |difference| ≤ {V1_TOLERANCE:g} in predictions and Z.",
        "",
        "| Example | Seed | Epochs A / B | max difference | Result |",
        "|---|---|---|---|---|",
        *[f"| {r.example} | {r.seed} | {r.epochs_A} / {r.epochs_B} | {r.max_diff:.3g} | "
          f"{'pass' if r['pass'] else 'FAIL'} |" for _, r in v1.iterrows()],
        "",
        "## V2, the product (A vs C): not passed yet (information only, no verdict)",
        "",
        "The original (A, as published) run three times per seed, next to C. Mean test Spearman over "
        "the 30 metabolites (predicted vs measured Y_val).",
        "",
        "| Example | Seed | Epochs A (3 runs) | Epochs C | Spearman A (3 runs) | A's own range | Spearman C | "
        "C − mean A | C inside A's range | max diff between A runs |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *[f"| {r.example} | {r.seed} | {r.epochs_A} | {r.epochs_C} | "
          f"{' / '.join(f'{x:.4f}' for x in r.scc_A)} | {r.A_range:.4f} | {r.scc_C:.4f} | "
          f"{r.C_minus_A_mean:+.4f} | {'yes' if r.C_within_A_range else 'no'} | {r.A_vs_A_max_diff:.3g} |"
          for r in sp.itertuples()],
        "",
        f"Average C − mean A: {sp['C_minus_A_mean'].mean():+.4f} (E1 {sp[sp.example == 'E1']['C_minus_A_mean'].mean():+.4f}, "
        f"E2 {sp[sp.example == 'E2']['C_minus_A_mean'].mean():+.4f}). "
        f"Average range of the original's own three runs: {sp['A_range'].mean():.4f}.",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
