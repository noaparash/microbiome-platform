"""Step 2 for a comparison on a public dataset (FRANZOSA, YACHIDA): run the platform's LOCATE (Python 3.13) and
summarise prediction quality the way the paper's supplementary Fig. S1 does (per-metabolite Spearman on the 20%
test set).

1. the engine as shipped: one run (split seed 42, training seed 42);
2. 16 training seeds (0-15) on the same split: each run's per-metabolite Spearman;
3. per metabolite, the best of those 16 (as the paper's analysis code builds Fig. 3/S1:
   LOCATE_all_analysis, Fig_3/swarm_plot_different_models_metab_predictions.py, choose_best_config).

Usage: python dataset_locate.py <platform-format folder> <work folder> <results folder> [--top-detected N]
--top-detected N keeps only the N metabolites detected (> 0) in the most samples (ties: table order); a
sensitivity check for a paper whose metabolite count is smaller than the published table's.
"""

import contextlib
import json
import sys
import time
from pathlib import Path

import dataclasses
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from microplatform import workflows
from microplatform.core.inputs import sort_uploads
from microplatform.core.metabolites import LOCATE_METABOLITES, prepare_metabolites
from microplatform.core.profiler import read_table
from microplatform.engines.locate import SEED, TEST_SIZE, LocateEngine, _quiet, fit_and_predict, metabolite_scores

data, work, results = (Path(p) for p in sys.argv[1:4])
top_detected = int(sys.argv[sys.argv.index("--top-detected") + 1]) if "--top-detected" in sys.argv else None
results.mkdir(parents=True, exist_ok=True)


def stats(rho: pd.Series) -> dict:
    rho = rho.dropna()
    q = rho.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
    return {"metabolites": int(len(rho)), "mean": round(float(rho.mean()), 4), "median": round(float(q[0.5]), 4),
            "q25": round(float(q[0.25]), 4), "q75": round(float(q[0.75]), 4),
            "p05": round(float(q[0.05]), 4), "p95": round(float(q[0.95]), 4),
            "share_below_0": round(float((rho < 0).mean()), 4)}


inputs = sort_uploads([("counts.csv", (data / "counts.csv").read_bytes())])
run = workflows.start_run(work / "runs", inputs)
dataset, _ = workflows.build_dataset(run, LocateEngine.preprocessing, work / "cache", engine="LOCATE")  # cached
metabolites = read_table(data / "metabolites.csv", index_col=0)
metabolites.index = metabolites.index.astype(str)
if top_detected:
    detected = (metabolites > 0).mean()
    metabolites = metabolites[detected.sort_values(ascending=False, kind="stable").index[:top_detected]]
dataset = dataclasses.replace(dataset, metabolites=metabolites.loc[dataset.features.index]).validate()
summary = {"features": int(dataset.features.shape[1]), "samples": int(dataset.features.shape[0]),
           "metabolites_in": int(metabolites.shape[1]), "top_detected": top_detected}

# 1. the engine as shipped
start = time.time()
result = LocateEngine().run(dataset, work / "engine")
engine_scores = result.tables["metabolite_scores"].set_index("metabolite")["spearman"]
summary["engine"] = {**stats(engine_scores), "epochs": result.record["epochs"],
                     "seconds": round(time.time() - start), "summary": result.summary,
                     "metabolites_prepared": result.record["metabolites"]}
engine_scores.to_csv(results / "engine_scores.csv")
print("engine:", json.dumps(summary["engine"], indent=1), flush=True)

# 2. 16 training seeds on the engine's split, with the engine's preparation
paired = list(dataset.features.index)
X = dataset.features
Y, _ = prepare_metabolites(dataset.metabolites, LOCATE_METABOLITES)
train, test = train_test_split(paired, test_size=TEST_SIZE, random_state=SEED)
per_seed = {}
for seed in range(16):
    folder = work / f"seed{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    with contextlib.chdir(folder), _quiet():
        out = fit_and_predict(X.loc[train], Y.loc[train], X.loc[test], Y.loc[test], seed=seed)
    rho = metabolite_scores(Y.loc[test], out["pred_val"]).set_index("metabolite")["spearman"]
    per_seed[seed] = rho
    summary.setdefault("seeds", {})[seed] = {**stats(rho), "epochs": out["epochs"]}
    print(f"seed {seed}: median {summary['seeds'][seed]['median']}, mean {summary['seeds'][seed]['mean']}, "
          f"epochs {out['epochs']}", flush=True)
table = pd.DataFrame(per_seed)
table.to_csv(results / "seed_scores.csv")

# 3. per metabolite, the best of the 16 runs (the paper's figure construction)
summary["best_of_16"] = stats(table.max(axis=1))
summary["single_run_medians"] = {"min": float(min(s["median"] for s in summary["seeds"].values())),
                                 "max": float(max(s["median"] for s in summary["seeds"].values())),
                                 "mean": round(float(np.mean([s["median"] for s in summary["seeds"].values()])), 4)}
(results / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print("best of 16:", summary["best_of_16"])
print("single-run medians:", summary["single_run_medians"])
