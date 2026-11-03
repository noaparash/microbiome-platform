"""Turn the timing results (results.jsonl from run_all.sh) into the run-time table (Markdown).
Usage: python make_table.py <results.jsonl> <out.md> "<machine description>" "<date>"
"""

import json
import sys
from pathlib import Path

results, out, machine, date = sys.argv[1:5]
rows = [json.loads(line) for line in Path(results).read_text(encoding="utf-8").splitlines() if line.strip()]

TOOLS = {"preprocess": "MIPMLP (just preprocess)", "differ": "miMic", "predict": "iMic",
         "group": "GIMIC", "metabolites": "LOCATE"}


def duration(seconds):
    if seconds is None:
        return "—"
    if seconds < 1:
        return "< 1 s"
    if seconds < 90:
        return f"{seconds:.0f} s"
    return f"{seconds / 60:.1f} min"


datasets = []
for row in rows:
    if row["dataset"] not in datasets:
        datasets.append(row["dataset"])

lines = [
    "# Run times of the platform's tools",
    "",
    f"Measured {date} on {machine}, with the platform's own code path (`mp.analyze`, the same",
    "workflow the website's background worker runs). Each analysis ran in its own process,",
    "capped at 60 minutes for this measurement only: an entry \"> 60 min\" was stopped there",
    "(the platform itself never stops a run). These are laptop timings; the timings that",
    "matter are the lab server's, to be measured after deployment.",
    "",
    "**How to read it**",
    "",
    "- **Preprocessing (MIPMLP) is a one-time cost per dataset.** Its result is cached: every",
    "  later analysis of the same data (another tool, or the same one again) starts from the",
    "  cached table instantly. That is why, below, only the first analysis of each dataset pays",
    "  it. LOCATE uses its own variant of the table (each feature z-scored), so it pays one more",
    "  preprocessing pass the first time.",
    "- **Runs happen in the background.** After clicking Run, the user gets a results link and",
    "  can close the page; the analysis continues on the server and the page (or an optional",
    "  email) shows the results when they are ready. The user is never blocked, even for the",
    "  longest runs here.",
    "- **Peak memory** is the most memory the analysis used at once (the whole process: Python,",
    "  the data and the tool). It is what the lab server needs per analysis running at the same",
    "  time. For a run stopped at 60 minutes it is the peak until then (\"at least\").",
    "- **Large datasets need the lab server.** On the big public datasets (tens of thousands of",
    "  taxa), some tools did not finish within an hour on the laptop.",
    "- The data overview figures (added after this measurement) take about 16 to 39 s more on the",
    "  big datasets, and a few seconds on the small ones.",
    "",
]
for name in datasets:
    first = next((r for r in rows if r["dataset"] == name and r.get("samples")), {})
    size = (f"{first.get('samples')} samples, {first.get('taxa'):,} taxa → {first.get('features'):,} features"
            if first else "")
    mets = next((r.get("metabolites") for r in rows if r["dataset"] == name and r.get("metabolites")), None)
    lines += [f"## {name}", "", size + (f"; {mets:,} metabolites" if mets else "") + ".", "",
              "| Tool | Preprocessing | Tool itself | Total | Peak memory |",
              "|---|---|---|---|---|"]
    for row in (r for r in rows if r["dataset"] == name):
        tool = TOOLS.get(row["goal"], row["goal"])
        if row.get("status", "").startswith("time-out"):
            peak = row.get("peak_memory_gb")
            lines.append(f"| {tool} | cached (0 s) | **> 60 min** (stopped) | **> 60 min** | "
                         f"{'at least ' + str(peak) + ' GB' if peak is not None else '—'} |")
            continue
        if row.get("status") != "done":
            note = row.get("message") or ""
            lines.append(f"| {tool} | — | **{row['status']}**{': ' + note if note else ''} | "
                         f"{duration(row.get('total_s'))} | {row.get('peak_memory_gb', '—')} GB |")
            continue
        pre = "cached (0 s)" if row["from_cache"] else duration(row["preprocessing_s"])
        # "Just preprocess" has no tool: the rest is saving the cleaned table and drawing the figures.
        tool_time = (f"{duration(row['tool_s'])} (saving, figures)" if row["goal"] == "preprocess"
                     else duration(row["tool_s"]))
        lines.append(f"| {tool} | {pre} | {tool_time} | {duration(row['total_s'])} | "
                     f"{row.get('peak_memory_gb', '—')} GB |")
    lines.append("")
Path(out).write_text("\n".join(lines), encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")  # the Windows console is not UTF-8 by default
print("\n".join(lines))
