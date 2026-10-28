"""Microbiome platform: the Louzoun lab's microbiome tools behind one interface.

Quick start::

    import microplatform as mp

    view = mp.analyze("counts.csv", "labels.csv")   # whole analysis, no website
    print(view.run.path)                            # table, figures, record

    counts = mp.read_table("counts.csv")            # or step by step
    print(mp.profile_counts(counts).summary())
    result = mp.preprocess(counts)                  # MIPMLP, the paper's settings

Everything listed in ``__all__`` is the public API; it is documented on the
website's "Docs & API" page (generated from these docstrings). Changes to it
are recorded in CHANGELOG.md.
"""

__version__ = "0.2.0"

from microplatform.core.contract import Dataset
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import sort_uploads
from microplatform.core.preprocessing import CANONICAL, PreprocessSettings, preprocess
from microplatform.core.profiler import profile_counts, profile_labels, read_table
from microplatform.references import TOOLS
from microplatform.router.goals import GOALS
from microplatform.workflows import analyze, build_dataset, describe, run_goal, start_run

__all__ = [
    "analyze",
    "read_table",
    "profile_counts",
    "profile_labels",
    "preprocess",
    "PreprocessSettings",
    "CANONICAL",
    "sort_uploads",
    "start_run",
    "describe",
    "run_goal",
    "build_dataset",
    "Dataset",
    "UserFacingError",
    "GOALS",
    "TOOLS",
]
