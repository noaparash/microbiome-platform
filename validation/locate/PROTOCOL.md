# LOCATE on Python 3.13: validation protocol (fixed before any comparison was run)

Recorded 2026-10-31, before running any comparison. The tolerances below are not
changed after seeing results. If a check fails, the cause is investigated; the
tolerance is never widened.

## What is compared

| Name | Where | LOCATE | Python | torch | Lightning | numpy | pandas |
|---|---|---|---|---|---|---|---|
| **A** reference | `locate-reference/env-original` (test only, never shipped) | original LOCATE-model 0.0.3, unchanged | 3.10.11 | 1.13.0+cpu | 1.8.3 | 1.23.5 ¹ | 1.3.5 |
| **B** conversion check | `locate-reference/env-port` (test only, never shipped) | `locate_lightning2` (this repo) | 3.10.11 | 1.13.0+cpu | 2.2.5 | 1.23.5 | 1.3.5 |
| **C** product | the platform's `.venv` | `locate_lightning2` (this repo) | 3.13 | 2.14.1+cpu | 2.6.6 | 2.5.4 | 2.3.3 |

¹ LOCATE-model pins numpy 1.21.6, but the only torch 1.13.0 builds available were
compiled against numpy ≥ 1.23. With 1.21.6, `tensor.numpy()` fails ("Numpy is not
available"), so the published pins cannot run `LOCATE_predict`. numpy 1.23.5 is the
smallest change that runs; numpy only moves data in and out, and torch does all of
the model's arithmetic. Everything else in A is exactly as pinned.

A and B differ **only** in Lightning and the conversion. A and C differ in
everything except the model logic.

## Data (the same files for every run)

- **E1, the authors' example:** the shapes and recipe of the authors'
  `usage_example.py`: X_train 100×50, X_val 30×50, Y_train 100×30, Y_val 30×30,
  each `log(uniform(0, 1) + 0.1)`. Drawn once with numpy seed 2026 and saved as CSV.
- **E2, a structured example:** X = the miMic authors' example microbiome
  (257 samples), prepared as for LOCATE (MIPMLP sub-PCA, species, log10(x + 0.1),
  z-score per feature). Y = 30 synthetic metabolites that depend on X (fixed random
  non-linear map plus noise, numpy seed 2026), then relative → log → z-score as in
  `core/metabolites.py`. Split 80/20 with `train_test_split(random_state=42)`; the
  test part is X_val/Y_val. Unlike E1, there is something to learn, so training runs
  for many epochs.

## Each run

Seeds 0, 1, 2, 3, 4 (each example). Before training: `random.seed`, `np.random.seed`,
`torch.manual_seed` and `pl.seed_everything` with that seed. Then exactly the authors'
calls: `LOCATE_training(X_train, Y_train, X_val, Y_val)` with its defaults, then
`LOCATE_predict(model, X, Y.columns)` for X_val and X_train. Recorded: predictions,
Z, the number of epochs trained, the model's mode at prediction, and versions.

## Checks and tolerances

**V1, the conversion (A vs B), for every example and seed:**
- the same number of epochs trained (early stopping at the same epoch);
- predictions and Z, on X_val and X_train: max |difference| ≤ **1e-6**.

**V2, the product (A vs C), for every example and seed.** Different torch versions
may do floating-point arithmetic in a different order, and 1000 epochs of training
can magnify that, so two tiers are fixed now:
- **identical:** the same number of epochs and max |prediction difference| ≤ **1e-4**;
- **equivalent** (if not identical): per run, the mean over metabolites of the
  Spearman correlation between predicted and measured Y_val differs by ≤ **0.02**
  between A and C; and over all 10 runs, the average of those differences is
  ≤ **0.01** in absolute value (no systematic shift).

**Pass:** V2 passes if every run is "identical", or every run is at least
"equivalent". V1 does not change the verdict; it shows whether any difference
comes from the conversion (V1 would fail) or from the library versions (V1 passes).

**Decision:** LOCATE stays hidden ("Planned") and no faithfulness claim is made
unless V2 passes. A later check, V3, compares C with the authors' own LOCATE results
on a real paired dataset, with a tolerance agreed with them.
