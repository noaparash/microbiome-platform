import pytest

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


def test_a_table_without_labels_is_explained_kindly_not_as_an_error():
    """Counts only: the plan names what runs (MIPMLP, GIMIC, the data overview) and what each
    missing file would add (labels: miMic, iMic; metabolites: LOCATE), without sounding like a fault."""
    rec = recommend(goal_options(COUNTS))
    text = " ".join(rec.reasons)
    assert rec.goal_id == "preprocess"
    assert "No labels file, and that's fine" in text
    assert "clean and normalise it (MIPMLP) and see how your samples group (GIMIC)" in text
    assert "data overview (composition, diversity and sparsity)" in text and "without group tests" in text
    assert "(miMic and iMic) need a labels file" in text and "add one below without starting over" in text
    assert "(LOCATE) needs a metabolite table" in text
    assert not any(word in text.lower() for word in ("error", "cannot", "invalid"))
    # With a metabolite table but no labels, LOCATE is among what can run.
    with_metabolites = " ".join(recommend(goal_options(COUNTS | {"metabolites"})).reasons)
    assert "link your bacteria to your metabolites (LOCATE)" in with_metabolites
    assert "needs a metabolite table" not in with_metabolites


def test_with_labels_there_is_no_note_about_labels():
    assert not any("labels file" in r for r in recommend(goal_options(COUNTS_AND_LABELS, "binary")).reasons)


def test_a_switched_off_tool_is_not_promised(monkeypatch):
    monkeypatch.setenv("MICROPLATFORM_DISABLED_GOALS", "differ,group")
    text = " ".join(recommend(goal_options(COUNTS)).reasons)
    assert "(iMic) needs a labels file" in text and "miMic" not in text and "GIMIC" not in text


def test_requirement_text_is_readable():
    assert requirement_text(get_goal("preprocess")) == "a counts table"
    assert requirement_text(get_goal("differ")) == "a counts table and a labels file"
    assert requirement_text(get_goal("metabolites")) == "a counts table and a metabolite table"


def test_recommendation_without_labels_is_preprocessing():
    rec = recommend(goal_options(COUNTS))
    assert rec.goal_id == "preprocess"
    assert any("first step" in r for r in rec.reasons)
    # Only tasks that can actually run once labels are added are offered as "unlocks".
    assert rec.unlock["labels"] == ["Find bacteria that differ between groups",
                                    "Predict the outcome from the microbiome"]


@pytest.mark.parametrize("kind", ["binary", "continuous"])
def test_usable_labels_recommend_mimic(kind):
    rec = recommend(goal_options(COUNTS_AND_LABELS, kind))
    assert rec.goal_id == "differ"
    assert any("miMic" in r for r in rec.reasons)
    assert "labels" not in rec.unlock  # labels are already there


def test_categorical_labels_disable_mimic_with_the_reason():
    options = goal_options(COUNTS_AND_LABELS, "categorical")
    differ = next(o for o in options if o.goal.id == "differ")
    assert not differ.enabled
    assert "three or more groups" in differ.reason and "combine them into two" in differ.reason
    assert recommend(options).goal_id == "preprocess"


def test_recommendation_explains_a_request_that_misses_an_input():
    rec = recommend(goal_options(COUNTS_AND_LABELS, "binary"), requested="metabolites")
    assert rec.goal_id == "differ"  # the best task that can run instead
    assert "How do my bacteria relate to my metabolites?" in rec.reasons[0]
    assert "needs a metabolite table" in rec.reasons[0]
    assert rec.unlock["metabolites"] == ["Link bacteria to metabolites"]  # and it can be added in place


def test_an_uploaded_metabolite_table_recommends_locate():
    rec = recommend(goal_options(COUNTS_AND_LABELS | {"metabolites"}, "binary"))
    assert rec.goal_id == "metabolites" and any("metabolite table" in r for r in rec.reasons)
    assert "metabolites" not in rec.unlock


def test_recommendation_honours_a_runnable_request():
    rec = recommend(goal_options(COUNTS), requested="preprocess")
    assert rec.goal_id == "preprocess" and rec.reasons[0].startswith("You asked")


def test_every_tool_has_a_goal():
    assert {g.tool for g in GOALS} == {"MIPMLP", "miMic", "iMic", "GIMIC", "LOCATE"}


def test_get_goal():
    assert get_goal("preprocess").tool == "MIPMLP"
    assert get_goal("nonsense") is None
