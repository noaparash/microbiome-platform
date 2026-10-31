# LOCATE on Python 3.13: validation results (Amendment 1)

Run 1, as first written, failed: see RESULTS-run1.md and PROTOCOL.md, Amendment 1.

A first V1′ batch was invalid: a bug in run_all.ps1 dropped the `--gels` option, so those runs used
the default (unrepeatable) lstsq (their run.json says `lstsq: default`). It was fixed, the comparison
now refuses runs without the setting, and V1′ was re-run. The tolerance is unchanged.

| Setup | Python | torch | Lightning | numpy | pandas |
|---|---|---|---|---|---|
| A | 3.10.11 | 1.13.0+cpu | 1.8.3 | 1.23.5 | 1.3.5 |
| B | 3.10.11 | 1.13.0+cpu | 2.2.5 | 1.23.5 | 1.3.5 |
| C | 3.13.3 | 2.14.1+cpu | 2.6.6 | 2.5.4 | 2.3.3 |

## V1′, the conversion (A vs B, both with lstsq driver='gels', test only): **PASS**

Tolerance (V1's, unchanged): the same epochs and max |difference| ≤ 1e-06 in predictions and Z.

| Example | Seed | Epochs A / B | max difference | Result |
|---|---|---|---|---|
| E1 | 0 | 169 / 169 | 0 | pass |
| E1 | 1 | 61 / 61 | 0 | pass |
| E1 | 2 | 53 / 53 | 0 | pass |
| E1 | 3 | 78 / 78 | 0 | pass |
| E1 | 4 | 88 / 88 | 0 | pass |
| E2 | 0 | 277 / 277 | 0 | pass |
| E2 | 1 | 221 / 221 | 0 | pass |
| E2 | 2 | 248 / 248 | 0 | pass |
| E2 | 3 | 274 / 274 | 0 | pass |
| E2 | 4 | 287 / 287 | 0 | pass |

## V2, the product (A vs C): not passed yet (information only, no verdict)

The original (A, as published) run three times per seed, next to C. Mean test Spearman over the 30 metabolites (predicted vs measured Y_val).

| Example | Seed | Epochs A (3 runs) | Epochs C | Spearman A (3 runs) | A's own range | Spearman C | C − mean A | C inside A's range | max diff between A runs |
|---|---|---|---|---|---|---|---|---|---|
| E1 | 0 | 169/169/169 | 95 | 0.0392 / 0.0392 / 0.0392 | 0.0000 | 0.0174 | -0.0217 | no | 0.00022 |
| E1 | 1 | 61/61/61 | 60 | -0.0274 / -0.0274 / -0.0274 | 0.0000 | -0.0401 | -0.0127 | no | 2.91e-05 |
| E1 | 2 | 53/53/53 | 67 | 0.0144 / 0.0145 / 0.0144 | 0.0000 | -0.0326 | -0.0470 | no | 3.87e-06 |
| E1 | 3 | 78/78/78 | 89 | 0.0416 / 0.0416 / 0.0416 | 0.0000 | -0.0341 | -0.0757 | no | 3.94e-06 |
| E1 | 4 | 88/88/88 | 80 | -0.0042 / -0.0042 / -0.0042 | 0.0000 | 0.0366 | +0.0408 | no | 5.3e-06 |
| E2 | 0 | 343/245/388 | 295 | 0.4185 / 0.4224 / 0.3708 | 0.0516 | 0.3656 | -0.0383 | no | 1.97 |
| E2 | 1 | 257/327/257 | 302 | 0.4362 / 0.4085 / 0.4375 | 0.0291 | 0.3786 | -0.0488 | no | 1.36 |
| E2 | 2 | 223/248/248 | 254 | 0.3819 / 0.3532 / 0.3662 | 0.0286 | 0.4215 | +0.0544 | no | 1.24 |
| E2 | 3 | 300/355/306 | 321 | 0.4034 / 0.4127 / 0.4035 | 0.0093 | 0.3898 | -0.0167 | no | 1.57 |
| E2 | 4 | 316/393/284 | 402 | 0.3913 / 0.4101 / 0.3686 | 0.0415 | 0.3670 | -0.0229 | no | 1.43 |

Average C − mean A: -0.0189 (E1 -0.0233, E2 -0.0145). Average range of the original's own three runs: 0.0160.
