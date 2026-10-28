"""Run the authors' LOCATE in LOCATE's own Python environment.

This file is copied into a run's work folder and executed by the interpreter in
``MICROPLATFORM_LOCATE_PYTHON`` (a separate environment with LOCATE-model 0.0.3
and its pinned torch 1.13 / pytorch-lightning 1.8 / numpy 1.21 / pandas 1.3,
which only install on Python 3.7-3.10). It must therefore:
- run on Python 3.7+ and pandas 1.3 (no newer syntax),
- never import ``microplatform`` (it is not installed there).

It calls the authors' two functions exactly as their usage example and micrOS
do, ``LOCATE_training(X_train, Y_train, X_val, Y_val, **params)`` then
``LOCATE_predict(model, X, metabolite_names)``, after fixing every random seed.
The only addition: ``LOCATE_predict`` returns predictions without sample IDs, so
they are re-attached here (the rows are in X's order).

Input (in the work folder): X_train.csv, Y_train.csv, X_val.csv, Y_val.csv, job.json.
Output: Z_train.csv, Z_val.csv, pred_train.csv, pred_val.csv, environment.json.
"""

import inspect
import json
import os
import platform
import random
import sys


def package_version(name):
    try:
        from importlib.metadata import version  # Python 3.8+
        return version(name)
    except Exception:
        try:
            import pkg_resources  # Python 3.7
            return pkg_resources.get_distribution(name).version
        except Exception:
            return "unknown"


def main(work_dir):
    os.chdir(work_dir)  # LOCATE writes lightning_logs/ into the current folder
    with open("job.json") as handle:
        job = json.load(handle)
    seed = int(job["seed"])

    import numpy as np
    import pandas as pd
    import pytorch_lightning as pl
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    pl.seed_everything(seed)

    from LOCATE import LOCATE_predict, LOCATE_training

    def read(name):
        return pd.read_csv(name + ".csv", index_col=0, float_precision="round_trip")

    X_train, Y_train, X_val, Y_val = (read(n) for n in ("X_train", "Y_train", "X_val", "Y_val"))
    X_train.index = X_train.index.astype(str)
    X_val.index = X_val.index.astype(str)

    model = LOCATE_training(X_train, Y_train, X_val, Y_val, **job.get("params", {}))
    Z_train, pred_train = LOCATE_predict(model, X_train, Y_train.columns)
    Z_val, pred_val = LOCATE_predict(model, X_val, Y_val.columns)
    pred_train.index = X_train.index
    pred_val.index = X_val.index

    for name, table in (("Z_train", Z_train), ("Z_val", Z_val), ("pred_train", pred_train), ("pred_val", pred_val)):
        table.to_csv(name + ".csv")

    defaults = {name: p.default for name, p in inspect.signature(LOCATE_training).parameters.items()
                if p.default is not inspect.Parameter.empty}
    with open("environment.json", "w") as handle:
        json.dump({
            "python": platform.python_version(),
            "LOCATE-model": package_version("LOCATE-model"),
            "torch": torch.__version__,
            "pytorch-lightning": pl.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "hyperparameters": dict(defaults, **job.get("params", {})),
            "model_mode_at_prediction": "training" if model.training else "evaluation",
        }, handle, indent=2)


if __name__ == "__main__":
    main(sys.argv[1])
