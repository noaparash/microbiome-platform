"""Shared core: preprocess a counts table once with MIPMLP, record how, and cache it.

Every engine works from MIPMLP output. One canonical setting set is used by
default. An engine that needs a variation asks for it with
``CANONICAL.with_changes(...)``. Each distinct (data, settings) pair is
computed once and cached on disk.

This module is the only place that calls MIPMLP. Swapping in the lab's
internal version means changing ``_run_mipmlp`` and nothing else.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import time
import warnings
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from pathlib import Path
from typing import Literal

import pandas as pd

from microplatform.core.contract import ID_COLUMN, TAXONOMY_ROW
from microplatform.core.errors import UserFacingError
from microplatform.core.profiler import profile_counts


class PreprocessError(UserFacingError):
    """The data cannot be preprocessed."""


@dataclass(frozen=True)
class PreprocessSettings:
    """MIPMLP options, in our own spelling (MIPMLP's is ``taxnomy_group``)."""

    taxonomy_level: int = 7  # 6 = genus, 7 = species
    taxonomy_group: Literal["sub PCA", "mean", "sum"] = "sub PCA"
    epsilon: float = 0.1  # added before log10 to avoid log(0)
    normalization: Literal["log", "relative"] = "log"
    z_scoring: Literal["No", "row", "col", "both"] = "No"
    rare_bacteria_threshold: float = 0.01  # drop taxa present in < 1% of samples

    def with_changes(self, **changes) -> PreprocessSettings:
        """A per-engine variation of these settings."""
        return replace(self, **changes)

    def to_mipmlp_kwargs(self) -> dict:
        return {
            "taxonomy_level": self.taxonomy_level,
            "taxnomy_group": self.taxonomy_group,
            "epsilon": self.epsilon,
            "normalization": self.normalization,
            "z_scoring": self.z_scoring,
            "rare_bacteria_threshold": self.rare_bacteria_threshold,
            # Fixed: no extra dimension reduction (paper recommendation),
            # and no plotting, which would write files into the working directory.
            "pca": (0, "PCA"),
            "plot": False,
        }


# The paper's recommended pipeline (log, sub-PCA, no dimension reduction) at
# species level, which iMic, miMic and GIMIC all use.
CANONICAL = PreprocessSettings()


@dataclass
class PreprocessResult:
    table: pd.DataFrame  # samples × features
    settings: PreprocessSettings
    n_input_taxa: int
    from_cache: bool
    seconds: float
    mipmlp_version: str

    @property
    def n_features(self) -> int:
        return self.table.shape[1]

    def record(self) -> dict:
        """Everything needed to reproduce this run, for the report."""
        return {
            "tool": "MIPMLP",
            "mipmlp_version": self.mipmlp_version,
            "settings": asdict(self.settings),
            "samples": self.table.shape[0],
            "input_taxa": self.n_input_taxa,
            "output_features": self.n_features,
        }

    def summary(self) -> list[str]:
        level = {6: "genus", 7: "species"}.get(self.settings.taxonomy_level,
                                               f"level {self.settings.taxonomy_level}")
        return [
            f"Grouped {self.n_input_taxa:,} taxa into {self.n_features:,} features at {level} "
            f"level ({self.settings.taxonomy_group}), then applied {self.settings.normalization} scaling.",
            "Taxa that MIPMLP cannot place (unnamed, viruses) or that appear in fewer than "
            f"{self.settings.rare_bacteria_threshold:.0%} of samples were left out.",
        ]


def preprocess(
    raw: pd.DataFrame,
    settings: PreprocessSettings = CANONICAL,
    cache_dir: Path | None = None,
) -> PreprocessResult:
    """Run MIPMLP on a counts table in the shared format, using the cache if possible."""
    profile = profile_counts(raw)
    if not profile.ok:
        errors = [i for i in profile.issues if i.level == "error"]
        raise PreprocessError(" ".join(i.message for i in errors), " ".join(i.fix for i in errors))
    raw = _standardise(raw)

    cache_file = None
    if cache_dir is not None:
        cache_file = Path(cache_dir) / f"mipmlp-{cache_key(raw, settings)}.pkl"
        if cache_file.exists():
            table = pd.read_pickle(cache_file)
            return PreprocessResult(table, settings, profile.n_taxa, True, 0.0, version("MIPMLP"))

    start = time.perf_counter()
    table = _run_mipmlp(raw, settings)
    seconds = time.perf_counter() - start

    if table.empty or table.shape[1] == 0:
        raise PreprocessError(
            "Preprocessing left no bacteria.",
            "Check that the taxonomy row names real taxa (not just 'k__Bacteria') "
            "and that most bacteria appear in more than 1% of samples.",
        )
    if table.isna().any().any():
        raise PreprocessError(
            "Preprocessing produced missing values.",
            "This is a bug on our side. Please send this dataset to the lab.",
        )

    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        table.to_pickle(cache_file)
        cache_file.with_suffix(".json").write_text(
            json.dumps(asdict(settings), indent=2), encoding="utf-8"
        )
    return PreprocessResult(table, settings, profile.n_taxa, False, seconds, version("MIPMLP"))


def cache_key(raw: pd.DataFrame, settings: PreprocessSettings) -> str:
    """Stable fingerprint of (data, settings, MIPMLP version)."""
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(raw, index=False).to_numpy().tobytes())
    h.update("|".join(map(str, raw.columns)).encode())
    h.update(json.dumps(asdict(settings), sort_keys=True).encode())
    h.update(version("MIPMLP").encode())
    return h.hexdigest()[:16]


def _standardise(raw: pd.DataFrame) -> pd.DataFrame:
    """Give MIPMLP exactly the names it expects: an ID column and a taxonomy row."""
    raw = raw.rename(columns={raw.columns[0]: ID_COLUMN}).copy()
    ids = raw[ID_COLUMN].astype(str)
    raw[ID_COLUMN] = ids.where(ids.str.strip().str.lower() != TAXONOMY_ROW, TAXONOMY_ROW)
    return raw


def _run_mipmlp(raw: pd.DataFrame, settings: PreprocessSettings) -> pd.DataFrame:
    import MIPMLP  # imported here: it loads PyTorch, which is slow

    # MIPMLP prints progress and emits pandas warnings; keep them out of the app's output.
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        try:
            return MIPMLP.preprocess(raw, **settings.to_mipmlp_kwargs())
        except Exception as exc:  # MIPMLP raises bare errors; translate for the user
            raise PreprocessError(
                f"MIPMLP could not process this table ({exc}).",
                "Check that the file matches the template. If it does, please send it to the lab.",
            ) from exc
