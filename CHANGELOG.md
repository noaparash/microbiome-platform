# Changelog

All notable changes to `microplatform`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Before 1.0, a minor version
(0.x) may change the public API, but only with a note under **Changed** or
**Removed** here; see "Public API and stability" in `docs/package-guide.md`.

## [Unreleased]

### Removed
- The website's dark mode: the site is always light, whatever the computer's setting (the figures were
  already drawn in the light palette).

### Changed
- Composition (bars and pie, at every level): every taxon found gets its own colour (no "Other", no top 12;
  past the palette, generated colours, never grey). The legend lists them up to 20 (`composition.LEGEND_MAX`);
  with more, there is none (`Figure.legend`): hover names a segment and the CSV lists every one. Only past
  `composition.MAX_TAXA` (1,500) would the rest be summed as "Other (named, rare)". The split violins keep the
  12 most abundant. Bars draw only the segments there are, as one collection, so a thousand species still
  take seconds.
- The results page opens composition at the run's taxonomy level (species unless chosen; phylum for a
  table used as it is), not always at phylum.
- The two sparsity figures (taxa per sample, prevalence) count taxa at the run's level
  (`overview_figures(..., level=)`, `overview.level_table`): columns added up by lineage, as MIPMLP groups
  them. Alpha and beta diversity stay on the table as uploaded.

