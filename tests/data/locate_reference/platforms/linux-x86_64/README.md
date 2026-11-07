# LOCATE reference for Linux x86-64 (the lab server peptibase10)

Different processors round floating-point arithmetic differently, and LOCATE's training amplifies
that, so each platform keeps its own exact-match reference (see ../../RULE.md).

- `scores.csv`: Amendment 2 (validation/locate/SERVER-peptibase10-PLAN.md, recorded before running):
  per seed 30-69, the mean test Spearman of the original (A, Python 3.10 reference setup on the
  laptop) and of the product on peptibase10 (S). Rule: d = S - A; pass if mean(d) ± t(0.95, 39) ×
  SD / √40 lies within ±0.02. Result: PASS, mean -0.0020, interval [-0.0121, +0.0082]
  (RESULTS-peptibase10-amend2.md). The first attempt, seeds 10-29, failed by 0.001
  (RESULTS-peptibase10.md).
- `pred_val_seed{10,11,12}.csv`, `seed*.json`: the product's exact test-set predictions on
  peptibase10 (AlmaLinux 9.8, Intel Xeon Gold 6342, torch 2.14.1+cpu, 4 threads per run).
