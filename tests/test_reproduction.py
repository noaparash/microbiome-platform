"""Reproduction tests: each engine gives exactly what the original tool gives.

For every engine, run the authors' tool the way their own example does, on
their example data, and check that our engine's result is identical. This
proves the adapter feeds the original tool faithfully (see docs/tool-inputs.he.md).
Every new engine must add its test here.
"""

import warnings

import MIPMLP
import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core.preprocessing import CANONICAL
from microplatform.examples import EXAMPLE_COUNTS


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return workflows.start_example_run(tmp_path_factory.mktemp("runs"))


def test_mipmlp_matches_the_authors_call(run, tmp_path):
    """miMic's own preprocessing is MIPMLP.preprocess(raw, taxnomy_group="sub PCA")."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        theirs = MIPMLP.preprocess(pd.read_csv(EXAMPLE_COUNTS), taxnomy_group="sub PCA")

    ours = workflows.build_dataset(run, CANONICAL, tmp_path)[0].features

    pd.testing.assert_index_equal(ours.columns, theirs.columns)
    assert list(ours.index) == [str(i) for i in theirs.index]
    pd.testing.assert_frame_equal(ours, theirs, check_names=False, check_index_type=False)
