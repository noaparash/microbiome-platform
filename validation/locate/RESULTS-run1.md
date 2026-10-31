# LOCATE on Python 3.13: validation results

Produced by `validation/locate/compare.py` with the tolerances in PROTOCOL.md (fixed before the runs).

| Setup | Python | torch | Lightning | numpy | pandas |
|---|---|---|---|---|---|
| A | 3.10.11 | 1.13.0+cpu | 1.8.3 | 1.23.5 | 1.3.5 |
| B | 3.10.11 | 1.13.0+cpu | 2.2.5 | 1.23.5 | 1.3.5 |
| C | 3.13.3 | 2.14.1+cpu | 2.6.6 | 2.5.4 | 2.3.3 |

- **V1, the conversion (A vs B): FAIL** (same epochs, max difference ≤ 1e-06)
- **V2, the product (A vs C): FAIL** — tier none (average Spearman shift C − A: -0.0225; limit ±0.01)

| Example | Seed | Epochs A / B / C | max diff A–B | max diff A–C | mean test Spearman A / B / C | V1 | V2 |
|---|---|---|---|---|---|---|---|
| E1 | 0 | 169 / 169 / 95 | 7.61e-05 | 1.35e+00 | 0.0392 / 0.0392 / 0.0174 | FAIL | no |
| E1 | 1 | 61 / 61 / 60 | 9.70e-05 | 9.37e-01 | -0.0274 / -0.0274 / -0.0401 | FAIL | equivalent |
| E1 | 2 | 53 / 53 / 67 | 1.85e-06 | 1.19e+00 | 0.0144 / 0.0144 / -0.0326 | FAIL | no |
| E1 | 3 | 78 / 78 / 89 | 2.74e-06 | 1.17e+00 | 0.0416 / 0.0416 / -0.0341 | FAIL | no |
| E1 | 4 | 88 / 88 / 80 | 4.80e-06 | 9.42e-01 | -0.0042 / -0.0042 / 0.0366 | FAIL | no |
| E2 | 0 | 343 / 371 / 295 | 2.04e+00 | 2.39e+00 | 0.4185 / 0.4311 / 0.3656 | FAIL | no |
| E2 | 1 | 257 / 270 / 302 | 1.86e+00 | 2.46e+00 | 0.4362 / 0.3985 / 0.3786 | FAIL | no |
| E2 | 2 | 223 / 248 / 254 | 2.01e+00 | 2.47e+00 | 0.3819 / 0.3657 / 0.4215 | FAIL | no |
| E2 | 3 | 300 / 274 / 321 | 2.14e+00 | 4.30e+00 | 0.4034 / 0.3985 / 0.3898 | FAIL | equivalent |
| E2 | 4 | 316 / 334 / 402 | 1.73e+00 | 2.02e+00 | 0.3913 / 0.3696 / 0.3670 | FAIL | no |

Model mode at prediction (A and C): training.
