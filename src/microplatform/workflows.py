"""Complete workflows: start a run, describe it, and run the chosen goal.

The website calls these, and so will the future background worker.
Neither of them needs to know how profiling or preprocessing works.

Every goal runs the same way: build the one canonical ``Dataset`` (see
``core/contract.py``), validate it, and hand it to the goal's engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from microplatform import runs
from microplatform.core.contract import ID_COLUMN, Dataset, InputKind
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import (
    InputError,
    Inputs,
    read_labels_upload,
    read_metabolites_upload,
    sort_uploads,
)
from microplatform.core.metabolites import MetaboliteProfile, profile_metabolites
from microplatform.core.preprocessing import (
    CANONICAL,
    PreprocessResult,
    PreprocessSettings,
    preprocess,
    use_as_is,
)
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
from microplatform.reports import figures, overview
from microplatform.reports.bundle import build_bundle
from microplatform.router.goals import GoalOption, Recommendation, get_goal, goal_options, recommend

TABLE_PREVIEW_ROWS = 15  # rows of each result table shown on the page; the CSV has all

# Plain words for a declared preprocessing variation, shown as the results page's "Different table" note.
SETTING_WORDS = {
    ("z_scoring", "col"): "the cleaned table with one extra step, as the LOCATE paper does: each feature "
                          "rescaled to mean 0 and spread 1 (z-score per feature; the shared table is not rescaled)",
}

__all__ = [
    "RunView", "add_labels", "add_metabolites", "analyze", "build_bundle", "build_dataset", "describe", "run_goal",
    "set_preprocessing", "start_example_run", "start_run",
]

# How a run's table becomes the features: preprocessed with MIPMLP, or used as it is because it already
# looks preprocessed (never preprocessed twice without the user choosing it). See ``preprocessing_mode``.
PREPROCESSING_MODES = ("mipmlp", "as_is")
AS_IS_NOTHING_TO_DO = ("Your table is used as it is, because it already looks preprocessed, so there is nothing "
                       "to preprocess. If it is raw data, choose to preprocess it in the data check above.")
AS_IS_NEEDS_MIPMLP = ("{tool} needs MIPMLP's own preprocessing ({how}), so it cannot use a table that is already "
                      "preprocessed. If your table is raw data, choose to preprocess it in the data check above.")


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
    metabolites: MetaboliteProfile | None = None  # the metabolite table's check, if there is one
    preprocessing: str = "mipmlp"  # "mipmlp" or "as_is" (see PREPROCESSING_MODES)

    @property
    def as_is(self) -> bool:
        """The table is used as uploaded, without MIPMLP (it already looks preprocessed)."""
        return self.preprocessing == "as_is"

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
        if not self.record or self.record.get("skipped"):
            return None
        shared = asdict(CANONICAL)
        used = self.record.get("settings", {})
        diffs = [SETTING_WORDS.get((key, used[key]),
                                   f"{key.replace('_', ' ')} '{used[key]}' (the shared table uses '{shared[key]}')")
                 for key in shared if key in used and used[key] != shared[key]]
        return f"This analysis used {'; '.join(diffs)}." if diffs else None

    @property
    def findings(self) -> list[figures.ExportedFigure]:
        return [f for f in self.figures if f.section == "findings"]

    @property
    def quality_figures(self) -> list[figures.ExportedFigure]:
        return [f for f in self.figures if f.section == "quality"]

    @property
    def overview_figures(self) -> list[figures.ExportedFigure]:
        """The data overview (composition, diversity, sparsity): descriptive, the same for every tool."""
        return [f for f in self.figures if f.section == "overview"]

    @property
    def overview_note(self) -> str | None:
        """Why a finished run has no descriptive overview (negative values), or None."""
        if self.show_results and not self.overview_figures and self.profile.has_negatives:
            return overview.OVERVIEW_UNAVAILABLE
        return None

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
    run = runs.create(root, inputs.counts_name, inputs.counts, inputs.labels_name, inputs.labels,
                      inputs.metabolites_name, inputs.metabolites)
    if inputs.counts_layout != "row":  # recorded so the data check can say where the taxonomy came from
        run.update_meta(counts_layout=inputs.counts_layout)
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
    metabolites: str | Path | None = None,
    preprocessing: str | None = None,
) -> RunView:
    """Run a whole analysis from files on disk, without the website.

    ``goal`` is one of ``"preprocess"`` (MIPMLP only), ``"differ"`` (miMic),
    ``"predict"`` (iMic), ``"group"`` (GIMIC) or ``"metabolites"`` (LOCATE, which needs
    ``metabolites``: a table with sample IDs first and one column per metabolite); it
    defaults to the recommended task (see ``GOALS``). ``options`` are its advanced settings, e.g. ``{"grouping": "mean"}``
    for GIMIC. All outputs are written to a new folder inside ``out_dir``,
    ``view.run.path``: ``processed.csv``, ``tables/``, ``figures/``, ``record.json`` and
    ``engine.json``. ``view.engine`` holds the summary and the record of every setting.
    ``preprocessing`` is ``"mipmlp"`` or ``"as_is"`` (use the table as it is, for a table that is
    already preprocessed); by default it is ``"as_is"`` exactly when the table already looks
    preprocessed (negative values, or samples adding up to different totals), so a table is never
    preprocessed twice without asking for it. ``view.preprocessing`` says which was used.
    Raises ``UserFacingError`` (with a message and a fix) if the data cannot be used.
    """
    paths = [Path(p) for p in (counts, labels, metabolites) if p]
    run = start_run(Path(out_dir), sort_uploads([(p.name, p.read_bytes()) for p in paths]), goal)
    if preprocessing is not None:
        set_preprocessing(run, preprocessing)
    run_goal(run, goal or describe(run).default_goal, Path(cache_dir) if cache_dir else None, options)
    return describe(run)


def example_overview() -> tuple[CountsProfile, LabelProfile]:
    """The data check of the bundled example dataset, for the Example page."""
    counts = profile_counts(read_table(EXAMPLE_COUNTS))
    return counts, profile_labels(read_table(EXAMPLE_TAGS, index_col=0), counts.sample_ids)


def add_labels(run: runs.Run, name: str, content: bytes) -> None:
    """Add a labels file from the Plan step, without starting over."""
    run.add_labels(name, read_labels_upload(name, content))


def add_metabolites(run: runs.Run, name: str, content: bytes) -> None:
    """Add a metabolite table from the Plan step, without starting over."""
    run.add_metabolites(name, read_metabolites_upload(name, content))


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
    metabolite_profile = _profile_metabolites(run, profile.sample_ids, issues)
    if metabolite_profile is not None and metabolite_profile.ok:
        available.add("metabolites")
    options = goal_options(frozenset(available), label_profile.kind if usable_labels else None)
    meta = run.meta()
    mode = preprocessing_mode(meta, profile)
    if mode == "as_is":
        options = _without_mipmlp(options)
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
        # Advanced settings are preprocessing variations: none apply to a table used as it is.
        options={} if mode == "as_is" else {goal: e.options for goal, e in ENGINES.items() if e.options},
        metabolites=metabolite_profile,
        preprocessing=mode,
    )


def preprocessing_mode(meta: dict, profile: CountsProfile) -> str:
    """'as_is' or 'mipmlp': the user's choice if made, otherwise 'as_is' exactly when the table already
    looks preprocessed (``CountsProfile.looks_preprocessed``), so nothing is preprocessed twice by default."""
    chosen = meta.get("preprocessing")
    if chosen in PREPROCESSING_MODES:
        return chosen
    return "as_is" if profile.looks_preprocessed else "mipmlp"


def set_preprocessing(run: runs.Run, mode: str) -> None:
    """The user's choice from the data check: 'as_is' (use the table as uploaded) or 'mipmlp'."""
    if mode not in PREPROCESSING_MODES:
        raise InputError(f"'{mode}' is not a preprocessing choice.", "Choose 'as_is' or 'mipmlp'.")
    if run.status in ("queued", "running"):
        raise InputError("This analysis is already running.", "Wait for it to finish, then change the choice.")
    run.update_meta(preprocessing=mode)


