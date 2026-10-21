"""Background runs through the website: the waiting page, the results link, email on and off."""

import io
import re
import time

import pytest

from microplatform.engines import ENGINES
from microplatform.engines.mipmlp import MipmlpEngine
from microplatform.core.errors import UserFacingError
from microplatform.examples import EXAMPLE_COUNTS
from microplatform.notify import EmailSettings
from microplatform.web import create_app

COUNTS = (EXAMPLE_COUNTS.name, EXAMPLE_COUNTS.read_bytes())
SETTINGS = EmailSettings("smtp.lab.ac.il", "platform@lab.ac.il")


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))


def make_client(tmp_path, **config):
    app = create_app({"TESTING": True, "RUNS_DIR": tmp_path / "runs", "CACHE_DIR": tmp_path / "cache", **config})
    return app, app.test_client()


def upload_counts(client):
    data = {"files": [(io.BytesIO(COUNTS[1]), COUNTS[0])]}
    return client.post("/upload", data=data, content_type="multipart/form-data").headers["Location"]


def test_run_in_the_background_then_show_results(tmp_path):
    app, client = make_client(tmp_path, JOBS="thread")
    try:
        url = upload_counts(client)
        client.post(f"{url}/run", data={"goal": "preprocess"})
        page = client.get(url).get_data(as_text=True)
        if "Results:" not in page:  # it may already be done on a fast machine
            assert 'http-equiv="refresh"' in page
            assert "You can close this page" in page
            assert re.search(r"(Waiting to start|Running)…", page)
            assert f"http://localhost{url}" in page  # the results link to keep
        deadline = time.time() + 300
        while "Results:" not in page and time.time() < deadline:
            time.sleep(0.5)
            page = client.get(url).get_data(as_text=True)
        assert "Results: Preprocessed with MIPMLP" in page
        assert 'http-equiv="refresh"' not in page  # no more refreshing once done
    finally:
        app.extensions["microplatform.worker"].stop()


def test_external_mode_only_queues(tmp_path):
    _, client = make_client(tmp_path, JOBS="external")
    url = upload_counts(client)
    client.post(f"{url}/run", data={"goal": "preprocess"})
    page = client.get(url).get_data(as_text=True)
    assert "Waiting to start…" in page and 'http-equiv="refresh"' in page


def test_clicking_run_twice_is_explained(tmp_path):
    _, client = make_client(tmp_path, JOBS="external")
    url = upload_counts(client)
    client.post(f"{url}/run", data={"goal": "preprocess"})
    page = client.post(f"{url}/run", data={"goal": "preprocess"}, follow_redirects=True).get_data(as_text=True)
    assert "already running" in page


def test_no_email_field_while_email_is_off(tmp_path):
    _, client = make_client(tmp_path, JOBS="inline", EMAIL=None)
    page = client.get(upload_counts(client)).get_data(as_text=True)
    assert 'name="email"' not in page and "Run" in page


def test_email_field_and_message_when_email_is_on(tmp_path):
    notifier = FakeNotifier()
    _, client = make_client(tmp_path, JOBS="inline", EMAIL=SETTINGS, NOTIFIER=notifier)
    url = upload_counts(client)
    page = client.get(url).get_data(as_text=True)
    assert 'name="email"' in page and "never data" in page
    client.post(f"{url}/run", data={"goal": "preprocess", "email": "me@lab.ac.il"})
    [(to, _, body)] = notifier.sent
    assert to == "me@lab.ac.il" and f"http://localhost{url}" in body


def test_an_invalid_email_is_explained_on_the_page(tmp_path):
    _, client = make_client(tmp_path, JOBS="inline", EMAIL=SETTINGS, NOTIFIER=FakeNotifier())
    url = upload_counts(client)
    page = client.post(f"{url}/run", data={"goal": "preprocess", "email": "nope"},
                       follow_redirects=True).get_data(as_text=True)
    assert "does not look like an email address" in page and "How to fix:" in page


class _UserProblem(MipmlpEngine):
    def run(self, data, work_dir):
        raise UserFacingError("Your data broke the tool.", "Try other data.")


def test_a_failed_run_shows_why_and_offers_run_again(tmp_path, monkeypatch):
    monkeypatch.setitem(ENGINES, "preprocess", _UserProblem())
    _, client = make_client(tmp_path, JOBS="inline")
    url = upload_counts(client)
    page = client.post(f"{url}/run", data={"goal": "preprocess"}, follow_redirects=True).get_data(as_text=True)
    assert "The analysis did not finish" in page and "Your data broke the tool." in page
    assert "Try other data." in page
    assert 'type="submit">Run</button>' in page  # the plan is offered again
    assert "Results:" not in page


@pytest.mark.parametrize("bad", ["sideways"])
def test_an_unknown_jobs_mode_is_rejected(tmp_path, bad):
    with pytest.raises(ValueError, match="JOBS"):
        make_client(tmp_path, JOBS=bad)
