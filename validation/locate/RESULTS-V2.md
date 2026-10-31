# LOCATE on Python 3.13: V2, the product vs the original (approved rule)

Rule (PROTOCOL.md, approved and recorded before running): E2, new seeds 10-29; d = mean test Spearman(C) − mean test Spearman(A); pass if the 90% confidence interval of the mean of d lies within ±0.02.

| Setup | Python | torch | Lightning | numpy | pandas |
|---|---|---|---|---|---|
| A (original, as published) | 3.10.11 | 1.13.0+cpu | 1.8.3 | 1.23.5 | 1.3.5 |
| C (the product) | 3.13.3 | 2.14.1+cpu | 2.6.6 | 2.5.4 | 2.3.3 |

## Verdict: **PASS**

- Mean difference d (C − A): **-0.0013**; 90% confidence interval **[-0.0193, +0.0168]** (margin ±0.02).
- Direction: **no systematic direction**. C was lower in 11 of 20 seeds and higher in 9.
- Mean test Spearman: A 0.3816, C 0.3804. Spread of d across seeds (SD): 0.0467.

| Seed | Epochs A | Epochs C | Spearman A | Spearman C | d = C − A |
|---|---|---|---|---|---|
| 10 | 245 | 160 | 0.3509 | 0.4116 | +0.0607 |
| 11 | 301 | 260 | 0.4009 | 0.3553 | -0.0456 |
| 12 | 339 | 243 | 0.4188 | 0.3729 | -0.0459 |
| 13 | 327 | 311 | 0.3538 | 0.4007 | +0.0469 |
| 14 | 225 | 278 | 0.3940 | 0.3471 | -0.0469 |
| 15 | 260 | 303 | 0.3694 | 0.4097 | +0.0403 |
| 16 | 310 | 126 | 0.4106 | 0.3065 | -0.1041 |
| 17 | 234 | 227 | 0.4103 | 0.3731 | -0.0372 |
| 18 | 429 | 244 | 0.3953 | 0.3909 | -0.0044 |
| 19 | 169 | 194 | 0.3651 | 0.3723 | +0.0072 |
| 20 | 238 | 514 | 0.3479 | 0.3944 | +0.0466 |
| 21 | 264 | 156 | 0.3783 | 0.3611 | -0.0173 |
| 22 | 308 | 197 | 0.4170 | 0.3580 | -0.0590 |
| 23 | 171 | 221 | 0.3452 | 0.4074 | +0.0622 |
| 24 | 300 | 378 | 0.3900 | 0.3742 | -0.0158 |
| 25 | 212 | 321 | 0.4147 | 0.3981 | -0.0166 |
| 26 | 391 | 386 | 0.3846 | 0.3732 | -0.0115 |
| 27 | 237 | 282 | 0.3500 | 0.4034 | +0.0535 |
| 28 | 290 | 337 | 0.3747 | 0.4075 | +0.0328 |
| 29 | 242 | 290 | 0.3613 | 0.3898 | +0.0285 |
