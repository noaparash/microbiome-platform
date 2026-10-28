"""Results pages: keyboard and screen-reader basics, phones and dark mode, and no data leaving the page."""

import io
import json
import re
from pathlib import Path

import pytest

from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.reports import figures
from microplatform.web import create_app

STATIC = Path(__file__).parents[1] / "src" / "microplatform" / "web" / "static"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    instance = tmp_path_factory.mktemp("instance")
    app = create_app({"TESTING": True, "JOBS": "inline",
                      "RUNS_DIR": instance / "runs", "CACHE_DIR": instance / "cache"})
    return app.test_client()


@pytest.fixture(scope="module")
def mimic_page(client):
    files = [(io.BytesIO(p.read_bytes()), p.name) for p in (EXAMPLE_COUNTS, EXAMPLE_TAGS)]
    url = client.post("/upload", data={"files": files}, content_type="multipart/form-data").headers["Location"]
    client.post(f"{url}/run", data={"goal": "differ"})
    return url, client.get(url).get_data(as_text=True)


def test_figure_titles_are_headings_and_images_are_described(mimic_page):
    _, page = mimic_page
    assert '<h4 class="figure-title" id="fig-mimic_significant_taxa">Bacteria that differ between the groups</h4>' in page
    assert 'aria-labelledby="fig-mimic_significant_taxa"' in page
    for alt in re.findall(r'<img src="[^"]+\.png" alt="([^"]*)"', page):
        assert len(alt) > 20  # title and caption, not empty


def test_download_links_say_which_figure_they_belong_to(mimic_page):
    _, page = mimic_page
    assert 'PNG<span class="visually-hidden"> of “Bacteria that differ between the groups”</span>' in page


def test_result_tables_are_named_scrollable_regions_with_aligned_headers(mimic_page):
    _, page = mimic_page
    assert 'role="region" aria-label="Most significant taxa" tabindex="0"' in page
    assert '<caption class="visually-hidden">Most significant taxa</caption>' in page
    assert '<th scope="col" class="text-col">Direction</th>' in page  # text: left-aligned header
    assert '<th scope="col">p-value</th>' in page  # number: right-aligned, plain-language name


def test_data_check_folds_away_once_results_are_shown_but_problems_stay(mimic_page):
    _, page = mimic_page
    folded = page.split('<details class="check-details">', 1)[1].split("</details>", 1)
    assert "Median reads" in folded[0]  # the full check is one click away
    assert "1 sample has over" in folded[1]  # the warning stays visible


def test_running_page_updates_quietly(client, tmp_path):
    from microplatform import jobs

    app = create_app({"TESTING": True, "JOBS": "external",
                      "RUNS_DIR": tmp_path / "runs", "CACHE_DIR": tmp_path / "cache"})
    queued = app.test_client()
    url = queued.post("/example").headers["Location"]
    queued.post(f"{url}/run", data={"goal": "preprocess"})
    page = queued.get(url).get_data(as_text=True)
    # Without JavaScript the page refreshes itself; with it, app.js polls and announces only the status.
    assert '<noscript><meta http-equiv="refresh" content="4"></noscript>' in page
    assert 'data-status="queued"' in page and '<span role="status">Waiting to start…</span>' in page
    assert "aria-live" not in page.split('id="results"', 1)[1].split(">", 1)[0]


def test_interactive_figures_never_offer_to_upload_data(tmp_path):
    import pandas as pd

    fig = figures.Figure(name="demo", title="Demo", caption="A demo.", kind="column",
                         data=pd.DataFrame({"x": ["a", "b"], "y": [1, 2]}), x="x", y="y",
                         x_label="x", y_label="y")
    figures.export([fig], tmp_path)
    html = (tmp_path / f"{fig.name}.html").read_text(encoding="utf-8")
    assert '"showSendToCloud": false' in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "showSendToCloud: false" in js and "displayModeBar: false" in js


def test_dark_mode_chart_colours_cover_the_python_palette():
    """app.js maps each light chart colour to a --plot-N token; the light tokens must equal the palette."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    js_colors = json.loads(re.search(r"const PLOT_COLORS = (\[.*?\]);", js).group(1))
    python = [figures.ACCENT, figures.CONTRAST, figures.MARKER, *figures.PALETTE[2:]]
    assert js_colors == python
    light = css.split("@media (prefers-color-scheme: dark)", 1)[0]
    for i, color in enumerate(python, start=1):
        assert f"--plot-{i}: {color};" in light
    assert css.count(f"--plot-{len(python)}:") == 3  # light, dark (system), dark (chosen)
