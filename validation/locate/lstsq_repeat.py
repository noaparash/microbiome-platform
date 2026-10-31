"""Diagnostic: does torch.linalg.lstsq (the default CPU driver, as LOCATE calls it) give the same answer
for the same input, called 200 times in one process? Runs in any environment (A, B or C)."""

import torch

torch.manual_seed(0)
Z = torch.randn(205, 10)
Y = torch.randn(205, 30)
first = torch.linalg.lstsq(Z, Y).solution
outcomes, worst = {}, 0.0
for _ in range(200):
    sol = torch.linalg.lstsq(Z, Y).solution
    key = hash(sol.numpy().tobytes())
    outcomes[key] = outcomes.get(key, 0) + 1
    worst = max(worst, float((sol - first).abs().max()))
scale = float(first.abs().max())
print(f"torch {torch.__version__}: {len(outcomes)} different answers in 200 calls; largest difference {worst:.3g} "
      f"(values up to {scale:.3g}, so relative {worst / scale:.2g}); float32 precision is 1.2e-07")
