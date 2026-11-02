"""Step 1 for the FRANZOSA comparison: the platform's data checks and MIPMLP preprocessing on the converted
files (no LOCATE yet). Usage: python franzosa_check.py <platform-format folder> <work folder>"""

import sys
import time
from pathlib import Path

from microplatform import workflows
from microplatform.core.inputs import sort_uploads
from microplatform.core.metabolites import profile_metabolites
from microplatform.core.profiler import profile_counts, read_table
from microplatform.engines.locate import LocateEngine

data, work = Path(sys.argv[1]), Path(sys.argv[2])
inputs = sort_uploads([("counts.csv", (data / "counts.csv").read_bytes())])
profile = profile_counts(inputs.counts)
print("counts check:", *profile.summary(), sep="\n  ")
print("  issues:", [(i.level, i.message) for i in profile.issues] or "none")

metabolites = read_table(data / "metabolites.csv", index_col=0)
metabolites.index = metabolites.index.astype(str)
mprofile = profile_metabolites(metabolites, profile.sample_ids)
print("metabolite check:", *mprofile.summary(), [(i.level, i.message) for i in mprofile.issues] or "no issues")

run = workflows.start_run(work / "runs", inputs)
start = time.time()
dataset, result = workflows.build_dataset(run, LocateEngine.preprocessing, work / "cache", engine="LOCATE")
print(f"MIPMLP ({LocateEngine.preprocessing.taxonomy_group}, level {LocateEngine.preprocessing.taxonomy_level}, "
      f"{LocateEngine.preprocessing.normalization}, z-score {LocateEngine.preprocessing.z_scoring}): "
      f"{result.input_taxa if hasattr(result, 'input_taxa') else '?'} taxa -> {dataset.features.shape[1]} features "
      f"for {dataset.features.shape[0]} samples in {time.time() - start:.0f} s")
print("run folder:", run.path)
