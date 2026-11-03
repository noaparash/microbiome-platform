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
from microplatform.reports.figures import FORMATS, OTHER, OTHER_COLOR, TAXON_PALETTE, export, to_plotly
from microplatform.reports.overview import (
    ALL_SAMPLES,
    AVERAGES,
    DESCRIPTIVE,
    FIGURE_NAMES,
    NO_LABEL,
    RICHNESS,
    SHANNON,
    TOP_TAXA,
    UNASSIGNED,
    alpha_diversity,
    bray_curtis_pcoa,
    overview_figures,
    relative_abundance,
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

def test_relative_abundance_is_percent_of_each_samples_reads(counts):
    percent = relative_abundance(counts)
    assert np.allclose(percent.sum(axis=1), 100)
    assert list(percent.columns)[-1] == OTHER and len(percent.columns) == TOP_TAXA + 1
    # Firmicutes in one sample, by hand from the raw counts (not from the log-transformed table).
    sample = counts.iloc[0]
    firmicutes = sample[[c for c in counts.columns if ";p__Firmicutes;" in c]].sum() / sample.sum() * 100
    assert percent.iloc[0]["Firmicutes"] == pytest.approx(firmicutes)
    assert list(percent.columns[:2]) == ["Firmicutes", "Bacteroidetes"]  # most abundant first


def test_composition_does_not_depend_on_the_preprocessing(counts):
    other = CANONICAL.with_changes(z_scoring="col")
    a = overview_figures(counts, CANONICAL)[0].data
    b = overview_figures(counts, other)[0].data
    pd.testing.assert_frame_equal(a, b)


def test_few_taxa_need_no_other_and_unnamed_ones_are_unassigned():
    table = _table({"Firmicutes": [5, 0], "": [5, 10]})
    percent = relative_abundance(table)
    assert list(percent.columns) == [UNASSIGNED, "Firmicutes"]  # no "Other" when nothing is left over
    assert percent.loc["s0"].tolist() == [50, 50]


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

def test_every_figure_is_made_and_labelled_descriptive(grouped):
    assert tuple(grouped) == FIGURE_NAMES
    for fig in grouped.values():
        assert fig.section == "overview"
        assert fig.caption.endswith(DESCRIPTIVE), fig.name


def test_composition_bars_group_samples_and_add_the_group_averages(grouped, labels):
    data = grouped["composition_bars"].data
    assert list(data.columns) == ["sample", "group", "phylum", "percent"]
    assert set(data["group"]) == {"Tag 0", "Tag 1", AVERAGES}
    assert np.allclose(data.groupby("sample")["percent"].sum(), 100, atol=1e-3)
    averages = data[data["group"] == AVERAGES].pivot(index="sample", columns="phylum", values="percent")
    samples = data[data["group"] == "Tag 1"].pivot(index="sample", columns="phylum", values="percent")
    assert np.allclose(averages.loc["Tag 1 average"], samples.mean(), atol=1e-3)
    assert data[data["group"] == "Tag 1"]["sample"].nunique() == (labels.values == 1).sum()


def test_a_taxon_has_the_same_colour_in_the_bars_and_the_pies(grouped):
    bars, pie = dict(grouped["composition_bars"].colors), dict(grouped["composition_pie"].colors)
    assert bars == pie
    assert bars[OTHER] == OTHER_COLOR and bars["Firmicutes"] == TAXON_PALETTE[0]
    assert set(bars.values()) <= {*TAXON_PALETTE, OTHER_COLOR}  # Okabe-Ito: colour-blind safe


def test_a_group_has_the_same_colour_in_the_diversity_boxes_and_the_map(grouped):
    assert dict(grouped["alpha_diversity"].colors) == dict(grouped["beta_pcoa"].colors)
    assert set(grouped["beta_pcoa"].data["group"]) == {"Tag 0", "Tag 1"}


def test_pies_one_per_group_each_adding_up_to_100(grouped, plain):
    data = grouped["composition_pie"].data
    assert np.allclose(data.groupby("group")["percent"].sum(), 100, atol=1e-3)
    assert "group" not in plain["composition_pie"].data  # no labels: one pie of all samples


def test_without_labels_nothing_is_grouped(plain):
    assert "group" not in plain["composition_bars"].data and plain["composition_bars"].group_by is None
    assert set(plain["alpha_diversity"].data["group"]) == {ALL_SAMPLES}
    assert plain["beta_pcoa"].color_by is None


def test_continuous_labels_are_not_groups(counts):
    values = pd.Series(np.linspace(0, 1, len(counts)), index=counts.index, name="Tag")
    figs = {f.name: f for f in overview_figures(counts, CANONICAL, values, "continuous")}
    assert figs["composition_bars"].group_by is None


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


def test_many_taxa_are_summed_as_other():
    table = _table({f"Phylum{i:02d}": [i + 1, 30 - i] for i in range(30)})
    bars = overview_figures(table, CANONICAL)[0]
    assert bars.data["phylum"].nunique() == TOP_TAXA + 1 and OTHER in set(bars.data["phylum"])


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
    assert width >= 2000  # 10 inches at 200 dpi
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
    assert bars.layout.barmode == "stack" and len(bars.data) == TOP_TAXA + 1
    assert {t.marker.color for t in bars.data} == set(dict(grouped["composition_bars"].colors).values())
    pies = to_plotly(grouped["composition_pie"])
    assert [t.type for t in pies.data] == ["pie", "pie"]
    boxes = to_plotly(grouped["alpha_diversity"])
    assert {t.type for t in boxes.data} == {"box"} and boxes.layout.yaxis2.title.text == RICHNESS
    assert to_plotly(grouped["beta_pcoa"]).layout.xaxis.title.text.startswith("PCo1 (")


def test_pie_percentages_are_readable_on_every_slice():
    for colour in (*TAXON_PALETTE, OTHER_COLOR):
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
        "figures.export(overview.overview_figures(c, CANONICAL, l.values, l.kind), pathlib.Path(tempfile.mkdtemp()))",
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
        assert "not statistical tests" in zf.read("README.txt").decode()


def test_the_results_page_shows_the_overview_as_descriptive(tmp_path):
    from microplatform.web import create_app

    app = create_app({"TESTING": True, "JOBS": "inline", "RUNS_DIR": tmp_path / "runs", "CACHE_DIR": tmp_path / "c"})
    client = app.test_client()
    url = client.post("/example").headers["Location"]
    page = client.post(f"{url}/run", data={"goal": "preprocess"}, follow_redirects=True).get_data(as_text=True)
    section = page.split('<section class="data-overview section-break" aria-labelledby="overview-heading">', 1)[1]
    section = section.split("</section>", 1)[0]
    assert '<h3 id="overview-heading">Data overview</h3>' in section
    assert "Descriptive, not statistical tests." in section
    assert 'class="figure figure-wide"' in section and "Composition of each sample (phylum)" in section
    assert page.index("overview-heading") < page.index("Reproducibility record")
