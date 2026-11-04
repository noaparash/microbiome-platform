"""miMic's full output bundle by the authors' own code (engines/mimic_authors.py)."""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import microplatform.web
from microplatform.core.errors import UserFacingError
from microplatform.engines import mimic_authors
from microplatform.engines.mimic import load_mimic

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "tests" / "data" / "mimic_example"
PLOTS = ["correlations_tree.pdf", "correlations_tree.png", "correlations_tree.svg", "corrs_within_family.png",
         "hist.png", "interaction.png", "rsp_vs_beta.png", "tax_vs_rp_sp_anova_p.png"]


# --- the adjustments: scoped, and each one gives the old behaviour -----------------------------

def test_the_adjustments_are_undone_after_a_run():
    load_mimic()
    import ete3
    import mimic_da.miMic_test as mt

    before = (mt.stats, mt.cm, mt.creare_tree_view, mt.calculate_rsp, ete3.TreeNode.show,
              ete3.TreeNode.render, pd.Index.__ne__)
    with mimic_authors.compatible():
        assert mt.stats is not before[0] and mt.cm is not before[1]
    assert before == (mt.stats, mt.cm, mt.creare_tree_view, mt.calculate_rsp, ete3.TreeNode.show,
                      ete3.TreeNode.render, pd.Index.__ne__)


def test_kstest_gives_the_documented_result():
    import mimic_da.miMic_test as mt

    x = np.random.default_rng(0).normal(size=200)
    with mimic_authors.compatible():
        got = mt.stats.kstest(x, "norm", args=(0.1, 1.2))
        assert mt.stats.kstest is not stats.kstest and mt.stats.f is stats.f  # everything else unchanged
    want = stats.kstest(x, stats.norm(0.1, 1.2).cdf)
    assert (got.statistic, got.pvalue) == (want.statistic, want.pvalue)


def test_colormaps_are_the_same():
    import matplotlib
    import mimic_da.miMic_test as mt

    with mimic_authors.compatible():
        assert mt.cm.get_cmap("Set2").colors == matplotlib.colormaps["Set2"].colors


def test_the_index_test_gives_the_old_numpy_answer_only_inside_the_tree_drawer(monkeypatch):
    load_mimic()
    import mimic_da.miMic_test as mt

    seen = {}

    def drawer(*args, **kwargs):  # stands in for the authors' drawer, which the adjustment wraps
        seen["empty"] = bool(pd.Index([]) != None)  # noqa: E711 (miMic's own test)
        seen["one"] = bool(pd.Index(["a"]) != None)  # noqa: E711
        seen["mask"] = list(pd.Index(["a", "b"]) != "a")  # other comparisons are unchanged

    monkeypatch.setattr(mt, "creare_tree_view", drawer)
    with mimic_authors.compatible():
        mt.creare_tree_view()
        with pytest.raises(ValueError):  # outside the drawer: NumPy's current behaviour
            bool(pd.Index([]) != None)  # noqa: E711
    assert seen == {"empty": False, "one": True, "mask": [False, True]}


# --- inputs -------------------------------------------------------------------------------------

def _table():
    return pd.DataFrame(np.arange(12, dtype=float).reshape(4, 3), index=["s1", "s2", "s3", "s4"],
                        columns=["k__B;p__x", "k__B;p__y", "k__B;p__z"])


def test_labels_are_aligned_to_the_table_and_coded():
    tags = pd.DataFrame({"Tag": ["sick", "well", "sick", None]}, index=["s3", "s1", "s2", "s4"])
    tag, coding, test, table = mimic_authors._prepare(_table(), tags)
    assert list(tag.index) == ["s1", "s2", "s3"] and list(table.index) == ["s1", "s2", "s3"]
    assert tag["Tag"].tolist() == [1, 0, 0] and coding == {"0": "sick", "1": "well"} and test == "man"


def test_numeric_sample_ids_match_as_text():
    table = _table()
    table.index = [1, 2, 3, 4]
    tag, _, test, _ = mimic_authors._prepare(table, pd.DataFrame({"Tag": [0.5, 1.5, 2.25, 9.75]},
                                                                 index=[4, 3, 2, 1]))
    assert list(tag.index) == ["1", "2", "3", "4"] and test == "corr"


@pytest.mark.parametrize("tags", [pd.DataFrame({"Tag": [0, 1, 2, 1]}, index=["s1", "s2", "s3", "s4"]),
                                  pd.DataFrame({"a": [0, 1, 0, 1], "b": 1}, index=["s1", "s2", "s3", "s4"])])
def test_unusable_labels_are_refused(tags):
    with pytest.raises(UserFacingError):
        mimic_authors._prepare(_table(), tags)


def test_a_table_with_gaps_is_refused():
    table = _table()
    table.iloc[0, 0] = np.nan
    with pytest.raises(UserFacingError):
        mimic_authors._prepare(table, pd.DataFrame({"Tag": [0, 1, 0, 1]}, index=table.index))


# --- the website never touches the bundle ------------------------------------------------------

def test_the_website_never_uses_the_bundle_or_its_folder():
    web = Path(microplatform.web.__file__).parent
    for path in web.rglob("*"):
        if path.suffix in {".py", ".html", ".js", ".css"}:
            text = path.read_text(encoding="utf-8")
            assert "mimic_authors" not in text and not re.search(r"build[/\\]", text), path


# --- end to end, on the authors' example ----------------------------------------------------------

@pytest.mark.slow
def test_the_whole_bundle_on_the_authors_example(tmp_path):
    import MIPMLP

    processed = MIPMLP.preprocess(pd.read_csv(EXAMPLE / "for_process.csv"), taxnomy_group="sub PCA")
    processed.to_csv(tmp_path / "processed.csv")
    record = mimic_authors.run(tmp_path / "processed.csv", EXAMPLE / "tag.csv", tmp_path / "run", seeds=(42, 0))
    out = tmp_path / "run"
    assert sorted(p.name for p in (out / "plots").iterdir()) == PLOTS
    for name in mimic_authors.TABLES:
        assert (out / name).exists()
    assert len(pd.read_csv(out / "df_corrs.csv", index_col=0)) == 114  # as in the reproduction test
    assert record["differs_on_repeat_of_main_seed"] == []  # the same seed gives the same files
    assert "df_corrs.csv" not in " ".join(record["differs_between_seeds"])  # tables never depend on it
    assert record["adjustments"] == mimic_authors.ADJUSTMENTS and record["version"] == "1.0.1"
    assert not list(Path.cwd().glob("*.pkl")) and not (Path.cwd() / "plots").exists()  # nothing stray
