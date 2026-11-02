# LOCATE-model 0.0.3: findings for the authors

Found while validating a Lightning 2 / Python 3.13 version of LOCATE against the
original (see PROTOCOL.md and RESULTS*.md in this folder). The original was run unchanged
in a reference environment: Python 3.10.11, torch 1.13.0+cpu, pytorch-lightning 1.8.3,
pandas 1.3.5, on Windows (x86-64).

## 1. LOCATE is not reproducible, even with a fixed seed

The same data, the same seed and the same environment, run twice, gave different models.
On the authors' `usage_example.py` recipe the predictions differed by up to 3e-4; on a
structured example (257 samples) one run stopped at epoch 343 and the next at 279, with
predictions differing by up to 2.2. Across three runs of the same seed, the mean test
Spearman varied by about 0.03.

**Cause:** `torch.linalg.lstsq` (torch 1.13, default driver `gelsy`, CPU), which LOCATE
calls at every training step in `find_transformer`. For an identical input it sometimes
returns an answer that differs in the last digit (about 1.5e-7; 2-3 different answers in
200 calls). Training for hundreds of epochs, with early stopping, magnifies that into a
different model. Single-threading and `MKL_CBWR=COMPATIBLE` did not remove it. With
`driver="gels"`, `"gelsd"` or `"gelss"` the answer is always the same, and LOCATE then
reproduces itself exactly. In torch 2.14 the default driver gave the same answer in 200
calls.

To see it: `lstsq_repeat.py` (200 identical calls), `repeat_check.ps1` (whole runs twice).

## 2. The pinned dependency versions do not work together

LOCATE-model 0.0.3 pins `torch==1.13.0` and `numpy==1.21.6`. The torch 1.13.0 builds
available today were compiled against numpy ≥ 1.23 (C API version 0x10; numpy 1.21 is
0xe), so with numpy 1.21.6 `tensor.numpy()` fails and `LOCATE_predict` raises
`RuntimeError: Numpy is not available` (training itself runs). The reference environment
therefore used **numpy 1.23.5**, the smallest change that runs; everything else was
exactly as pinned. Separately, `pytorch-lightning==1.8.3` can only be installed with
pip < 24.1, because its metadata has a non-standard specifier (`torch>=1.9.*`).

## Smaller points

- micrOS: `import LOCATE` is commented out, so its LOCATE option would fail; it passes the
  metabolite table without the log and z-score that `LOCATE_training` expects; and it uses
  the test samples as the early-stopping validation set.
- `neurons2` sizes the (unused) discriminator, but supplementary Table S3 lists it as
  "Number of neurons layer 2".
- The LICENSE file's copyright line is the packaging template's ("The Python Packaging
  Authority"), not the authors'.
- Lightning 2 removed automatic optimization with several optimizers, so LOCATE cannot run
  on Lightning 2 unchanged. `locate_lightning2` (microplatform repository) is a conversion
  that gives bit-identical results to the original when lstsq is made repeatable in both.

## Result of the Python 3.13 validation (for information)

The conversion is bit-identical to the original when lstsq is made repeatable in both
(10/10 runs, every training step traced). The Python 3.13 product (torch 2.14) against
the original as published (torch 1.13), on 20 new seeds: mean test Spearman 0.3804 vs
0.3816, difference −0.0013, 90% CI [−0.0193, +0.0168]: equivalent within ±0.02, with no
systematic direction.

## From reproducing FRANZOSA (FRANZOSA.md)

- **Fig. 3 / Fig. S1 show the best of 16 runs per metabolite.** The analysis code
  (`choose_best_config`) keeps, for every metabolite, the highest of 16 test-set correlations.
  On FRANZOSA this construction raised the median from about 0.36 (a single run) to about 0.50.
  It should be stated in the paper, or a single-run (or mean-of-runs) result shown beside it.
- **Table S2's species count for FRANZOSA (9,154) matches no version** of the Borenstein
  collection (163, 34,754 or 55,882 species). Which version and filter were used?
- With the current collection, the platform's LOCATE built like Fig. S1A gives a median of
  0.495 (paper ≈ 0.44, read from the figure).
