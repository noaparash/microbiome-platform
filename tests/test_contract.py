"""The shared data contract (core/contract.py) holds for every module and every engine.

If any of these fail, some tool has started to expect different inputs or a
different representation from the others. Fix the tool, not this test.
"""

import ast
import typing
from pathlib import Path

import pandas as pd
import pytest

import microplatform
from microplatform import workflows
from microplatform.core.contract import (
    ALLOWED_VARIATIONS,
    ID_COLUMN,
    INPUT_KINDS,
    LABEL_COLUMN,
    RANK_SEPARATOR,
    TAXONOMY_ROW,
    ContractError,
    Dataset,
    check_settings,
)
from microplatform.core.inputs import sort_uploads
from microplatform.core.preprocessing import CANONICAL
from microplatform.engines import ENGINES, Engine
from microplatform.examples import EXAMPLE_COUNTS
from microplatform.router.goals import GOALS, get_goal

PACKAGE = Path(microplatform.__file__).parent
CONVENTIONS = {ID_COLUMN, TAXONOMY_ROW, LABEL_COLUMN, RANK_SEPARATOR}


# --- 1. the conventions are defined in exactly one place ------------------------------

def test_conventions_are_never_retyped_outside_the_contract():
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.name == "contract.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Literal text inside f-strings is prose (e.g. "2024;25:113" in a citation), not a convention.
        prose = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in CONVENTIONS and id(node) not in prose:
                offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno} {node.value!r}")
    assert not offenders, "Import these names from core/contract.py instead: " + ", ".join(offenders)


# --- 2. every engine follows the contract ----------------------------------------------

@pytest.mark.parametrize("engine", ENGINES.values(), ids=lambda e: e.name)
def test_engine_declares_a_valid_interface(engine):
    assert isinstance(engine, Engine)
    goal = get_goal(engine.goal)
    assert goal is not None and goal.tool == engine.name
    assert engine.requires == goal.requires, "engine and goal disagree on required inputs"
    assert "counts" in engine.requires and engine.requires <= set(INPUT_KINDS)
    check_settings(engine.preprocessing)  # only allowed variations of CANONICAL


@pytest.mark.parametrize("engine", ENGINES.values(), ids=lambda e: e.name)
def test_engine_consumes_only_the_canonical_dataset(engine):
    hints = typing.get_type_hints(type(engine).run)
    assert hints["data"] is Dataset, "engines must take the shared Dataset, nothing else"


def test_every_goal_names_valid_inputs():
    for goal in GOALS:
        assert "counts" in goal.requires and goal.requires <= set(INPUT_KINDS), goal.id


def test_available_goals_and_engines_match():
    available = {g.id for g in GOALS if g.status == "available"}
    assert available == set(ENGINES), "every available goal needs an engine, and vice versa"


# --- 3. the canonical representation -----------------------------------------------------

@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return workflows.start_example_run(tmp_path_factory.mktemp("runs"))


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("cache")


@pytest.fixture(scope="module")
def dataset(run, cache):
    return workflows.build_dataset(run, CANONICAL, cache)[0]


def test_example_dataset_meets_the_contract(dataset):
    assert dataset.features.index.name == ID_COLUMN
    assert dataset.labels.name == LABEL_COLUMN and dataset.label_kind == "binary"
    assert dataset.available_inputs == {"counts", "labels"}
    assert dataset.features.columns.str.contains(RANK_SEPARATOR).all()


@pytest.mark.parametrize("engine", ENGINES.values(), ids=lambda e: e.name)
def test_every_engine_runs_on_the_same_representation(engine, run, cache, tmp_path):
    data = workflows.build_dataset(run, engine.preprocessing, cache)[0]
    assert data.validate() is data
    engine.run(data, tmp_path)


def test_a_differently_named_label_column_is_normalised(tmp_path):
    counts = (EXAMPLE_COUNTS.name, EXAMPLE_COUNTS.read_bytes())
    ids = pd.read_csv(EXAMPLE_COUNTS)[ID_COLUMN].iloc[:-1]
    labels = pd.DataFrame({"sample": ids, "disease": [0, 1] * (len(ids) // 2)}).to_csv(index=False)
    run = workflows.start_run(tmp_path, sort_uploads([counts, ("labels.csv", labels.encode())]))
    data = workflows.build_dataset(run, CANONICAL, tmp_path / "cache")[0]
    assert data.labels.name == LABEL_COLUMN


def _with_missing_value(d):
    features = d.features.copy()
    features.iloc[0, 0] = float("nan")
    return features


BREAKS = {
    "missing value": _with_missing_value,
    "duplicate sample": lambda d: pd.concat([d.features, d.features.iloc[:1]]),
    "unnamed index": lambda d: d.features.rename_axis(None),
    "non-float column": lambda d: d.features.assign(extra="x"),
}


@pytest.mark.parametrize("name", BREAKS)
def test_broken_features_are_rejected(dataset, name):
    with pytest.raises(ContractError):
        Dataset(BREAKS[name](dataset), dataset.settings, dataset.raw_counts).validate()


def test_labels_must_follow_the_contract(dataset):
    base = dict(features=dataset.features, settings=dataset.settings, raw_counts=dataset.raw_counts)
    with pytest.raises(ContractError):  # wrong name
        Dataset(**base, labels=dataset.labels.rename("disease"), label_kind="binary").validate()
    with pytest.raises(ContractError):  # unknown sample
        Dataset(**base, labels=pd.Series([1], index=["nobody"], name=LABEL_COLUMN),
                label_kind="binary").validate()
    with pytest.raises(ContractError):  # labels without a kind
        Dataset(**base, labels=dataset.labels).validate()


# --- 4. preprocessing variations -------------------------------------------------------------

@pytest.mark.parametrize("field", sorted(ALLOWED_VARIATIONS))
def test_allowed_variations_pass(field):
    value = {"taxonomy_level": 6, "z_scoring": "col"}[field]
    check_settings(CANONICAL.with_changes(**{field: value}))


@pytest.mark.parametrize("change", [{"normalization": "relative"}, {"taxonomy_group": "mean"},
                                    {"rare_bacteria_threshold": 0.05}])
def test_other_variations_are_rejected(change):
    with pytest.raises(ContractError):
        check_settings(CANONICAL.with_changes(**change))
