"""Metabolite tables: check them, and prepare them the way the LOCATE paper does.

A metabolite table has one row per sample (sample IDs in the first column, the
same IDs as the counts table) and one numeric column per metabolite, holding
concentrations or intensities (not yet log-transformed).

Preparation, from the LOCATE paper (Shtossel et al., Microbiome 2024, Methods,
"Metabolite preprocessing"): "all metabolic samples were first normalized to
relative frequencies, such that the metabolites of each sample would sum to 1.
Then, those were log-normalized and further z-scored, such that the average
value of each metabolite would be 0 and its variance would be 1."

The paper does not give the log base or the value added before the log (needed
for zeros). Until the authors confirm them, ``LOCATE_METABOLITES`` uses log10
(as MIPMLP does for the microbiome) and a placeholder pseudocount, and every
result records ``confirmed: False``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from microplatform.core.profiler import Issue

MIN_PAIRED = 20  # samples with both tables: enough for an 80/20 split with a usable test set


@dataclass(frozen=True)
class MetaboliteSettings:
    """How metabolites are prepared before modelling (recorded with every result)."""

    normalization: str = "relative"  # each sample sums to 1
    log_base: float = 10.0
    pseudocount: float = 1e-6  # PLACEHOLDER: added before the log; not given in the paper
    z_scoring: str = "column"  # each metabolite: mean 0, variance 1
    confirmed: bool = False  # True once the authors confirm log_base and pseudocount

    def with_changes(self, **changes) -> MetaboliteSettings:
        return replace(self, **changes)


LOCATE_METABOLITES = MetaboliteSettings()


@dataclass
class MetaboliteProfile:
    n_samples: int
    n_metabolites: int
    n_paired: int  # samples that are also in the counts table
    issues: list[Issue]

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def summary(self) -> list[str]:
        return [f"{self.n_samples} samples and {self.n_metabolites} metabolites; "
                f"{self.n_paired} samples are also in the counts table."]


def profile_metabolites(table: pd.DataFrame, sample_ids: list[str]) -> MetaboliteProfile:
    """Check a metabolite table (index = sample ID) against the counts table's sample IDs."""
    issues: list[Issue] = []
    ids = [str(i) for i in table.index]
    paired = len(set(ids) & {str(s) for s in sample_ids})

    if len(set(ids)) != len(ids):
        repeated = sorted({i for i in ids if ids.count(i) > 1})[:3]
        issues.append(Issue("error", f"Some sample IDs appear more than once (e.g. {', '.join(repeated)}).",
                            "Keep one row per sample."))
    text = [c for c in table.columns if not pd.api.types.is_numeric_dtype(table[c])]
    if text:
        issues.append(Issue("error", f"{len(text)} column(s) are not numbers (e.g. '{text[0]}').",
                            "Keep only the sample-ID column and one numeric column per metabolite."))
    numbers = table.drop(columns=text)
    if numbers.isna().any().any():
        issues.append(Issue("error", f"{int(numbers.isna().sum().sum())} values are missing.",
                            "Fill in the missing values (for example with 0 for 'not detected') "
                            "or remove those metabolites."))
    if (numbers < 0).any().any():
        issues.append(Issue("error", "Some values are negative, so the table looks already transformed "
                                     "(log or z-score).",
                            "Upload the measured concentrations or intensities; the platform normalises them."))
    empty = numbers.index[numbers.fillna(0).sum(axis=1) == 0]
    if len(empty):
        issues.append(Issue("error", f"{len(empty)} sample(s) have no metabolite signal at all "
                                     f"(e.g. '{empty[0]}').", "Remove those samples."))
    if paired < MIN_PAIRED:
        issues.append(Issue("error", f"Only {paired} samples are in both the counts and the metabolite table; "
                                     f"LOCATE needs at least {MIN_PAIRED}.",
                            "Check that both tables use the same sample IDs in their first column."))
    elif paired < len(ids):
        issues.append(Issue("warning", f"{len(ids) - paired} metabolite samples are not in the counts table "
                                       "and will be left out."))
    return MetaboliteProfile(len(ids), table.shape[1], paired, issues)


def prepare_metabolites(table: pd.DataFrame, settings: MetaboliteSettings = LOCATE_METABOLITES,
                        ) -> tuple[pd.DataFrame, dict]:
    """Relative → log → z-score per metabolite, as in the paper. Returns the table and a record.

    Metabolites that are constant across these samples have no z-score and are left out
    (the record says how many).
    """
    values = table.astype(float)
    relative = values.div(values.sum(axis=1), axis=0)
    logged = np.log(relative + settings.pseudocount) / np.log(settings.log_base)
    spread = logged.std(axis=0, ddof=0)
    kept = logged.loc[:, spread > 0]
    prepared = (kept - kept.mean(axis=0)) / kept.std(axis=0, ddof=0)
    record = {"settings": asdict(settings), "z_score_sd": "population (ddof=0)",
              "metabolites_in": int(table.shape[1]),
              "metabolites_used": int(prepared.shape[1]),
              "left_out_constant": int(table.shape[1] - prepared.shape[1])}
    return prepared, record
