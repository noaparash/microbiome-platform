"""Auto-profiling: work out what an uploaded table contains.

The profiler never changes the data. It only *describes* the data, so the
router can decide which tools fit and the web page can explain them in plain
language. Problems are reported as ``Issue`` objects instead of crashing, so
the user sees one clear message.

Expected counts format (shared by MIPMLP, miMic and SAMBA):
first column ``ID``, one row per sample, one column per taxon, and a final
row named ``taxonomy``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import IO, Literal

import numpy as np
import pandas as pd

from microplatform.core.contract import ID_COLUMN, LABEL_COLUMN, RANK_SEPARATOR, TAXONOMY_ROW, LabelKind
from microplatform.core.errors import UserFacingError

RANKS = ("kingdom", "phylum", "class", "order", "family", "genus", "species")

# A numeric label with at most this many distinct integer values is treated
# as categorical (e.g. 0/1/2 disease stages); anything else is continuous.
MAX_CATEGORIES = 10

# A sample with more than this many times the median read depth is flagged.
DEPTH_OUTLIER = 10

Severity = Literal["error", "warning"]
ValueKind = Literal["counts", "relative", "transformed"]

# Read depth (and the "Sequencing depth per sample" figure) exists only for read counts; for other
# values the page says why it is missing instead.
DEPTH_UNAVAILABLE: dict[str, str] = {
    "relative": "Sequencing depth isn't available for relative-abundance data: each sample's values are "
                "shares that add up to the same total, not read counts.",
    "transformed": "Sequencing depth isn't available: the values don't look like read counts (they may "
                   "already be transformed), so they can't be added up into reads per sample.",
}


class ProfileError(UserFacingError):
    """The file cannot be read as a table, or is missing required columns."""


@dataclass(frozen=True)
class Issue:
    level: Severity
    message: str
    fix: str = ""  # how the user can fix it


@dataclass
class CountsProfile:
    n_samples: int
    n_taxa: int
    id_column: str
    has_taxonomy: bool
    taxonomy_depth: int  # deepest rank named for most taxa (0 if no taxonomy)
    rank_coverage: dict[str, float]  # fraction of taxa named at each rank
    value_kind: ValueKind
    zero_fraction: float
    min_reads: float
    median_reads: float
    sample_ids: list[str]
    issues: list[Issue] = field(default_factory=list)
    has_negatives: bool = False  # only transformed values (e.g. log, z-scores) can be negative
    table_check: "TableCheck | None" = None  # the detected table type and its evidence (check_table)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    @property
    def looks_preprocessed(self) -> bool:
        """Neither read counts nor complete relative abundances: negative values, or samples whose
        values add up to different totals. Such a table may already be preprocessed (MIPMLP output,
        or a table prepared for one tool), and preprocessing it again would change it."""
        return self.value_kind == "transformed"

    @property
    def preprocessed_because(self) -> str:
        """Why the table looks already preprocessed, in plain words (for the data check)."""
        if self.has_negatives:
            return "it has negative values, as log-transformed or z-scored data does"
        return "its samples add up to different totals, so it is neither read counts nor complete relative abundances"

    @property
    def depth_note(self) -> str | None:
        """Why there is no read depth (None for read counts, which have it)."""
        return DEPTH_UNAVAILABLE.get(self.value_kind)

    def summary(self) -> list[str]:
        """Plain-language description for the web page."""
        lines = [f"{self.n_samples:,} samples and {self.n_taxa:,} bacterial taxa."]
        if self.has_taxonomy:
            lines.append(
                f"Taxonomy found, named down to {RANKS[self.taxonomy_depth - 1]} level "
                f"for most taxa ({self.rank_coverage['species']:.0%} named at species)."
            )
        lines.append(
            {
                "counts": "Values are raw read counts",
                "relative": "Values are relative abundances",
                "transformed": ("Values look already transformed (e.g. log)" if self.has_negatives else
                                "Values are not read counts, and samples add up to different totals"),
            }[self.value_kind]
            + f"; {self.zero_fraction:.0%} of entries are zero."
        )
        if self.value_kind == "counts":
            lines.append(
                f"Sequencing depth: median {self.median_reads:,.0f} reads per sample "
                f"(lowest {self.min_reads:,.0f})."
            )
        return lines


@dataclass
class LabelProfile:
    column: str
    kind: LabelKind
    n_labelled: int  # samples that have both counts and a label
    class_counts: dict[str, int]  # empty for continuous labels
    missing: list[str]  # samples with counts but no label
    issues: list[Issue] = field(default_factory=list)
    # The labels aligned to the counts' sample IDs, named LABEL_COLUMN (contract form).
    values: pd.Series | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def summary(self) -> list[str]:
        if self.kind == "continuous":
            desc = "a continuous outcome"
        else:
            groups = ", ".join(f"'{k}' ({v} samples)" for k, v in self.class_counts.items())
            desc = f"{len(self.class_counts)} groups: {groups}"
        lines = [f"Label '{self.column}' is {self.kind}, with {desc}."]
        if self.missing:
            lines.append(f"{len(self.missing)} samples have no label and will be skipped.")
        return lines


def read_table(source: str | IO, **kwargs) -> pd.DataFrame:
    """Read a CSV or TSV upload.

    The separator is decided from the header line: tab if it has tabs but
    no commas, otherwise comma. pandas' automatic sniffing is avoided because
    taxonomy strings are full of ';', which fools it.
    """
    try:
        return pd.read_csv(source, sep=_header_separator(source), float_precision="round_trip", **kwargs)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise ProfileError(
            "The file could not be read as a table.",
            "Save it as CSV (comma-separated) or TSV (tab-separated). "
            "In Excel: File → Save As → CSV UTF-8.",
        ) from exc


def _header_separator(source: str | IO) -> str:
    if hasattr(source, "readline"):
        header = source.readline()
        source.seek(0)
    else:
        with open(source, encoding="utf-8", errors="replace") as f:
            header = f.readline()
    if isinstance(header, bytes):
        header = header.decode("utf-8", errors="replace")
    return "\t" if "\t" in header and "," not in header else ","


def profile_counts(raw: pd.DataFrame) -> CountsProfile:
    """Describe a counts table in the shared ``ID`` + ``taxonomy``-row format."""
    issues: list[Issue] = []
    if raw.shape[1] < 2 or raw.shape[0] < 1:
        raise ProfileError(
            "The table needs a sample-ID column and at least one bacteria column.",
            "Put sample IDs in the first column and one bacterium per column after it.",
        )

    id_column = str(raw.columns[0])
    if id_column != ID_COLUMN:
        issues.append(Issue(
            "warning",
            f"The first column is named '{id_column}' instead of '{ID_COLUMN}'. "
            "We read it as the sample IDs.",
            f"Rename the first column to '{ID_COLUMN}' to silence this message.",
        ))

    is_tax_row = _taxonomy_rows(raw)
    has_taxonomy = bool(is_tax_row.any())
    if not has_taxonomy:
        issues.append(
            Issue(
                "error",
                f"No '{TAXONOMY_ROW}' row was found, so we cannot tell which bacterium each column is.",
                f"Add a last row whose first cell is '{TAXONOMY_ROW}' and whose other cells hold each "
                "column's lineage, e.g. k__Bacteria;p__Firmicutes;c__Bacilli;…",
            )
        )

    taxonomy = raw.loc[is_tax_row].iloc[-1, 1:].astype(str) if has_taxonomy else None
    body = raw.loc[~is_tax_row]
    sample_ids = body.iloc[:, 0].astype(str).tolist()

    values = body.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    not_numbers = values.isna() & body.iloc[:, 1:].notna()
    bad = int(not_numbers.to_numpy().sum())
    if bad:
        row, col = next(zip(*not_numbers.to_numpy().nonzero()))
        example = f"sample '{sample_ids[row]}' contains '{body.iloc[row, col + 1]}'"
        issues.append(Issue(
            "error",
            f"{bad} entries are not numbers (for example, {example}).",
            "Every cell except the ID column and the taxonomy row must be a number. "
            "Empty cells are fine; they are read as 0.",
        ))
    values = values.fillna(0)

    duplicated = sorted({s for s in sample_ids if sample_ids.count(s) > 1})
    if duplicated:
        issues.append(Issue(
            "error",
            f"Some sample IDs appear more than once: {', '.join(duplicated[:3])}.",
            "Give every sample a unique ID, or merge the duplicated rows.",
        ))
    if len(sample_ids) < 10:
        issues.append(Issue(
            "warning",
            f"Only {len(sample_ids)} samples. Statistical results will be unreliable.",
            "Add more samples if you can.",
        ))

    kind = value_kind(values)
    reads = values.sum(axis=1)
    empty = int((reads == 0).sum())
    if empty:
        names = [s for s, r in zip(sample_ids, reads) if r == 0][:3]
        issues.append(Issue(
            "warning",
            f"{empty} samples have no reads at all (e.g. {', '.join(names)})." if kind == "counts" else
            f"{empty} samples are all zero (e.g. {', '.join(names)}).",
            "Check these samples' sequencing, or remove them.",
        ))

    # Sequencing depth exists only for read counts (relative abundances all add up to the same total).
    median = reads.median() if len(reads) and kind == "counts" else 0
    deep = [(s, r) for s, r in zip(sample_ids, reads) if median > 0 and r > DEPTH_OUTLIER * median]
    if deep:
        name, top = max(deep, key=lambda d: d[1])
        issues.append(Issue(
            "warning",
            f"{len(deep)} {'sample has' if len(deep) == 1 else 'samples have'} over {DEPTH_OUTLIER}× the median sequencing depth "
            f"(e.g. '{name}': {top:,.0f} reads vs a median of {median:,.0f}).",
            "Check them for contamination or a sequencing error. Preprocessing uses log of raw "
            "counts, so unusually deep samples stand out in every analysis.",
        ))

    depth, coverage = _taxonomy_depth(taxonomy) if taxonomy is not None else (0, {r: 0.0 for r in RANKS})

    return CountsProfile(
        n_samples=len(sample_ids),
        n_taxa=values.shape[1],
        id_column=id_column,
        has_taxonomy=has_taxonomy,
        taxonomy_depth=depth,
        rank_coverage=coverage,
        value_kind=kind,
        zero_fraction=float((values == 0).to_numpy().mean()),
        min_reads=float(reads.min()) if len(reads) else 0.0,
        median_reads=float(reads.median()) if len(reads) else 0.0,
        sample_ids=sample_ids,
        issues=issues,
        has_negatives=bool((values < 0).to_numpy().any()),
        table_check=check_table(values, taxonomy.tolist() if taxonomy is not None else None),
    )


def profile_labels(tags: pd.DataFrame, sample_ids: list[str]) -> LabelProfile:
    """Describe a label table (index = sample ID) against the counts' sample IDs."""
    issues: list[Issue] = []
    if LABEL_COLUMN in tags.columns:
        column = LABEL_COLUMN
    elif tags.shape[1] == 1:
        column = str(tags.columns[0])
    elif tags.shape[1] == 0:
        raise ProfileError(
            "The labels file has no label column.",
            f"Use two columns: sample IDs first, then the label in a column named '{LABEL_COLUMN}'.",
        )
    else:
        raise ProfileError(
            f"The labels file has several columns and none is named '{LABEL_COLUMN}'.",
            f"Rename the column holding the outcome to '{LABEL_COLUMN}'.",
        )

    labels = tags[column]
    labels.index = labels.index.astype(str)
    labels = labels[~labels.index.duplicated()].dropna()

    matched = labels.reindex(sample_ids).dropna()
    missing = [s for s in sample_ids if s not in matched.index]
    if matched.empty:
        issues.append(Issue(
            "error",
            "None of the sample IDs in the labels file match the counts table "
            f"(labels have e.g. '{labels.index[0] if len(labels) else '-'}', "
            f"counts have e.g. '{sample_ids[0] if sample_ids else '-'}').",
            "The first column of the labels file must hold the same sample IDs as the counts table.",
        ))

    kind = _label_kind(matched)
    class_counts = (
        {}
        if kind == "continuous"
        else {str(k): int(v) for k, v in matched.value_counts().sort_index().items()}
    )
    if kind != "continuous" and len(class_counts) < 2:
        issues.append(Issue(
            "error",
            "The label has only one value, so there is nothing to compare.",
            f"The '{LABEL_COLUMN}' column needs at least two different values, e.g. 0 and 1.",
        ))
    elif class_counts and min(class_counts.values()) < 5:
        issues.append(Issue(
            "warning",
            "Some groups have fewer than 5 samples, so differences will be hard to detect.",
            "Add samples to the smaller groups if you can.",
        ))

    return LabelProfile(
        column=column,
        kind=kind,
        n_labelled=len(matched),
        class_counts=class_counts,
        missing=missing,
        issues=issues,
        values=matched.rename(LABEL_COLUMN),
    )


