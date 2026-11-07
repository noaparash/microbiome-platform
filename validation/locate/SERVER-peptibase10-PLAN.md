# LOCATE on the lab server peptibase10: re-validation plan (recorded before running)

Written 2026-11-07, before any of the runs below; committed before running them.

## Why

On peptibase10 (AlmaLinux 9.8, Intel Xeon Gold 6342) the product's exact-match test fails:
its predictions differ from the ones recorded on the laptop (Windows, Intel i7-1255U).
Measured once, before this plan, on seed 10: the same split and the same stopping epoch
(160), predictions differing by a median of 0.002 (largest 0.015, values about 0.43), mean
test Spearman 0.4103 on the server vs 0.4116 on the laptop. Different processors and math
libraries round floating-point arithmetic differently, and training amplifies that. By the
project's rule, changed results mean re-validation before LOCATE is relied on there.

## Rule (the approved V2 rule, unchanged; validation/locate/PROTOCOL.md, RESULTS-V2.md)

- Data: example E2 (`validation/locate/data/E2`), seeds 10–29, the product as deployed on
  peptibase10 (code commit noted in the results; `uv.lock`: torch 2.14.1+cpu, Lightning 2.6.6).
- Score per seed: mean test Spearman over metabolites (`compare_v2.mean_test_spearman`).
- S = the server's score, A = the original LOCATE's score per seed as recorded in
  `tests/data/locate_reference/v2_scores.csv` (no new runs of the original).
- d = S − A; **PASS if the 90% confidence interval of the mean of d,
  mean ± 1.729 × SD / √20, lies within ±0.02.** Direction is reported as in V2
  ("systematically lower" = the whole interval below 0 → documented and flagged).
- Also reported, not judged: S − C (the laptop's product scores, same file).

## Run conditions

Low priority (`nice`), a fixed thread count (`OMP_NUM_THREADS=4` per process, several
seeds side by side), on the shared server.

## After a PASS

The server's exact predictions for seeds 10–12 become the exact-match reference for that
machine (`tests/data/locate_reference/` per machine), so its test checks the server and the
laptop keeps its own. After a FAIL: LOCATE stays off on the server; findings are written up.

## Amendment 2 (recorded 2026-11-07, after the FAIL in RESULTS-peptibase10.md, before any run below)

The owner's decision: re-test with more seeds, so the rule can tell "equivalent" from "different"
(with 20 seeds the 90% interval's half-width was about 0.018, so any mean shift beyond about
±0.002 failed, in either direction).

- **New seeds only: 30–69 (40 seeds).** Seeds 10–29 are not reused or pooled.
- **The original (A)** runs as in V2: `run_all.ps1 -Setups A -Examples E2 -Seeds (30..69)
  -Folder runs-amend2`, in the Python 3.10 reference setup on the laptop (LOCATE-model 0.0.3,
  torch 1.13.0+cpu, default lstsq driver), unchanged.
- **The server (S)** runs as before: `server_check.py run SEED OUT` on peptibase10, 4 threads per
  run, low priority, the same code commit as the deployed product.
- **The rule is V2's, with the interval for 40 seeds:** d = S − A per seed (mean test Spearman,
  `compare_v2.mean_test_spearman`); PASS if mean(d) ± t(0.95, 39) × SD / √40 lies within ±0.02,
  with t(0.95, 39) = 1.685. Direction reported as in V2. The margin is unchanged.
- This result is final for the server: after a PASS, LOCATE is enabled there and the server's exact
  predictions for seeds 10–12 become its exact-match reference; after a FAIL, LOCATE stays off on
  the server and no further amendment is made without a new decision by the owner.
