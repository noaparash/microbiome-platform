"""MIPMLP as an engine: the goal "Just preprocess".

The preprocessing itself happens before any engine runs, because every
engine needs it. This engine adds the quality-check figures.
"""

from __future__ import annotations

from pathlib import Path

from microplatform.core.contract import Dataset
from microplatform.engines.base import Engine, EngineResult
from microplatform.reports import figures


class MipmlpEngine(Engine):
    name = "MIPMLP"
    goal = "preprocess"
    requires = frozenset({"counts"})

    def run(self, data: Dataset, out_dir: Path) -> EngineResult:
        exported = figures.export(figures.preprocessing_figures(data.raw_counts, data.settings), out_dir)
        return EngineResult(figures=exported)
