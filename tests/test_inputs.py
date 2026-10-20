import pytest

from microplatform.core.inputs import InputError, sort_uploads
from microplatform.core.profiler import profile_counts, profile_labels, read_table
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS, TEMPLATES

COUNTS = (EXAMPLE_COUNTS.name, EXAMPLE_COUNTS.read_bytes())
TAGS = (EXAMPLE_TAGS.name, EXAMPLE_TAGS.read_bytes())


@pytest.mark.parametrize("files", [[COUNTS, TAGS], [TAGS, COUNTS]])
def test_files_are_recognised_in_any_order(files):
    inputs = sort_uploads(files)
    assert inputs.counts_name == "example_counts.csv"
    assert inputs.labels_name == "example_tag.csv"
    assert inputs.labels.columns.tolist() == ["Tag"]


def test_counts_alone_is_enough():
    inputs = sort_uploads([COUNTS])
    assert inputs.labels is None


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "No file"),
        ([COUNTS, TAGS, TAGS], "at most two"),
        ([("data.xlsx", b"PK...")], "Excel"),
        ([("notes.pdf", b"%PDF")], "not a CSV or TSV"),
        ([TAGS], "No counts table"),
        ([COUNTS, COUNTS], "Both files look like counts"),
        ([TAGS, TAGS], "Neither file"),
        ([("empty.csv", b"")], "could not be read"),
    ],
)
def test_bad_uploads_say_what_and_how_to_fix(files, message):
    with pytest.raises(InputError, match=message) as info:
        sort_uploads(files)
    assert info.value.fix  # every error comes with a suggested fix


def test_templates_follow_the_expected_format():
    counts = profile_counts(read_table(TEMPLATES["counts_template.csv"]))
    assert counts.ok and counts.has_taxonomy and counts.value_kind == "counts"
    labels = profile_labels(read_table(TEMPLATES["labels_template.csv"], index_col=0), counts.sample_ids)
    assert labels.ok and labels.missing == []
