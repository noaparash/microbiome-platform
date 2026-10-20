from microplatform.router.goals import GOALS, default_goal, get_goal, goal_options


def test_just_preprocess_is_offered_and_preselected():
    options = goal_options(has_labels=False)
    preprocess = next(o for o in options if o.goal.id == "preprocess")
    assert preprocess.enabled
    assert preprocess.goal.title == "Just preprocess (MIPMLP only)"
    assert default_goal(options) == "preprocess"


def test_unavailable_goals_explain_why():
    for option in goal_options(has_labels=True):
        if not option.enabled:
            assert option.reason


def test_every_tool_has_a_goal():
    assert {g.tool for g in GOALS} == {"MIPMLP", "miMic", "iMic", "GIMIC", "LOCATE"}


def test_get_goal():
    assert get_goal("preprocess").tool == "MIPMLP"
    assert get_goal("nonsense") is None