def count_matrix(raw: pd.DataFrame) -> pd.DataFrame:
    """Samples × taxa as numbers (anything unreadable counts as 0).

    The index holds sample IDs; columns are taxonomy strings when the table
    has a taxonomy row.
    """
    is_tax_row = _taxonomy_rows(raw)
    body = raw.loc[~is_tax_row]
    values = body.iloc[:, 1:].apply(pd.to_numeric, errors="coerce").fillna(0)
    values.index = body.iloc[:, 0].astype(str)
    if is_tax_row.any():
        values.columns = raw.loc[is_tax_row].iloc[-1, 1:].astype(str).to_numpy()
    return values


def is_counts_table(table: pd.DataFrame) -> bool:
    """True if the table has a 'taxonomy' row, i.e. it is a counts table, not labels."""
    return table.shape[1] >= 2 and bool(_taxonomy_rows(table).any())


def _taxonomy_rows(table: pd.DataFrame) -> pd.Series:
    return table.iloc[:, 0].astype(str).str.strip().str.lower() == TAXONOMY_ROW


def _taxonomy_depth(taxonomy: pd.Series) -> tuple[int, dict[str, float]]:
    """Return the deepest rank named for most taxa, and per-rank coverage."""
    ranks = taxonomy.str.split(RANK_SEPARATOR).apply(lambda parts: [_strip_prefix(p) for p in parts])
    coverage = {
        rank: float(ranks.apply(lambda p, i=i: len(p) > i and bool(p[i])).mean())
        for i, rank in enumerate(RANKS)
    }
    depth = max((i + 1 for i, r in enumerate(RANKS) if coverage[r] > 0.5), default=0)
    return depth, coverage


