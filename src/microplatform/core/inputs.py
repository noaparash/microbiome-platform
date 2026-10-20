"""Sort uploaded files into a counts table and an optional labels file.

The user may upload the files in any order and with any names. A counts
table is recognised by its 'taxonomy' row; anything else is a labels file.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from microplatform.core.contract import TAXONOMY_ROW
from microplatform.core.errors import UserFacingError
from microplatform.core.profiler import ProfileError, is_counts_table, read_table

ALLOWED_SUFFIXES = {".csv", ".tsv", ".txt"}
EXCEL_SUFFIXES = {".xlsx", ".xls", ".xlsm"}


class InputError(UserFacingError):
    """The uploaded files cannot be used as they are."""


@dataclass
class Inputs:
    counts_name: str
    counts: pd.DataFrame
    labels_name: str | None = None
    labels: pd.DataFrame | None = None  # index = sample ID


def sort_uploads(files: list[tuple[str, bytes]]) -> Inputs:
    """Take ``(filename, content)`` pairs and work out which file is which."""
    if not files:
        raise InputError("No file was uploaded.", "Choose a counts table (and optionally a labels file).")
    if len(files) > 2:
        raise InputError(
            f"{len(files)} files were uploaded; at most two are expected.",
            "Upload one counts table and, optionally, one labels file.",
        )

    counts = labels = None
    for name, content in files:
        table = _read_upload(name, content)
        if is_counts_table(table):
            if counts is not None:
                raise InputError(
                    f"Both files look like counts tables (both have a '{TAXONOMY_ROW}' row).",
                    "Upload one counts table at a time, optionally with a labels file.",
                )
            counts = (name, table)
        else:
            if labels is not None:
                raise InputError(
                    f"Neither file has a '{TAXONOMY_ROW}' row, so no counts table was found.",
                    f"Add a last row named '{TAXONOMY_ROW}' to the counts table. See the template.",
                )
            labels = (name, table.set_index(table.columns[0]))

    if counts is None:
        raise InputError(
            f"No counts table was found: a counts table has a last row named '{TAXONOMY_ROW}'.",
            f"Upload the counts table too, or add the '{TAXONOMY_ROW}' row to it. See the template.",
        )
    return Inputs(counts[0], counts[1], *(labels or (None, None)))


def read_labels_upload(name: str, content: bytes) -> pd.DataFrame:
    """A labels file added later, from the Plan step (index = sample ID)."""
    table = _read_upload(name, content)
    if is_counts_table(table):
        raise InputError(
            f"'{name}' looks like a counts table (it has a '{TAXONOMY_ROW}' row), not a labels file.",
            "Upload a labels file: sample IDs in the first column and the label in a second column.",
        )
    return table.set_index(table.columns[0])


def _read_upload(name: str, content: bytes) -> pd.DataFrame:
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
    try:
        return read_table(io.BytesIO(content))
    except ProfileError as exc:
        raise InputError(f"'{name}': {exc.message}", exc.fix) from exc
