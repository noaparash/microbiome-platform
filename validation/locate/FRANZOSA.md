# LOCATE on a real dataset: FRANZOSA (IBD, 2019) vs the paper

The platform's LOCATE (Python 3.13, `locate_lightning2`) on FRANZOSA_IBD_2019 from the Borenstein
curated microbiome-metabolome collection, compared with what the LOCATE paper reports for the
same dataset. This is a check against the paper's *published figure*, not against the authors'
own run (that still needs Oshrit's results and settings). LOCATE stays hidden ("Planned").

## The data

Source: github.com/borenstein-lab/microbiome-metabolome-curated-data (MIT licence),
`data/processed_data/FRANZOSA_IBD_2019/`, current release (species counts added 2024-01-29;
species table release 2023-02-07; metabolite table 2022-06-17).

| File | Content | Used as |
|---|---|---|
| `species.counts.tsv` | 220 samples × 55,882 species, integer read counts (median 22.5 M reads/sample, 85% zeros); each column name is the 7-rank GTDB lineage `d__…;p__…;…;s__…` | the counts table |
| `mtb.tsv` | 220 samples × 8,848 metabolites, non-negative intensities, no missing values, 27% zeros | the metabolite table |
| `mtb.map.tsv`, `metadata.tsv` | metabolite annotations; 88 CD, 76 UC, 56 controls, one sample per subject | not used |

All 220 samples are in both tables. The conversion (`borenstein_to_platform.py`) is mechanical:
ID first, one column per taxon (t1…t55882), and a last row `taxonomy` holding the lineage; the
metabolites are copied unchanged. Both tables pass the platform's own checks with no issues.

## The paper's number (the target)

The paper gives no number in its text for FRANZOSA; LOCATE's result is only plotted:
supplementary Fig. S1A, a box plot of per-metabolite Spearman correlations (measured vs
predicted, 20% test set). Read from the figure's pixels (axis 50 px per 1.0; reading
uncertainty about ±0.02): **median ≈ 0.44, quartiles ≈ 0.30-0.54, whiskers ≈ 0.04-0.76**, and
practically no metabolite below 0.

How that figure was built (the authors' analysis code, LOCATE_all_analysis,
`Fig_3/swarm_plot_different_models_metab_predictions.py`, `choose_best_config`): it loads 16
LOCATE result files per dataset and keeps, **per metabolite, the best correlation of the 16**.
What the 16 are (configurations, splits or seeds) is not stated.

## Reconstructed preprocessing and every assumption

1. **Data version.** The current release, the only one with read counts. The paper's Table S2
   lists FRANZOSA with **8,848 metabolites (matches)** but **9,154 species**, which matches no
   version of the collection (163 in Jan 2022, MetaPhlAn; 34,754 in Feb 2022 and 55,882 since
   Feb 2023, GTDB). The paper probably used relative abundances (`species.tsv`; the counts
   were added after the paper) and possibly a filter; neither can be reconstructed.
2. **Microbiome**, as in the paper's Methods: MIPMLP, species level, sub-PCA,
   log10(count + 0.1), then a z-score per taxon (the platform's shared table plus
   `z_scoring="col"`). 55,882 taxa → **44,195 features** (MIPMLP drops taxa in < 1% of samples).
   Open: the authors' analysis repo names files `…_log_subpca_zscore_row`, which in MIPMLP
   means a z-score per *sample*.
3. **Metabolites**, as in the Methods: relative (each sample sums to 1) → log → z-score per
   metabolite. The log base (10) and the value added before the log (1e-6) are the platform's
   **placeholders**; the paper gives neither, and 27% of values are 0 here. All 8,848
   metabolites were used (none constant). The analysis repo's loaders for *other* tools used a
   "classified" (grouped) FRANZOSA metabolite table and filled missing values with the table
   mean; whether LOCATE did is unknown.
4. **Split and hyperparameters.** The engine's single 80/20 split (`random_state=42`):
   176 training, 44 test samples; the test samples also serve as the early-stopping set (as in
   micrOS). The authors' default hyperparameters; the paper tuned each dataset with NNI, and
   Table S3 gives values only for the 16S datasets.
5. **Measure.** Spearman per metabolite on the 44 test samples, summarised as in the figure
   (median and quartiles; the mean is also reported).

## Results (`franzosa_locate.py`; full numbers in locate-reference/franzosa-results/summary.json)

| | Median | Quartiles | 5th-95th percentile | Below 0 | Mean |
|---|---|---|---|---|---|
| **Paper, Fig. S1A** (best of 16 per metabolite, read from the figure) | **≈ 0.44** | ≈ 0.30-0.54 | (whiskers ≈ 0.04-0.76) | ≈ 0% | — |
| **Platform, best of 16 per metabolite** (same construction; training seeds 0-15, same split) | **0.495** | 0.366-0.611 | 0.209-0.758 | 0.01% | 0.489 |
| **Platform, one run (the engine as shipped)** | **0.365** | 0.192-0.518 | −0.022-0.696 | 6.4% | 0.351 |
| Platform, each of the 16 single runs | 0.277-0.408 (mean 0.355) | | | | 0.270-0.389 |

Engine run: 114 epochs, 17 s; MIPMLP preprocessing about 8 minutes (cached afterwards).

## Reading

- **Built the way the paper's figure was built, the platform's LOCATE reproduces the published
  result on FRANZOSA**: the same shape (no metabolites below 0 to speak of, a similar spread)
  and a median about **0.05 higher** than the paper's ≈ 0.44. The difference is within what the
  known deviations can explain (a different data version with 5× more species, placeholder
  metabolite settings, default instead of tuned hyperparameters, and what the 16 runs are).
- **The paper's figure is optimistic by construction.** Taking, for every metabolite, the best
  of 16 correlations measured on the same test samples raised the median from 0.355 (a typical
  single run) to 0.495 here. A single run, which is what a user of the platform gets, has a
  median of **0.365** on FRANZOSA.
- This supports, but does not replace, the check against the authors' own results (V3): it
  compares with a published figure, read from pixels, under reconstructed settings.

## For the LOCATE authors

The figure's best-of-16-per-metabolite construction should be stated in the paper, or a
single-run (or mean-of-runs) result reported beside it; on FRANZOSA it changes the median by
about +0.13.
