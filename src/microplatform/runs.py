"""On-disk storage for one analysis ("run"): its uploads, status and results.

It lives in the package, not the web layer, so a background worker or a
command-line tool can use the same runs. Each run is a folder named by a
random 32-character ID, which is also the run's results link:

    runs/<id>/meta.json        file names, creation time, goal, status
                               (uploaded → running → done | failed) and any error
    runs/<id>/counts.csv       the uploaded counts table (shared format)
    runs/<id>/labels.csv       optional labels, sample ID as the first column
    runs/<id>/processed.csv    MIPMLP output, once preprocessing has run
    runs/<id>/figures/         each figure as PNG, SVG, HTML and JSON, plus its data CSV
    runs/<id>/record.json      reproducibility record and plain-language summary
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

from microplatform.core.contract import ID_COLUMN
from microplatform.core.preprocessing import PreprocessResult
from microplatform.core.profiler import read_table

_RUN_ID = re.compile(r"[0-9a-f]{32}")

Status = Literal["uploaded", "running", "done", "failed"]


@dataclass(frozen=True)
class Run:
    id: str
    path: Path

    @property
    def counts_file(self) -> Path:
        return self.path / "counts.csv"

    @property
    def labels_file(self) -> Path:
        return self.path / "labels.csv"

    @property
    def processed_file(self) -> Path:
        return self.path / "processed.csv"

    @property
    def record_file(self) -> Path:
        return self.path / "record.json"

    @property
    def figures_dir(self) -> Path:
        return self.path / "figures"

    def figure_file(self, name: str) -> Path | None:
        """A file inside this run's figures folder, or None (never anything outside it).

        Only exact names of existing files are accepted. Building a path from the
        name and checking that it exists is not enough: Windows ignores case and
        trailing dots, so 'figures.json..' would open 'figures.json'.
        """
        if not self.figures_dir.is_dir():
            return None
        existing = {p.name: p for p in self.figures_dir.iterdir() if p.is_file()}
        return existing.get(name)

    def meta(self) -> dict:
        return json.loads((self.path / "meta.json").read_text(encoding="utf-8"))

    def update_meta(self, **changes) -> None:
        meta = {**self.meta(), **changes}
        (self.path / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    @property
    def status(self) -> Status:
        return self.meta()["status"]

    def set_status(self, status: Status, **details) -> None:
        self.update_meta(status=status, updated=_now(), **details)

    def counts(self) -> pd.DataFrame:
        return read_table(self.counts_file)

    def labels(self) -> pd.DataFrame | None:
        return read_table(self.labels_file, index_col=0) if self.labels_file.exists() else None

    def record(self) -> dict | None:
        if not self.record_file.exists():
            return None
        return json.loads(self.record_file.read_text(encoding="utf-8"))

    def processed_preview(self, rows: int = 5) -> pd.DataFrame:
        return pd.read_csv(self.processed_file, index_col=0, nrows=rows)

    def save_result(self, result: PreprocessResult) -> None:
        table = result.table.rename_axis(ID_COLUMN)
        table.to_csv(self.processed_file)
        record = {
            **result.record(),
            "summary": result.summary(),
            "seconds": round(result.seconds, 1),
            "from_cache": result.from_cache,
            "finished": _now(),
        }
        self.record_file.write_text(json.dumps(record, indent=2), encoding="utf-8")


def create(
    root: Path,
    counts_name: str,
    counts: pd.DataFrame,
    labels_name: str | None = None,
    labels: pd.DataFrame | None = None,
) -> Run:
    run_id = uuid.uuid4().hex
    run = Run(run_id, Path(root) / run_id)
    run.path.mkdir(parents=True)
    counts.to_csv(run.counts_file, index=False)
    if labels is not None:
        labels.to_csv(run.labels_file)
    meta = {
        "counts_name": counts_name,
        "labels_name": labels_name,
        "created": _now(),
        "status": "uploaded",
    }
    (run.path / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return run


def load(root: Path, run_id: str) -> Run | None:
    """Return the run, or None if the ID is malformed or unknown (never touches other paths)."""
    if not _RUN_ID.fullmatch(run_id):
        return None
    run = Run(run_id, Path(root) / run_id)
    return run if (run.path / "meta.json").exists() else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
