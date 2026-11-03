"""Two-group labels for a Borenstein-collection dataset: 0 = controls/healthy, 1 = everyone else.
Usage: python make_labels.py <metadata.tsv> <labels.csv>"""

import sys

import pandas as pd

meta = pd.read_csv(sys.argv[1], sep="\t")
control = meta["Study.Group"].isin(["Control", "Healthy"])
pd.DataFrame({"ID": meta["Sample"], "Tag": (~control).astype(int)}).to_csv(sys.argv[2], index=False)
print(f"{int(control.sum())} controls, {int((~control).sum())} cases -> {sys.argv[2]}")
