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

Run ID:   {run_id}
Input:    {counts_name}
Created:  {created}
Analysis: {analysis}

{findings}Contents
--------
results/processed_table.csv   MIPMLP output: one row per sample, one column per feature
results/<table>.csv           the analysis' result tables (e.g. significant taxa), if any
record.json                   preprocessing settings and version, to reproduce this run
analysis.json                 the analysis tool's version, settings and findings, if any
figures/<name>.png / .svg     figures (SVG text stays editable)
figures/<name>.html           interactive figures; open them in any browser, works offline
figures/<name>.csv            the exact data behind each figure
                              (composition_*, alpha_diversity, beta_pcoa, taxa_*: the data overview,
                              descriptive figures of the data itself, not statistical tests)
inputs/                       the files you uploaded

Preprocessing settings
----------------------
{settings}

Please cite
-----------
{citations}
"""


def build_bundle(run: Run) -> bytes:
    meta, record, engine = run.meta(), run.record() or {}, run.engine_record()
    settings = "\n".join(f"{k}: {v}" for k, v in record.get("settings", {}).items())
    findings = ""
    if engine and engine["summary"]:
        findings = "Findings\n--------\n" + "\n".join(f"- {line}" for line in engine["summary"]) + "\n\n"
    if engine and engine.get("notes"):
        findings += ("How to read these results\n-------------------------\n"
                     + "\n".join(f"- {line}" for line in engine["notes"]) + "\n\n")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", README.format(
            run_id=run.id, counts_name=meta["counts_name"], created=meta["created"],
            analysis=engine["tool"] if engine else "preprocessing only",
            findings=findings, settings=settings or "(not run yet)", citations=_citations(engine),
        ))
        if record:
            zf.writestr("record.json", json.dumps(record, indent=2))
        if engine:
            zf.writestr("analysis.json", json.dumps(engine, indent=2, default=str))
        if run.processed_file.exists():
            zf.write(run.processed_file, "results/processed_table.csv")
        if run.tables_dir.exists():
            for path in sorted(run.tables_dir.glob("*.csv")):
                zf.write(path, f"results/{path.name}")
        zf.write(run.counts_file, "inputs/counts.csv")
        if run.labels_file.exists():
            zf.write(run.labels_file, "inputs/labels.csv")
        if run.metabolites_file.exists():
            zf.write(run.metabolites_file, "inputs/metabolites.csv")
        if run.figures_dir.exists():
            for path in sorted(run.figures_dir.iterdir()):
                if path.suffix != ".json":  # JSON copies are only for the web page
                    zf.write(path, f"figures/{path.name}")
    return buffer.getvalue()


def _citations(engine: dict | None) -> str:
    """Every tool used in the run (MIPMLP always, since every analysis starts with it)."""
    used = ["MIPMLP"] + ([engine["tool"]] if engine and engine["tool"] != "MIPMLP" else [])
    return "\n".join(f"{name}: {get_tool(name).paper.citation}" for name in used)
