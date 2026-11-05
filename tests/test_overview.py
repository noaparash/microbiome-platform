"""The data overview: composition, diversity and sparsity figures, made with every analysis."""

import io
import math
import subprocess
import sys
import zipfile

import numpy as np
import pandas as pd
import pytest
from scipy.spatial.distance import pdist, squareform

from microplatform import workflows
from microplatform.core.preprocessing import CANONICAL
from microplatform.core.profiler import count_matrix, profile_labels, read_table
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.reports import figures
from microplatform.reports.composition import MEAN, OTHER_GREY, PALETTES, TOP_PHYLA
from microplatform.reports.figures import FORMATS, OTHER, export, to_plotly
from microplatform.reports.overview import (
    ALL_SAMPLES,
    DESCRIPTIVE,
    EXPLORATORY,
    FIGURE_NAMES,
    NO_LABEL,
    RICHNESS,
    SHANNON,
    VIOLIN,
    alpha_diversity,
    bray_curtis_pcoa,
    overview_figures,
)

LINEAGE = "k__Bacteria;p__{};c__;o__;f__;g__;s__"


@pytest.fixture(scope="module")
def counts():
    return count_matrix(read_table(EXAMPLE_COUNTS))


@pytest.fixture(scope="module")
def labels(counts):
    return profile_labels(read_table(EXAMPLE_TAGS, index_col=0), list(counts.index))


@pytest.fixture(scope="module")
def grouped(counts, labels):
    return {f.name: f for f in overview_figures(counts, CANONICAL, labels.values, labels.kind)}


@pytest.fixture(scope="module")
def plain(counts):
    return {f.name: f for f in overview_figures(counts, CANONICAL)}


def _table(columns: dict[str, list[float]], samples=None) -> pd.DataFrame:
    """A small counts table: {phylum: counts per sample}."""
    n = len(next(iter(columns.values())))
    table = pd.DataFrame(columns, index=samples or [f"s{i}" for i in range(n)], dtype=float)
    table.columns = [LINEAGE.format(name) for name in table.columns]
    return table


# --- the numbers ------------------------------------------------------------------------

def test_composition_is_percent_of_each_samples_phylum_abundance(grouped, counts):
    data = grouped["composition_bars"].data
    assert np.allclose(data.groupby("sample")["percent"].sum(), 100, atol=1e-3)
    # Firmicutes in one sample, by hand from the raw counts (not from the log-transformed table).
    sample = counts.loc["a101"]
    phylum = sample[[c for c in counts.columns if ";p__" in c and c.split(";")[1] != "p__"]].sum()
    firmicutes = sample[[c for c in counts.columns if ";p__Firmicutes;" in c]].sum() / phylum * 100
    row = data[(data["sample"] == "a101") & (data["phylum"] == "Firmicutes")]
    assert row["percent"].iloc[0] == pytest.approx(firmicutes, abs=1e-3)


def test_composition_does_not_depend_on_the_preprocessing(counts):
    other = CANONICAL.with_changes(z_scoring="col")
    a = overview_figures(counts, CANONICAL)[0].data
    b = overview_figures(counts, other)[0].data
    pd.testing.assert_frame_equal(a, b)


def test_shannon_and_richness():
    table = _table({"A": [10, 10, 0], "B": [10, 0, 0], "C": [10, 0, 5], "D": [10, 0, 0]})
    alpha = alpha_diversity(table)
    assert alpha.loc["s0", SHANNON] == pytest.approx(math.log(4))  # four equal taxa
    assert alpha.loc["s1", SHANNON] == pytest.approx(0)  # one taxon: no diversity
    assert alpha[RICHNESS].tolist() == [4, 1, 1]


def test_pcoa_reproduces_the_bray_curtis_distances_when_they_fit_on_a_map():
    # Three samples whose distances (1, 0.6, 0.6) obey the triangle inequality: they fit on a plane exactly.
    table = _table({"A": [10, 0, 4], "B": [0, 10, 4], "C": [0, 0, 2]})
    coords, explained = bray_curtis_pcoa(table)
    relative = table.div(table.sum(axis=1), axis=0)
    expected = squareform(pdist(relative, "braycurtis"))
    assert np.allclose(squareform(pdist(coords)), expected, atol=1e-9)
    assert np.allclose(coords.mean(), 0) and np.all(np.diff(explained) <= 0) and explained.sum() <= 1 + 1e-9


