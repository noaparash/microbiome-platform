"""Which simple metabolite filter turns YACHIDA's 450 metabolites into the paper's 174? Usage: python yachida_filters.py <dataset folder>"""
import sys
from pathlib import Path
import pandas as pd
folder = Path(sys.argv[1])
mtb = pd.read_csv(folder / "mtb.tsv", sep="\t", index_col=0)
mmap = pd.read_csv(folder / "mtb.map.tsv", sep="\t")
present = (mtb > 0).mean()
for t in (0.05, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 0.95, 0.99, 1.0):
    print(f"detected in >= {t:.0%} of samples: {(present >= t).sum()}")
print("high-confidence:", int(mmap['High.Confidence.Annotation'].astype(str).str.upper().eq('TRUE').sum()))
print("with KEGG id:", int(mmap['KEGG'].notna().sum()), "| with HMDB:", int(mmap['HMDB'].notna().sum()))
s = present.sort_values(ascending=False)
print("presence of the 174th / 175th most detected:", s.iloc[173], s.iloc[174])
