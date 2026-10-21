"""The one interface every tool implements.

An engine declares what it is, which goal it answers, which inputs it
requires, and (optionally) an allowed variation of the canonical
preprocessing. It receives only a validated ``Dataset`` (see
``core/contract.py``), never raw uploads, so all tools stand on the same
inputs and the same representation.

Engines *return* their findings; the workflow stores them. An engine never
decides where or how results are saved.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import pandas as pd

from microplatform.core.contract import Dataset, InputKind
from microplatform.core.preprocessing import CANONICAL, PreprocessSettings
from microplatform.reports.figures import Figure


@dataclass
class EngineResult:
    summary: list[str] = field(default_factory=list)  # plain-language findings
    figures: list[Figure] = field(default_factory=list)  # drawn through reports.figures
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)  # name → table, saved as CSV
    record: dict = field(default_factory=dict)  # tool version and every setting, for reproducibility


class Engine(ABC):
    name: ClassVar[str]  # the tool, e.g. "miMic"
    goal: ClassVar[str]  # the goal it answers (an id in router/goals.py)
    requires: ClassVar[frozenset[InputKind]]
    preprocessing: ClassVar[PreprocessSettings] = CANONICAL

    @abstractmethod
    def run(self, data: Dataset, work_dir: Path) -> EngineResult:
        """Analyse ``data``. ``work_dir`` is a private scratch folder for the tool's own files."""
