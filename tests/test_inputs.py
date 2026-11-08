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


# --- taxonomy in the column names (no taxonomy row) ----------------------------------------------

from microplatform.core.inputs import is_lineage, with_taxonomy_row  # noqa: E402

LINEAGES = ["k__Bacteria;p__Actinobacteria;c__Actinobacteria;o__Bifidobacteriales;f__;g__;s__",
            "k__Bacteria;p__;c__;o__;f__;g__;s__",
            "k__Bacteria;p__Firmicutes;c__Clostridia",
            "k__Bacteria;p__Firmicutes;c__Clostridia"]  # the same lineage twice


def _headers_table(sep=","):
    """A typical lab table: ERR sample IDs, lineages as column names (empty ranks, one repeated),
    relative abundances with many zeros, no taxonomy row."""
    rng = np.random.default_rng(1)
    rows = []
    for i in range(12):
        values = rng.dirichlet(np.ones(len(LINEAGES))) * (rng.random(len(LINEAGES)) > 0.4)
        values[0] += 0.01  # never an all-zero sample
        values = 100 * values / values.sum()  # percentages: each sample adds up to 100
        rows.append([f"ERR15490{i:02d}", *(repr(float(v)) for v in values)])
    lines = [sep.join(["ID", *LINEAGES])] + [sep.join(r) for r in rows]
    return ("abundances.csv" if sep == "," else "abundances.tsv"), ("\n".join(lines) + "\n").encode()


@pytest.mark.parametrize(("name", "expected"), [
    ("k__Bacteria;p__Firmicutes;c__Bacilli", True), ("k__Bacteria;p__;c__", True),
    ("d__Bacteria; p__Bacillota", True), ("k__Bacteria", True), ("k__Bacteria;", True),
    ("Tag", False), ("ASV_1", False), ("met1", False), ("Bacteria;Firmicutes", False), ("", False)])
def test_lineage_names_are_recognised(name, expected):
    assert is_lineage(name) is expected


@pytest.mark.parametrize("sep", [",", "\t"])
def test_a_table_with_lineages_as_column_names_is_a_counts_table(sep):
    name, content = _headers_table(sep)
    inputs = sort_uploads([(name, content), TAGS])
    assert inputs.counts_layout == "headers" and inputs.counts_name == name
    raw = inputs.counts
    assert str(raw.iloc[-1, 0]) == "taxonomy" and len(raw) == 13
    assert raw.iloc[-1, 1:].tolist() == LINEAGES  # exactly as written, the repeated name too
    profile = profile_counts(raw)
    assert profile.has_taxonomy and profile.n_taxa == 4 and profile.value_kind == "relative"
    assert not [i for i in profile.issues if i.level == "error"]


def test_the_shared_format_is_left_alone():
    assert with_taxonomy_row(COUNTS[1]) is None  # it already has a taxonomy row
    assert sort_uploads([COUNTS]).counts_layout == "row"
    assert with_taxonomy_row(TAGS[1]) is None and with_taxonomy_row(METABOLITES[1]) is None


def test_a_table_without_any_taxonomy_still_explains_both_layouts():
    table = b"ID,ASV_1,ASV_2,ASV_3\ns1,1,2,3\ns2,4,5,6\n"
    with pytest.raises(InputError) as caught:
        sort_uploads([("plain.csv", table)])
    assert "column names that are taxonomy strings" in caught.value.message
    assert "as the column name, or in a last row named 'taxonomy'" in caught.value.fix


def test_a_lineage_table_cannot_be_added_as_labels():
    name, content = _headers_table()
    with pytest.raises(InputError, match="looks like a counts table"):
        read_added_upload("labels", name, content)
