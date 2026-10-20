"""The shared data contract: one set of conventions, one representation, every tool.

Every engine (MIPMLP, miMic, iMic, GIMIC, LOCATE, and any added later) is
built on exactly what this module defines, and nothing else:

1. **Input conventions**: the names that uploaded files use.
2. **Input kinds**: what a task can require (counts, labels, metabolites, timepoints).
3. **The canonical representation** (``Dataset``): the single MIPMLP output that
   every engine consumes, with the labels aligned to it.
4. **Allowed variations**: the only preprocessing settings an engine may change.

``tests/test_contract.py`` fails if any module or engine diverges from it.
Never re-type these names elsewhere; import them from here.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Literal, get_args

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from microplatform.core.preprocessing import PreprocessSettings

# --- 1. Input conventions -------------------------------------------------------

ID_COLUMN = "ID"  # first column of every uploaded table: the sample ID
TAXONOMY_ROW = "taxonomy"  # last row of the counts table: each column's lineage
LABEL_COLUMN = "Tag"  # label column of the labels file
RANK_SEPARATOR = ";"  # between ranks in taxonomy strings and feature names

# --- 2. Input kinds ------------------------------------------------------------------

InputKind = Literal["counts", "labels", "metabolites", "timepoints"]
INPUT_KINDS: tuple[InputKind, ...] = get_args(InputKind)

# How each input is named to the user ("Needs a labels file.").
INPUT_NAMES: dict[InputKind, str] = {
    "counts": "a counts table",
    "labels": "a labels file",
    "metabolites": "a metabolite table",
    "timepoints": "a timepoints file",
}

# --- 3. Allowed per-engine preprocessing variations -------------------------------

# Engines may change only these fields of CANONICAL (e.g. genus instead of species,
# or z-scoring for LOCATE). Normalization, grouping and the rare-taxa threshold
# are the same for every tool, so all tools see the same kind of numbers.
ALLOWED_VARIATIONS = frozenset({"taxonomy_level", "z_scoring"})

LabelKind = Literal["binary", "categorical", "continuous"]


def short_feature_name(name: str) -> str:
    """The deepest named rank of a feature: 'Bacteria;…;Actinomycetaceae_0;;' → 'Actinomycetaceae_0'."""
    parts = [p for p in str(name).split(RANK_SEPARATOR) if p.strip()]
    return parts[-1] if parts else str(name)


class ContractError(Exception):
    """Internal bug: data that breaks the contract reached an engine."""


def check_settings(settings: PreprocessSettings) -> None:
    from microplatform.core.preprocessing import CANONICAL

    changed = {f.name for f in fields(settings) if getattr(settings, f.name) != getattr(CANONICAL, f.name)}
    if not changed <= ALLOWED_VARIATIONS:
        raise ContractError(f"Preprocessing may only vary {sorted(ALLOWED_VARIATIONS)}; got {sorted(changed)}.")


# --- 4. The canonical representation -----------------------------------------------

@dataclass(frozen=True)
class Dataset:
    """What every engine receives. Build it once per run and settings, and validate it.

    features     MIPMLP output: one row per sample (index named ``ID_COLUMN``,
                 string sample IDs), one float column per feature, no missing values.
                 Feature names are lineages joined by ``RANK_SEPARATOR``.
    settings     the preprocessing settings that produced ``features``.
    raw_counts   the uploaded counts (samples × taxa), for quality checks only;
                 engines must model ``features``, never these.
    labels       optional; a Series named ``LABEL_COLUMN``, indexed by sample IDs
                 that all appear in ``features``.
    label_kind   binary / categorical / continuous, set whenever labels are set.
    metabolites  optional (planned, for LOCATE): samples × metabolites, indexed by
                 sample IDs that all appear in ``features``.
    """

    features: pd.DataFrame
    settings: PreprocessSettings
    raw_counts: pd.DataFrame
    labels: pd.Series | None = None
    label_kind: LabelKind | None = None
    metabolites: pd.DataFrame | None = None

    @property
    def available_inputs(self) -> frozenset[InputKind]:
        present = {"counts"}
        if self.labels is not None:
            present.add("labels")
        if self.metabolites is not None:
            present.add("metabolites")
        return frozenset(present)

    def validate(self) -> Dataset:
        """Raise ``ContractError`` if anything breaks the contract; return self otherwise."""
        f = self.features
        _require(isinstance(f, pd.DataFrame) and not f.empty, "features must be a non-empty table")
        _require(f.index.name == ID_COLUMN, f"features index must be named '{ID_COLUMN}'")
        _require(all(isinstance(i, str) for i in f.index), "sample IDs must be strings")
        _require(f.index.is_unique, "sample IDs must be unique")
        _require(all(pd.api.types.is_float_dtype(t) for t in f.dtypes), "features must be floats")
        _require(bool(np.isfinite(f.to_numpy()).all()), "features must have no missing or infinite values")
        _require(set(f.index) <= set(self.raw_counts.index), "every feature row must come from the counts")
        check_settings(self.settings)

        if self.labels is not None:
            _require(self.labels.name == LABEL_COLUMN, f"labels must be named '{LABEL_COLUMN}'")
            _require(set(self.labels.index) <= set(f.index), "every labelled sample must have features")
            _require(not self.labels.isna().any(), "labels must have no missing values")
            _require(self.label_kind in get_args(LabelKind), "label_kind must be set with labels")
        else:
            _require(self.label_kind is None, "label_kind is set but there are no labels")

        if self.metabolites is not None:
            _require(set(self.metabolites.index) <= set(f.index), "every metabolite row must have features")
        return self


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(f"Data contract broken: {message}.")
