"""Describe one dataset of the Borenstein curated microbiome-metabolome collection (read only).
Usage: python inspect_borenstein.py <dataset folder>"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

folder = Path(sys.argv[1])
species = pd.read_csv(folder / "species.counts.tsv", sep="\t", index_col=0)
mtb = pd.read_csv(folder / "mtb.tsv", sep="\t", index_col=0)
mtb_map = pd.read_csv(folder / "mtb.map.tsv", sep="\t")
meta = pd.read_csv(folder / "metadata.tsv", sep="\t")

print("species.counts:", species.shape, "| index name:", species.index.name, "| first IDs:", list(species.index[:3]))
values = species.to_numpy()
print("  values: integers?", bool(np.allclose(values, np.round(values))), "| min", values.min(), "max", values.max(),
      "| zeros", f"{(values == 0).mean():.0%}", "| reads/sample median", int(np.median(values.sum(axis=1))))
taxa = list(species.columns)
print("  taxon names, e.g.:", taxa[0])
depth = pd.Series([len(t.split(";")) for t in taxa]).value_counts().to_dict()
print("  ranks per name:", depth, "| prefixes:", sorted({p[:3] for t in taxa for p in t.split(";")}))
print("  names without a species part:", sum(not t.split(";")[-1].startswith("s__") or t.endswith("s__") for t in taxa))

print("mtb:", mtb.shape, "| first IDs:", list(mtb.index[:3]))
m = mtb.to_numpy(dtype=float)
print("  values: min", np.nanmin(m), "max", np.nanmax(m), "| missing", f"{np.isnan(m).mean():.1%}",
      "| negatives", int((m < 0).sum()), "| zeros", f"{(m == 0).mean():.1%}")
print("  metabolite names, e.g.:", list(mtb.columns[:3]))
print("mtb.map:", mtb_map.shape, "| columns:", list(mtb_map.columns))
annotated = mtb_map["High.Confidence.Annotation"] if "High.Confidence.Annotation" in mtb_map else None
if annotated is not None:
    print("  high-confidence annotations:", int(annotated.astype(str).str.upper().eq("TRUE").sum()), "of", len(mtb_map))

print("metadata:", meta.shape, "| columns:", list(meta.columns)[:12])
print("  study groups:", meta["Study.Group"].value_counts().to_dict())
print("  subjects:", meta["Subject"].nunique(), "| samples:", meta["Sample"].nunique())
s_ids, m_ids = set(species.index), set(mtb.index)
print("paired samples (in both tables):", len(s_ids & m_ids), "| only species:", len(s_ids - m_ids),
      "| only mtb:", len(m_ids - s_ids))
