"""Diagnostic (environment A): where do two runs of the ORIGINAL LOCATE, same seed, first differ?
Prints a fingerprint of the model after each stage; run twice and compare the output.
Usage: python trace_original.py <example folder>"""

import hashlib
import random
import sys

import numpy as np
import pandas as pd
import pytorch_lightning as pl
import torch
from LOCATE import LOCATE_Model


def fingerprint(*tensors):
    h = hashlib.sha256()
    for t in tensors:
        h.update(t.detach().contiguous().numpy().tobytes())
    return h.hexdigest()[:12]


def read(name):
    return pd.read_csv(f"{sys.argv[1]}/{name}.csv", index_col=0, float_precision="round_trip")


X_train, Y_train = read("X_train"), read("Y_train")
random.seed(0); np.random.seed(0); torch.manual_seed(0); pl.seed_everything(0)
Y = torch.tensor(Y_train.to_numpy()).type(torch.float32)
X = torch.tensor(X_train.to_numpy()).type(torch.float32)
print("inputs      ", fingerprint(X, Y))

# The model's own pieces, as LOCATE_training builds and trains it (defaults of LOCATE_training).
model = LOCATE_Model(Y, X, X.shape[1], 10, 0.02, 0.2, 0.001, 0.01, 1.0, 0.0, "elu", "elu", 20, 10, 0.08)
print("init weights", fingerprint(*model.linear_representation.parameters()))
print("init X      ", fingerprint(model.X))

Z = model.linear_representation(X)
print("forward Z   ", fingerprint(Z))
sol = torch.linalg.lstsq(Z, Y).solution
print("lstsq       ", fingerprint(sol))
for i in range(3):
    torch.manual_seed(123)
    a, b, c = torch.svd_lowrank(sol, q=min(6, Y.shape[1]))
    print(f"svd_lowrank{i}", fingerprint(a, b, c))
