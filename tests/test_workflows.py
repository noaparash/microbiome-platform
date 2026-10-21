"""The full workflow, used without any website: the package is the product."""

import pandas as pd
import pytest

from microplatform import runs, workflows
from microplatform.core.inputs import InputError, sort_uploads
from microplatform.core.preprocessing import PreprocessError

BAD_COUNTS = b"ID,asv0\na,x\ntaxonomy,k__Bacteria\n"


@pytest.fixture
def root(tmp_path):
    return tmp_path / "runs"


def test_new_run_is_uploaded_and_ready(root):
    run = workflows.start_example_run(root)
    view = workflows.describe(run)
    assert run.status == "uploaded"
    assert view.ready and view.record is None
    assert view.default_goal == "differ"  # binary labels: miMic is recommended
    assert view.labels.kind == "binary"


def test_preprocess_only_end_to_end(root, tmp_path):
    run = workflows.start_example_run(root)
    workflows.run_goal(run, "preprocess", cache_dir=tmp_path / "cache")
    assert run.status == "done"
    assert run.meta()["goal"] == "preprocess"
    view = workflows.describe(run)
    assert view.record["output_features"] > 0
    assert pd.read_csv(run.processed_file, index_col=0).shape[0] == 40
    assert runs.load(root, run.id) == run  # the run ID is a stable results link


def test_unavailable_goal_is_refused(root):
    run = workflows.start_example_run(root)
    with pytest.raises(InputError, match="cannot run") as info:
        workflows.run_goal(run, "predict")
    assert info.value.fix == "Coming next."
    assert run.status == "uploaded"


def test_failure_is_recorded_with_its_fix(root):
    run = workflows.start_run(root, sort_uploads([("bad.csv", BAD_COUNTS)]))
    view = workflows.describe(run)
    assert not view.ready
    assert all(issue.fix for issue in view.issues)
    with pytest.raises(PreprocessError):
        workflows.run_goal(run, "preprocess")
    assert run.status == "failed"
    assert run.meta()["error"]["fix"]


def test_the_requested_question_is_remembered(root):
    run = workflows.start_example_run(root, requested_goal="differ")
    assert run.meta()["requested_goal"] == "differ"
    assert workflows.start_example_run(root, requested_goal="nonsense").meta().get("requested_goal") is None


def test_labels_can_be_added_later(root):
    counts = ("counts.csv", b"ID,asv0\ns1,4\ns2,5\ntaxonomy,k__Bacteria\n")
    run = workflows.start_run(root, sort_uploads([counts]))
    assert workflows.describe(run).available_inputs == {"counts"}
    workflows.add_labels(run, "tags.csv", b"ID,Tag\ns1,0\ns2,1\n")
    view = workflows.describe(run)
    assert view.available_inputs == {"counts", "labels"}
    assert view.meta["labels_name"] == "tags.csv"


def test_steps_follow_the_run(root, tmp_path):
    run = workflows.start_example_run(root)
    assert workflows.describe(run).step == 3
    workflows.run_goal(run, "preprocess", cache_dir=tmp_path / "cache")
    assert workflows.describe(run).step == 4
    bad = workflows.start_run(root, sort_uploads([("bad.csv", BAD_COUNTS)]))
    assert workflows.describe(bad).step == 2


def test_label_file_problem_does_not_block_preprocessing(root):
    labels = ("labels.csv", b"ID,a,b\nx,1,2\n")  # several columns, none named Tag
    counts = ("counts.csv", b"ID,asv0\ns1,4\ntaxonomy,k__Bacteria\n")
    view = workflows.describe(workflows.start_run(root, sort_uploads([counts, labels])))
    assert view.ready
    assert any("Tag" in issue.message for issue in view.issues)
