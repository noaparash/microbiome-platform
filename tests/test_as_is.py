"""Never preprocess twice by default: a table that already looks preprocessed is used as it is.

A real case (2026-11-08): a table prepared for miMic (64 selected taxa, values that do not add up to
one total per sample) was preprocessed again by MIPMLP (64 -> 49 features), and miMic's result moved
away from the authors' (42 taxa instead of their 34, just_mimic.csv). Used as it is, the engine gives
exactly the authors' 34 taxa and p-values (checked on that private file through the platform; here the
same is shown on the authors' public example).
"""

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from microplatform import workflows
from microplatform.core import preprocessing
from microplatform.core.inputs import sort_uploads
from microplatform.core.preprocessing import CANONICAL, preprocess
from microplatform.core.profiler import profile_counts, read_table
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.reports.overview import OVERVIEW_UNAVAILABLE

TAGS = (EXAMPLE_TAGS.name, EXAMPLE_TAGS.read_bytes())


@pytest.fixture(scope="module")
def mipmlp_output() -> bytes:
    """The example's MIPMLP output as a user would upload it: sample IDs, then one column per feature
    named as MIPMLP names it ('Bacteria;…;Lachnospiraceae_0;;'), log values (negatives too)."""
    table = preprocess(read_table(EXAMPLE_COUNTS)).table
    return table.rename_axis("ID").to_csv().encode()


def _upload(tmp_path, *files, **kwargs):
    return workflows.start_run(tmp_path / "runs", sort_uploads(list(files)), **kwargs)


def _selected_shares() -> bytes:
    """Like the real case: relative abundances of a few selected taxa, so samples add up to different totals."""
    raw = pd.read_csv(EXAMPLE_COUNTS, dtype=str)
    values = raw.iloc[:-1, 1:].astype(float)
    shares = values.div(values.sum(axis=1), axis=0).iloc[:, :40]  # 40 of 263 taxa: totals differ
    shares.columns = raw.iloc[-1, 1:41].tolist()
    shares.insert(0, "ID", raw.iloc[:-1, 0].to_numpy())
    return shares.to_csv(index=False).encode()


# --- recognising a table that is already preprocessed ------------------------------------------

def test_raw_counts_and_relative_abundances_are_preprocessed_as_usual():
    assert not profile_counts(read_table(EXAMPLE_COUNTS)).looks_preprocessed


def test_mipmlp_output_and_selected_shares_look_preprocessed(mipmlp_output):
    processed = profile_counts(sort_uploads([("processed.csv", mipmlp_output)]).counts)
    assert processed.looks_preprocessed and processed.has_negatives and processed.ok
    assert "negative values" in processed.preprocessed_because
    shares = profile_counts(sort_uploads([("shares.csv", _selected_shares())]).counts)
    assert shares.looks_preprocessed and not shares.has_negatives
    assert "add up to different totals" in shares.preprocessed_because


# --- the plan ----------------------------------------------------------------------------------

def test_such_a_table_is_used_as_it_is_by_default_and_the_plan_says_what_cannot_run(tmp_path, mipmlp_output):
    view = workflows.describe(_upload(tmp_path, ("processed.csv", mipmlp_output), TAGS))
    assert view.as_is and view.options == {}  # no preprocessing variations for a table used as it is
    goals = {o.goal.id: o for o in view.goals}
    assert not goals["preprocess"].enabled and "nothing to preprocess" in goals["preprocess"].reason
    assert goals["differ"].enabled and goals["predict"].enabled and goals["group"].enabled
    assert view.default_goal == "differ"


def test_locate_needs_mipmlp_and_says_so(tmp_path, mipmlp_output):
    raw = pd.read_csv(io.BytesIO(mipmlp_output))
    metabolites = pd.DataFrame({"ID": raw["ID"], **{f"m{i}": range(1, len(raw) + 1) for i in range(4)}})
    run = _upload(tmp_path, ("processed.csv", mipmlp_output), ("met.csv", metabolites.to_csv(index=False).encode()))
    locate = next(o for o in workflows.describe(run).goals if o.goal.id == "metabolites")
    assert not locate.enabled and "LOCATE needs MIPMLP's own preprocessing" in locate.reason
    with pytest.raises(workflows.UserFacingError, match="cannot use a table that is already preprocessed"):
        workflows.build_dataset(run, CANONICAL.with_changes(z_scoring="col"), as_is=True)


