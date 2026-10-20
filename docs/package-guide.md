# Package guide

`microplatform` is the product; the website is a thin layer over it. This
guide is for using the package from Python and for adding to it.

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

Python 3.13. `pandas` is pinned below 3, because MIPMLP 1.2.19 breaks on pandas 3.

## Use it

```python
import microplatform as mp

# A whole analysis, as on the website:
view = mp.analyze("counts.csv", "labels.csv", out_dir="runs")
view.recommendation.reasons    # why this task
view.run.path                  # processed.csv, figures/, record.json

# Or step by step:
counts = mp.read_table("counts.csv")
profile = mp.profile_counts(counts)          # .summary(), .issues, .ok
result = mp.preprocess(counts)               # MIPMLP, the paper's settings
result.table                                 # samples × features
result.record()                              # every setting and version
```

Everything in `microplatform.__all__` is the public API. The website's
**Docs & API** page lists it with signatures, generated from the code.

## How it is organised

```
src/microplatform/
  core/contract.py      the shared data contract: conventions + Dataset (read this first)
  core/profiler.py      data check
  core/inputs.py        recognises uploaded files
  core/preprocessing.py the only module that calls MIPMLP (cached)
  engines/              one adapter per tool, all implementing engines/base.py
  router/goals.py       the tasks, their required inputs, the recommendation
  reports/              figures (PNG/SVG/HTML + CSV) and the results ZIP
  references.py         the tools and their citations (one source)
  runs.py               one folder per analysis
  workflows.py          end-to-end workflows (used by the website and by mp.analyze)
  web/                  thin Flask layer: routes and templates only
```

## The rules that keep it consistent

These are enforced by tests:

1. **One data contract** (`core/contract.py`). Names like `ID`, `Tag` and
   `taxonomy` are defined there only. Every engine receives the same validated
   `Dataset` and may vary only `taxonomy_level` and `z_scoring`.
   (`tests/test_contract.py`)
2. **Package first.** The website contains no data logic.
   (`tests/test_web.py::test_web_layer_holds_no_business_logic`)
3. **Faithful to the originals.** Every engine reproduces the authors' own
   result on their example data. (`tests/test_reproduction.py`)

## Adding a tool (an engine)

1. Read `docs/tool-inputs.he.md` for that tool's native input and the
   planned adapter.
2. Write `src/microplatform/engines/<tool>.py`: a subclass of `Engine` with
   `name`, `goal`, `requires` and, if needed, an allowed `preprocessing`
   variation. `run(data: Dataset, out_dir)` converts the `Dataset` to the
   tool's native input, calls the authors' code (inside `out_dir`, since some
   tools write files to the current folder) and exports figures through
   `reports.figures` (`Figure` + `export`).
3. Register it in `engines/__init__.py` and set its goal to `"available"` in
   `router/goals.py`.
4. Add its reproduction test to `tests/test_reproduction.py`.
5. Run `python -m pytest`. The contract tests check the rest.
