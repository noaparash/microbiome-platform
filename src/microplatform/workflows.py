"""Complete workflows: start a run, describe it, and run the chosen goal.

The website calls these, and so will the future background worker.
Neither of them needs to know how profiling or preprocessing works.

Every goal runs the same way: build the one canonical ``Dataset`` (see
``core/contract.py``), validate it, and hand it to the goal's engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from microplatform import runs
from microplatform.core.contract import ID_COLUMN, Dataset, InputKind
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import InputError, Inputs
from microplatform.core.preprocessing import CANONICAL, PreprocessResult, PreprocessSettings, preprocess
from microplatform.core.profiler import (
    CountsProfile,
    Issue,
    LabelProfile,
    ProfileError,
    count_matrix,
    profile_counts,
    profile_labels,
    read_table,
)
from microplatform.engines import ENGINES
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.reports import figures
from microplatform.reports.bundle import build_bundle
from microplatform.router.goals import GoalOption, default_goal, get_goal, goal_options

__all__ = [
    "RunView", "build_bundle", "build_dataset", "describe", "run_goal",
    "start_example_run", "start_run",
]


@dataclass
class RunView:
    """Everything a results page (or report) needs to show about one run."""

    run: runs.Run
    meta: dict
    profile: CountsProfile
    labels: LabelProfile | None
    issues: list[Issue]  # counts and label problems together
    available_inputs: frozenset[InputKind]
    goals: list[GoalOption]
    default_goal: str
    settings: PreprocessSettings
    record: dict | None
    preview: pd.DataFrame | None
    figures: list[figures.ExportedFigure]

    @property
    def ready(self) -> bool:
        """True if the counts table is usable; label problems do not block preprocessing."""
        return self.profile.ok


def start_run(root: Path, inputs: Inputs) -> runs.Run:
    return runs.create(root, inputs.counts_name, inputs.counts, inputs.labels_name, inputs.labels)


def start_example_run(root: Path) -> runs.Run:
    return runs.create(
        root,
        "Example dataset (miMic authors)",
        read_table(EXAMPLE_COUNTS),
        EXAMPLE_TAGS.name,
        read_table(EXAMPLE_TAGS, index_col=0),
    )


def describe(run: runs.Run) -> RunView:
    profile = profile_counts(run.counts())
    issues = list(profile.issues)
    label_profile = _profile_labels(run, profile.sample_ids, issues)

    available: set[InputKind] = {"counts"}
    if label_profile is not None and label_profile.ok:
        available.add("labels")
    options = goal_options(frozenset(available))
    record = run.record()
    return RunView(
        run=run,
        meta=run.meta(),
        profile=profile,
        labels=label_profile,
        issues=issues,
        available_inputs=frozenset(available),
        goals=options,
        default_goal=default_goal(options),
        settings=CANONICAL,
        record=record,
        preview=run.processed_preview() if record else None,
        figures=figures.load_manifest(run.figures_dir),
    )


def build_dataset(
    run: runs.Run, settings: PreprocessSettings = CANONICAL, cache_dir: Path | None = None
) -> tuple[Dataset, PreprocessResult]:
    """The one canonical representation every engine consumes, validated against the contract."""
    raw = run.counts()
    result = preprocess(raw, settings, cache_dir=cache_dir)
    features = result.table.rename_axis(ID_COLUMN)
    features.index = features.index.astype(str)

    label_profile = _profile_labels(run, list(features.index), issues=[])
    usable = label_profile is not None and label_profile.ok
    dataset = Dataset(
        features=features,
        settings=settings,
        raw_counts=count_matrix(raw),
        labels=label_profile.values if usable else None,
        label_kind=label_profile.kind if usable else None,
    )
    return dataset.validate(), result


def run_goal(run: runs.Run, goal_id: str, cache_dir: Path | None = None) -> None:
    """Run the chosen goal and store its outputs in the run folder.

    Raises ``UserFacingError`` with a message and a fix if it cannot run.
    """
    goal = get_goal(goal_id)
    option = next((o for o in describe(run).goals if goal and o.goal.id == goal.id), None)
    if option is None or not option.enabled or goal_id not in ENGINES:
        raise InputError(
            f"'{goal.title if goal else goal_id}' cannot run on this data yet.",
            option.reason if option else "Choose one of the listed options.",
        )
    engine = ENGINES[goal_id]

    run.set_status("running", goal=goal_id, error=None)
    try:
        dataset, result = build_dataset(run, engine.preprocessing, cache_dir)
        run.save_result(result)  # the shared representation is kept for every run
        engine.run(dataset, run.figures_dir)
    except UserFacingError as exc:
        run.set_status("failed", error={"message": exc.message, "fix": exc.fix})
        raise
    run.set_status("done")


def _profile_labels(run: runs.Run, sample_ids: list[str], issues: list[Issue]) -> LabelProfile | None:
    """Profile the run's labels file, if any; problems are appended to ``issues``."""
    labels = run.labels()
    if labels is None:
        return None
    try:
        profile = profile_labels(labels, sample_ids)
    except ProfileError as exc:
        issues.append(Issue("error", exc.message, exc.fix))
        return None
    issues += profile.issues
    return profile
