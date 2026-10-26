"""Labels in the form the lab's tools expect, shared by every engine that uses labels."""

from __future__ import annotations

import pandas as pd


def native_tag(labels: pd.Series, kind: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """Labels as one column (named like ``labels``); binary labels coded 0/1 in sorted order.

    miMic and iMic both compare ``tag == 0`` with ``tag == 1`` (iMic's loss needs 0/1),
    so two-group labels written as words are coded, and the coding is returned to record.
    """
    if kind == "binary":
        values = sorted(labels.unique(), key=lambda v: (isinstance(v, str), v))
        coding = {"0": str(values[0]), "1": str(values[1])}
        coded = labels.map({values[0]: 0, values[1]: 1}).astype(int)
    else:
        coding = {}
        coded = labels.astype(float)
    return coded.to_frame(labels.name), coding
