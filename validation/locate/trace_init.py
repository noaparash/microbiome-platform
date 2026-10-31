"""Diagnostic (environment A): fingerprint every lstsq / svd_lowrank call while the ORIGINAL model is
built, plus the random-number state before each call. Run twice and compare.
Usage: python trace_init.py <example folder>"""

import hashlib
import random
import sys

import numpy as np
import pandas as pd
import pytorch_lightning as pl
import torch


def fp(*tensors):
    h = hashlib.sha256()
    for t in tensors:
        h.update(t.detach().contiguous().numpy().tobytes())
    return h.hexdigest()[:10]


real_lstsq, real_svd = torch.linalg.lstsq, torch.svd_lowrank


def lstsq(A, B, *args, **kwargs):
    out = real_lstsq(A, B, *args, **kwargs)
    print(f"  lstsq  in A={fp(A)} B={fp(B)} rng={fp(torch.get_rng_state())} -> {fp(out.solution)}"
          f"  (rank {int(torch.linalg.matrix_rank(A))} of {A.shape[1]})")
    return out


def svd(M, *args, **kwargs):
    rng = fp(torch.get_rng_state())
    a, b, c = real_svd(M, *args, **kwargs)
    print(f"  svd    in M={fp(M)} rng={rng} -> {fp(a, b, c)}")
    return a, b, c


torch.linalg.lstsq, torch.svd_lowrank = lstsq, svd
from LOCATE import LOCATE_Model  # noqa: E402  (after patching, so the model uses the wrappers)

read = lambda n: pd.read_csv(f"{sys.argv[1]}/{n}.csv", index_col=0, float_precision="round_trip")
X_train, Y_train = read("X_train"), read("Y_train")
random.seed(0); np.random.seed(0); torch.manual_seed(0); pl.seed_everything(0)
Y = torch.tensor(Y_train.to_numpy()).type(torch.float32)
X = torch.tensor(X_train.to_numpy()).type(torch.float32)
model = LOCATE_Model(Y, X, X.shape[1], 10, 0.02, 0.2, 0.001, 0.01, 1.0, 0.0, "elu", "elu", 20, 10, 0.08)
print("init X", fp(model.X))
