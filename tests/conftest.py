"""Shared test guards."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]

# What the authors' tools write into "the current folder" (miMic's plots and .pkl files, LOCATE's
# Lightning logs, MIPMLP's scalers). Our engines always run them inside a run's own work folder, so
# none of these may ever appear in the project folder. Checked after every test, so a leak names
# the test that caused it (a stray plots/ was once found after a full run and never reproduced).
STRAY = ("plots", "lightning_logs", "df_corrs.pkl", "miMic&Utest.pkl", "u_test_without_mimic.pkl",
         "sub_pca_scaler.pkl", "pca_scaler.pkl")


@pytest.fixture(autouse=True)
def nothing_written_into_the_project_folder():
    before = {name for name in STRAY if (ROOT / name).exists()}
    yield
    leaked = {name for name in STRAY if (ROOT / name).exists()} - before
    assert not leaked, f"a tool wrote {sorted(leaked)} into the project folder {ROOT}"