def test_pcoa_is_the_same_every_time(counts):
    first, _ = bray_curtis_pcoa(counts)
    second, _ = bray_curtis_pcoa(counts.iloc[:, ::-1])  # column order must not flip the axes
    pd.testing.assert_frame_equal(first, second, atol=1e-9)


# --- the figures ---------------------------------------------------------------------------

def test_every_figure_is_made_and_labelled_honestly(grouped, plain):
    """With groups, the two diversity figures carry tests and say they are exploratory; the rest
    (and every figure without groups) say they are descriptive."""
    assert tuple(grouped) == FIGURE_NAMES
    tested = {"alpha_diversity", "beta_pcoa"}
    for fig in grouped.values():
        assert fig.section == "overview"
        assert fig.caption.endswith(EXPLORATORY if fig.name in tested else DESCRIPTIVE), fig.name
        assert (fig.stats is not None) == (fig.name in tested), fig.name
    for fig in plain.values():
        assert fig.caption.endswith(DESCRIPTIVE) and fig.stats is None, fig.name


def test_composition_bars_are_the_samples_and_their_mean(grouped, counts):
    fig = grouped["composition_bars"]
    data = fig.data
    assert list(data.columns) == ["panel", "sample", "phylum", "percent"] and fig.kind == "composition"
    assert set(data.loc[data["sample"] == MEAN, "panel"]) == {"Average"}
    wide = data[data["panel"] == "Samples"].pivot(index="sample", columns="phylum", values="percent")
    mean = data[data["sample"] == MEAN].set_index("phylum")["percent"]
    assert np.allclose(wide.mean().loc[mean.index], mean, atol=1e-3)
    assert len(wide) == len(counts)  # every sample, not grouped by label
    # Sorted by Firmicutes, most first; "Other" (if any) drawn last.
    firmicutes = data[(data["panel"] == "Samples") & (data["phylum"] == "Firmicutes")]["percent"]
    assert firmicutes.is_monotonic_decreasing
    assert list(dict(fig.colors))[-1] == OTHER


def test_a_phylum_has_the_same_colour_in_the_bars_and_the_pies(grouped):
    bars, pie = dict(grouped["composition_bars"].colors), dict(grouped["composition_pie"].colors)
    assert bars == pie
    assert bars[OTHER] == OTHER_GREY and bars["Firmicutes"] == PALETTES["lab"][0]  # the lab's look by default


def test_a_group_has_the_same_colour_in_the_diversity_boxes_and_the_map(grouped):
    assert dict(grouped["alpha_diversity"].colors) == dict(grouped["beta_pcoa"].colors)
    assert set(grouped["beta_pcoa"].data["group"]) == {"Tag 0", "Tag 1"}


def test_pies_one_per_group_each_adding_up_to_100(grouped, plain):
    data = grouped["composition_pie"].data
    assert np.allclose(data.groupby("group")["percent"].sum(), 100, atol=1e-3)
    assert "group" not in plain["composition_pie"].data  # no labels: one pie of all samples


def test_without_labels_nothing_is_grouped(plain):
    assert "group" not in plain["composition_pie"].data
    assert set(plain["alpha_diversity"].data["group"]) == {ALL_SAMPLES}
    assert plain["beta_pcoa"].color_by is None


def test_continuous_labels_are_not_groups(counts):
    values = pd.Series(np.linspace(0, 1, len(counts)), index=counts.index, name="Tag")
    figs = {f.name: f for f in overview_figures(counts, CANONICAL, values, "continuous", split_violin=True)}
    assert "group" not in figs["composition_pie"].data and VIOLIN not in figs


def test_samples_missing_from_the_labels_are_shown_as_no_label(counts, labels):
    partial = labels.values.iloc[:30]
    figs = {f.name: f for f in overview_figures(counts, CANONICAL, partial, "binary")}
    groups = list(dict.fromkeys(figs["alpha_diversity"].data["group"]))
    assert groups[-1] == NO_LABEL and (figs["alpha_diversity"].data["group"] == NO_LABEL).sum() == 2 * 10


