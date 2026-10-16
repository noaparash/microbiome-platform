# Microbiome Platform

One web platform that combines five microbiome-analysis tools from
Prof. Yoram Louzoun's lab. It works out which tool fits your data and your
question, and asks you for as little as possible.

| Tool | What it answers |
|---|---|
| **MIPMLP** | Preprocessing: turns raw counts into a clean table every tool uses |
| **iMic / gMic** | *What predicts my outcome?* |
| **miMic** | *Which bacteria differ between my groups?* |
| **GIMIC** | *How similar are my samples, and how do they group?* |
| **LOCATE** | *How do my bacteria relate to my metabolites?* |

> **Status:** early development (version 1: MIPMLP end-to-end).

## Quick start (Windows, PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

Instructions for running the web app will be added in a later step.

## Project layout

```
src/microplatform/
  core/       dataset model, auto-profiler, MIPMLP preprocessing
  engines/    one adapter per tool (all share one interface)
  router/     picks tools from the data and the user's goal
  reports/    unified results and reproducible reports
  web/        Flask app (pages, templates, styles)
tests/        automated tests and small sample data
docs/         documentation
```

## Citing the underlying tools

- MIPMLP: Jasner et al., *Frontiers in Immunology* (2021)
- iMic: Shtossel et al., *Gut Microbes* (2023)
- miMic: Shtossel, Finkelstein & Louzoun, *Genome Biology* 25:113 (2024)
- GIMIC: Shtossel & Louzoun, *Genome Biology* 26:350 (2025)
- LOCATE: Shtossel et al., *Microbiome* 12:24 (2024)
