"""Sort uploaded files into a counts table, an optional labels file and an optional metabolite table.

The user may upload the files in any order and with any names. Each file is
recognised by its shape:
- a counts table has a 'taxonomy' row, or its column names are themselves taxonomy
  strings (``k__Bacteria;p__Firmicutes;c__…``, empty ranks such as ``p__`` allowed):
  the "taxonomy in the column names" layout. That layout is turned into the shared
  format here, once, by adding a 'taxonomy' row that repeats each column's name
  exactly as written in the file (``with_taxonomy_row``), so everything after the
  upload sees the same table a combined upload would give;
- a labels file has a 'Tag' column, or a single column besides the sample IDs;
- a metabolite table has at least ``MIN_METABOLITE_COLUMNS`` numeric columns
  besides the sample IDs (one per metabolite), no 'Tag' column and no 'taxonomy'
  row. With fewer, it is read as a labels file (a label plus a stray column), so
  the user gets the labels file's own message instead of a wrong guess.
A file added from the Plan step is the kind the user chose; only a counts table
is refused there.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from microplatform.core.contract import INPUT_NAMES, LABEL_COLUMN, RANK_SEPARATOR, TAXONOMY_ROW
from microplatform.core.errors import UserFacingError
from microplatform.core.profiler import ProfileError, is_counts_table, read_table

# One rank of a lineage: a rank letter and two underscores (k__, d__, p__, … s__), name optional.
RANK_PART = re.compile(r"^[A-Za-z]__")
# The share of the columns (after the IDs) whose names must be lineages for a table to be read as
# "taxonomy in the column names". A few others (e.g. "Unassigned") are kept, as written.
MIN_LINEAGE_SHARE = 0.9
COUNTS_LAYOUTS = {"row": "a 'taxonomy' row", "headers": "taxonomy in the column names"}

ALLOWED_SUFFIXES = {".csv", ".tsv", ".txt"}
EXCEL_SUFFIXES = {".xlsx", ".xls", ".xlsm"}
MAX_FILES = 3  # a counts table, a labels file and a metabolite table
MIN_METABOLITE_COLUMNS = 3

TableKind = Literal["counts", "labels", "metabolites"]

# What each kind of file looks like, for messages and the format help.
LOOKS_LIKE: dict[TableKind, str] = {
    "counts": f"it has a '{TAXONOMY_ROW}' row, or taxonomy strings as its column names",
    "labels": f"it has a '{LABEL_COLUMN}' column or a single column besides the sample IDs",
    "metabolites": f"it has {MIN_METABOLITE_COLUMNS} or more numeric columns (one per metabolite) and no "
                   f"'{TAXONOMY_ROW}' row",
}


class InputError(UserFacingError):
    """The uploaded files cannot be used as they are."""


@dataclass
class Inputs:
    counts_name: str
    counts: pd.DataFrame
    labels_name: str | None = None
    labels: pd.DataFrame | None = None  # index = sample ID
    metabolites_name: str | None = None
    metabolites: pd.DataFrame | None = None  # index = sample ID (strings), one column per metabolite
    counts_layout: str = "row"  # "row" or "headers" (taxonomy in the column names), see COUNTS_LAYOUTS


def is_lineage(name: str) -> bool:
    """'k__Bacteria;p__;c__…' is a lineage: every non-empty rank starts with a rank letter and '__'."""
    parts = [p.strip() for p in str(name).split(RANK_SEPARATOR)]
    return bool(parts[0]) and all(RANK_PART.match(p) for p in parts if p)


def with_taxonomy_row(content: bytes) -> bytes | None:
    """A table whose column names are lineages, in the shared format; None for any other table.

    The 'taxonomy' row repeats each column's name exactly as written in the file (names that
    appear twice stay identical; pandas would rename the second to '….1'), and is added to the
    file's text, so the table is then read exactly as a combined upload would be.
    """
    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    if len(lines) < 2:
        return None
    separator = "\t" if "\t" in lines[0] and "," not in lines[0] else ","
    header = next(csv.reader([lines[0]], delimiter=separator))
    names = header[1:]
    first_cells = {next(csv.reader([line], delimiter=separator), [""])[0].strip().lower()
                   for line in lines[1:] if line.strip()}
    if not names or TAXONOMY_ROW in first_cells:
        return None  # already has a taxonomy row (or no columns)
    if sum(is_lineage(n) for n in names) < MIN_LINEAGE_SHARE * len(names):
        return None
    out = io.StringIO()
    csv.writer(out, delimiter=separator, lineterminator="\n").writerow([TAXONOMY_ROW, *names])
    return (text.rstrip("\r\n") + "\n" + out.getvalue()).encode("utf-8")


def table_kind(table: pd.DataFrame) -> TableKind:
    """Which kind of input a table is (see the module docstring)."""
    if is_counts_table(table):
        return "counts"
    columns = table.columns[1:]  # the first column holds the sample IDs
    numeric = [c for c in columns if pd.api.types.is_numeric_dtype(table[c])]
    if LABEL_COLUMN in columns or len(numeric) < MIN_METABOLITE_COLUMNS:
        return "labels"
    return "metabolites"


def sort_uploads(files: list[tuple[str, bytes]]) -> Inputs:
    """Take ``(filename, content)`` pairs and work out which file is which."""
    if not files:
        raise InputError("No file was uploaded.", "Choose a counts table (and optionally a labels file).")
    if len(files) > MAX_FILES:
        raise InputError(
            f"{len(files)} files were uploaded; at most {MAX_FILES} are expected.",
            "Upload one counts table and, if your question needs them, one labels file and one "
            "metabolite table.",
        )

    found: dict[TableKind, tuple[str, pd.DataFrame]] = {}
    layout = "row"
    for name, content in files:
        table, from_headers = _read_upload(name, content)
        kind = table_kind(table)
        if from_headers and kind == "counts":
            layout = "headers"
        if kind in found:
            raise InputError(
                f"'{found[kind][0]}' and '{name}' both look like {_noun(kind)}s "
                f"({LOOKS_LIKE[kind]}).",
                _one_of_each(kind),
            )
        found[kind] = (name, table if kind == "counts" else _by_sample(table))

    if "counts" not in found:
        raise InputError(
            f"No counts table was found: a counts table either has a last row named '{TAXONOMY_ROW}', "
            "or column names that are taxonomy strings (e.g. k__Bacteria;p__Firmicutes;…).",
            f"Upload the counts table too, or give each bacteria column its lineage: as the column name, "
            f"or in a last row named '{TAXONOMY_ROW}'. See the template.",
        )
    labels = found.get("labels", (None, None))
    metabolites = found.get("metabolites", (None, None))
    return Inputs(*found["counts"], *labels, *metabolites, counts_layout=layout)


def read_labels_upload(name: str, content: bytes) -> pd.DataFrame:
    """A labels file added later, from the Plan step (index = sample ID)."""
    return read_added_upload("labels", name, content)


def read_metabolites_upload(name: str, content: bytes) -> pd.DataFrame:
    """A metabolite table added later, from the Plan step (index = sample ID)."""
    return read_added_upload("metabolites", name, content)


def read_added_upload(kind: TableKind, name: str, content: bytes) -> pd.DataFrame:
    """A file added to an existing run as ``kind`` (index = sample ID); a counts table is refused."""
    table, _ = _read_upload(name, content)
    if table_kind(table) == "counts":
        raise InputError(
            f"'{name}' looks like a counts table ({LOOKS_LIKE['counts']}), not {INPUT_NAMES[kind]}.",
            _expected(kind),
        )
    return _by_sample(table)


def _by_sample(table: pd.DataFrame) -> pd.DataFrame:
    table = table.set_index(table.columns[0])
    table.index = table.index.astype(str)  # sample IDs are strings everywhere (see the contract)
    return table


def _noun(kind: TableKind) -> str:
    """'labels file' (INPUT_NAMES without its article)."""
    return INPUT_NAMES[kind].split(" ", 1)[1]


def _expected(kind: TableKind) -> str:
    return {
        "counts": f"Upload a counts table: sample IDs first, one column per taxon, and a last row "
                  f"named '{TAXONOMY_ROW}'.",
        "labels": f"Upload a labels file: sample IDs in the first column and the label in a column named "
                  f"'{LABEL_COLUMN}'.",
        "metabolites": "Upload a metabolite table: sample IDs in the first column, then one numeric column "
                       "per metabolite.",
    }[kind]


def _one_of_each(kind: TableKind) -> str:
    if kind == "counts":
        return "Upload one counts table at a time, optionally with a labels file or a metabolite table."
    return f"Upload at most one {_noun(kind)}. {_expected(kind)}"


def _read_upload(name: str, content: bytes) -> tuple[pd.DataFrame, bool]:
    """The table, and whether its taxonomy came from the column names (then in the shared format)."""
    suffix = Path(name).suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        raise InputError(
            f"'{name}' is an Excel file, which we don't read directly.",
            "In Excel, choose File → Save As → CSV UTF-8, then upload the .csv file.",
        )
    if suffix not in ALLOWED_SUFFIXES:
        raise InputError(
            f"'{name}' is not a CSV or TSV file.",
            "Export the table as .csv (comma-separated) or .tsv (tab-separated).",
        )
    combined = with_taxonomy_row(content)
    try:
        return read_table(io.BytesIO(combined if combined is not None else content)), combined is not None
    except ProfileError as exc:
        raise InputError(f"'{name}': {exc.message}", exc.fix) from exc