def _without_mipmlp(options: list[GoalOption]) -> list[GoalOption]:
    """The goals for a table used as it is: those that need MIPMLP's own run are switched off, with why."""
    adjusted = []
    for option in options:
        engine = ENGINES.get(option.goal.id)
        if option.goal.id == "preprocess":
            option = replace(option, enabled=False, reason=AS_IS_NOTHING_TO_DO, missing=())
        elif option.enabled and engine is not None and engine.preprocessing != CANONICAL:
            how = "with a z-score per taxon" if engine.preprocessing.z_scoring != "No" else "with settings of its own"
            option = replace(option, enabled=False, reason=AS_IS_NEEDS_MIPMLP.format(tool=option.goal.tool, how=how))
        adjusted.append(option)
    return adjusted


def build_dataset(
    run: runs.Run, settings: PreprocessSettings = CANONICAL, cache_dir: Path | None = None,
    engine: str | None = None, as_is: bool = False,
) -> tuple[Dataset, PreprocessResult]:
    """The one canonical representation every engine consumes, validated against the contract.

    ``engine`` names the engine it is for, so only that engine's declared exceptions apply.
    ``as_is``: the uploaded table is the features (it is already preprocessed; ``use_as_is``), which
    only engines that use the shared settings can take.
    """
    raw = run.counts()
    if as_is and settings != CANONICAL:
        raise UserFacingError(
            "This analysis needs MIPMLP's own preprocessing settings, so it cannot use a table that is "
            "already preprocessed.",
            "If your table is raw data, choose to preprocess it in the data check; otherwise choose "
            "another task or the default settings.")
    result = use_as_is(raw) if as_is else preprocess(raw, settings, cache_dir=cache_dir)
    features = result.table.rename_axis(ID_COLUMN)
    features.index = features.index.astype(str)

    label_profile = _profile_labels(run, list(features.index), issues=[])
    usable = label_profile is not None and label_profile.ok
    metabolite_profile = _profile_metabolites(run, list(features.index), issues=[])
    metabolites = None
    if metabolite_profile is not None and metabolite_profile.ok:
        table = run.metabolites()
        metabolites = table.loc[[s for s in features.index if s in set(table.index)]]  # counts-table order
    dataset = Dataset(
        features=features,
        settings=settings,
        raw_counts=count_matrix(raw),
        labels=label_profile.values if usable else None,
        label_kind=label_profile.kind if usable else None,
        metabolites=metabolites,
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

    as_is = preprocessing_mode(run.meta(), profile_counts(run.counts())) == "as_is"
    run.set_status("running", goal=goal_id, error=None, choices=choices)
    try:
        dataset, result = build_dataset(run, engine.settings_for(choices), cache_dir, engine.name, as_is=as_is)
        run.save_result(result)  # the representation this engine used is kept for every run
        figures.export(figures.preprocessing_figures(dataset.raw_counts, dataset.settings), run.figures_dir)
        figures.export(overview.overview_figures(dataset.raw_counts, dataset.settings, dataset.labels,
                                                 dataset.label_kind, dataset=_dataset_name(run)), run.figures_dir)
        found = engine.run(dataset, run.path / "work" / engine.name.lower(), choices)
        _save_engine_result(run, engine, found, choices)
    except UserFacingError as exc:
        run.set_status("failed", error={"message": exc.message, "fix": exc.fix})
        raise
    run.set_status("done")


def _dataset_name(run: runs.Run) -> str | None:
    """The uploaded counts file's name without its extension (the composition figure's heading)."""
    name = run.meta().get("counts_name")
    return Path(name).stem if name else None


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
    figures.export_rendered(found.rendered, run.figures_dir)  # the tool's own figure leads the findings
    run.save_engine_record({
        "tool": engine.name,
        "goal": engine.goal,
        "choices": choices,
        "summary": found.summary,
        "notes": found.notes,
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


def _profile_metabolites(run: runs.Run, sample_ids: list[str], issues: list[Issue]) -> MetaboliteProfile | None:
    """Check the run's metabolite table, if any; problems are appended to ``issues``, marked as its own."""
    table = run.metabolites()
    if table is None:
        return None
    profile = profile_metabolites(table, sample_ids)
    issues += [replace(i, message=f"Metabolite table: {i.message}") for i in profile.issues]
    return profile
