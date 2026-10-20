"""'Download everything': one ZIP with the inputs, results, figures and record."""

from __future__ import annotations

import io
import json
import zipfile

from microplatform.references import get_tool
from microplatform.runs import Run

README = """\
Microbiome Platform results
===========================

Run ID:  {run_id}
Input:   {counts_name}
Created: {created}

Contents
--------
results/processed_table.csv   MIPMLP output: one row per sample, one column per feature
record.json                   every setting and version used, to reproduce this run
figures/<name>.png / .svg     figures (SVG text stays editable)
figures/<name>.html           interactive figures; open them in any browser, works offline
figures/<name>.csv            the exact data behind each figure
inputs/                       the files you uploaded

Settings
--------
{settings}

Please cite
-----------
{citations}
"""


def build_bundle(run: Run) -> bytes:
    meta, record = run.meta(), run.record() or {}
    settings = "\n".join(f"{k}: {v}" for k, v in record.get("settings", {}).items())

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", README.format(
            run_id=run.id, counts_name=meta["counts_name"], created=meta["created"],
            settings=settings or "(not run yet)",
            citations=_citations(record),
        ))
        if record:
            zf.writestr("record.json", json.dumps(record, indent=2))
        if run.processed_file.exists():
            zf.write(run.processed_file, "results/processed_table.csv")
        zf.write(run.counts_file, "inputs/counts.csv")
        if run.labels_file.exists():
            zf.write(run.labels_file, "inputs/labels.csv")
        if run.figures_dir.exists():
            for path in sorted(run.figures_dir.iterdir()):
                if path.suffix != ".json":  # JSON copies are only for the web page
                    zf.write(path, f"figures/{path.name}")
    return buffer.getvalue()


def _citations(record: dict) -> str:
    """Every tool used in the run (MIPMLP always, since every analysis starts with it)."""
    used = ["MIPMLP"] + [t for t in record.get("tools", []) if t != "MIPMLP"]
    return "\n".join(f"{name}: {get_tool(name).paper.citation}" for name in used)
