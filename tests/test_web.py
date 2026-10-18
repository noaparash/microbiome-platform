import io

import pandas as pd
import pytest

from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.web import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    instance = tmp_path_factory.mktemp("instance")
    app = create_app({
        "TESTING": True,
        "RUNS_DIR": instance / "runs",
        "CACHE_DIR": instance / "cache",
    })
    return app.test_client()


def upload(client, *paths):
    files = [(io.BytesIO(p.read_bytes()), p.name) for p in paths]
    return client.post("/upload", data={"files": files}, content_type="multipart/form-data")


@pytest.fixture(scope="module")
def processed_run(client):
    """Upload the example, preprocess it once, and return its analysis URL."""
    response = upload(client, EXAMPLE_COUNTS, EXAMPLE_TAGS)
    url = response.headers["Location"]
    client.post(f"{url}/preprocess")
    return url


# --- home page ----------------------------------------------------------------

def test_home_page(client):
    page = client.get("/").get_data(as_text=True)
    assert "Drop your files here" in page
    assert "MIPMLP" in page and "miMic" in page


def test_security_headers(client):
    headers = client.get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


# --- upload -------------------------------------------------------------------------

def test_upload_shows_profile(client):
    response = upload(client, EXAMPLE_COUNTS, EXAMPLE_TAGS)
    assert response.status_code == 302
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "40 samples and 263 bacterial taxa" in page
    assert "binary" in page
    assert "Preprocess with MIPMLP" in page


def test_file_order_does_not_matter(client):
    response = upload(client, EXAMPLE_TAGS, EXAMPLE_COUNTS)
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "40 samples" in page and "binary" in page


def test_counts_alone_is_enough(client):
    response = upload(client, EXAMPLE_COUNTS)
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "40 samples" in page and "binary" not in page


def test_example_button(client):
    response = client.post("/example")
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Example dataset" in page and "40 samples" in page


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "Choose a counts table"),
        ([(b"a,b\n1,2\n", "notes.pdf")], "not a CSV or TSV"),
        ([(b"ID,Tag\na,1\n", "labels.csv")], "No counts table found"),
    ],
)
def test_bad_uploads_explain_the_problem(client, files, message):
    data = {"files": [(io.BytesIO(content), name) for content, name in files]}
    response = client.post("/upload", data=data, content_type="multipart/form-data",
                           follow_redirects=True)
    assert message in response.get_data(as_text=True)


def test_counts_problems_are_shown_and_block_preprocessing(client):
    bad = b"ID,asv0,asv1\na,1,x\nb,3,4\ntaxonomy,k__Bacteria,k__Bacteria\n"
    response = client.post("/upload", data={"files": [(io.BytesIO(bad), "bad.csv")]},
                           content_type="multipart/form-data", follow_redirects=True)
    page = response.get_data(as_text=True)
    assert "not numbers" in page
    assert "Preprocess with MIPMLP" not in page


# --- preprocessing and results ----------------------------------------------------

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
    url = upload(client, EXAMPLE_COUNTS).headers["Location"]
    assert client.get(f"{url}/download").status_code == 404


@pytest.mark.parametrize("run_id", ["0" * 32, "not-a-run", "..%2F..%2Fetc"])
def test_unknown_or_malformed_run_is_404(client, run_id):
    assert client.get(f"/runs/{run_id}").status_code == 404
