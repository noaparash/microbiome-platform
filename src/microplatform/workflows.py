"""Complete workflows: start a run, describe it, and run the chosen goal.

The website calls these, and so will the future background worker.
Neither of them needs to know how profiling or preprocessing works.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from microplatform import runs
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import InputError, Inputs
from microplatform.core.preprocessing import CANONICAL, PreprocessSettings, preprocess
from microplatform.core.profiler import (
    CountsProfile,
    Issue,
    LabelProfile,
    ProfileError,
    profile_counts,
    profile_labels,
    read_table,
)
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.router.goals import GoalOption, default_goal, get_goal, goal_options


@dataclass
class RunView:
    """Everything a results page (or report) needs to show about one run."""

    run: runs.Run
    meta: dict
    profile: CountsProfile
    labels: LabelProfile | None
    issues: list[Issue]  # counts and label problems together
    goals: list[GoalOption]
    default_goal: str
    settings: PreprocessSettings
    record: dict | None
    preview: pd.DataFrame | None

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

    label_profile = None
    labels = run.labels()
    if labels is not None:
        try:
            label_profile = profile_labels(labels, profile.sample_ids)
            issues += label_profile.issues
        except ProfileError as exc:
            issues.append(Issue("error", exc.message, exc.fix))

    options = goal_options(has_labels=label_profile is not None and label_profile.ok)
    record = run.record()
    return RunView(
        run=run,
        meta=run.meta(),
        profile=profile,
        labels=label_profile,
        issues=issues,
        goals=options,
        default_goal=default_goal(options),
        settings=CANONICAL,
        record=record,
        preview=run.processed_preview() if record else None,
    )


def run_goal(run: runs.Run, goal_id: str, cache_dir: Path | None = None) -> None:
    """Run the chosen goal and store its outputs in the run folder.

    Raises ``UserFacingError`` with a message and a fix if it cannot run.
    """
    goal = get_goal(goal_id)
    option = next((o for o in describe(run).goals if goal and o.goal.id == goal.id), None)
    if option is None or not option.enabled:
        raise InputError(
            f"'{goal.title if goal else goal_id}' cannot run on this data yet.",
            option.reason if option else "Choose one of the listed options.",
        )

    run.set_status("running", goal=goal_id, error=None)
    try:
        _WORKFLOWS[goal_id](run, cache_dir)
    except UserFacingError as exc:
        run.set_status("failed", error={"message": exc.message, "fix": exc.fix})
        raise
    run.set_status("done")


def _preprocess_only(run: runs.Run, cache_dir: Path | None) -> None:
    run.save_result(preprocess(run.counts(), CANONICAL, cache_dir=cache_dir))


# One entry per available goal; engines will add theirs here.
_WORKFLOWS = {"preprocess": _preprocess_only}
