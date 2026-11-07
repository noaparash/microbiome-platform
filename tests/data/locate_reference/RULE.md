# LOCATE reference for the product tests

Evidence from the approved V2 validation (validation/locate/PROTOCOL.md, RESULTS-V2.md):
the product (locate_lightning2, Python 3.13) vs the original LOCATE-model 0.0.3 as
published (Python 3.10 reference environment, never shipped), on example E2, seeds 10-29.

- `v2_scores.csv`: per seed, the mean test Spearman of the original (A) and of the product (C).
  The rule: d = C − A; pass if the 90% confidence interval of the mean of d,
  mean ± 1.729 × SD / √20, lies within ±0.02. Result: PASS, mean −0.0013,
  interval [−0.0193, +0.0168], no systematic direction.
- `C_pred_val_seed{10,11,12}.csv`, `C_run_seed*.json`: the product's exact test-set
  predictions on those seeds (torch 2.14.1, Lightning 2.6.6). The product is deterministic,
  so it must reproduce them exactly; if a library upgrade changes them, re-run the
  validation in validation/locate/ before accepting the upgrade.

## Other platforms (`platforms/<os>-<cpu>/`)

Different processors round floating-point arithmetic differently, and training amplifies that,
so the exact predictions above hold on the laptop (Windows, x86-64) only. Another platform gets
its own folder after passing the same rule against the original on its own runs: `scores.csv`
(seed, A, S) and its exact predictions for seeds 10-12. Linux x86-64 (the lab server
peptibase10): Amendment 2, seeds 30-69, PASS (validation/locate/RESULTS-peptibase10-amend2.md).
A platform without a folder skips the exact-match test with a message: re-validate there first.
