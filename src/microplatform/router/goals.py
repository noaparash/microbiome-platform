"""What the user can ask for, and which tool answers it.

For now the router only offers choices and a default. Rules that pick the
default from the data (labels → miMic, metabolites → LOCATE, …) arrive with
the engines themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["available", "next", "planned"]


@dataclass(frozen=True)
class Goal:
    id: str
    title: str
    description: str
    tool: str
    status: Status
    needs_labels: bool = False


GOALS: tuple[Goal, ...] = (
    Goal("preprocess", "Just preprocess (MIPMLP only)",
         "Get the cleaned, normalised table to use in your own analysis.",
         "MIPMLP", "available"),
    Goal("differ", "Find bacteria that differ between groups",
         "Which taxa are linked to the label, tested along the taxonomy tree.",
         "miMic", "next", needs_labels=True),
    Goal("predict", "Predict the outcome from the microbiome",
         "A neural network on tree-ordered images of each sample.",
         "iMic", "planned", needs_labels=True),
    Goal("group", "See how samples group",
         "Distances between samples, a map of them, and clusters.",
         "GIMIC", "planned"),
    Goal("metabolites", "Link bacteria to metabolites",
         "Predict metabolite levels and find a shared representation.",
         "LOCATE", "planned"),
)


@dataclass(frozen=True)
class GoalOption:
    goal: Goal
    enabled: bool
    reason: str = ""  # why it is disabled, in plain language


def get_goal(goal_id: str) -> Goal | None:
    return next((g for g in GOALS if g.id == goal_id), None)


def goal_options(has_labels: bool) -> list[GoalOption]:
    options = []
    for goal in GOALS:
        if goal.status != "available":
            reason = "Coming next." if goal.status == "next" else "Planned."
            options.append(GoalOption(goal, False, reason))
        elif goal.needs_labels and not has_labels:
            options.append(GoalOption(goal, False, "Needs a labels file."))
        else:
            options.append(GoalOption(goal, True))
    return options


def default_goal(options: list[GoalOption]) -> str:
    """The pre-selected choice, so most users only need one click."""
    return next(o.goal.id for o in options if o.enabled)
