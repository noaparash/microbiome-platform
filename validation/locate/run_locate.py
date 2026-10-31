"""One validation run (PROTOCOL.md, "Each run"). Runs in A, B and C, so it uses only Python 3.7
syntax and no microplatform code.

Usage: python run_locate.py <original|lightning2> <example folder> <seed> <output folder> [--gels]
  original    imports the authors' package `LOCATE` (environment A)
  lightning2  imports `locate_lightning2` (environments B and C; put src/ on PYTHONPATH in B)
  --gels      TEST ONLY (PROTOCOL.md, Amendment 1): make torch.linalg.lstsq repeatable by calling it
              with driver="gels". In torch 1.13 the default driver (gelsy) is not repeatable.
              Applied identically to A and B; never part of the product.
"""

import json
import os
import platform
import random
import sys


def main(impl, data_dir, seed, out_dir, gels=False):
    import numpy as np
    import pandas as pd
    import pytorch_lightning as pl
    import torch

    if gels:  # before LOCATE is imported; LOCATE looks up torch.linalg.lstsq at each call
        original_lstsq = torch.linalg.lstsq

        def lstsq_gels(A, B, *args, **kwargs):
            kwargs["driver"] = "gels"
            return original_lstsq(A, B, *args, **kwargs)

        torch.linalg.lstsq = lstsq_gels

    if impl == "original":
        from LOCATE import LOCATE_predict, LOCATE_training
    else:
        from locate_lightning2 import LOCATE_predict, LOCATE_training

    def read(name):
        return pd.read_csv(os.path.join(data_dir, name + ".csv"), index_col=0, float_precision="round_trip")

    X_train, Y_train, X_val, Y_val = (read(n) for n in ("X_train", "Y_train", "X_val", "Y_val"))
    os.makedirs(out_dir, exist_ok=True)
    os.chdir(out_dir)  # lightning_logs/ goes here

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    pl.seed_everything(seed)

    model = LOCATE_training(X_train, Y_train, X_val, Y_val)
    mode = "training" if model.training else "evaluation"
    Z_val, pred_val = LOCATE_predict(model, X_val, Y_val.columns)
    Z_train, pred_train = LOCATE_predict(model, X_train, Y_train.columns)
    pred_val.index, pred_train.index = X_val.index, X_train.index

    for name, table in (("pred_val", pred_val), ("pred_train", pred_train), ("Z_val", Z_val), ("Z_train", Z_train)):
        table.to_csv(name + ".csv", float_format="%.9g")
    with open("run.json", "w") as handle:
        json.dump({"impl": impl, "seed": seed, "lstsq": "gels (test only)" if gels else "default",
                   "epochs": int(model.current_epoch),
                   "mode_at_prediction": mode, "python": platform.python_version(),
                   "torch": torch.__version__, "lightning": pl.__version__,
                   "numpy": np.__version__, "pandas": pd.__version__}, handle, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], os.path.abspath(sys.argv[2]), int(sys.argv[3]), os.path.abspath(sys.argv[4]),
         gels="--gels" in sys.argv[5:])