def test_the_user_can_choose_to_preprocess_it_anyway(tmp_path, mipmlp_output):
    run = _upload(tmp_path, ("processed.csv", mipmlp_output))
    workflows.set_preprocessing(run, "mipmlp")
    view = workflows.describe(run)
    assert not view.as_is and next(o for o in view.goals if o.goal.id == "preprocess").enabled
    with pytest.raises(workflows.InputError):
        workflows.set_preprocessing(run, "twice")


# --- the run -----------------------------------------------------------------------------------

def test_used_as_it_is_gives_exactly_the_result_of_the_normal_run(tmp_path, mipmlp_output, monkeypatch):
    """The example run normally (MIPMLP, then miMic) and its MIPMLP output uploaded and used as it is
    give the same miMic result, and the second never calls MIPMLP."""
    normal = _upload(tmp_path / "normal", (EXAMPLE_COUNTS.name, EXAMPLE_COUNTS.read_bytes()), TAGS)
    workflows.run_goal(normal, "differ", tmp_path / "cache")

    def no_mipmlp(*args, **kwargs):
        raise AssertionError("MIPMLP must not run on a table used as it is")

    monkeypatch.setattr(preprocessing, "_run_mipmlp", no_mipmlp)
    as_is = _upload(tmp_path / "as_is", ("processed.csv", mipmlp_output), TAGS)
    workflows.run_goal(as_is, "differ", tmp_path / "cache")

    expected = normal.table("significant_taxa")
    found = as_is.table("significant_taxa")
    assert len(found) > 0
    pd.testing.assert_frame_equal(found, expected)
    record = as_is.record()
    assert record["skipped"] and record["tool"] == "none" and "settings" not in record
    view = workflows.describe(as_is)
    assert view.overview_figures == [] and view.overview_note == OVERVIEW_UNAVAILABLE  # negatives: no overview
    assert "used exactly as uploaded" in record["summary"][0]

    with zipfile.ZipFile(io.BytesIO(workflows.build_bundle(as_is))) as zf:
        readme = zf.read("README.txt").decode()
    assert "none: the uploaded table was used as it is" in readme and "MIPMLP" not in readme.split("Please cite")[1]


def test_analyze_uses_a_preprocessed_table_as_it_is_unless_told_otherwise(tmp_path, mipmlp_output):
    path = tmp_path / "processed.csv"
    path.write_bytes(mipmlp_output)
    view = workflows.analyze(path, goal="group", out_dir=tmp_path / "a", cache_dir=tmp_path / "cache")
    assert view.as_is and view.record["skipped"]
    with pytest.raises(workflows.UserFacingError):
        workflows.analyze(path, goal="preprocess", out_dir=tmp_path / "b", cache_dir=tmp_path / "cache")


def test_web_shows_the_choice_and_switches(tmp_path, mipmlp_output):
    from microplatform.web import create_app

    app = create_app({"TESTING": True, "JOBS": "inline", "RUNS_DIR": tmp_path / "runs", "CACHE_DIR": tmp_path / "cache"})
    client = app.test_client()
    url = client.post("/upload", data={"files": [(io.BytesIO(mipmlp_output), "processed.csv")]},
                      content_type="multipart/form-data").headers["Location"]
    page = client.get(url).get_data(as_text=True)
    assert "Your table already looks preprocessed" in page and "MIPMLP is not run on it again" in page
    assert "preprocess it with MIPMLP" in page
    page = client.post(f"{url}/preprocessing", data={"preprocessing": "mipmlp"},
                       follow_redirects=True).get_data(as_text=True)
    assert "MIPMLP will preprocess this table." in page and "applies the log and the grouping twice" in page
    assert "Use my table as it is" in page
