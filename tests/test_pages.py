"""The site's content pages: Example, Methods, Docs & API, About, and the navigation."""

from pathlib import Path

import pytest

import microplatform.web
from microplatform import __version__
from microplatform.references import TOOLS
from microplatform.web import create_app

PAGES = {
    "/": "New analysis",
    "/example": "Example",
    "/methods": "Methods",
    "/docs": "Docs &amp; API",
    "/about": "About",
}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    instance = tmp_path_factory.mktemp("instance")
    return create_app({"TESTING": True, "RUNS_DIR": instance / "runs",
                       "CACHE_DIR": instance / "cache"}).test_client()


@pytest.mark.parametrize(("path", "label"), PAGES.items())
def test_every_page_loads_and_is_marked_in_the_navigation(client, path, label):
    response = client.get(path)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for other in PAGES.values():
        assert f">{other}</a>" in page  # the full navigation is on every page
    assert f'aria-current="page">{label}</a>' in page


@pytest.mark.parametrize("path", PAGES)
def test_lab_identity_on_every_page(client, path):
    page = client.get(path).get_data(as_text=True)
    assert "Prof. Yoram Louzoun Lab" in page and "Bar-Ilan University" in page
    assert "img/yolo_lab.jpg" in page


def test_lab_logo_is_served(client):
    response = client.get("/static/img/yolo_lab.jpg")
    assert response.status_code == 200 and response.mimetype == "image/jpeg"
    response.close()


def test_question_cards_have_icons(client):
    page = client.get("/").get_data(as_text=True)
    assert page.count('class="icon-badge"') == 5


def test_stylesheet_never_resets_transforms_globally():
    """Regression: `* { transform: none }` scrambled plotly's titles and labels."""
    css = (Path(microplatform.web.__file__).parent / "static" / "style.css").read_text(encoding="utf-8")
    assert "transform: none !important" not in css


def test_example_page_shows_the_real_data_check(client):
    page = client.get("/example").get_data(as_text=True)
    assert "40 samples and 263 bacterial taxa" in page
    assert "a498" in page  # the depth outlier, flagged as on any upload
    assert "Analyse the example" in page


@pytest.mark.parametrize("name", ["example_counts.csv", "example_tag.csv"])
def test_example_files_download(client, name):
    response = client.get(f"/downloads/{name}")
    assert response.status_code == 200 and "attachment" in response.headers["Content-Disposition"]


def test_methods_page_lists_every_tool_with_its_paper(client):
    page = client.get("/methods").get_data(as_text=True)
    for tool in TOOLS:
        assert f">{tool.name}</h3>" in page and tool.paper.url in page
    assert "log10(count + 0.1)" in page and "sub PCA" in page
    assert "taxonomy level and z scoring" in page  # the allowed variations, from the contract


def test_docs_page_has_the_generated_api_reference(client):
    page = client.get("/docs").get_data(as_text=True)
    assert "mp.analyze(" in page and "Run a whole analysis from files on disk" in page
    assert f"version {__version__}" in page


def test_about_page_cites_every_tool(client):
    page = client.get("/about").get_data(as_text=True)
    for tool in TOOLS:
        assert tool.paper.doi in page
