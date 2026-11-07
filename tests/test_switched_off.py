"""A server can switch tasks off (MICROPLATFORM_DISABLED_GOALS): shown as not offered, and they cannot run."""

import pytest

from microplatform import workflows
from microplatform.core.inputs import InputError
from microplatform.router.goals import SWITCHED_OFF, goal_options, recommend, switched_off

EVERYTHING = frozenset({"counts", "labels", "metabolites"})


def test_nothing_is_switched_off_by_default(monkeypatch):
    monkeypatch.delenv("MICROPLATFORM_DISABLED_GOALS", raising=False)
    assert switched_off() == frozenset()
    assert all(o.enabled for o in goal_options(EVERYTHING, "binary"))


def test_a_switched_off_task_is_listed_with_the_reason_and_never_recommended(monkeypatch):
    monkeypatch.setenv("MICROPLATFORM_DISABLED_GOALS", " metabolites ")
    options = {o.goal.id: o for o in goal_options(EVERYTHING, "binary")}
    assert not options["metabolites"].enabled and options["metabolites"].reason == SWITCHED_OFF
    assert options["differ"].enabled
    rec = recommend(list(options.values()))
    assert rec.goal_id == "differ"  # a metabolite table would otherwise pick LOCATE
    asked = recommend(list(options.values()), requested="metabolites")
    assert "not offered on this server" in asked.reasons[0] and asked.goal_id != "metabolites"
    without = recommend(list({o.goal.id: o for o in goal_options(frozenset({"counts"}), None)}.values()))
    assert "metabolites" not in without.unlock  # no "add a metabolite table" for a task that cannot run


def test_an_unknown_task_name_is_refused(monkeypatch):
    monkeypatch.setenv("MICROPLATFORM_DISABLED_GOALS", "metabolites,locate")
    with pytest.raises(ValueError, match="unknown tasks"):
        switched_off()


def test_it_cannot_run_and_the_site_says_so(monkeypatch, tmp_path):
    from microplatform.web import create_app

    monkeypatch.setenv("MICROPLATFORM_DISABLED_GOALS", "metabolites")
    run = workflows.start_example_run(tmp_path / "runs")
    with pytest.raises(InputError, match="cannot run"):
        workflows.check_goal(run, "metabolites")
    app = create_app({"TESTING": True, "JOBS": "inline", "RUNS_DIR": tmp_path / "r", "CACHE_DIR": tmp_path / "c"})
    client = app.test_client()
    assert "Not on this server" in client.get("/").get_data(as_text=True)
    assert "Not on this server" in client.get("/methods").get_data(as_text=True)
