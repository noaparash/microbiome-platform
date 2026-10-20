"""What the user can ask for, which tool answers it, and which inputs it needs.

``requires`` is how the upload adapts to the task: "Just preprocess" needs
only a counts table; miMic and iMic also need a labels file; LOCATE needs a
metabolite table. A task whose inputs are missing is shown with what to add.

For now the router offers these choices with a default. Rules that pick the
default from the data (labels → miMic, metabolites → LOCATE, …) arrive with
the engines themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from microplatform.core.contract import INPUT_KINDS, INPUT_NAMES, InputKind

Status = Literal["available", "next", "planned"]

COUNTS: frozenset[InputKind] = frozenset({"counts"})
COUNTS_AND_LABELS: frozenset[InputKind] = frozenset({"counts", "labels"})
COUNTS_AND_METABOLITES: frozenset[InputKind] = frozenset({"counts", "metabolites"})


@dataclass(frozen=True)
class Goal:
    id: str
    title: str
    description: str
    tool: str
    status: Status
    requires: frozenset[InputKind]


GOALS: tuple[Goal, ...] = (
    Goal("preprocess", "Just preprocess (MIPMLP only)",
         "Get the cleaned, normalised table to use in your own analysis.",
         "MIPMLP", "available", COUNTS),
    Goal("differ", "Find bacteria that differ between groups",
         "Which taxa are linked to the label, tested along the taxonomy tree.",
         "miMic", "next", COUNTS_AND_LABELS),
    Goal("predict", "Predict the outcome from the microbiome",
         "A neural network on tree-ordered images of each sample.",
         "iMic", "planned", COUNTS_AND_LABELS),
    Goal("group", "See how samples group",
         "Distances between samples, a map of them, and clusters.",
         "GIMIC", "planned", COUNTS),
    Goal("metabolites", "Link bacteria to metabolites",
         "Predict metabolite levels and find a shared representation.",
         "LOCATE", "planned", COUNTS_AND_METABOLITES),
)


@dataclass(frozen=True)
class GoalOption:
    goal: Goal
    enabled: bool
    reason: str = ""  # why it is disabled, in plain language
    missing: tuple[InputKind, ...] = ()  # inputs the user would need to add


def get_goal(goal_id: str) -> Goal | None:
    return next((g for g in GOALS if g.id == goal_id), None)


def goal_options(available: frozenset[InputKind]) -> list[GoalOption]:
    """Each goal, enabled or not, given which inputs the user has provided."""
    options = []
    for goal in GOALS:
        missing = tuple(k for k in INPUT_KINDS if k in goal.requires - available)
        needs = f"Needs {' and '.join(INPUT_NAMES[k] for k in missing)}." if missing else ""
        if goal.status != "available":
            reason = " ".join(filter(None, ["Coming next." if goal.status == "next" else "Planned.", needs]))
            options.append(GoalOption(goal, False, reason, missing))
        elif missing:
            options.append(GoalOption(goal, False, needs, missing))
        else:
            options.append(GoalOption(goal, True))
    return options


def default_goal(options: list[GoalOption]) -> str:
    """The pre-selected choice, so most users only need one click."""
    return next(o.goal.id for o in options if o.enabled)