def test_edge_cases_zero_reads_few_samples_and_identical_samples():
    empty = _table({"A": [5, 0, 3], "B": [5, 0, 1]})  # s1 has no reads
    figs = {f.name: f for f in overview_figures(empty, CANONICAL)}
    assert "s1" not in set(figs["composition_bars"].data["sample"])
    assert "1 sample without reads is left out." in figs["composition_bars"].caption
    assert "beta_pcoa" not in figs  # 2 samples with reads: too few for a map
    assert set(figs["taxa_per_sample"].data["sample"]) == {"s0", "s1", "s2"}  # sparsity shows every sample

    same = _table({"A": [5, 5, 5], "B": [5, 5, 5]})
    assert "beta_pcoa" not in {f.name for f in overview_figures(same, CANONICAL)}  # nothing to separate


def test_many_phyla_are_summed_as_other():
    table = _table({f"Phylum{i:02d}": [i + 1, 30 - i] for i in range(30)})
    bars = overview_figures(table, CANONICAL)[0]
    assert bars.data["phylum"].nunique() == TOP_PHYLA + 1 and OTHER in set(bars.data["phylum"])


def test_options_dataset_name_palette_and_split_violin(counts, labels):
    figs = {f.name: f for f in overview_figures(counts, CANONICAL, labels.values, labels.kind, dataset="gut study",
                                                palette="colorblind", split_violin=True)}
    assert figs["composition_bars"].suptitle == "gut study"
    assert set(dict(figs["composition_bars"].colors).values()) <= {*PALETTES["colorblind"], OTHER_GREY}
    names = list(figs)
    assert names.index(VIOLIN) == names.index("composition_pie") + 1
    violin = figs[VIOLIN]
    assert list(dict.fromkeys(violin.data["group"])) == ["Tag 0", "Tag 1"]  # group A is the left half
    assert OTHER not in set(violin.data["phylum"]) and "Tag 0 vs Tag 1" in violin.title
    assert dict(violin.colors) == dict(figs["alpha_diversity"].colors)  # a group keeps its colour


def test_a_log_transformed_table_gets_no_composition(counts):
    logged = np.log10(counts + 0.1)  # negative values: not abundances
    names = {f.name for f in overview_figures(logged, CANONICAL)}
    assert "composition_bars" not in names and "composition_pie" not in names and "alpha_diversity" in names


def test_sparsity_figures(grouped, counts):
    rows = grouped["taxa_per_sample"].data
    assert rows.set_index("sample")["taxa_detected"].equals((counts > 0).sum(axis=1).rename("taxa_detected")
                                                            .rename_axis("sample"))
    assert grouped["taxa_per_sample"].marker[1].startswith("median")
    assert grouped["taxa_prevalence"].marker[0] == CANONICAL.rare_bacteria_threshold * 100


# --- rendering ---------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def exported(grouped, tmp_path_factory):
    out = tmp_path_factory.mktemp("overview")
    return out, {e.name: e for e in export(list(grouped.values()), out)}


def test_every_format_is_written_in_print_resolution(exported):
    out, figs = exported
    for fig in figs.values():
        for fmt in (*FORMATS, "json"):
            assert (out / fig.files[fmt]).stat().st_size > 0
    # The width from the PNG header (Pillow is not used: on Windows it can stop PyTorch loading later).
    width = int.from_bytes((out / "composition_bars.png").read_bytes()[16:20], "big")
    assert width >= 4500  # 16 inches at 300 dpi (as the lab's figure scripts)
    assert "<text" in (out / "alpha_diversity.svg").read_text(encoding="utf-8")  # editable text


def test_data_csv_is_exactly_what_is_plotted(grouped, exported):
    out, _ = exported
    for fig in grouped.values():
        pd.testing.assert_frame_equal(pd.read_csv(out / f"{fig.name}.csv"), fig.data, check_dtype=False)


def test_wide_figures_take_the_whole_row(exported):
    _, figs = exported
    assert figs["composition_bars"].wide and figs["composition_pie"].wide and figs["alpha_diversity"].wide
    assert not figs["beta_pcoa"].wide