def _strip_prefix(part: str) -> str:
    """'g__Bacteroides' -> 'Bacteroides'; 's__' -> ''."""
    part = part.strip()
    return part.split("__", 1)[1].strip() if "__" in part else part


def value_kind(values: pd.DataFrame) -> ValueKind:
    arr = values.to_numpy(dtype=float)
    if (arr < 0).any():
        return "transformed"
    if (arr % 1 == 0).all():
        return "counts"
    sums = arr.sum(axis=1)
    sums = sums[sums > 0]
    if len(sums) and ((abs(sums - 1) < 0.01).all() or (abs(sums - 100) < 1).all()):
        return "relative"
    return "transformed"


# --- what kind of table is this? (decides whether MIPMLP should run; see check_table) -----------

TableType = Literal["counts", "relative", "partial_relative", "preprocessed", "unclear"]

RELATIVE_TOLERANCE = 0.01  # a full relative-abundance sample adds up to 1 (or 100) within this
MANY_ZEROS = 0.10  # partial relative abundances: at least this share of exact zeros (a log removes them)
SUB_PCA_NAMES = 0.5  # MIPMLP's sub-PCA endings ('_0', '_1', …) on at least this share of the columns
SUB_PCA_ENDING = re.compile(r"_\d{1,2}$")  # only MIPMLP's short component index, never IDs like '_388775'
ZERO_MEAN = 1e-6  # a column whose |mean| is below this × its spread looks centred (z-scored)

