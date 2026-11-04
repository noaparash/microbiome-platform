# Changelog

All notable changes to `microplatform`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Before 1.0, a minor version
(0.x) may change the public API, but only with a note under **Changed** or
**Removed** here; see "Public API and stability" in `docs/package-guide.md`.

## [Unreleased]

### Added
- `engines/mimic_authors.py`: miMic's full standard output bundle, made by the authors'
  own code from end to end (`apply_mimic` test mode with `samba.micro2matrix`, then plot
  mode): their result tables (`df_corrs.csv`, `miMic&Utest.csv`, `u_test_without_mimic.csv`,
  `just_mimic.csv`), their diagnostic plots and their cladogram (`correlations_tree` as SVG,
  PNG and PDF). One run per seed plus a repeat of the main seed, so the effect of miMic's
  label shuffling is visible; `run.json` records versions, input checksums, settings, the
  authors' function behind each output and the library adjustments. Command line:
  `python -m microplatform.engines.mimic_authors processed.csv tag.csv out_dir`. Not used
  by the website.
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
