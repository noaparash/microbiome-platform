"""Convert one dataset of the Borenstein curated collection to the platform's input format (no science):
- counts:      species.counts.tsv (samples x taxa, the 7-rank GTDB lineage in each column name) ->
               counts.csv with ID first, one column per taxon (t1, t2, ...) and a last row 'taxonomy'
               holding the lineage, as MIPMLP and the platform expect;
- metabolites: mtb.tsv (samples x metabolites, intensities) -> metabolites.csv, ID first, unchanged values.
Usage: python borenstein_to_platform.py <dataset folder> <output folder>
"""

import sys
from pathlib import Path

import pandas as pd

from microplatform.core.contract import ID_COLUMN, TAXONOMY_ROW

source, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

species = pd.read_csv(source / "species.counts.tsv", sep="\t", index_col=0)
lineages = list(species.columns)
species.columns = [f"t{i + 1}" for i in range(len(lineages))]
counts = species.astype("int64").astype(object)
counts.loc[TAXONOMY_ROW] = lineages
counts.index.name = ID_COLUMN
counts.to_csv(out / "counts.csv")

mtb = pd.read_csv(source / "mtb.tsv", sep="\t", index_col=0)
mtb.index.name = ID_COLUMN
mtb.to_csv(out / "metabolites.csv")
print(f"counts: {species.shape[0]} samples x {species.shape[1]} taxa; metabolites: {mtb.shape}")
