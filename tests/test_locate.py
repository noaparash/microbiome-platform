"""LOCATE: the Lightning-2 conversion (locate_lightning2), metabolite checks and preparation, and the
engine. Faithfulness to the original is checked separately, against the original LOCATE in its own
Python 3.10 environment (validation/locate/: PROTOCOL.md, RESULTS.md)."""

import ast
import contextlib
import dataclasses
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import locate_lightning2
from microplatform import workflows
from microplatform.core.contract import Dataset, check_settings
from microplatform.core.metabolites import (LOCATE_METABOLITES, MIN_PAIRED, prepare_metabolites,
                                            profile_metabolites)
from microplatform.engines import ENGINES
from microplatform.engines.locate import LocateEngine, fit_and_predict
from microplatform.router.goals import get_goal

PORT = Path(locate_lightning2.__file__).parent


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    """The example's shared table (with LOCATE's z-scoring) and metabolites that depend on it."""
    tmp = tmp_path_factory.mktemp("locate_data")
    run = workflows.start_example_run(tmp / "runs")
    data, _ = workflows.build_dataset(run, LocateEngine.preprocessing, tmp / "cache", engine="LOCATE")
    rng = np.random.default_rng(0)
    levels = np.exp(data.features.to_numpy()[:, :10] @ rng.normal(size=(10, 12)))  # positive, like concentrations
    metabolites = pd.DataFrame(levels, index=data.features.index, columns=[f"m{i}" for i in range(12)])
    metabolites["never_detected"] = 0.0  # constant after preparation: left out
    return dataclasses.replace(data, metabolites=metabolites).validate()


# --- the conversion -------------------------------------------------------------------------------

def test_the_conversion_keeps_the_authors_interface():
    assert {"LOCATE_Model", "LOCATE_training", "LOCATE_predict"} <= set(locate_lightning2.__all__)
    signature = inspect.signature(locate_lightning2.LOCATE_training)
    defaults = {k: p.default for k, p in signature.parameters.items() if p.default is not inspect.Parameter.empty}
    assert defaults == {  # LOCATE-model 0.0.3's defaults, unchanged
        "representation_size": 10, "weight_decay_rep": 0.02, "weight_decay_dis": 0.2, "lr_rep": 0.001,
        "lr_dis": 0.01, "rep_coef": 1.0, "dis_coef": 0.0, "activation_rep": "elu", "activation_dis": "elu",
        "neurons": 20, "neurons2": 10, "dropout": 0.08}
    assert locate_lightning2.BASED_ON == "LOCATE-model 0.0.3"
    assert (PORT / "LICENSE.txt").exists() and (PORT / "CHANGES.md").exists()


def test_the_conversion_stands_alone_and_marks_every_change():
    """It must not import microplatform (it is also tested in a separate Python 3.10 environment)."""
    for path in PORT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        imported += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(name.startswith("microplatform") for name in imported), path.name
    model = (PORT / "LOCATE_model.py").read_text(encoding="utf-8")
    functions = (PORT / "LOCATE_functions.py").read_text(encoding="utf-8")
    assert model.count("[lightning2]") == 3 and functions.count("[lightning2]") == 3  # CHANGES.md lists 6
    assert "self.automatic_optimization = False" in model


# --- the engine follows the contract ------------------------------------------------------------

def test_locate_engine_follows_the_contract():
    engine = LocateEngine()
    assert engine.requires == get_goal("metabolites").requires == {"counts", "metabolites"}
    check_settings(engine.preprocessing, engine.name)  # z-scoring per feature is an allowed variation
    assert engine.preprocessing.z_scoring == "col" and engine.preprocessing.taxonomy_group == "sub PCA"
    assert inspect.get_annotations(LocateEngine.run, eval_str=True)["data"] is Dataset
    # Not offered to users until it is validated against the original (validation/locate/).
    assert get_goal("metabolites").status == "planned" and "metabolites" not in ENGINES


def test_engine_runs_the_converted_locate(dataset, tmp_path):
    result = LocateEngine().run(dataset, tmp_path / "work")
    scores = result.tables["metabolite_scores"]
    assert len(scores) == 12 and "never_detected" not in set(scores["metabolite"])
    test_rows = result.tables["predicted_metabolites_test"]
    assert len(test_rows) == 8 and test_rows["sample"].isin(dataset.features.index).all()
    latent = result.tables["latent_representation"]
    assert len(latent) == 40 and list(latent.columns[:3]) == ["sample", "set", "z1"] and latent.shape[1] == 12
    record = result.record
    assert record["package"] == "locate_lightning2" and record["based_on"] == "LOCATE-model 0.0.3"
    assert record["seed"] == 42 and record["epochs"] > 0
    assert record["metabolites"]["left_out_constant"] == 1 and not record["metabolites"]["settings"]["confirmed"]
    assert any("provisional" in line for line in result.summary)
    # Honest reporting (validation/locate/PROTOCOL.md, revised standard): one run, and why the paper looks better.
    assert any("one training run" in line and "best of 16" in line for line in result.summary)
    assert [f.name for f in result.figures] == ["locate_metabolite_scores"]
    assert (tmp_path / "work" / "lightning_logs").exists()  # the tool's own files stay in the work folder


def test_the_product_is_repeatable(dataset, tmp_path):
    """Unlike the original on torch 1.13 (validation/locate, Amendment 1), the same seed gives the same result."""
    X = dataset.features.iloc[:, :20]
    Y, _ = prepare_metabolites(dataset.metabolites)
    runs = []
    for i in range(2):
        folder = tmp_path / str(i)
        folder.mkdir()
        with contextlib.chdir(folder):
            runs.append(fit_and_predict(X.iloc[:32], Y.iloc[:32], X.iloc[32:], Y.iloc[32:], seed=0))
    assert runs[0]["epochs"] == runs[1]["epochs"]
    pd.testing.assert_frame_equal(runs[0]["pred_val"], runs[1]["pred_val"], check_exact=True)


# --- metabolite tables ----------------------------------------------------------------------

def _table(n=30, m=5, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.uniform(0.1, 10, size=(n, m)), index=[f"s{i}" for i in range(n)],
                        columns=[f"met{j}" for j in range(m)])


def test_a_good_metabolite_table_passes():
    table = _table()
    profile = profile_metabolites(table, list(table.index))
    assert profile.ok and profile.n_paired == 30 and profile.n_metabolites == 5


@pytest.mark.parametrize(("change", "words"), [
    (lambda t: t.assign(met0=-t["met0"]), "negative"),
    (lambda t: t.mask(t > 9.5), "missing"),
    (lambda t: t.assign(note="x"), "not numbers"),
    (lambda t: t.iloc[: MIN_PAIRED - 1], f"needs at least {MIN_PAIRED}"),
])
def test_metabolite_problems_come_with_a_fix(change, words):
    table = change(_table())
    profile = profile_metabolites(table, [f"s{i}" for i in range(30)])
    errors = [i for i in profile.issues if i.level == "error"]
    assert not profile.ok and any(words in i.message for i in errors) and all(i.fix for i in errors)


def test_preparation_is_relative_then_log_then_zscore():
    table = _table()
    prepared, record = prepare_metabolites(table)
    assert np.allclose(prepared.mean(), 0) and np.allclose(prepared.std(ddof=0), 1)
    # Relative first: scaling a whole sample (e.g. a more concentrated extract) changes nothing.
    scaled = table.copy()
    scaled.iloc[0] *= 10
    assert np.allclose(prepare_metabolites(scaled)[0], prepared)
    assert record["settings"] == dataclasses.asdict(LOCATE_METABOLITES) and record["metabolites_used"] == 5
