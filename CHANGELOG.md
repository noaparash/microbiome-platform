# Changelog

All notable changes to `microplatform`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Before 1.0, a minor version
(0.x) may change the public API, but only with a note under **Changed** or
**Removed** here; see "Public API and stability" in `docs/package-guide.md`.

## [Unreleased]

### Added
- `locate_lightning2`: LOCATE (LOCATE-model 0.0.3) converted to Lightning 2, so it
  runs natively on Python 3.13. Six marked changes, listed in its CHANGES.md; the
  model's logic is unchanged. Validated against the original in a Python 3.10
  reference environment (`validation/locate/`): with the original's one source of
  run-to-run noise removed in both, the conversion is **bit-identical** (V1′). The
  product-vs-original check (V2) awaits an approved rule.
- LOCATE's engine, not enabled yet (`engines/locate.py`, `core/metabolites.py`):
  metabolite-table checks and the paper's metabolite preparation (relative → log →
  z-score; log base and pseudocount provisional). It runs `locate_lightning2`
  in-process.
- Dependency: `pytorch-lightning>=2.2,<3` (already installed with MIPMLP).

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
