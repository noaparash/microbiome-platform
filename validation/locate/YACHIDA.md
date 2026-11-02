# LOCATE on a real dataset: YACHIDA (colorectal cancer, 2019) vs the paper

The platform's LOCATE (Python 3.13, `locate_lightning2`) on YACHIDA_CRC_2019 from the Borenstein
curated microbiome-metabolome collection, compared with what the LOCATE paper reports for the same
dataset. This is the second dataset under the revised validation standard (PROTOCOL.md, "Revised
validation standard"): a like-for-like comparison with the paper's published figure, with every
reconstructed setting documented. The procedure was fixed before running (commit fe7f01a) and is
exactly FRANZOSA's (FRANZOSA.md). LOCATE stays hidden ("Planned") until the owner has reviewed it.

## The data

Source: github.com/borenstein-lab/microbiome-metabolome-curated-data (MIT licence),
`data/processed_data/YACHIDA_CRC_2019/`, current release (`main` at commit 89a519d8; metabolite
table from 2022-01-13, never changed since; species counts added 2024-01-29).

| File | Content | Used as |
|---|---|---|
| `species.counts.tsv` | 347 samples × 57,702 species, integer read counts (median 32.9 M reads/sample, 85% zeros); 7-rank GTDB lineage as column names | the counts table |
| `mtb.tsv` | 347 samples × 450 metabolites (targeted, KEGG-named), non-negative, no missing values, **60% zeros** | the metabolite table |
| `mtb.map.tsv`, `metadata.tsv` | annotations (439 of 450 high-confidence); 127 healthy, 220 with findings from polyps to stage III-IV cancer | not used |

All 347 samples are in both tables. Converted with `borenstein_to_platform.py` (unchanged); both
tables pass the platform's checks with no issues (`dataset_check.py`). MIPMLP: 57,702 taxa →
**43,166 features** in 872 s (cached afterwards).

## The paper's number (the target)

As for FRANZOSA, the paper gives no number in its text; the result is supplementary **Fig. S1E**, a
box plot of per-metabolite Spearman correlations on the 20% test set. Read from the figure's pixels
(axis ticks 0.0 at y = 812.1 and 0.5 at y = 775.5, about 73 px per 1.0, so reading uncertainty about
±0.02): **median ≈ 0.22, quartiles ≈ 0.16-0.30, whiskers ≈ −0.03 to 0.51**, a few outliers down to
≈ −0.1 and up to ≈ 0.56.

How the figure was built: the authors' analysis code (LOCATE_all_analysis,
`Fig_3/swarm_plot_different_models_metab_predictions.py`) keeps **per metabolite, the best of 16
runs** (`choose_best_config`). Its last saved setting is `list_of_pairs = ["YACHIDA_CRC_2019"]`, so
this exact code made the YACHIDA panel.

## Reconstructed preprocessing and every assumption

1. **Data version.** The current release, the only one with read counts. The paper's Table S2 lists
   YACHIDA with **16,383 species and 174 metabolites; neither matches** the collection. Species: 500
   (Jan 2022, MetaPhlAn), 470 (Jan-Feb 2022), 42,143 (Feb 2022 - Jul 2023, GTDB, relative) and 57,702
   (counts, since 2024). Metabolites: 450 in the only version ever published. The authors' loaders for
   other tools read their own `Data/YACHIDA_CRC_2019/metab.csv`, which is not in their repository.
   **How the 174 were chosen cannot be reconstructed.** No simple detection filter gives exactly 174:
   detected in ≥ 40% of samples → 187, ≥ 50% → 164; the 174th and 175th most detected tie at 45.5%
   (`yachida_filters.py`).
2. **Microbiome**, as for FRANZOSA and the paper's Methods: MIPMLP species level, sub-PCA,
   log10(count + 0.1), z-score per taxon. The same open question: the analysis repo's file names
   (`tax7_log_subpca_zscore_row`) suggest a z-score per *sample*.
3. **Metabolites**, as in the Methods: relative → log → z-score per metabolite, with the platform's
   **placeholders** for the log base (10) and the value added before the log (1e-6). This matters
   more here than for FRANZOSA: 60% of the values are 0. 4 metabolites are 0 in every sample and are
   left out (446 remain). **36 more cannot be scored** because they are never detected in any of the
   70 test samples (their correlation is undefined); 410 are scored.
4. **Split and hyperparameters**: the engine's single 80/20 split (`random_state=42`): 277
   training, 70 test samples, the test samples also used for early stopping (as in micrOS); the
   authors' default hyperparameters (Table S3 gives tuned values only for the 16S datasets).
5. **"16"**: 16 training seeds (0-15) on the same split, as for FRANZOSA; the code does not say
   whether the paper's 16 were configurations or seeds.
6. **Main comparison = all metabolites**, as for FRANZOSA. Because the paper used 174, one
   sensitivity run keeps the 174 metabolites detected in the most samples (`--top-detected 174`).
   It is a guess at the paper's filter, reported beside the main result.

## Results (`dataset_locate.py`; `yachida/summary.json`, `yachida/summary-top174.json`)

| | Median | Quartiles | 5th-95th percentile | Below 0 | Mean |
|---|---|---|---|---|---|
| **Paper, Fig. S1E** (best of 16 per metabolite, read from the figure) | **≈ 0.22** | ≈ 0.16-0.30 | (whiskers ≈ −0.03-0.51) | ≈ 0% | — |
| **Platform, best of 16 per metabolite** (all 410 scored) | **0.276** | 0.201-0.377 | 0.103-0.571 | 0.2% | 0.299 |
| **Platform, one run (the engine as shipped)** | **0.144** | 0.031-0.272 | −0.141-0.501 | 21% | 0.159 |
| Platform, each of the 16 single runs | 0.119-0.187 (mean 0.150) | | | | 0.120-0.182 |
| *Sensitivity, 174 most detected:* best of 16 | 0.359 | 0.262-0.459 | 0.147-0.661 | 0% | 0.370 |
| *Sensitivity, 174 most detected:* one run | 0.155 | 0.030-0.309 | −0.133-0.520 | 21% | 0.175 |

Engine run: 155 epochs, 34 s.

## Reading

- **Built the way the paper's figure was built, the platform's LOCATE reproduces the published
  YACHIDA result**: the same shape (almost nothing below 0, a similar spread) and a median about
  **0.06 higher** than the paper's ≈ 0.22. That is the same direction and size as on FRANZOSA
  (+0.05), and within what the known deviations can explain (a different data version, different
  metabolites, placeholder metabolite settings, default hyperparameters).
- **YACHIDA is much harder to predict than FRANZOSA** (best-of-16 median 0.28 vs 0.50), in the
  paper as in ours. The ranking between datasets is reproduced too.
- **The same inflation on both datasets.** Best-of-16 raised the median from 0.150 (a typical single
  run) to 0.276: **+0.13**, as on FRANZOSA (+0.13). A user of the platform gets one run: on YACHIDA
  the median is **0.14**, and about a fifth of the metabolites are predicted worse than chance
  (correlation below 0).
- **The sensitivity guess does not explain the 174.** Keeping the 174 most detected metabolites moves
  the best-of-16 median *away* from the paper (0.36 vs ≈ 0.22). Whatever the authors' filter was, it
  was probably not "most often detected"; the main comparison (all metabolites) is the closer one.

## For the LOCATE authors

- The best-of-16 construction inflates the published medians by about 0.13 on both FRANZOSA and
  YACHIDA; a single-run (or mean-of-runs) result should be shown beside it.
- Table S2's YACHIDA counts (16,383 species, 174 metabolites) match no version of the collection;
  which metabolites were used, and how were they chosen?
