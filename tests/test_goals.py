from microplatform.router.goals import GOALS, default_goal, get_goal, goal_options

COUNTS = frozenset({"counts"})
COUNTS_AND_LABELS = frozenset({"counts", "labels"})


def test_just_preprocess_is_offered_and_preselected():
    options = goal_options(COUNTS)
    preprocess = next(o for o in options if o.goal.id == "preprocess")
    assert preprocess.enabled
    assert preprocess.goal.title == "Just preprocess (MIPMLP only)"
    assert default_goal(options) == "preprocess"


def test_unavailable_goals_explain_why():
    for option in goal_options(COUNTS_AND_LABELS):
        if not option.enabled:
            assert option.reason


def test_each_task_asks_for_the_right_inputs():
    """The upload adapts to the task: counts only, + labels, or + metabolites."""
    requires = {g.tool: g.requires for g in GOALS}
    assert requires["MIPMLP"] == {"counts"}
    assert requires["miMic"] == requires["iMic"] == {"counts", "labels"}
    assert requires["GIMIC"] == {"counts"}
    assert requires["LOCATE"] == {"counts", "metabolites"}


def test_missing_inputs_are_named():
    mimic = next(o for o in goal_options(COUNTS) if o.goal.tool == "miMic")
    assert mimic.missing == ("labels",)
    assert "Needs a labels file." in mimic.reason
    locate = next(o for o in goal_options(COUNTS_AND_LABELS) if o.goal.tool == "LOCATE")
    assert locate.missing == ("metabolites",)
    assert "metabolite table" in locate.reason


def test_every_tool_has_a_goal():
    assert {g.tool for g in GOALS} == {"MIPMLP", "miMic", "iMic", "GIMIC", "LOCATE"}


def test_get_goal():
    assert get_goal("preprocess").tool == "MIPMLP"
    assert get_goal("nonsense") is None