### Fixed
- The lab palette listed one colour (#ccebc5) twice, so two taxa could share it.

### Added
- A taxonomy level per run, for every tool: the Plan step offers phylum down to the deepest rank the
  table names for most taxa, and species (the default, unchanged); `mp.analyze(..., taxonomy_level="genus")`
  does the same. MIPMLP groups the bacteria at that level and every tool uses that table. Below species,
  miMic runs its test and shows its results, but not its own cladogram and real-vs-shuffled figure
  (the authors' plot code needs species level). At phylum and class, iMic's and GIMIC's results say
  that the few features make them less informative; at phylum, GIMIC's distances are undefined, so it
  stops with a message. The reproducibility record says at which level the tools were reproduced
  against the authors' published results (species).
- Composition at finer levels: the data overview's "Show composition at" switch shows the composition
  bars and pie at phylum (the default, unchanged) or at any finer rank the table names (class to
  species), all drawn with the run from the uploaded table. Below phylum: the 12 most abundant taxa,
  "Other (named, rare)" and "Not named at <rank>" (so each bar is still 100% of the sample); names as in
  the table, with the family added where two share a name. The analysis is not affected.
- Look at one taxon: on the results page, under the composition figures, pick a level (those the composition
  was drawn at) and a taxon from a searchable list (named taxa only, most abundant first) to draw it on demand:
  one bar per sample (its % of the sample's whole total, reads on hover), and with groups a box per group with
  every sample as a dot; "Found in X of N samples; mean, median". Descriptive, no test; PNG, SVG, interactive
  and CSV (% and reads). Package: `composition.taxon_choices`, `composition.taxon_abundance`,
  `overview.taxon_figures`, `workflows.taxon_choices` / `look_at_taxon` / `taxon_lookup`; `Figure.hover_data`.
  The latest 8 taxa drawn are kept per run (in the run's figures folder; not in the results ZIP).

### Fixed
- Results page: a chart that sets its own height (miMic's taxa bars, the RP vs SP check) no longer
  runs past its box over the caption and the download links.
- `mp.analyze(..., out_dir="runs")` with a relative folder crashed for iMic (the engines change into
  their work folder); work folders are now absolute.
- LOCATE's summary no longer calls a correlation above 0 "better than chance" (no test was made).

### Changed
- Phylum composition (bars, pie and the comparison violins) is now in % of each sample's whole total, as at the
  finer levels: abundance with no phylum (and a phylum written as unassigned, uncultured, unknown, …) is the
  light-grey segment "Not named at phylum", no longer left out with the rest scaled up to 100%. A table that
  names a phylum everywhere draws exactly as before. `phylum_percent` adds the column "Not named at phylum"
  (only if some sample has any), keeps samples that have reads but no phylum, and reports `not_named_percent`
  (= `unassigned_percent`); `top_phyla` puts it last, after "Other".
- Look at one taxon, at phylum: the list uses the phylum figures' own phyla, names and shares (an old and a
  new name of one phylum appear as the name the table uses more, e.g. Patescibacteria, not TM7).
- Every figure caption says what the figure shows, how to read it, and what kind of result it is
  (a tool's statistical test, exploratory tests, model performance, or descriptive). The fine print
  (method, settings, provenance) moved to a new `Figure.details` / `RenderedFigure.details`, shown
  under a closed "Method details" on the page and in the ZIP's `figures/FIGURES.txt`.
- miMic's bar chart explains its score: the centred Mann-Whitney U, which grows with the number of
  samples (compare bars within one figure, not across datasets).
- CLAUDE.md (the assistant's working notes) is no longer in the repository.

### Added
- **Reads vs taxa detected** (data quality, read counts only): one dot per sample, with the low
  regions shaded (below 25% of the median reads or taxa, or under 1,000 reads; `profiler.LOW_FRACTION`
  and `MIN_READS`), weak samples coloured and named. The data check lists the same samples as an amber,
  non-blocking warning (`profiler.low_samples`, one rule for both). New figure kind `depth_taxa`;
  `reports.figures.reads_vs_taxa`.
- **MetaPhlAn 4 output (shotgun) as an input** (`core/metaphlan.py`): one file, recognised by its
  `#mpa_…` line or `clade_name` header, with clades as rows or samples as rows, or one sample's profile.
  Only the species are kept (the other ranks are sums of them). Estimated read counts
  (`-t rel_ab_w_read_stats`) are kept as counts; relative abundances (%) are used as they are, and the
  data check states what that limits. The read-count form is switched off (`metaphlan.COUNTS_VALIDATED`)
  until it has been confirmed on a real MetaPhlAn counts file. A phylum-rank `…_unclassified` is counted
  in "Other" in the composition figures.
- Overview composition figures: one phylum, one bar. GTDB variants (`Bacillota_A_368345`) are shown as
  their base phylum, and old/new names of one phylum (Firmicutes/Bacillota) as the one the table uses
  more; the caption says so. Display only (`composition.MERGE_GTDB_VARIANTS`).
- **YaMAS 16S output as an input** (`core/yamas.py`): upload YaMAS's `otu.csv` and `taxonomy.csv`
  together (any names, any order; recognised by their shape), or pass them to
  `mp.analyze(("otu.csv", "taxonomy.csv"), ...)`: `counts` now also takes that pair (a single
  table works as before). They become one counts table with the read counts kept (no
  percentages) and every lineage standardised by the lab's `normalize_taxonomy_name` (copied
  unchanged from `docs/preprocess_16S.py`); OTUs with the same lineage stay separate. The pair
  counts as one input: up to 4 files per upload (was 3). The data check says how the files were read.
- **Group tests on the diversity figures**, as in the lab's reference analysis
  (louzounlab/Early-Pregnancy-Oral-Microbiome), only when the samples form groups
  (`reports/diversity_stats.py`):
  - alpha diversity: the test chosen by Shapiro-Wilk normality per group (Student's t /
    Mann-Whitney U; with more groups an overall one-way ANOVA / Kruskal-Wallis plus every
    pair), Benjamini-Hochberg (FDR) correction, significance brackets (*** ** * ns) on the
    corrected p-values, Cohen's d, each panel titled with its test;
  - beta diversity: PERMANOVA (scikit-bio, 999 permutations, seed 42) with pseudo-F and p in
    the subtitle, η² (between/total sums of squares on all PCoA axes) and PERMANOVA's R²,
    PERMDISP (scikit-bio, spatial medians, on a PCoA with every axis) in the caption, and
    95% normal-theory ellipses per group;
  - each figure's tests saved as `<figure>_tests.csv`, linked as "Tests (CSV)" and in the
    results ZIP. Groups with fewer than 3 samples are not tested.
- Figure options `brackets`, `panel_titles`, `ellipses`, `subtitle` and `stats`;
  `figures.ellipse_outline`.
- **uv**: `uv.lock` pins every dependency at the version the tests and validations ran
  with (`[tool.uv] constraint-dependencies` holds back 17 packages where newer releases
  exist), `.python-version` = 3.13, and PyTorch comes from the CPU-only index
  (`[tool.uv.sources]`). `uv sync` installs the package, the website and the tests (a `dev`
  dependency group); `uv run flask --app microplatform.web run` starts the site.
- Dependency: `scikit-bio>=0.7.4,<0.8` (a Python 3.13 wheel; adds biom-format, h5py and
  requests).
- `engines/mimic_authors.py`: miMic's full standard output bundle, made by the authors'
  own code from end to end (`apply_mimic` test mode with `samba.micro2matrix`, then plot
  mode): their result tables (`df_corrs.csv`, `miMic&Utest.csv`, `u_test_without_mimic.csv`,
  `just_mimic.csv`), their diagnostic plots and their cladogram (`correlations_tree` as SVG,
  PNG and PDF). One run per seed plus a repeat of the main seed, so the effect of miMic's
  label shuffling is visible; `run.json` records versions, input checksums, settings, the
  authors' function behind each output and the library adjustments. Command line:
  `python -m microplatform.engines.mimic_authors processed.csv tag.csv out_dir`. Not used
  by the website.
- `reports/composition.py`: phylum composition in the lab's figure style (the fig_1B scripts
  in `references/composition/`). Reads counts or relative tables, with lineage columns or
  MetaPhlAn's every-rank rows (only the phylum rows are used); drops columns with no phylum
  (Bacteria, Archaea, Unassigned, Unclassified) and samples left empty; values must be
  finite and not negative; every sample is re-normalized to 100%. The top 12 phyla by mean,
  the rest "Other" (#BDBDBD, drawn last). One colour per phylum across figures and datasets
  (fixed slots for common gut phyla, old and new names alike). Figure kinds `composition`
  (samples and their mean, 5:1, legend below, the dataset's name as heading, 300 dpi) and
  `violin` (split violins per phylum, two groups).
- `overview_figures(..., dataset=None, palette="lab", split_violin=False)`: the heading of
  the composition figure; `palette="colorblind"` for a colour-blind-safer 12-hue set (the
  default "lab" is tab20 + Set3 + Pastel1 without their greys); `split_violin=True` adds the
  per-phylum split violins when the samples form two groups.
- **Counts tables with the taxonomy in the column names** (no `taxonomy` row): every column
  after the sample IDs named by its lineage (`k__Bacteria;p__;c__…`, empty ranks allowed; at
  least `MIN_LINEAGE_SHARE` = 90% of the columns). `sort_uploads` (and so the website and
  `mp.analyze`) adds the `taxonomy` row from the names exactly as written and reads the result
  as a combined upload, so everything downstream is unchanged; `Inputs.counts_layout` is
  `"headers"` and the data check says so. New in `core.inputs`: `is_lineage`,
  `with_taxonomy_row`. Faithfulness (test_reproduction.py): the authors' example re-expressed this
  way (40 and all 257 samples, and a variant with a repeated lineage) gives exactly the
  combined format's preprocessed table.
- **A table without labels is explained in the Plan**: what runs without labels (MIPMLP,
  GIMIC, the descriptive data overview) and what a labels file or a metabolite table would add.

### Added
- **miMic's own cladogram** is the headline miMic figure (`mimic_cladogram`: the authors' SVG and PNG
  unchanged, an HTML page showing the SVG, and the significant taxa as CSV). It is drawn by mimic-da's
  own code: the final call of `apply_mimic(mode="plot")`,
  `calculate_all_imgs_tag_corr(mode="plot", colorful=True)` → `creare_tree_view` (ete3), with the
  recorded `mimic_authors.ADJUSTMENTS`; the rest of plot mode (16 more test passes that feed only its
  other diagnostic plots) is skipped. Reproduction test: byte for byte the SVG that the authors' whole
  plot mode writes. New `figures.RenderedFigure` / `export_rendered` (a tool-drawn figure, copied, never
  redrawn) and `EngineResult.rendered`; checked on the headless Linux server (Qt offscreen).

### Changed
- **Never preprocessed twice by default (correctness).** A table that already looks preprocessed
  (`CountsProfile.looks_preprocessed`: negative values, or samples adding up to different totals,
  such as MIPMLP output or a table prepared for miMic) is used **as it is**
  (`preprocessing.use_as_is`, record `{"tool": "none", "skipped": true, "why": …}`): MIPMLP is not
  run on it again. The data check says so and lets the user choose MIPMLP instead
  (`workflows.set_preprocessing`, `POST /runs/<id>/preprocessing`, meta `preprocessing`).
  Tasks that need MIPMLP's own run are switched off with a reason ("Just preprocess"; LOCATE, which
  z-scores each taxon), as are the advanced settings (GIMIC's "mean" grouping). New:
  `mp.analyze(..., preprocessing=None | "as_is" | "mipmlp")`, `build_dataset(..., as_is=False)`.
  MIPMLP's own output names (`Bacteria;…;Lachnospiraceae_0;;`, no `k__` prefixes) are now
  recognised as taxonomy in the column names, so MIPMLP output can be uploaded. Found on a real
  run: a table prepared for miMic was preprocessed again (64 → 49 features) and miMic found 42 taxa;
  used as it is, it gives exactly the authors' 34 (`just_mimic.csv`), with identical p-values. Tables
  with negative values get no descriptive overview (it needs abundances; the page says why).
- **miMic's headline is its own tree test.** "N taxa are significant" used to count miMic's taxa together
  with those found only by the plain per-leaf test (the authors' `df_corrs.csv` = `just_mimic.csv` +
  `u_test_without_mimic.csv`). Now the headline, the `significant_taxa` table, the bar figure and the
  record count miMic's tree test only (= `just_mimic.csv`); the leaf-only taxa are a separate
  `leaf_test_only` table, mentioned in one sentence. The reproduction test checks both files.
- **miMic's RP vs SP check, redrawn in the platform's style** (`mimic_rp_sp`, "Is miMic's result more than chance?"): grouped bars per starting level (real labels teal, shuffled orange), each count written on its bar, a linear scale (miMic's log scale drew no bar for 0), and the levels the a-priori test passed on a grey band. The numbers are miMic's own (the table it passes to `plot_rp_sp_anova_p`; a test checks they are equal), and miMic's own drawing ships beside it unchanged as "miMic's original" (`mimic_rp_sp_original.png/.svg`, byte for byte the authors'). The seed, the shuffle and the band are in the record (`rp_sp_check`). New in `reports.figures`: kind `grouped_barh` (`shade`, `shade_label`) and `Figure.originals` / `original_label` (a tool's own drawing offered as extra downloads).
- **miMic's RP vs SP check is the authors' own figure** (`mimic_rp_sp`, their `tax_vs_rp_sp_anova_p`), replacing our `mimic_apriori_test` bar chart. The engine now runs miMic's whole plot mode (`apply_mimic(mode="plot")`, seed 42, as `engines/mimic_authors.py`), which draws both this plot (`plot_rp_sp_anova_p`) and the cladogram; byte for byte the authors' figures (reproduction test). It comes after the significant-taxa bars, at its own size, in `figures/1_result/`; PNG + an SVG of the same matplotlib figure; its CSV has RP and SP per starting level. The a-priori p-values stay in the summary and the `apriori_test` table. `RenderedFigure` gained `lead` and `wide`. Where Times New Roman (which miMic asks for) is missing, its metric-compatible clone Nimbus Roman is used, and matplotlib's settings are restored after miMic (it changed them globally).
- **miMic's cladogram in the lab's reference proportions** (a declared readability change from mimic-da 1.0.1, matching the colleague's rendered tree): every node marker is at most 57 units across (`TREE_MARKER_MAX`; the colleague's largest marker is ~0.57 of the label size), where miMic sizes them 17 × −log10(p) with no limit (2,338 units on a p = 1e-137 taxon, which stretched the tree so its 100 pt labels were ~4 px tall). Labels stay at miMic's 100 pt; the circle is closed (ete3's default 359° left a wedge cut out). Shapes, fills, colours and taxa are miMic's. Recorded as `tree_markers` and `tree_closed`.
- **miMic's cladogram PNG** is 180 mm at 300 dpi (2,125 px, as the lab's reference); ete3's default was
  the SVG's size in pixels (73,630 px square on a 64-taxon tree).
- **The result first, the descriptive overview last, everywhere:** the overview is headed
  "Descriptive overview of your data (not the analysis result)", and the ZIP's figures are in
  `figures/1_result/`, `figures/2_data_quality/`, `figures/3_descriptive_overview/`.
- **Website:** the home page leads with "Start an analysis" (primary) and offers "See an example"
  as the secondary button. In the Plan step the optional "Add a labels file" / "Add a metabolite
  table" boxes now come before Run, under "Have more files? Add them before you run"; the email
  field and Run (last) belong to the run form through `form="run-form"`.
- **Results emails:** a From name ("Microbiome Platform", or `MICROPLATFORM_SMTP_SENDER_NAME`),
  `Date` and `Message-ID` headers, and the plain text with the same words as HTML beside it
  (multipart/alternative; no images, nothing loaded). A link to 127.0.0.1/localhost says it opens
  only on the server or through an SSH tunnel. The worker now logs every outcome (sent, failed,
  or not sent and why) with the address masked (`notify.mask_address`).
- **No sequencing depth for relative abundances.** "Sequencing depth per sample"
  (`reads_per_sample`, and its CSV) is made only when the values are read counts
  (`profiler.value_kind`, now public, the same rule that hides the "Median reads" tile); otherwise
  the results page says why (`CountsProfile.depth_note`). For non-count data the data check no longer
  warns about depth outliers, an all-zero sample is "all zero" (not "no reads"), and the alpha
  diversity caption no longer speaks of reads or raw counts.
- `requires-python` is now `==3.13.*` (was `>=3.13`): every tool is validated on 3.13.
  `torch>=2.14,<2.15` is a direct dependency (LOCATE's validated predictions depend on it).
- The data overview is "mostly descriptive": the two diversity figures with group tests
  end with `EXPLORATORY` ("not corrected across this report, and not a tool's finding");
  every other caption still ends with `DESCRIPTIVE`. The page note and ZIP README say so.
- The composition bars are now the fig_1B layout: every sample sorted by Firmicutes (else
  the top phylum) and one mean bar, no longer grouped by label (the pies still are, and the
  split violins compare two groups). 12 phyla instead of 7, in the lab's palette instead of
  Okabe-Ito. Composition is now the share of phylum-assigned abundance (abundance with no
  phylum is left out and the caption says how much). The pies use the same phyla and
  colours. `overview.relative_abundance` and the `rank`/`top_n` choice of rank were removed
  (internal, not in the public API).
- A table that cannot be relative abundance (negative or non-finite values) gets no
  composition figures instead of wrong ones.
- One phylum→colour map everywhere: `figures.taxon_colors` (used by any per-phylum figure built
  without explicit colours) now returns `composition.phylum_colors`; the old Okabe-Ito fallback
  (`TAXON_PALETTE`) and its separate grey (`OTHER_COLOR`, #BBBBBB) were removed. A test on the
  authors' GIMIC example (16 phyla) checks that bars and pies use the same map and draw "Other"
  grey and last (data, SVG legend and interactive traces).
- Four scoped library adjustments let mimic-da 1.0.1's plot mode run on Python 3.13's
  libraries without changing the package: SciPy 1.18's `kstest(x, 'norm', args=...)` bug,
  matplotlib's removed `cm.get_cmap`, NumPy 2.2's empty-array truth value (in the tree
  drawer only), and no interactive tree window.

## [0.3.0] — 2026-11-04

All five of the lab's tools are now available. LOCATE runs natively on Python 3.13
(a validated conversion of the authors' code), metabolite tables can be uploaded,
every analysis ends with a descriptive data overview, and long runs on the lab
server are never cut short.

### Added
- **LOCATE is available** ("Link bacteria to metabolites"), on the website and in
  the package. Its validation was accepted by the project owner (2026-11-02) under
  the revised standard in `validation/locate/PROTOCOL.md`.
- Metabolite tables as an input: recognised automatically among the uploads (at
  least 3 numeric columns, no `Tag` column, no `taxonomy` row), checked with a fix
  for every problem, addable from the Plan step without starting over, kept in the
  results ZIP (`inputs/metabolites.csv`), and a downloadable template. An uploaded
  metabolite table makes LOCATE the recommended task.
- `Dataset.metabolites` is validated by the contract (string, unique sample IDs
  that all have features; numbers only; no missing values).
- `locate_lightning2`: LOCATE (LOCATE-model 0.0.3) converted to Lightning 2, so it
  runs natively on Python 3.13. Six marked changes, listed in its CHANGES.md; the
  model's logic is unchanged. Validated against the original in a Python 3.10
  reference environment (`validation/locate/`): with the original's one source of
  run-to-run noise removed in both, the conversion is **bit-identical** (V1′). The
  Python 3.13 product is equivalent to the original under the approved rule (V2:
  mean difference in test Spearman −0.0013, 90% CI [−0.0193, +0.0168] within ±0.02,
  no systematic direction). Against the paper's published figures on two public
  datasets (FRANZOSA, YACHIDA; `validation/locate/`), built the same way (best of
  16 runs per metabolite), the medians are about 0.05 above the paper's, with the
  same shape.
- LOCATE's engine (`engines/locate.py`, `core/metabolites.py`): metabolite-table
  checks and the paper's metabolite preparation (relative → log → z-score; the log
  base and pseudocount are not in the paper, so they are a recorded reconstruction:
  log10, 1e-6). It runs `locate_lightning2` in-process. Its summary reports one run
  honestly and says that the paper's figures keep the best of 16 runs per
  metabolite (about +0.13 on the median).
- Dependency: `pytorch-lightning>=2.2,<3` (already installed with MIPMLP).

- `EngineResult.notes`: how to read an engine's findings (limits and caveats),
  kept apart from `summary` and saved in `engine.json` as `"notes"`. iMic, GIMIC
  and LOCATE moved their caveats there; the website shows them in a "How to read
  these results" box under the findings, and the results ZIP's README lists them.
- Website accessibility: a "Skip to content" link on every page; tests that every
  text colour meets WCAG AA (4.5:1) in light and dark mode.
- **Data overview** (`reports/overview.py`), made with every analysis and shown at
  the end of the results page under "Data overview" (labelled "Descriptive, not
  statistical tests"). Every figure comes as PNG (200 dpi), SVG, interactive HTML
  and CSV, and is included in the results ZIP. The figures:
  - stacked composition bars per sample (phylum, the top 7 + "Other"; grouped by
    label, with an average bar per group);
  - composition pies (one per group);
  - alpha diversity (Shannon, richness) as boxes with every sample shown;
  - a beta diversity PCoA of Bray-Curtis distances;
  - row sparsity (taxa per sample).

  Composition and diversity are computed from the raw counts (relative
  abundance), independent of the log preprocessing. The taxon colours use the
  Okabe-Ito palette, and each taxon and each group keeps one colour across
  figures. Samples without reads are left out (the captions say how many). The
  PCoA needs 3 samples that differ. Continuous labels are not grouped.
- Figure kinds `stacked`, `pie` and `box`; `Figure.colors` fixes the colour of each
  value; `ExportedFigure.wide` lets a figure take the whole row.
- A run-time table measured on a laptop (`docs/run-times.md`, made by
  `benchmarks/`): every tool takes under 2 minutes on the example datasets; on two
  large public datasets (about 44,000 features) miMic, iMic and GIMIC take over an
  hour and miMic/GIMIC use 7.5 GB or more, so large datasets need the lab server.

### Changed
- "How widespread each taxon is" (`taxa_prevalence`) moved from "Data quality"
  into the data overview, as its column-sparsity figure, with the same cut-off
  line. `preprocessing_figures` now returns only the sequencing-depth figure.
- Figure legends for groups sit above the plot, clear of the axis title. On
  phones, side legends move below the plot and two-panel figures stack.
- Website polish: numbers in the stat tiles never break mid-number on phones (and
  shrink a little instead); every count is shown with thousands separators
  (55,882); a "Metabolites" tile in the data check; the five question cards sit
  as two and three on wide screens; status badges appear only for a tool that is
  not available; sentence case in the settings lists.
- `mp.analyze` takes `metabolites=` (a metabolite table's path), added last so
  existing calls are unchanged.
- Uploads: up to three files (counts, labels, metabolites). Two files of the same
  kind are refused with a message naming both.
- **Long runs are never cut short.** On `systemctl stop`/`restart` (or a reboot) the
  worker now waits up to 4 hours for the analysis in progress (`TimeoutStopSec=4h`,
  was 30 minutes); nothing else limits a run's time.
- **A running analysis is never wrongly marked "interrupted".** The worker's lock
  now records its host, process ID and process start time, and a run whose heartbeat
  is late is left alone while that same process is still alive (a reused process ID
  does not count). This holds with any number of workers on one server.
- Deployment guide: the lab server needs at least 16 GB of RAM.

### Known limits
- LOCATE's metabolite preparation uses a reconstructed log base and pseudocount
  (log10, 1e-6: not stated in the paper), recorded with every run. One engine run is
  reported, while the paper's figures keep the best of 16 runs per metabolite.
- iMic predicts with dropout on (as published) and takes two-group labels only.
- miMic's categorical mode is broken upstream and is refused with a reason.
- Email notifications are built but off until the lab provides SMTP settings.

## [0.2.0] — 2026-10-28

The package reaches a clean, citable state with four of the lab's five tools.
Each tool runs the authors' own code, unchanged, and each has a reproduction
test against the authors' published example.

### Added
- **miMic** (`goal="differ"`): differential abundance along the taxonomy tree
  (binary or continuous labels). Reproduces the authors' example exactly
  (the same 114 taxa, identical p and scc).
- **GIMIC** (`goal="group"`): distances between all samples, a UMAP map, and
  within/between-group distances. Grouping is selectable
  (`options={"grouping": "mean"}`; the default is sub-PCA, the shared table).
  In mean mode it reproduces the published example exactly.
- **iMic** (`goal="predict"`): prediction from taxonomy-tree images (two-group
  labels, fixed seed). Probabilities are identical to MIPMLP's `apply_iMic`
  (difference 0.0), and the AUC is computed from probabilities.
- The shared data contract (`core/contract.py`, `mp.Dataset`) that every
  engine consumes, enforced by tests.
- Engine options (`EngineOption`); `mp.analyze(..., options=...)`.
- Background runs: a disk queue and a separate worker
  (`python -m microplatform.worker`), results links, and optional email
  (off until SMTP settings are given).
- Lab-server deployment: `microplatform.web.wsgi:app` for gunicorn, systemd
  units, an HTTPS nginx template restricted to the lab network, a settings
  template, and a manual, logged retention command
  (`python -m microplatform.retention`).
- `mp.UserFacingError` in the public API: every problem the package reports to
  a user has a `message` and a `fix`.
- `CITATION.cff` (authors to be confirmed with the lab) and this changelog.

### Changed
- **Flask is now optional.** `pip install microplatform` installs the
  analysis package only; the website needs `pip install "microplatform[web]"`
  (or `[server]` on a Linux server, which adds gunicorn).
- Figures: the interactive files never show plotly's "Share chart" button,
  which would upload the data to Chart Studio.
- Results pages: accessibility and phone/dark-mode fixes.

### Known limits
- LOCATE is not available yet: its published package pins torch 1.13,
  numpy 1.21 and pandas 1.3.5, which do not install on Python 3.13, and its
  reproduction test needs a real microbiome + metabolome dataset.
- iMic predicts with dropout on (as published) and takes two-group labels only.
- miMic's categorical mode is broken upstream and is refused with a reason.

## [0.1.0] — 2026-10-20

The first working version: MIPMLP end to end (not tagged as a release).

### Added
- Data check (`mp.profile_counts`, `mp.profile_labels`): size, taxonomy depth,
  value kind, sparsity, read depth and outliers; problems come with a fix.
- MIPMLP preprocessing with the paper's settings (`mp.CANONICAL`: species
  level, sub-PCA, log), cached and recorded (`mp.preprocess`).
- Figures as PNG, SVG and interactive HTML, each with its data as CSV, and a
  "download everything" ZIP.
- The website: upload, data check, plan, results; templates for the input
  format; a "Just preprocess (MIPMLP only)" option.
- `mp.analyze` for a whole analysis without the website.
