"""The one interface every tool implements.

An engine declares what it is, which goal it answers, which inputs it
requires, and (optionally) an allowed variation of the canonical
preprocessing. It receives only a validated ``Dataset`` (see
``core/contract.py``), never raw uploads, so all tools stand on the same
inputs and the same representation.

An engine may offer a few ``options`` (advanced settings with a documented
default). Choices are validated here, never in the website.

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
from microplatform.core.inputs import InputError
from microplatform.core.preprocessing import CANONICAL, PreprocessSettings
from microplatform.reports.figures import Figure, RenderedFigure


@dataclass
class EngineResult:
    summary: list[str] = field(default_factory=list)  # plain-language findings
    # How to read the findings: limits and caveats (e.g. one run, a small test set). Shown apart from the
    # findings and never folded away, so they are read together.
    notes: list[str] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)  # drawn through reports.figures
    # Drawn by the tool's own plotting code (e.g. miMic's cladogram), copied unchanged; shown first.
    rendered: list[RenderedFigure] = field(default_factory=list)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)  # name → table, saved as CSV
    record: dict = field(default_factory=dict)  # tool version and every setting, for reproducibility
    highlight: tuple[str, str] | None = None  # (table name, heading): the table to preview on the page


@dataclass(frozen=True)
class EngineOption:
    """An advanced setting: the allowed values, what each means, and the default."""

    name: str
    label: str
    values: dict[str, str]  # value → plain-language description
    default: str


class Engine(ABC):
    name: ClassVar[str]  # the tool, e.g. "miMic"
    goal: ClassVar[str]  # the goal it answers (an id in router/goals.py)
    requires: ClassVar[frozenset[InputKind]]
    preprocessing: ClassVar[PreprocessSettings] = CANONICAL
    options: ClassVar[tuple[EngineOption, ...]] = ()

    def resolve(self, choices: dict | None) -> dict[str, str]:
        """Every option's value: the user's choice if valid, otherwise the default.

        Raises ``InputError`` for an unknown option or value.
        """
        choices = dict(choices or {})
        known = {o.name: o for o in self.options}
        for name in choices:
            if name not in known:
                raise InputError(f"{self.name} has no setting called '{name}'.",
                                 f"Known settings: {', '.join(known) or 'none'}.")
        resolved = {}
        for option in self.options:
            value = choices.get(option.name) or option.default
            if value not in option.values:
                raise InputError(f"'{value}' is not a choice for {option.label.lower()}.",
                                 f"Choose one of: {', '.join(option.values)}.")
            resolved[option.name] = value
        return resolved

    def settings_for(self, choices: dict[str, str]) -> PreprocessSettings:
        """The preprocessing for these (resolved) choices. Engines with options override this."""
        return self.preprocessing

    @abstractmethod
    def run(self, data: Dataset, work_dir: Path, choices: dict[str, str] | None = None) -> EngineResult:
        """Analyse ``data``. ``work_dir`` is a private scratch folder for the tool's own files."""