def test_interactive_versions(grouped):
    bars = to_plotly(grouped["composition_bars"])
    shown = grouped["composition_bars"].data["phylum"].nunique()
    assert bars.layout.barmode == "stack" and len(bars.data) == 2 * shown  # samples panel + mean panel
    assert {t.marker.color for t in bars.data} == {dict(grouped["composition_bars"].colors)[t.name] for t in bars.data}
    assert bars.layout.legend.orientation == "h" and bars.layout.meta["panels"] == "side by side"
    pies = to_plotly(grouped["composition_pie"])
    assert [t.type for t in pies.data] == ["pie", "pie"]
    boxes = to_plotly(grouped["alpha_diversity"])
    assert {t.type for t in boxes.data} == {"box"} and boxes.layout.yaxis2.title.text == RICHNESS
    assert to_plotly(grouped["beta_pcoa"]).layout.xaxis.title.text.startswith("PCo1 (")


def test_pie_percentages_are_readable_on_every_slice():
    for colour in (*PALETTES["lab"], *PALETTES["colorblind"], OTHER_GREY):
        ink = figures._ink(colour)
        assert _contrast(ink, colour) >= 4.5, colour


def test_drawing_the_overview_leaves_pytorch_loadable():
    """The tools load PyTorch after the overview is drawn (when preprocessing came from the cache).

    On Windows, matplotlib's own boxplot made that fail (WinError 1114); a fresh process shows it.
    """
    script = "\n".join([
        "import tempfile, pathlib",
        "from microplatform.core.preprocessing import CANONICAL",
        "from microplatform.core.profiler import count_matrix, profile_labels, read_table",
        "from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS",
        "from microplatform.reports import figures, overview",
        "c = count_matrix(read_table(EXAMPLE_COUNTS))",
        "l = profile_labels(read_table(EXAMPLE_TAGS, index_col=0), list(c.index))",
        "figs = overview.overview_figures(c, CANONICAL, l.values, l.kind, split_violin=True)",
        "assert 'composition_violin' in [f.name for f in figs]",
        "figures.export(figs, pathlib.Path(tempfile.mkdtemp()))",
        "import torch",
        "print('loaded')",
    ])
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0 and "loaded" in done.stdout, done.stderr[-2000:]


def _contrast(a: str, b: str) -> float:
    def luminance(hex_colour):
        channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --- through the workflow, the website and the ZIP ------------------------------------------------

@pytest.fixture(scope="module")
def finished_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("runs")
    run = workflows.start_example_run(root)
    workflows.run_goal(run, "preprocess", cache_dir=root / "cache")
    return run


def test_every_analysis_gets_the_overview_and_the_zip_has_it(finished_run):
    view = workflows.describe(finished_run)
    assert tuple(f.name for f in view.overview_figures) == FIGURE_NAMES
    with zipfile.ZipFile(io.BytesIO(workflows.build_bundle(finished_run))) as zf:
        names = set(zf.namelist())
        for name in FIGURE_NAMES:
            assert {f"figures/{name}.{fmt}" for fmt in FORMATS} <= names
        readme = zf.read("README.txt").decode()
        assert "mostly descriptive" in readme and "Exploratory" in readme


def test_the_results_page_shows_the_overview_as_descriptive(tmp_path):
    from microplatform.web import create_app

    app = create_app({"TESTING": True, "JOBS": "inline", "RUNS_DIR": tmp_path / "runs", "CACHE_DIR": tmp_path / "c"})
    client = app.test_client()
    url = client.post("/example").headers["Location"]
    page = client.post(f"{url}/run", data={"goal": "preprocess"}, follow_redirects=True).get_data(as_text=True)
    section = page.split('<section class="data-overview section-break" aria-labelledby="overview-heading">', 1)[1]
    section = section.split("</section>", 1)[0]
    assert '<h3 id="overview-heading">Data overview</h3>' in section
    assert "Mostly descriptive." in section and "<strong>exploratory</strong>" in section
    assert 'class="figure figure-wide"' in section and "Composition of each sample (phylum)" in section
    assert page.index("overview-heading") < page.index("Reproducibility record")
