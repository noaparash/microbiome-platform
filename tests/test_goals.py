from microplatform.router.goals import (
    GOALS,
    default_goal,
    get_goal,
    goal_options,
    recommend,
    requirement_text,
)

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


def test_requirement_text_is_readable():
    assert requirement_text(get_goal("preprocess")) == "a counts table"
    assert requirement_text(get_goal("differ")) == "a counts table and a labels file"
    assert requirement_text(get_goal("metabolites")) == "a counts table and a metabolite table"


def test_recommendation_without_a_request():
    rec = recommend(goal_options(COUNTS))
    assert rec.goal_id == "preprocess"
    assert any("first step" in r for r in rec.reasons)
    assert set(rec.unlock["labels"]) == {"Find bacteria that differ between groups",
                                         "Predict the outcome from the microbiome"}


def test_recommendation_explains_an_unavailable_request():
    rec = recommend(goal_options(COUNTS_AND_LABELS), requested="differ")
    assert rec.goal_id == "preprocess"
    assert "Which bacteria differ between my groups?" in rec.reasons[0]
    assert "not in the platform yet" in rec.reasons[0]
    assert "labels" not in rec.unlock  # labels are already there


def test_recommendation_honours_a_runnable_request():
    rec = recommend(goal_options(COUNTS), requested="preprocess")
    assert rec.goal_id == "preprocess" and rec.reasons[0].startswith("You asked")


def test_every_tool_has_a_goal():
    assert {g.tool for g in GOALS} == {"MIPMLP", "miMic", "iMic", "GIMIC", "LOCATE"}


def test_get_goal():
    assert get_goal("preprocess").tool == "MIPMLP"
    assert get_goal("nonsense") is None
