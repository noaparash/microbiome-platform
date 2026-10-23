"""What the user can ask for, which tool answers it, and which inputs it needs.

``requires`` is how the upload adapts to the task: "Just preprocess" needs
only a counts table; miMic and iMic also need a labels file; LOCATE needs a
metabolite table. ``label_kinds`` limits a task to the label types its tool
handles. A task that cannot run says why, and what to add.

``recommend`` picks the pre-selected task and explains why in plain language:
what the user asked for if it can run; otherwise miMic when there are usable
labels; otherwise preprocessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from microplatform.core.contract import INPUT_KINDS, INPUT_NAMES, InputKind, LabelKind

Status = Literal["available", "next", "planned"]

COUNTS: frozenset[InputKind] = frozenset({"counts"})
COUNTS_AND_LABELS: frozenset[InputKind] = frozenset({"counts", "labels"})
COUNTS_AND_METABOLITES: frozenset[InputKind] = frozenset({"counts", "metabolites"})

# Inputs that can already be added to an existing run from the Plan step.
ADDABLE: frozenset[InputKind] = frozenset({"labels"})

LABEL_WORDS = {"binary": "two groups", "categorical": "three or more groups", "continuous": "a continuous label"}


@dataclass(frozen=True)
class Goal:
    id: str
    title: str
    question: str  # how the home page asks it
    description: str
    tool: str
    status: Status
    requires: frozenset[InputKind]
    label_kinds: frozenset[LabelKind] | None = None  # None: any label type
    unsupported_note: str = ""  # why other label types cannot run (shown to the user)


GOALS: tuple[Goal, ...] = (
    Goal("preprocess", "Just preprocess (MIPMLP only)",
         "I just want my data cleaned and normalised",
         "Get the cleaned, normalised table to use in your own analysis.",
         "MIPMLP", "available", COUNTS),
    Goal("differ", "Find bacteria that differ between groups",
         "Which bacteria differ between my groups?",
         "Which taxa are linked to the label, tested along the taxonomy tree.",
         "miMic", "available", COUNTS_AND_LABELS,
         label_kinds=frozenset({"binary", "continuous"}),
         unsupported_note="the published miMic code fails on three or more groups; "
                          "combine them into two, or use a continuous label"),
    Goal("predict", "Predict the outcome from the microbiome",
         "Can the microbiome predict my outcome?",
         "A neural network on tree-ordered images of each sample.",
         "iMic", "next", COUNTS_AND_LABELS),
    Goal("group", "See how samples group",
         "How do my samples group together?",
         "Distances between samples, a map of them, and clusters.",
         "GIMIC", "available", COUNTS),
    Goal("metabolites", "Link bacteria to metabolites",
         "How do my bacteria relate to my metabolites?",
         "Predict metabolite levels and find a shared representation.",
         "LOCATE", "planned", COUNTS_AND_METABOLITES),
)


@dataclass(frozen=True)
class GoalOption:
    goal: Goal
    enabled: bool
    reason: str = ""  # why it is disabled, in plain language
    missing: tuple[InputKind, ...] = ()  # inputs the user would need to add


@dataclass(frozen=True)
class Recommendation:
    goal_id: str
    reasons: list[str]  # plain-language "why", shown in the Plan step
    unlock: dict[InputKind, list[str]]  # input the user can add now → task titles it enables


def get_goal(goal_id: str | None) -> Goal | None:
    return next((g for g in GOALS if g.id == goal_id), None)


def requirement_text(goal: Goal) -> str:
    """'a counts table and a labels file' — for the upload box."""
    return " and ".join(INPUT_NAMES[k] for k in INPUT_KINDS if k in goal.requires)


def goal_options(available: frozenset[InputKind], label_kind: LabelKind | None = None) -> list[GoalOption]:
    """Each goal, enabled or not, given the inputs provided and the label type."""
    options = []
    for goal in GOALS:
        missing = tuple(k for k in INPUT_KINDS if k in goal.requires - available)
        needs = f"Needs {' and '.join(INPUT_NAMES[k] for k in missing)}." if missing else ""
        if goal.status != "available":
            reason = " ".join(filter(None, ["Coming next." if goal.status == "next" else "Planned.", needs]))
            options.append(GoalOption(goal, False, reason, missing))
        elif missing:
            options.append(GoalOption(goal, False, needs, missing))
        elif "labels" in goal.requires and goal.label_kinds and label_kind not in goal.label_kinds:
            reason = f"Your labels have {LABEL_WORDS.get(label_kind, 'an unsupported type')}: {goal.unsupported_note}."
            options.append(GoalOption(goal, False, reason[0].upper() + reason[1:]))
        else:
            options.append(GoalOption(goal, True))
    return options


def default_goal(options: list[GoalOption]) -> str:
    """The pre-selected choice, so most users only need one click."""
    return next(o.goal.id for o in options if o.enabled)


def recommend(options: list[GoalOption], requested: str | None = None) -> Recommendation:
    """Pick the pre-selected task and explain the choice."""
    by_id = {o.goal.id: o for o in options}
    asked = by_id.get(requested) if requested else None
    reasons: list[str] = []

    if asked and asked.enabled:
        chosen = asked.goal.id
        reasons.append(f"You asked: “{asked.goal.question}” — your data has everything this needs.")
    else:
        if asked:
            if asked.goal.status != "available":
                detail = f"{asked.goal.tool}, the tool that answers it, is not in the platform yet"
            elif asked.missing:
                detail = f"this needs {' and '.join(INPUT_NAMES[k] for k in asked.missing)}"
            else:
                detail = asked.reason.rstrip(".")[0].lower() + asked.reason.rstrip(".")[1:]
            reasons.append(f"You asked: “{asked.goal.question}” — {detail}, so we suggest what can run now.")
        if by_id["differ"].enabled:
            chosen = "differ"
            reasons.append("Your data has labels, so miMic can test which bacteria differ, "
                           "along the taxonomy tree.")
        else:
            chosen = default_goal(options)
    if chosen == "preprocess":
        reasons.append("Preprocessing with MIPMLP is the first step of every analysis, and it can run now.")
    else:
        reasons.append("Every analysis starts with MIPMLP preprocessing; the cleaned table is included in the results.")

    unlock: dict[InputKind, list[str]] = {}
    for option in options:
        for kind in option.missing:
            if kind in ADDABLE and option.goal.status == "available":
                unlock.setdefault(kind, []).append(option.goal.title)
    return Recommendation(chosen, reasons, unlock)
