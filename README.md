# Microbiome Platform

**One platform for the lab's five microbiome tools — it profiles your data, recommends the right method, runs it, and returns clear, reproducible results.**

<!-- Optional badges once decided: license · version · python 3.13 -->

---

## What it is

The lab has five microbiome tools (MIPMLP, iMic, miMic, GIMIC, LOCATE), each solving a different question and each with its own input format and quirks. This platform puts them behind **one interface**: you upload your data once, an automatic **profiler** reads what you have, a **router** recommends *which tool fits your question and why*, and the chosen engine runs — all on a single shared data representation.

It is built **package-first**: all the logic lives in one Python package (`microplatform`), and the website is a thin layer on top. So you can use it either by clicking through the website, or directly from Python.

**Who it's for:** lab members and collaborators analysing microbiome data, including those with no coding background.

---

## The five tools

Every analysis starts with **MIPMLP preprocessing**, then continues to the tool that fits the question.

| Tool | Answers the question… | In one line |
|------|----------------------|-------------|
| **MIPMLP** | "Clean and standardise my data" | Preprocessing: builds a taxonomy tree of log-frequencies, groups related taxa (sub-PCA), and filters rare taxa. The shared foundation every other tool starts from. |
| **iMic** | "Can the microbiome *predict* my label?" | Turns each sample into an image of its taxonomy tree and runs a convolutional neural network to predict a binary outcome. |
| **miMic** | "*Which bacteria* differ between my groups?" | A multi-layer statistical test that walks the taxonomy tree and finds the taxa associated with a label, with multiple-testing correction. |
| **GIMIC** (SAMBA) | "*How similar* are my samples, as a whole?" | Computes microbiome distances between samples for comparison and grouping. |
| **LOCATE** | "Link microbiome to *metabolites*" | A latent model that connects the microbiome to the metabolome and predicts metabolite levels. |

---

## Install

Setup is just a few commands, and **[uv](https://docs.astral.sh/uv/)** does the hard part for you — it builds a clean, isolated environment for this project alone, so nothing touches the rest of your machine. Install uv once:

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then grab the project and let uv build everything:

```bash
git clone https://github.com/noaparash/microbiome-platform.git
cd microbiome-platform
uv sync          # installs Python 3.13 + every dependency from the lock file
```

> That's it — `uv sync` reads `pyproject.toml` and `uv.lock`, so everyone gets exactly the same tested setup, Python 3.13 included.
>
> **Prefer uv.** `pip install -e ".[web]"` also works, but pip doesn't read `uv.lock`, so it may install newer, untested versions.

---

## Quick start

**Through the website** (point-and-click: upload → data check → recommended plan → results):

```bash
uv run flask --app microplatform.web run
# then open http://127.0.0.1:5000
```

**From Python:**

```python
import microplatform as mp

view = mp.analyze("counts.csv", "labels.csv", goal="differ", out_dir="runs")
print(view.status)              # "done"
print(view.engine["summary"])   # findings in plain sentences
# everything is written under view.run.path: the cleaned table,
# tables/, every figure (PNG, SVG, interactive HTML, CSV), and the settings records.
```

`goal` selects the tool: `"preprocess"` (MIPMLP), `"differ"` (miMic), `"predict"` (iMic),
`"group"` (GIMIC), or `"metabolites"` (LOCATE — also pass `metabolites="metabolites.csv"`).
Omit it to use the recommended task. Data problems raise `mp.UserFacingError` with a clear
message and a fix.

---

## How it works

```
your data ──▶ Profiler ──▶ Router ──▶  Engine (iMic · miMic · GIMIC · LOCATE)  ──▶ Results
                                │
                         MIPMLP preprocessing
                      (one shared representation,
                        computed once, cached)
```

- **Profiler** — detects what you have (labels? metabolites?) and summarises the data.
- **Router** — recommends the fitting tool *and explains the reason you see*.
- **Shared data contract** — every engine receives the exact same representation; an automated check fails if any tool deviates.
- **Background runs** — long analyses run as queued jobs, so the website stays responsive.

---

## What you get back

Every analysis returns a tidy results bundle — shown on the website and downloadable as a single ZIP. It's made to be understood even if you've never used these tools before.

**The figures.** Each figure comes four ways: a **PNG** to look at or drop into a slide, an editable **SVG**, an **interactive HTML** version (opens in any browser, works offline), and the **CSV** of the exact numbers behind it. You get:

- **The tool's findings** — for example, miMic's *"which bacteria differ between the groups"*: a bar chart where each bar is a bacterium, coloured by the group it's higher in, so the result is clear at a glance.
- **A friendly overview of your data itself:**
  - **Composition** — what each sample is made of, broken down by phylum.
  - **Diversity** — *alpha* (how varied each sample is on its own) and *beta* (how similar the samples are to one another).
  - **Sparsity** — how many taxa show up, and how common each one is.

Every figure carries a one-line caption saying what it shows and how to read it. Purely descriptive overviews are marked as descriptive, and statistical tests are marked as tests — so you always know which is which.

**And everything needed to trust and reproduce a run:**
- The **result tables** and the **cleaned (processed) table**, as CSV.
- **`record.json` / `analysis.json`** — every setting and version that was used, so the run can be repeated exactly.
- **`README.txt`** — a plain-language summary of what was found.

---

## What each tool produces

Every run returns the shared data overview and the reproducibility files above. On top of that, each tool adds its own result:

- **MIPMLP** — the cleaned, standardised table itself, as CSV: the shared representation every other tool builds on. Preprocessing produces a table, not a statistical test.
- **miMic** — a cladogram of the taxonomy tree marking the bacteria that differ between the groups; a bar chart of each significant taxon with its effect size and the group it is higher in; a "real vs shuffled labels" check that the findings are more than chance; and the significant-taxa table.
- **iMic** — the prediction performance on held-out test samples: a ROC curve with its AUC, and a per-sample table of each test sample's predicted probability and predicted group.
- **GIMIC** — the microbiome distances between the samples, with a view of how the samples compare and group together.
- **LOCATE** — the metabolite levels predicted from the microbiome, together with how well each metabolite is predicted.

---

## Scientific integrity

Reliability and faithfulness to the original tools come first:

- Each tool **wraps the authors' own package** — no statistics are reimplemented.
- Each tool has a **reproduction test** against the authors' reference results.
- Everything runs on **Python 3.13** (LOCATE was updated from Lightning 1 to 2 for this, and the conversion was validated against the paper's results).
- Known limitations and non-determinism are **documented honestly**, not hidden.

---

*Developed in the lab of Prof. Yoram Louzoun, Bar-Ilan University.*
