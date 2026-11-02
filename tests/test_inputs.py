import io

import numpy as np
import pandas as pd
import pytest

from microplatform.core.inputs import InputError, read_added_upload, sort_uploads, table_kind
from microplatform.core.metabolites import MIN_PAIRED, profile_metabolites
from microplatform.core.profiler import profile_counts, profile_labels, read_table
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS, TEMPLATES

COUNTS = (EXAMPLE_COUNTS.name, EXAMPLE_COUNTS.read_bytes())
TAGS = (EXAMPLE_TAGS.name, EXAMPLE_TAGS.read_bytes())


def _metabolites(columns=5, name="metabolome.csv"):
    ids = pd.read_csv(EXAMPLE_COUNTS)["ID"].iloc[:-1]
    values = np.random.default_rng(0).uniform(0, 100, size=(len(ids), columns))
    table = pd.DataFrame(values, columns=[f"met{i}" for i in range(columns)])
    table.insert(0, "sample", ids.to_numpy())
    return name, table.to_csv(index=False).encode()


METABOLITES = _metabolites()


@pytest.mark.parametrize("files", [[COUNTS, TAGS], [TAGS, COUNTS]])
def test_files_are_recognised_in_any_order(files):
    inputs = sort_uploads(files)
    assert inputs.counts_name == "example_counts.csv"
    assert inputs.labels_name == "example_tag.csv"
    assert inputs.labels.columns.tolist() == ["Tag"]


def test_counts_alone_is_enough():
    inputs = sort_uploads([COUNTS])
    assert inputs.labels is None and inputs.metabolites is None


@pytest.mark.parametrize("files", [[COUNTS, TAGS, METABOLITES], [METABOLITES, COUNTS, TAGS], [METABOLITES, COUNTS]])
def test_a_metabolite_table_is_recognised_in_any_order(files):
    inputs = sort_uploads(files)
    assert inputs.counts_name == "example_counts.csv" and inputs.metabolites_name == "metabolome.csv"
    assert inputs.metabolites.shape == (40, 5) and all(isinstance(i, str) for i in inputs.metabolites.index)
    assert inputs.labels_name == ("example_tag.csv" if TAGS in files else None)


def test_what_makes_a_metabolite_table():
    def kind(csv):
        return table_kind(pd.read_csv(io.StringIO(csv)))
    assert kind("ID,a,b,c\ns1,1,2,3\n") == "metabolites"  # three or more numeric columns
    assert kind("ID,a,b\ns1,1,2\n") == "labels"  # a label plus a stray column: the labels file's message
    assert kind("ID,Tag,a,b,c\ns1,1,2,3,4\n") == "labels"  # a Tag column means labels
    assert kind("ID,group,site,note\ns1,x,y,z\n") == "labels"  # words, not measurements


def test_a_file_added_from_the_plan_step_is_taken_as_asked():
    two = ("two.csv", b"ID,acetate,butyrate\ns1,1.5,2\n")  # too few columns to recognise, but the user said so
    assert read_added_upload("metabolites", *two).shape == (1, 2)
    with pytest.raises(InputError, match="looks like a counts table") as info:
        read_added_upload("metabolites", *COUNTS)
    assert "one numeric column per metabolite" in info.value.fix


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "No file"),
        ([COUNTS, TAGS, TAGS, TAGS], "at most 3"),
        ([("data.xlsx", b"PK...")], "Excel"),
        ([("notes.pdf", b"%PDF")], "not a CSV or TSV"),
        ([TAGS], "No counts table"),
        ([COUNTS, COUNTS], "both look like counts tables"),
        ([COUNTS, METABOLITES, _metabolites(name="second.csv")], "both look like metabolite tables"),
        ([COUNTS, TAGS, TAGS], "both look like labels files"),
        ([TAGS, TAGS], "both look like labels files"),
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
    metabolites = read_table(TEMPLATES["metabolites_template.csv"])
    assert table_kind(metabolites) == "metabolites"
    profile = profile_metabolites(metabolites.set_index("ID"), counts.sample_ids)
    # Only its size is too small for LOCATE (it is a format example): no other problem.
    assert [i.message for i in profile.issues if i.level == "error"] == [
        f"Only 3 samples are in both the counts and the metabolite table; LOCATE needs at least {MIN_PAIRED}."]
