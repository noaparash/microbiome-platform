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

---

## Amendment 1 (2026-10-31, after run 1 failed; written before any run under it)

**What run 1 showed** (RESULTS-run1.md): V1 and V2 both failed as written. Diagnosis,
using environment A only:
- the **original LOCATE is not repeatable against itself**: environment A, the same
  seed and data, run twice, gave the same epochs on E1 but differences up to 3e-4, and
  on E2 stopped at epoch 343 once and 279 the next time (differences up to 2.2).
  Single-threading and MKL_CBWR=COMPATIBLE did not remove it;
- the cause is `torch.linalg.lstsq` in torch 1.13 with its default driver (gelsy): the
  same input, called 200 times, gives 2-3 different answers that differ in the last
  digit (1.5e-7). LOCATE calls it at every training step, and hundreds of epochs plus
  early stopping magnify that. Its other drivers (gels, gelsd, gelss) give one answer.
  In torch 2.14 (environment C) the default driver gave one answer in 200 calls.

So V1's premise (the same environment and seed give identical results) is false for
the original code, and V1 as written cannot be passed even by the original against
itself.

**V1′, the conversion, exact (replaces V1).** For this check only, A and B both make
`lstsq` repeatable in the same way: `torch.linalg.lstsq(..., driver="gels")`, injected
by `run_locate.py --gels` (test only, never in the product). Then A and B differ only
in Lightning and the conversion. Precondition: A with `--gels`, run twice, must give
identical results; otherwise V1′ cannot be done. Check and tolerance are **V1's,
unchanged**: for every example and seed, the same number of epochs, and max |difference|
≤ 1e-6 in predictions and Z.

**V2, the product.** Run 1's numbers for C are already known, so a new pass rule chosen
now could be biased by them. Therefore: (1) the original's own run-to-run spread is
measured (environment A as published, two more runs per example and seed) and reported
next to C, for information only; (2) a revised V2 rule is **proposed to the project
owner** and, once approved, run on **new seeds (10-19)** that nobody has seen. Until
then V2 is "not passed" and LOCATE stays hidden.

### Results under Amendment 1 (see RESULTS.md)

- **V1′: PASS, exactly.** With the test-only repeatable lstsq in both, A and B gave
  bit-identical predictions and Z (difference 0) and stopped at the same epoch, in all 10
  runs. Step-by-step traces (`trace_steps.py`, `diff_traces.py`) also matched for every
  forward pass, gradient, parameter update and random-number state (320 events on E1,
  1,490 on E2). The only difference: the original also calls the discriminator's
  `Adam.step` with no gradients, which never changes anything; the conversion skips it.
- **V2: not passed** (no approved rule yet). Information only: on E2 the original
  differs from itself by 0.03 in mean Spearman across three runs of the same seed.

### Proposed rule for V2 (NOT approved, NOT run; for the project owner)

V1′ shows the conversion is exact, so A vs C now measures only the library upgrade
(torch 1.13 → 2.14 and the rest). That cannot be bit-exact (the original is not even
repeatable on its own torch), so the proposal compares **prediction quality**:
- data: E2-type structured data (E1 is random numbers: nothing to predict, so it is
  reported but not judged);
- **new seeds 10-29** (20 seeds; nobody has seen them); A as published, C as shipped;
- per seed, d = mean test Spearman(C) − mean test Spearman(A);
- **pass** if the 90% confidence interval of the mean of d lies within **±0.02**
  (a standard equivalence test, TOST). The margin, 0.02, is below the original's own
  run-to-run spread on E2 (0.03).

### V2 rule: APPROVED by the project owner (2026-10-31), recorded before running

The proposed rule above is approved as written:
- data: E2 (the structured example); seeds **10-29** (20 seeds, new); A = the original as
  published (default lstsq, no test-only changes), C = the product as shipped;
- per seed, d = mean test Spearman(C) − mean test Spearman(A), where mean test Spearman is the
  mean over the 30 metabolites of Spearman(predicted, measured Y_val);
- 90% confidence interval of the mean of d: mean ± t(0.95, df = 19) × SD / √20, with
  t(0.95, 19) = 1.729;
- **PASS** if the whole interval lies within **[−0.02, +0.02]**.

Owner's addition, also fixed before running: report the direction and size of the
difference, per seed and overall. The difference is called **systematically lower** if the
whole 90% interval lies below 0, and **systematically higher** if it lies above 0;
otherwise **no systematic direction**. If it is systematically lower, record it in the
docs and flag it for the LOCATE authors, whether or not V2 passes.