TABLE_TYPE_NAMES: dict[str, str] = {
    "counts": "read counts",
    "relative": "relative abundances",
    "partial_relative": "relative abundances of a subset of taxa",
    "preprocessed": "already preprocessed",
    "unclear": "unclear",
}


@dataclass(frozen=True)
class TableCheck:
    """The detected table type, the plain-language reasons, and the numbers they rest on.

    ``evidence`` holds every check (value range, negatives, share of zeros, row sums, …), so the
    reproducibility record can show exactly why a table was classified as it was."""

    type: TableType
    reasons: tuple[str, ...]
    evidence: dict

    @property
    def name(self) -> str:
        return TABLE_TYPE_NAMES[self.type]

    @property
    def sentence(self) -> str:
        """One plain-English sentence: what was detected and why."""
        why = "; ".join(self.reasons)
        if self.type == "unclear":
            return f"We can't tell what kind of values your table holds ({why})."
        if self.type == "preprocessed":
            return f"Your table looks already preprocessed ({why})."
        return f"Your table looks like {self.name} ({why})."


def _last_named_rank(name: str) -> str:
    """'Bacteria;…;Lachnospiraceae_0;;' -> 'Lachnospiraceae_0' (MIPMLP leaves the ranks below empty)."""
    parts = [p.strip() for p in str(name).split(RANK_SEPARATOR) if p.strip()]
    return parts[-1] if parts else str(name).strip()


