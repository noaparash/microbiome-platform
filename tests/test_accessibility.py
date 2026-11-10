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
    assert 'role="region" aria-label="Most significant taxa (miMic)" tabindex="0"' in page
    assert '<caption class="visually-hidden">Most significant taxa (miMic)</caption>' in page
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


# --- the whole site: keyboard, contrast, phones ------------------------------------------------

def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def _contrast(a: str, b: str) -> float:
    def luminance(hex_colour):
        channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# Every text colour on every background it is used on (WCAG AA for normal text: 4.5:1).
# The bright --accent / --accent-2 are fills only (buttons, dots, glows): text in the accent
# colour, links and focus rings use --accent-ink.
BACKGROUNDS = ("bg", "bg-2", "surface", "surface-2", "accent-soft")
TEXT_ON = ([(fg, bg) for fg in ("text", "muted", "accent-ink") for bg in BACKGROUNDS]
           + [("text", "warning-soft"), ("on-accent", "accent"), ("on-accent", "accent-2"),
              ("error", "error-soft"), ("warning", "warning-soft")])


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_text_colours_meet_wcag_aa_in_both_themes(theme):
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    tokens = _tokens(css.split(":root {", 1)[1].split("}", 1)[0])
    if theme == "dark":
        tokens |= _tokens(css.split(':root[data-theme="dark"] {', 1)[1].split("}", 1)[0])
    failing = {f"{fg} on {bg}": round(_contrast(tokens[fg], tokens[bg]), 2) for fg, bg in TEXT_ON
               if _contrast(tokens[fg], tokens[bg]) < 4.5}
    assert not failing, failing


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_focus_rings_stand_out_and_the_bright_accent_is_never_text(theme):
    """WCAG 1.4.11: a focus ring needs 3:1 against what is around it. The bright accent is too
    light for text (2.4–2.9:1 in the light theme), so no rule may use it as a text colour."""
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    tokens = _tokens(css.split(":root {", 1)[1].split("}", 1)[0])
    if theme == "dark":
        tokens |= _tokens(css.split(':root[data-theme="dark"] {', 1)[1].split("}", 1)[0])
    assert all(_contrast(tokens["accent-ink"], tokens[bg]) >= 3 for bg in BACKGROUNDS)
    rings = re.findall(r"outline:\s*3px solid var\(--([\w-]+)\)", css)
    assert rings and set(rings) == {"accent-ink"}
    assert not re.search(r"(?<![-\w])color:\s*var\(--accent(-2)?\)", css)


def test_every_page_starts_with_a_skip_link(client, mimic_page):
    for url in ("/", "/example", "/methods", "/docs", "/about", mimic_page[0]):
        page = client.get(url).get_data(as_text=True)
        body = page.split("<body>", 1)[1]
        first_link = re.search(r"<a [^>]*>", body).group(0)
        assert 'class="skip-link"' in first_link and 'href="#content"' in first_link, url
        assert '<main class="wrap" id="content" tabindex="-1">' in page


def test_numbers_never_break_and_read_the_same_everywhere(client):
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    stats_dd = re.search(r"\.stats dd \{([^}]*)\}", css).group(1)
    assert "white-space: nowrap" in stats_dd  # a phone showed "22,483,56 / 3"
    count = client.application.jinja_env.filters["count"]
    assert count(55882) == "55,882" and count(22483563.0) == "22,483,563" and count(40) == "40"


def test_caveats_are_shown_apart_from_the_findings_and_never_folded(client):
    files = [(io.BytesIO(p.read_bytes()), p.name) for p in (EXAMPLE_COUNTS, EXAMPLE_TAGS)]
    url = client.post("/upload", data={"files": files}, content_type="multipart/form-data").headers["Location"]
    page = client.post(f"{url}/run", data={"goal": "predict"}, follow_redirects=True).get_data(as_text=True)
    notes = re.search(r'<section class="reading-notes" aria-labelledby="notes-heading">(.*?)</section>', page, re.S)
    assert notes and "How to read these results" in notes.group(1)
    assert "Only 8 test samples" in notes.group(1) and "one random split" in notes.group(1)
    findings = page.index('class="facts findings"')
    assert findings < notes.start() < page.index("<h3>Findings</h3>")  # right under the findings, before figures
    assert "<details" not in page[findings:notes.end()]  # never folded away


def test_a_status_badge_appears_only_when_a_tool_is_not_available(client):
    for url in ("/", "/methods"):
        page = client.get(url).get_data(as_text=True)
        assert "chip-available" not in page  # all five are available: a badge would say nothing


def test_a_plot_with_its_own_height_gets_a_box_of_that_height():
    """Plotly figures that set a height (one row per taxon or level: barh, grouped_barh) must not run past
    their box over the caption and downloads (seen on the miMic results page, 2026-11-10)."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert re.search(r"if \(layout\.height\) \{\s*el\.style\.aspectRatio = \"auto\";\s*"
                     r"el\.style\.height = `\$\{layout\.height\}px`;", js)
    import pandas as pd

    data = pd.DataFrame({"name": list("abc"), "v": [1, 2, 3], "g": list("xyx")})
    for kind in ("barh", "grouped_barh"):
        fig = figures.Figure(name="t", title="t", caption="c", data=data, kind=kind, x="v", y="name",
                             x_label="v", y_label="", color_by="g" if kind == "grouped_barh" else None)
        assert figures.to_plotly(fig).layout.height  # the kinds this guards do set a height


def test_method_details_are_under_the_caption_and_in_the_zip(mimic_page, client):
    """Captions say what a figure shows and how to read it; the fine print sits in a closed "Method details"
    box under it, and in the ZIP's figures/FIGURES.txt (the caption rewrite, 2026-11-10)."""
    import zipfile

    url, page = mimic_page
    assert page.count('<details class="figure-details"><summary>Method details</summary>') >= 3
    assert "Mann-Whitney U statistic, centred" in page  # the miMic score, explained
    with zipfile.ZipFile(io.BytesIO(client.get(f"{url}/bundle").data)) as zf:
        notes = zf.read("figures/FIGURES.txt").decode()
    assert "figures/1_result/mimic_significant_taxa.*" in notes and "Method details: Score = " in notes
    assert notes.index("1_result") < notes.index("3_descriptive_overview")  # reading order
