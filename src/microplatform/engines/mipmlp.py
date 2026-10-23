"""MIPMLP as an engine: the goal "Just preprocess".

The preprocessing itself, and its data-quality figures, happen in the workflow
before any engine runs, because every engine needs them. So this engine only
has to say what the user gets.
"""

from __future__ import annotations

from pathlib import Path

from microplatform.core.contract import Dataset
from microplatform.engines.base import Engine, EngineResult


class MipmlpEngine(Engine):
    name = "MIPMLP"
    goal = "preprocess"
    requires = frozenset({"counts"})

    def run(self, data: Dataset, work_dir: Path, choices: dict[str, str] | None = None) -> EngineResult:
        rows, cols = data.features.shape
        return EngineResult(summary=[f"The cleaned table has {rows} samples and {cols} features, ready to download."])