def check_table(values: pd.DataFrame, names: list[str] | None = None) -> TableCheck:
    """Classify a samples × taxa table. ``names`` are the taxa's lineages (default: the column names).

    The rules, in order (the first that applies wins):

    1. **preprocessed**: any negative value (only a log or a z-score makes them), or at least
       ``SUB_PCA_NAMES`` of the columns end in MIPMLP's sub-PCA index (``_0``, ``_1``, … one or two
       digits on the last named rank; database IDs such as ``_388775`` do not count). Columns with a
       mean of about 0 (z-scored) are a *supporting* signal: they are reported, never decide alone.
    2. **counts**: every value a whole number, none negative.
    3. **relative**: every sample (except all-zero ones) adds up to 1, or to 100, within
       ``RELATIVE_TOLERANCE``.
    4. **partial_relative**: every value between 0 and 1, at least ``MANY_ZEROS`` exact zeros, and every
       sample adds up to 1 or less (within ``RELATIVE_TOLERANCE``): shares of a subset of the taxa.
    5. **unclear**: anything else.
    """
    arr = values.to_numpy(dtype=float)
    names = [str(n) for n in (names if names is not None else values.columns)]
    sums = arr.sum(axis=1) if arr.size else np.zeros(0)
    nonzero_sums = sums[sums > 0]
    spread = arr.std(axis=0) if arr.size else np.zeros(0)
    varying = spread > 0
    centred = int((np.abs(arr.mean(axis=0))[varying] <= ZERO_MEAN * spread[varying]).sum()) if arr.size else 0
    sub_pca = sum(1 for n in names if SUB_PCA_ENDING.search(_last_named_rank(n)))
    negatives = int((arr < 0).sum())
    zeros = float((arr == 0).mean()) if arr.size else 0.0
    whole = float((arr % 1 == 0).mean()) if arr.size else 0.0
    sums_to_one = int((np.abs(sums - 1) < RELATIVE_TOLERANCE).sum())
    evidence = {
        "min": float(arr.min()) if arr.size else 0.0,
        "max": float(arr.max()) if arr.size else 0.0,
        "negative_values": negatives,
        "zero_fraction": round(zeros, 4),
        "whole_number_fraction": round(whole, 4),
        "row_sum_min": float(sums.min()) if len(sums) else 0.0,
        "row_sum_max": float(sums.max()) if len(sums) else 0.0,
        "samples_adding_up_to_1": sums_to_one,
        "samples": int(arr.shape[0]),
        "columns": int(arr.shape[1]) if arr.ndim == 2 else 0,
        "columns_with_sub_pca_ending": sub_pca,
        "columns_with_mean_about_0": centred,
    }

    def found(kind: TableType, *reasons: str) -> TableCheck:
        return TableCheck(kind, tuple(reasons), evidence)

    centred_note = (f"{centred:,} of {len(names):,} columns have a mean of about 0, as z-scored data does"
                    if centred else None)
    pct = f"{zeros:.0%}"
    if negatives or (names and sub_pca >= SUB_PCA_NAMES * len(names)):
        reasons = []
        if negatives:
            reasons.append(f"{negatives:,} values are negative, as log-transformed or z-scored data is")
        if names and sub_pca >= SUB_PCA_NAMES * len(names):
            reasons.append(f"{sub_pca:,} of {len(names):,} column names end in MIPMLP's sub-PCA index (_0, _1, …)")
        return found("preprocessed", *reasons, *([centred_note] if centred_note else []))
    if whole == 1.0:
        return found("counts", "whole numbers, none negative")
    if len(nonzero_sums) and ((np.abs(nonzero_sums - 1) < RELATIVE_TOLERANCE).all()
                              or (np.abs(nonzero_sums - 100) < 100 * RELATIVE_TOLERANCE).all()):
        return found("relative", "every sample adds up to the same total")
    if arr.size and arr.max() <= 1 and zeros >= MANY_ZEROS and sums.max() <= 1 + RELATIVE_TOLERANCE:
        return found("partial_relative", "values between 0 and 1, none negative",
                     f"{pct} of the values are exactly 0",
                     f"samples add up to {sums.min():.2g}–{sums.max():.2g}, never above 1")
    reasons = [f"values from {evidence['min']:.3g} to {evidence['max']:.3g}, none negative",
               f"{pct} exactly 0", "not whole numbers, and samples add up to different totals"]
    return found("unclear", *reasons, *([centred_note] if centred_note else []))


def _label_kind(labels: pd.Series) -> LabelKind:
    numeric = pd.to_numeric(labels, errors="coerce")
    n_unique = labels.nunique()
    if n_unique <= 2:
        return "binary"
    if numeric.isna().any():
        return "categorical"
    if (numeric % 1 == 0).all() and n_unique <= MAX_CATEGORIES:
        return "categorical"
    return "continuous"
