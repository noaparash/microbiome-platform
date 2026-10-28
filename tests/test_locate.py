"""LOCATE's adapter: metabolite checks and preparation, and the engine's round trip through a
separate interpreter. The real LOCATE needs its own environment (not installed here), so these
tests run the same runner against a small stand-in package with the authors' two function
signatures. The reproduction test against the real tool is in test_reproduction.py."""

import ast
import dataclasses
import inspect
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core.contract import Dataset, check_settings
from microplatform.core.metabolites import (LOCATE_METABOLITES, MIN_PAIRED, prepare_metabolites,
                                            profile_metabolites)
from microplatform.engines import ENGINES
from microplatform.engines.locate import PYTHON_SETTING, RUNNER, LocateBackend, LocateEngine, LocateUnavailable
from microplatform.router.goals import get_goal

# A stand-in for the LOCATE package: the authors' two functions, same signatures and return
# shapes (LOCATE_predict returns predictions WITHOUT sample IDs), fitted by least squares on the
# first 10 features (the synthetic metabolites below depend only on those).
FAKE_LOCATE = '''
import numpy as np
import pandas as pd

class Model:
    training = True
    def __init__(self, weights):
        self.weights = weights

def LOCATE_training(X_train, Y_train, X_val, Y_val, representation_size=10, weight_decay_rep=0.02,
                    weight_decay_dis=0.2, lr_rep=0.001, lr_dis=0.01, rep_coef=1.0, dis_coef=0.0,
                    activation_rep="elu", activation_dis="elu", neurons=20, neurons2=10, dropout=0.08):
    weights, *_ = np.linalg.lstsq(X_train.to_numpy()[:, :10], Y_train.to_numpy(), rcond=None)
    return Model(weights)

def LOCATE_predict(model, X_val, metab_names):
    pred = X_val.to_numpy()[:, :10] @ model.weights
    Z_val = pd.DataFrame(pred[:, :3], index=X_val.index)
    return Z_val, pd.DataFrame(pred, columns=metab_names)
'''


@pytest.fixture(scope="module")
def fake_locate(tmp_path_factory):
    folder = tmp_path_factory.mktemp("fake_locate")
    (folder / "LOCATE").mkdir()
    (folder / "LOCATE" / "__init__.py").write_text(textwrap.dedent(FAKE_LOCATE), encoding="utf-8")
    return LocateBackend(sys.executable, extra_paths=(str(folder),))


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    """The example's shared table (with LOCATE's z-scoring) and metabolites that depend on it."""
    tmp = tmp_path_factory.mktemp("locate_data")
    run = workflows.start_example_run(tmp / "runs")
    data, _ = workflows.build_dataset(run, LocateEngine.preprocessing, tmp / "cache", engine="LOCATE")
    rng = np.random.default_rng(0)
    weights = rng.normal(size=(10, 12))
    levels = np.exp(data.features.to_numpy()[:, :10] @ weights)  # positive, like concentrations
    metabolites = pd.DataFrame(levels, index=data.features.index, columns=[f"m{i}" for i in range(12)])
    metabolites["never_detected"] = 0.0  # constant after preparation: left out
    return dataclasses.replace(data, metabolites=metabolites).validate()


# --- the engine follows the contract ------------------------------------------------------------

def test_locate_engine_follows_the_contract():
    engine = LocateEngine()
    assert engine.requires == get_goal("metabolites").requires == {"counts", "metabolites"}
    check_settings(engine.preprocessing, engine.name)  # z-scoring per feature is an allowed variation
    assert engine.preprocessing.z_scoring == "col" and engine.preprocessing.taxonomy_group == "sub PCA"
    assert inspect.get_annotations(LocateEngine.run, eval_str=True)["data"] is Dataset
    # Not offered to users until its environment exists and its reproduction test passes.
    assert get_goal("metabolites").status == "planned" and "metabolites" not in ENGINES


def test_the_runner_runs_on_locates_old_python():
    """The runner executes in LOCATE's Python 3.7-3.10 environment: no newer syntax, no microplatform."""
    source = RUNNER.read_text(encoding="utf-8")
    ast.parse(source, feature_version=(3, 7))
    assert "microplatform" not in "".join(
        line for line in source.splitlines() if line.lstrip().startswith(("import", "from")))


# --- the round trip through LOCATE's own interpreter -------------------------------------------

def test_engine_round_trip(dataset, fake_locate, tmp_path):
    result = LocateEngine(fake_locate).run(dataset, tmp_path / "work")
    scores = result.tables["metabolite_scores"]
    assert len(scores) == 12 and "never_detected" not in set(scores["metabolite"])
    # Predictions come back without sample IDs; if they were re-attached wrongly, the
    # correlations would be near 0. The stand-in fits these metabolites almost perfectly.
    assert scores["spearman"].median() > 0.8
    test_rows = result.tables["predicted_metabolites_test"]
    assert len(test_rows) == 8 and test_rows["sample"].isin(dataset.features.index).all()
    latent = result.tables["latent_representation"]
    assert len(latent) == 40 and list(latent.columns[:3]) == ["sample", "set", "z1"]
    assert (latent["set"] == "test").sum() == 8

    record = result.record
    assert record["tool"] == "LOCATE" and record["seed"] == 42 and record["test_size"] == 0.2
    assert record["environment"]["python"] == ".".join(map(str, sys.version_info[:3]))
    assert record["hyperparameters"]["dropout"] == 0.08  # the authors' defaults, read in their environment
    assert record["metabolites"]["left_out_constant"] == 1
    assert record["metabolites"]["settings"]["confirmed"] is False
    assert any("provisional" in line for line in result.summary)
    assert [f.name for f in result.figures] == ["locate_metabolite_scores"]
    assert (tmp_path / "work" / "locate.log").exists()


def test_without_locates_environment_it_says_what_to_do(dataset, tmp_path, monkeypatch):
    monkeypatch.delenv(PYTHON_SETTING, raising=False)
    with pytest.raises(LocateUnavailable) as error:
        LocateEngine().run(dataset, tmp_path)
    assert PYTHON_SETTING in error.value.fix


def test_a_failing_tool_reports_its_error(dataset, tmp_path):
    broken = LocateBackend(sys.executable, extra_paths=(str(tmp_path / "nowhere"),))
    with pytest.raises(RuntimeError, match="LOCATE failed"):
        LocateEngine(broken).run(dataset, tmp_path / "work")


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
