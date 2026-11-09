"""'Download everything': one ZIP with the inputs, results, figures and record."""

from __future__ import annotations

import io
import json
import zipfile

from microplatform.references import get_tool
from microplatform.reports.figures import load_manifest
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
results/processed_table.csv   {processed}
results/<table>.csv           the analysis' result tables (e.g. significant taxa), if any
record.json                   preprocessing settings and version, to reproduce this run
analysis.json                 the analysis tool's version, settings and findings, if any
figures/                      every figure as <name>.png / .svg (SVG text stays editable), <name>.html
                              (interactive; opens offline in any browser) and <name>.csv (its exact
                              data), in three folders, in reading order:
  1_result/                   the analysis result: the tool's findings
  2_data_quality/             quality checks of the uploaded table (e.g. sequencing depth)
  3_descriptive_overview/     what the data looks like (composition, diversity, sparsity): descriptive,
                              the same for every tool, NOT the analysis result. <name>_tests.csv: the
                              group tests shown on a figure, if any (alpha_diversity: Shapiro-Wilk,
                              t-test / Mann-Whitney / ANOVA / Kruskal-Wallis, FDR, Cohen's d;
                              beta_pcoa: PERMANOVA, eta squared, PERMDISP). Exploratory: not corrected
                              across the report, and not the analysis tool's findings
inputs/                       the files you uploaded

Preprocessing settings
----------------------
{settings}

Please cite
-----------
{citations}
"""


# The figure folders inside the ZIP, in reading order: the result first, the descriptive overview last.
FIGURE_FOLDERS = {"findings": "1_result", "quality": "2_data_quality", "overview": "3_descriptive_overview"}


def figure_folder(section: str) -> str:
    """'figures/1_result' etc.: where a figure of this section goes in the ZIP."""
    return f"figures/{FIGURE_FOLDERS.get(section, '2_data_quality')}"


def build_bundle(run: Run) -> bytes:
    meta, record, engine = run.meta(), run.record() or {}, run.engine_record()
    settings = "\n".join(f"{k}: {v}" for k, v in (record.get("settings") or {}).items())
    if record.get("skipped"):
        settings = f"none: the uploaded table was used as it is. {record.get('why', '')}"
    processed = ("the table the analysis used: your upload, as it is (not preprocessed)" if record.get("skipped")
                 else "MIPMLP output: one row per sample, one column per feature")
    sections = {name: fig.section for fig in load_manifest(run.figures_dir) for name in fig.files.values()}
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
            findings=findings, settings=settings or "(not run yet)", citations=_citations(engine, record),
            processed=processed,
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
                    zf.write(path, f"{figure_folder(sections.get(path.name, 'quality'))}/{path.name}")
    return buffer.getvalue()


def _citations(engine: dict | None, record: dict | None = None) -> str:
    """Every tool used in the run (MIPMLP unless the uploaded table was used as it is)."""
    mipmlp = [] if (record or {}).get("skipped") else ["MIPMLP"]
    used = mipmlp + ([engine["tool"]] if engine and engine["tool"] != "MIPMLP" else [])
    return "\n".join(f"{name}: {get_tool(name).paper.citation}" for name in used)
