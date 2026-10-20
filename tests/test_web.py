"""The website is a thin layer: these tests check that pages show what the package returns."""

import io
import re
from pathlib import Path

import pandas as pd
import pytest

import microplatform.web
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.web import create_app


def test_web_layer_holds_no_business_logic():
    """Package-first rule: the website must not touch data or tools directly."""
    for source in Path(microplatform.web.__file__).parent.glob("*.py"):
        code = source.read_text(encoding="utf-8")
        for forbidden in ("import pandas", "import MIPMLP", "microplatform.core.preprocessing",
                          "microplatform.core.profiler"):
            assert forbidden not in code, f"{source.name} uses {forbidden}"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    instance = tmp_path_factory.mktemp("instance")
    app = create_app({
        "TESTING": True,
        "RUNS_DIR": instance / "runs",
        "CACHE_DIR": instance / "cache",
    })
    return app.test_client()


def upload(client, *files, follow=False):
    data = {"files": [(io.BytesIO(content), name) for name, content in files]}
    return client.post("/upload", data=data, content_type="multipart/form-data",
                       follow_redirects=follow)


EXAMPLE = [(EXAMPLE_COUNTS.name, EXAMPLE_COUNTS.read_bytes()),
           (EXAMPLE_TAGS.name, EXAMPLE_TAGS.read_bytes())]


@pytest.fixture(scope="module")
def processed_run(client):
    """Upload the example, preprocess it once, and return its analysis URL."""
    url = upload(client, *EXAMPLE).headers["Location"]
    client.post(f"{url}/run", data={"goal": "preprocess"})
    return url


# --- home page ----------------------------------------------------------------

def test_home_page(client):
    page = client.get("/").get_data(as_text=True)
    assert "Drop your files here" in page
    assert "MIPMLP" in page and "miMic" in page
    assert "counts_template.csv" in page


def test_security_headers(client):
    headers = client.get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("name", ["counts_template.csv", "labels_template.csv"])
def test_templates_download(client, name):
    response = client.get(f"/templates/{name}")
    assert response.status_code == 200 and response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]


def test_unknown_template_is_404(client):
    assert client.get("/templates/..%2Fviews.py").status_code == 404


# --- upload and choice --------------------------------------------------------------

def test_upload_shows_profile_and_choices(client):
    response = upload(client, *EXAMPLE)
    assert response.status_code == 302
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "40 samples and 263 bacterial taxa" in page
    assert "binary" in page
    assert "Just preprocess (MIPMLP only)" in page
    assert re.search(r'value="preprocess"\s+checked', page)  # pre-selected: one click


def test_example_button(client):
    response = client.post("/example")
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Example dataset" in page and "40 samples" in page


def test_upload_error_shows_fix_and_opens_format_help(client):
    page = upload(client, ("data.xlsx", b"PK"), follow=True).get_data(as_text=True)
    assert "Excel file" in page
    assert "How to fix:" in page and "CSV UTF-8" in page
    assert '<details class="format" open>' in page


def test_bad_counts_show_fix_and_block_running(client):
    bad = ("bad.csv", b"ID,asv0,asv1\na,1,x\nb,3,4\ntaxonomy,k__Bacteria,k__Bacteria\n")
    page = upload(client, bad, follow=True).get_data(as_text=True)
    assert "not numbers" in page and "How to fix:" in page
    assert "This file needs fixing first" in page
    assert "Just preprocess" not in page


def test_unavailable_goal_is_explained(client):
    url = upload(client, *EXAMPLE).headers["Location"]
    page = client.post(f"{url}/run", data={"goal": "differ"}, follow_redirects=True).get_data(as_text=True)
    assert "cannot run on this data yet" in page


# --- results ---------------------------------------------------------------------

def test_results_are_shown(client, processed_run):
    page = client.get(processed_run).get_data(as_text=True)
    assert "Preprocessed with MIPMLP" in page
    assert "Grouped 263 taxa into" in page
    assert "Reproducibility record" in page and "sub PCA" in page


def test_download_is_the_processed_table(client, processed_run):
    response = client.get(f"{processed_run}/download")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "example_counts_mipmlp.csv" in response.headers["Content-Disposition"]
    table = pd.read_csv(io.BytesIO(response.data), index_col=0)
    assert table.shape[0] == 40 and not table.isna().any().any()


def test_download_before_preprocessing_is_404(client):
    url = upload(client, EXAMPLE[0]).headers["Location"]
    assert client.get(f"{url}/download").status_code == 404


@pytest.mark.parametrize("run_id", ["0" * 32, "not-a-run", "..%2F..%2Fetc"])
def test_unknown_or_malformed_run_is_404(client, run_id):
    assert client.get(f"/runs/{run_id}").status_code == 404
