# LOCATE on peptibase10: re-validation results (plan: SERVER-peptibase10-PLAN.md, recorded before running)

Run 2026-11-07 on peptibase10.math.biu.ac.il (AlmaLinux 9.8, Intel Xeon Gold 6342), code commit dde41ac,
torch 2.14.1+cpu, 4 threads per run, 5 seeds at a time, low priority; 28 s for all 20 seeds.

## Verdict under the approved V2 rule: **FAIL** (narrowly)


Verdict: FAIL. d = server − original: mean +0.0047, 90% CI [-0.0116, +0.0210] (margin ±0.02); no systematic direction (lower in 9 of 20 seeds).
Mean test Spearman: original 0.3816, laptop product 0.3804, server 0.3863. Server − laptop: mean +0.0060, largest |difference| 0.0535.
| Seed | Epochs | Spearman original (A) | laptop (C) | server | d = server − A | server − laptop |
|---|---|---|---|---|---|---|
| 10 | 160 | 0.3509 | 0.4116 | 0.4103 | +0.0594 | -0.0013 |
| 11 | 341 | 0.4009 | 0.3553 | 0.4088 | +0.0079 | +0.0535 |
| 12 | 421 | 0.4188 | 0.3729 | 0.3990 | -0.0198 | +0.0261 |
| 13 | 311 | 0.3538 | 0.4007 | 0.3725 | +0.0187 | -0.0282 |
| 14 | 265 | 0.3940 | 0.3471 | 0.3652 | -0.0288 | +0.0181 |
| 15 | 377 | 0.3694 | 0.4097 | 0.3947 | +0.0253 | -0.0150 |
| 16 | 126 | 0.4106 | 0.3065 | 0.3062 | -0.1045 | -0.0004 |
| 17 | 308 | 0.4103 | 0.3731 | 0.4001 | -0.0102 | +0.0270 |
| 18 | 280 | 0.3953 | 0.3909 | 0.3883 | -0.0070 | -0.0026 |
| 19 | 194 | 0.3651 | 0.3723 | 0.3730 | +0.0079 | +0.0007 |
| 20 | 589 | 0.3479 | 0.3944 | 0.4060 | +0.0581 | +0.0115 |
| 21 | 156 | 0.3783 | 0.3611 | 0.3605 | -0.0179 | -0.0006 |
| 22 | 168 | 0.4170 | 0.3580 | 0.3721 | -0.0449 | +0.0141 |
| 23 | 221 | 0.3452 | 0.4074 | 0.4072 | +0.0620 | -0.0002 |
| 24 | 303 | 0.3900 | 0.3742 | 0.3790 | -0.0110 | +0.0048 |
| 25 | 228 | 0.4147 | 0.3981 | 0.3701 | -0.0446 | -0.0280 |
| 26 | 386 | 0.3846 | 0.3732 | 0.4040 | +0.0194 | +0.0308 |
| 27 | 236 | 0.3500 | 0.4034 | 0.3962 | +0.0462 | -0.0073 |
| 28 | 346 | 0.3747 | 0.4075 | 0.4109 | +0.0363 | +0.0034 |
| 29 | 176 | 0.3613 | 0.3898 | 0.4025 | +0.0412 | +0.0127 |

## Reading it

- The upper end of the interval, +0.0210, is over the ±0.02 margin by 0.001. The mean difference
  is positive: the server scored slightly *higher* than the original on average (0.3863 vs 0.3816).
- With 20 seeds and this spread of d (SD ≈ 0.04–0.05), the interval's half-width is about 0.018, so
  any average shift beyond about ±0.002 fails, in either direction. The laptop's own V2 result
  ([−0.0193, +0.0168]) was equally close to the edge.
- Per seed, the server differs from the laptop by up to 0.05: rounding differences between
  processors act like another random seed for single LOCATE runs. The thread count does not
  change the result (seed 10: 0.4103 with 1, 4 and 8 threads).
- As planned: after a FAIL, LOCATE stays off on the server until the owner decides what next.
  No exact-match reference is recorded for this platform.
