"""Write the two validation examples (PROTOCOL.md, "Data") as CSV files. Run once, in the platform's
environment: python validation/locate/make_examples.py

E1: the authors' usage_example.py recipe (random numbers), drawn with a fixed seed.
E2: the miMic authors' example microbiome prepared as for LOCATE, with synthetic metabolites
    that depend on it, so there is something to learn.
"""

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from microplatform import workflows
from microplatform.core.inputs import sort_uploads
from microplatform.core.metabolites import prepare_metabolites
from microplatform.core.preprocessing import CANONICAL

HERE = Path(__file__).parent
DATA = HERE / "data"
SEED = 2026
MIMIC_COUNTS = HERE.parents[1] / "tests" / "data" / "mimic_example" / "for_process.csv"


def save(folder: Path, **tables: pd.DataFrame) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(folder / f"{name}.csv")


def e1() -> None:
    """Exactly the shapes and recipe of the authors' usage_example.py."""
    rng = np.random.RandomState(SEED)

    def table(rows, cols, prefix):
        return np.log(pd.DataFrame(rng.uniform(0, 1, size=(rows, cols)),
                                   index=[f"{prefix}_{i}" for i in range(rows)]) + 0.1)

    save(DATA / "E1", X_train=table(100, 50, "a"), X_val=table(30, 50, "b"),
         Y_train=table(100, 30, "a"), Y_val=table(30, 30, "b"))


def e2() -> None:
    work = Path(tempfile.mkdtemp())
    try:
        inputs = sort_uploads([(MIMIC_COUNTS.name, MIMIC_COUNTS.read_bytes())])
        run = workflows.start_run(work / "runs", inputs)
        data, _ = workflows.build_dataset(run, CANONICAL.with_changes(z_scoring="col"), work / "cache",
                                          engine="LOCATE")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    X = data.features
    rng = np.random.RandomState(SEED)
    weights = rng.normal(scale=1 / np.sqrt(X.shape[1]), size=(X.shape[1], 30))
    signal = np.tanh(X.to_numpy() @ weights) * 2 + rng.normal(scale=0.5, size=(len(X), 30))
    levels = pd.DataFrame(np.exp(signal), index=X.index, columns=[f"met_{j}" for j in range(30)])
    Y, _ = prepare_metabolites(levels)
    train, test = train_test_split(list(X.index), test_size=0.2, random_state=42)
    save(DATA / "E2", X_train=X.loc[train], X_val=X.loc[test], Y_train=Y.loc[train], Y_val=Y.loc[test])


if __name__ == "__main__":
    e1()
    e2()
    for folder in sorted(DATA.iterdir()):
        shapes = {p.stem: pd.read_csv(p, index_col=0).shape for p in sorted(folder.glob("*.csv"))}
        print(folder.name, shapes)
