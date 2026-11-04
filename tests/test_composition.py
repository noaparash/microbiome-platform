"""Phylum composition in the lab's fig_1B style (reports/composition.py)."""

import numpy as np
import pandas as pd
import pytest

from microplatform.reports.composition import (
    KNOWN_PHYLA,
    OTHER_GREY,
    PALETTES,
    TOP_PHYLA,
    CompositionError,
    phylum_colors,
    phylum_percent,
    sort_samples,
    top_phyla,
)
from microplatform.reports.figures import OTHER


def _relative(columns: dict[str, list[float]]) -> pd.DataFrame:
    n = len(next(iter(columns.values())))
    return pd.DataFrame(columns, index=[f"s{i}" for i in range(n)], dtype=float)


# --- (a) tables with taxonomy strings -------------------------------------------------------------

def test_lineages_are_collapsed_to_phylum_and_renormalized():
    table = _relative({
        "k__Bacteria;p__Firmicutes;c__Bacilli;o__;f__;g__;s__": [30, 10],
        "k__Bacteria; p__Firmicutes ;c__Clostridia;o__;f__;g__;s__": [30, 10],  # spaces around ';' are cleaned
        "k__Bacteria;p__Bacteroidetes;c__;o__;f__;g__;s__": [20, 70],
        "k__Bacteria;p__;c__;o__;f__;g__;s__": [20, 10],  # no phylum: left out, then re-normalized
    })
    percent, removed = phylum_percent(table)
    assert list(percent.columns) == ["Firmicutes", "Bacteroidetes"]
    assert percent.loc["s0"].tolist() == pytest.approx([75, 25]) and percent.loc["s1"].tolist() == pytest.approx([22.222222, 77.777778])
    assert removed["unassigned_percent"] == pytest.approx(15)  # (20% + 10%) / 2


@pytest.mark.parametrize("dropped", ["Bacteria", "Archaea", "Unassigned", "Unclassified", "k__Bacteria", "unassigned"])
def test_columns_without_a_phylum_are_dropped(dropped):
    percent, _ = phylum_percent(_relative({"p__Firmicutes": [50, 20], dropped: [50, 80]}))
    assert list(percent.columns) == ["Firmicutes"] and percent["Firmicutes"].tolist() == [100, 100]


def test_phylum_level_tables_with_or_without_prefixes():
    a, _ = phylum_percent(_relative({"Bacteria;Firmicutes": [1, 3], "Bacteria;Bacteroidetes": [3, 1]}))
    b, _ = phylum_percent(_relative({"p__Firmicutes": [1, 3], "p__Bacteroidetes": [3, 1]}))
    pd.testing.assert_frame_equal(a, b)
    assert a["Firmicutes"].tolist() == [25, 75]


def test_a_16s_table_with_taxa_named_only_to_phylum_is_not_taken_for_metaphlan():
    table = _relative({"k__Bacteria;p__Firmicutes": [10, 10],  # an ASV classified only to phylum
                       "k__Bacteria;p__Firmicutes;c__Bacilli": [10, 0],
                       "k__Bacteria;p__Bacteroidetes;c__Bacteroidia": [20, 10]})
    percent, _ = phylum_percent(table)
    assert percent.loc["s0", "Firmicutes"] == pytest.approx(50)  # both Firmicutes columns are counted


# --- (b) MetaPhlAn tables with every rank ---------------------------------------------------------

@pytest.mark.parametrize("sep", ["|", ","])
def test_metaphlan_uses_only_the_phylum_rows(sep):
    j = sep.join
    table = _relative({
        "k__Bacteria": [100, 100],
        j(["k__Bacteria", "p__Firmicutes"]): [60, 30],
        j(["k__Bacteria", "p__Firmicutes", "c__Bacilli"]): [60, 30],  # not counted again
        j(["k__Bacteria", "p__Bacteroidetes"]): [40, 70],
        j(["k__Bacteria", "p__Bacteroidetes", "c__Bacteroidia"]): [40, 70],
    })
    percent, _ = phylum_percent(table)
    assert percent.loc["s0"].tolist() == [60, 40] and percent.loc["s1"].tolist() == [30, 70]


# --- guards ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [-1.0, np.inf, np.nan])
def test_values_must_be_finite_and_not_negative(bad):
    with pytest.raises(CompositionError):
        phylum_percent(_relative({"p__Firmicutes": [5, bad], "p__Bacteroidetes": [5, 5]}))


def test_samples_with_nothing_at_phylum_level_are_dropped():
    percent, removed = phylum_percent(_relative({"p__Firmicutes": [5, 0, 1], "Unassigned": [5, 9, 0]}))
    assert list(percent.index) == ["s0", "s2"] and removed["samples_dropped"] == 1
    with pytest.raises(CompositionError):
        phylum_percent(_relative({"Unassigned": [1, 2]}))


# --- top phyla, order and colours -----------------------------------------------------------------

def test_top_12_by_mean_and_other_last():
    table = _relative({f"p__P{i:02d}": [i + 1, i + 1] for i in range(20)})
    top = top_phyla(phylum_percent(table)[0])
    assert len(top.columns) == TOP_PHYLA + 1 and top.columns[-1] == OTHER
    assert list(top.columns[:3]) == ["P19", "P18", "P17"]
    assert np.allclose(top.sum(axis=1), 100)


def test_samples_are_sorted_by_firmicutes_else_the_top_phylum():
    top = pd.DataFrame({"Bacteroidetes": [60, 20, 40], "Firmicutes": [40, 80, 60]}, index=["a", "b", "c"])
    assert list(sort_samples(top).index) == ["b", "c", "a"]
    top = pd.DataFrame({"Bacteroidota": [60, 20, 40], "Bacillota": [40, 80, 60]}, index=["a", "b", "c"])
    assert list(sort_samples(top).index) == ["b", "c", "a"]  # the same phylum, under its new name
    top = pd.DataFrame({"Bacteroidetes": [60, 20, 40], "Other": [40, 80, 60]}, index=["a", "b", "c"])
    assert list(sort_samples(top).index) == ["a", "c", "b"]


@pytest.mark.parametrize("palette", sorted(PALETTES))
def test_a_phylum_keeps_its_colour_across_datasets(palette):
    one = phylum_colors(["Firmicutes", "Bacteroidetes", "Mystery", OTHER], palette)
    two = phylum_colors(["Bacteroidetes", "Proteobacteria", "Firmicutes"], palette)
    assert one["Firmicutes"] == two["Firmicutes"] and one["Bacteroidetes"] == two["Bacteroidetes"]
    assert one[OTHER] == OTHER_GREY and phylum_colors(["Bacillota"], palette)["Bacillota"] == one["Firmicutes"]


@pytest.mark.parametrize("palette", sorted(PALETTES))
def test_colours_are_distinct_within_a_figure_and_never_grey(palette):
    names = [n[0] for n in KNOWN_PHYLA][:6] + [f"Unknown{i}" for i in range(6)]  # 12 shown, as at most
    colors = phylum_colors(names + [OTHER], palette)
    shown = [colors[n] for n in names]
    assert len(set(shown)) == len(shown) and OTHER_GREY not in shown
    for color in shown:
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        assert max(r, g, b) - min(r, g, b) > 16, color  # no grey that reads as "Other"


def test_the_default_is_the_lab_look():
    assert phylum_colors(["Firmicutes"])["Firmicutes"] == "#1f77b4"  # tab20's first colour, as in fig_1B
    with pytest.raises(ValueError):
        phylum_colors(["Firmicutes"], "rainbow")
