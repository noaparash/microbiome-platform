"""Diagnostic (environment A): which way of calling lstsq gives the same answer every time?
Each variant is called 200 times on the same input; prints how many different answers it gave."""

import torch

torch.manual_seed(0)
Z, Y = torch.randn(205, 10), torch.randn(205, 30)
variants = {
    "default (gelsy), as LOCATE": lambda: torch.linalg.lstsq(Z, Y).solution,
    "driver=gels": lambda: torch.linalg.lstsq(Z, Y, driver="gels").solution,
    "driver=gelsd": lambda: torch.linalg.lstsq(Z, Y, driver="gelsd").solution,
    "driver=gelss": lambda: torch.linalg.lstsq(Z, Y, driver="gelss").solution,
    "default in float64, then float32": lambda: torch.linalg.lstsq(Z.double(), Y.double()).solution.float(),
}
for name, call in variants.items():
    answers = {call().numpy().tobytes() for _ in range(200)}
    print(f"{name:36} {len(answers)} different answer(s) in 200 calls")
