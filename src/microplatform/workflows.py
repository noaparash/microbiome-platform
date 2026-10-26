"""Complete workflows: start a run, describe it, and run the chosen goal.

The website calls these, and so will the future background worker.
Neither of them needs to know how profiling or preprocessing works.

Every goal runs the same way: build the one canonical ``Dataset`` (see
``core/contract.py``), validate it, and hand it to the goal's engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from microplatform import runs
from microplatform.core.contract import ID_COLUMN, Dataset, InputKind
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import InputError, Inputs, read_labels_upload, sort_uploads
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
from microplatform.router.goals import GoalOption, Recommendation, get_goal, goal_options, recommend

TABLE_PREVIEW_ROWS = 15  # rows of each result table shown on the page; the CSV has all

__all__ = [
    "RunView", "add_labels", "analyze", "build_bundle", "build_dataset", "describe", "run_goal",
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
    recommendation: Recommendation
    default_goal: str
    settings: PreprocessSettings
    record: dict | None  # preprocessing record
    preview: pd.DataFrame | None
    figures: list[figures.ExportedFigure]
    engine: dict | None = None  # what the goal's engine found: tool, summary, record, tables
    tables: dict[str, pd.DataFrame] | None = None  # the engine's tables (first rows, for the page)
    options: dict | None = None  # goal id → the engine's advanced settings (EngineOption)

    @property
    def ready(self) -> bool:
        """True if the counts table is usable; label problems do not block preprocessing."""
        return self.profile.ok

    @property
    def result_title(self) -> str:
        """'Find bacteria that differ between groups (miMic)', or the preprocessing title."""
        if self.engine and self.engine["tool"] != "MIPMLP":
            return f"{get_goal(self.engine['goal']).title} ({self.engine['tool']})"
        return "Preprocessed with MIPMLP"

    @property
    def representation_note(self) -> str | None:
        """Plain words for any way this run's table differs from the shared table (None if it doesn't)."""
        if not self.record:
            return None
        shared = asdict(CANONICAL)
        used = self.record.get("settings", {})
        diffs = [f"{key.replace('_', ' ')} '{used[key]}' (the shared table uses '{shared[key]}')"
                 for key in shared if key in used and used[key] != shared[key]]
        return f"This analysis used {'; '.join(diffs)}." if diffs else None

    @property
    def findings(self) -> list[figures.ExportedFigure]:
        return [f for f in self.figures if f.section == "findings"]

    @property
    def quality_figures(self) -> list[figures.ExportedFigure]:
        return [f for f in self.figures if f.section == "quality"]

    @property
    def status(self) -> str:
        return self.meta.get("status", "uploaded")

    @property
    def in_progress(self) -> bool:
        """Queued or running in the background: the page should wait and refresh."""
        return self.status in ("queued", "running")

    @property
    def error(self) -> dict | None:
        return self.meta.get("error") if self.status == "failed" else None

    @property
    def show_plan(self) -> bool:
        return self.ready and self.status in ("uploaded", "failed")

    @property
    def show_results(self) -> bool:
        return self.status == "done" and bool(self.record)

    @property
    def elapsed_seconds(self) -> int | None:
        """Seconds since the run was queued, while it is in progress."""
        if not self.in_progress or "queued" not in self.meta:
            return None
        started = datetime.fromisoformat(self.meta["queued"])
        return max(0, int((datetime.now(timezone.utc) - started).total_seconds()))

    @property
    def step(self) -> int:
        """Where the run is in the 4-step flow: 1 Upload, 2 Data check, 3 Plan, 4 Results."""
        if self.in_progress or self.show_results:
            return 4
        return 3 if self.ready else 2


def start_run(root: Path, inputs: Inputs, requested_goal: str | None = None) -> runs.Run:
    """Store the uploads as a new run; ``requested_goal`` is the question picked on the home page."""
    run = runs.create(root, inputs.counts_name, inputs.counts, inputs.labels_name, inputs.labels)
    _remember_request(run, requested_goal)
    return run


def start_example_run(root: Path, requested_goal: str | None = None) -> runs.Run:
    run = runs.create(
        root,
        "Example dataset (miMic authors)",
        read_table(EXAMPLE_COUNTS),
        EXAMPLE_TAGS.name,
        read_table(EXAMPLE_TAGS, index_col=0),
    )
    _remember_request(run, requested_goal)
    return run


def analyze(
    counts: str | Path,
    labels: str | Path | None = None,
    goal: str | None = None,
    out_dir: str | Path = "microplatform-runs",
    cache_dir: str | Path | None = None,
    options: dict | None = None,
) -> RunView:
    """Run a whole analysis from files on disk, without the website.

    ``goal`` defaults to the recommended task; ``options`` are its advanced settings,
    e.g. ``{"grouping": "mean"}`` for GIMIC. All outputs (table, figures, record) are
    written to a new folder inside ``out_dir``: ``view.run.path``.
    """
    paths = [Path(counts)] + ([Path(labels)] if labels else [])
    run = start_run(Path(out_dir), sort_uploads([(p.name, p.read_bytes()) for p in paths]), goal)
    run_goal(run, goal or describe(run).default_goal, Path(cache_dir) if cache_dir else None, options)
    return describe(run)


def example_overview() -> tuple[CountsProfile, LabelProfile]:
    """The data check of the bundled example dataset, for the Example page."""
    counts = profile_counts(read_table(EXAMPLE_COUNTS))
    return counts, profile_labels(read_table(EXAMPLE_TAGS, index_col=0), counts.sample_ids)


def add_labels(run: runs.Run, name: str, content: bytes) -> None:
    """Add a labels file from the Plan step, without starting over."""
    run.add_labels(name, read_labels_upload(name, content))


def _remember_request(run: runs.Run, requested_goal: str | None) -> None:
    if get_goal(requested_goal):
        run.update_meta(requested_goal=requested_goal)


def describe(run: runs.Run) -> RunView:
    """Everything known about a run: data check, plan (recommendation and options) and results."""
    profile = profile_counts(run.counts())
    issues = list(profile.issues)
    label_profile = _profile_labels(run, profile.sample_ids, issues)

    available: set[InputKind] = {"counts"}
    usable_labels = label_profile is not None and label_profile.ok
    if usable_labels:
        available.add("labels")
    options = goal_options(frozenset(available), label_profile.kind if usable_labels else None)
    meta = run.meta()
    recommendation = recommend(options, meta.get("requested_goal"))
    record = run.record()
    engine = run.engine_record()
    return RunView(
        run=run,
        meta=meta,
        profile=profile,
        labels=label_profile,
        issues=issues,
        available_inputs=frozenset(available),
        goals=options,
        recommendation=recommendation,
        default_goal=recommendation.goal_id,
        settings=CANONICAL,
        record=record,
        preview=run.processed_preview() if record else None,
        figures=figures.load_manifest(run.figures_dir),
        engine=engine,
        tables={name: run.table(name, rows=TABLE_PREVIEW_ROWS) for name in engine["tables"]} if engine else None,
        options={goal: e.options for goal, e in ENGINES.items() if e.options},
    )


def build_dataset(
    run: runs.Run, settings: PreprocessSettings = CANONICAL, cache_dir: Path | None = None,
    engine: str | None = None,
) -> tuple[Dataset, PreprocessResult]:
    """The one canonical representation every engine consumes, validated against the contract.

    ``engine`` names the engine it is for, so only that engine's declared exceptions apply.
    """
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
        engine=engine,
    )
    return dataset.validate(), result


def run_goal(run: runs.Run, goal_id: str, cache_dir: Path | None = None, choices: dict | None = None) -> None:
    """Run the chosen goal and store its outputs in the run folder.

    ``choices`` are the engine's advanced settings (defaults when not given).
    Raises ``UserFacingError`` with a message and a fix if it cannot run.
    """
    engine = check_goal(run, goal_id)
    choices = engine.resolve(choices)

    run.set_status("running", goal=goal_id, error=None, choices=choices)
    try:
        dataset, result = build_dataset(run, engine.settings_for(choices), cache_dir, engine.name)
        run.save_result(result)  # the representation this engine used is kept for every run
        figures.export(figures.preprocessing_figures(dataset.raw_counts, dataset.settings), run.figures_dir)
        found = engine.run(dataset, run.path / "work" / engine.name.lower(), choices)
        _save_engine_result(run, engine, found, choices)
    except UserFacingError as exc:
        run.set_status("failed", error={"message": exc.message, "fix": exc.fix})
        raise
    run.set_status("done")


def check_goal(run: runs.Run, goal_id: str):
    """The engine for ``goal_id``, or ``InputError`` (with the reason) if it cannot run on this run's data."""
    goal = get_goal(goal_id)
    option = next((o for o in describe(run).goals if goal and o.goal.id == goal.id), None)
    if option is None or not option.enabled or goal_id not in ENGINES:
        raise InputError(
            f"'{goal.title if goal else goal_id}' cannot run on this data yet.",
            option.reason if option else "Choose one of the listed options.",
        )
    return ENGINES[goal_id]


def _save_engine_result(run: runs.Run, engine, found, choices: dict) -> None:
    """Store what an engine returned: tables as CSV, figures in every format, and its record."""
    for name, table in found.tables.items():
        run.save_table(name, table)
    figures.export(found.figures, run.figures_dir)
    run.save_engine_record({
        "tool": engine.name,
        "goal": engine.goal,
        "choices": choices,
        "summary": found.summary,
        "record": found.record,
        "tables": list(found.tables),
        "highlight": list(found.highlight) if found.highlight else None,
    })


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
