"""The iMic engine: the published defaults, refusals, the GPU path, and housekeeping."""

import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core.contract import LABEL_COLUMN, Dataset
from microplatform.core.errors import UserFacingError
from microplatform.core.preprocessing import CANONICAL
from microplatform.engines.imic import ImicEngine, default_params, load_imic

# micrOS's form defaults (app/templates/index.html), the same as apply_iMic's own.
MICROS_DEFAULTS = {
    "l1_loss": 0.1, "weight_decay": 0.01, "lr": 0.001, "batch_size": 128, "activation": "elu",
    "dropout": 0.1, "kernel_size_a": 4, "kernel_size_b": 4, "stride": 2, "padding": 3, "padding_2": 0,
    "kernel_size_a_2": 2, "kernel_size_b_2": 7, "stride_2": 3, "channels": 3, "channels_2": 14,
    "linear_dim_divider_1": 10, "linear_dim_divider_2": 6,
}


def test_defaults_are_the_published_ones():
    params = default_params()
    assert {k: v for k, v in params.items() if k != "input_dim"} == MICROS_DEFAULTS
    params["lr"] = 99  # a fresh copy each time: apply_iMic's own default dict is never changed
    assert default_params()["lr"] == 0.001


@pytest.mark.parametrize("kind", ["continuous", "categorical"])
def test_only_two_group_labels(kind, tmp_path):
    features = pd.DataFrame({"x": [0.1, 0.2, 0.3]}, index=pd.Index(["a", "b", "c"], name="ID"))
    labels = pd.Series([0.5, 1.0, 2.0] if kind == "continuous" else [0, 1, 2], index=features.index, name=LABEL_COLUMN)
    with pytest.raises(UserFacingError, match="two-group label"):
        ImicEngine().run(Dataset(features, CANONICAL, features, labels, kind), tmp_path)


def test_tiny_groups_are_refused(tmp_path):
    features = pd.DataFrame({"x": range(8)}, index=pd.Index([f"s{i}" for i in range(8)], name="ID"), dtype=float)
    labels = pd.Series([0] * 6 + [1] * 2, index=features.index, name=LABEL_COLUMN)
    with pytest.raises(UserFacingError, match="at least 5 samples"):
        ImicEngine().run(Dataset(features, CANONICAL, features, labels, "binary"), tmp_path)


def test_the_published_gpu_branch_fails_on_lightning_2(monkeypatch):
    """Documents the upstream bug: with a GPU, run_iMic builds Trainer(gpus=1), which Lightning 2 rejects."""
    import torch

    _, _, _, run_iMic = load_imic()
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    with pytest.raises(TypeError, match="gpus"):
        run_iMic([], [], None, {"batch_size": 1})


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("imic")
    run = workflows.start_example_run(root / "runs")
    workflows.run_goal(run, "predict", root / "cache")
    return run


def test_results_on_the_example(run):
    engine = run.engine_record()
    assert engine["tool"] == "iMic" and run.status == "done"
    assert set(engine["tables"]) == {"predictions", "test_metrics"}
    predictions = run.table("predictions")
    assert set(predictions["set"]) == {"train", "test"} and len(predictions) == 40
    assert predictions.filter(like="probability_of_").iloc[:, 0].between(0, 1).all()
    record = engine["record"]
    assert record["seed"] == 42 and record["test_size"] == 0.2 and record["device"].startswith("cpu")
    assert "dropout on" in record["prediction_mode"]
    assert any("Only 8 test samples" in line for line in engine["summary"])
    assert any(f.name == "imic_roc" for f in workflows.describe(run).figures)


def test_a_gpu_machine_uses_the_cpu_path(tmp_path, monkeypatch):
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    run = workflows.start_example_run(tmp_path / "runs")
    workflows.run_goal(run, "predict", tmp_path / "cache")
    assert run.status == "done"
    assert "GPU was present" in run.engine_record()["record"]["device"]
    assert torch.cuda.is_available() is True  # restored afterwards (the monkeypatch's fake)


def test_imic_never_writes_into_the_current_folder(tmp_path, monkeypatch):
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    run = workflows.start_example_run(tmp_path / "runs")
    workflows.run_goal(run, "predict", tmp_path / "cache")
    assert list(here.iterdir()) == []
    assert (run.path / "work" / "imic" / "lightning_logs").exists()


def test_recording_never_wraps_twice():
    from microplatform.engines.imic import recording_cnn

    mipmlp, _, _, _ = load_imic()
    once = recording_cnn(mipmlp.CNN)
    twice = recording_cnn(once)
    assert twice.__bases__ == (mipmlp.CNN,)  # straight on top of the authors' class
