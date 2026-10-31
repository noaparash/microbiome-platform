"""Diagnostic: trace the first training events of LOCATE in environment A (original) or B (conversion),
with lstsq made repeatable (driver="gels", as in Amendment 1). Each event prints a fingerprint of the
tensors involved, so two traces can be compared line by line to find the first difference.

Usage: python trace_steps.py <original|lightning2> <example folder> <seed> <events to print> <trace file>
"""

import hashlib
import os
import random
import sys
import tempfile

import numpy as np
import pandas as pd
import pytorch_lightning as pl
import torch

impl, data_dir, seed, limit = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
trace = open(os.path.abspath(sys.argv[5]), "w", encoding="utf-8")  # every event, unmixed with progress bars
events = []


def fp(*tensors):
    h = hashlib.sha256()
    for t in tensors:
        h.update(t.detach().contiguous().cpu().numpy().tobytes())
    return h.hexdigest()[:10]


def log(text):
    events.append(text)
    trace.write(f"{len(events)} {text}\n")
    if len(events) <= limit:
        print(f"{len(events):4} {text}")


original_lstsq = torch.linalg.lstsq
torch.linalg.lstsq = lambda A, B, *a, **k: original_lstsq(A, B, *a, **dict(k, driver="gels"))

if impl == "original":
    import LOCATE as package
    from LOCATE.LOCATE_model import GeneralModel
else:
    import locate_lightning2 as package
    from locate_lightning2.LOCATE_model import GeneralModel

real_find, real_forward = GeneralModel.find_transformer, GeneralModel.forward


def find_transformer(self, Z):
    real_find(self, Z)
    log(f"find_transformer Z={fp(Z)} grad={Z.requires_grad} -> X={fp(self.X)} rng={fp(torch.get_rng_state())}")


def forward(self, micro, train=False):
    out = real_forward(self, micro, train)
    log(f"forward train={train} training_mode={self.training} -> metab={fp(out[0])}")
    return out


GeneralModel.find_transformer, GeneralModel.forward = find_transformer, forward

real_adam_step = torch.optim.Adam.step


def adam_step(self, *args, **kwargs):
    result = real_adam_step(self, *args, **kwargs)
    params = [p for g in self.param_groups for p in g["params"]]
    grads = [p.grad for p in params if p.grad is not None]
    log(f"adam.step n_params={len(params)} grads={len(grads)} grad_fp={fp(*grads) if grads else '-'} "
        f"-> params={fp(*params)}")
    return result


torch.optim.Adam.step = adam_step

read = lambda n: pd.read_csv(f"{data_dir}/{n}.csv", index_col=0, float_precision="round_trip")
X_train, Y_train, X_val, Y_val = (read(n) for n in ("X_train", "Y_train", "X_val", "Y_val"))
os.chdir(tempfile.mkdtemp())
random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); pl.seed_everything(seed)
model = package.LOCATE_training(X_train, Y_train, X_val, Y_val)
trace.close()
print(f"total events {len(events)}, epochs {model.current_epoch}")
