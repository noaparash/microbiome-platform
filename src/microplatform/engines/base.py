"""The one interface every tool implements.

An engine declares what it is, which goal it answers, which inputs it
requires, and (optionally) an allowed variation of the canonical
preprocessing. It receives only a validated ``Dataset`` (see
``core/contract.py``), never raw uploads, so all tools stand on the same
inputs and the same representation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from microplatform.core.contract import Dataset, InputKind
from microplatform.core.preprocessing import CANONICAL, PreprocessSettings
from microplatform.reports.figures import ExportedFigure


@dataclass
class EngineResult:
    summary: list[str] = field(default_factory=list)  # plain-language findings
    figures: list[ExportedFigure] = field(default_factory=list)


class Engine(ABC):
    name: ClassVar[str]  # the tool, e.g. "miMic"
    goal: ClassVar[str]  # the goal it answers (an id in router/goals.py)
    requires: ClassVar[frozenset[InputKind]]
    preprocessing: ClassVar[PreprocessSettings] = CANONICAL

    @abstractmethod
    def run(self, data: Dataset, out_dir: Path) -> EngineResult:
        """Analyse ``data`` and write all outputs (figures via ``reports.figures``) to ``out_dir``."""
