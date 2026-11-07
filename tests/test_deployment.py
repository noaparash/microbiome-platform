"""Server readiness: the WSGI entry, configuration, queue-only mode, graceful stop,
retention, permissions and the deployment files."""

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from microplatform import jobs, retention, workflows
from microplatform.engines import ENGINES
from microplatform.engines.mipmlp import MipmlpEngine
from microplatform.web import create_app
from microplatform.worker import install_graceful_stop

ROOT = Path(__file__).parents[1]
DEPLOY = ROOT / "deploy"


# --- the WSGI entry point -----------------------------------------------------------------

def _import_wsgi(tmp_path, **env):
    code = ("import microplatform.web.wsgi as w; a = w.app; "
            "print(a.config['JOBS'], 'microplatform.worker' in a.extensions, a.config['SESSION_COOKIE_SECURE'])")
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("MICROPLATFORM_")}
    full_env.update({"MICROPLATFORM_INSTANCE": str(tmp_path), **env})
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=full_env, timeout=300)


def test_wsgi_entry_refuses_to_start_without_a_secret(tmp_path):
    result = _import_wsgi(tmp_path)
    assert result.returncode != 0 and "MICROPLATFORM_SECRET_KEY is not set" in result.stderr


def test_wsgi_entry_imports_the_app_in_queue_only_mode(tmp_path):
    result = _import_wsgi(tmp_path, MICROPLATFORM_SECRET_KEY="x" * 64, MICROPLATFORM_COOKIE_SECURE="1")
    assert result.returncode == 0, result.stderr[-500:]
    assert result.stdout.split() == ["external", "False", "True"]  # queues only, no worker thread, HTTPS cookies


# --- configuration from the environment ---------------------------------------------------

@pytest.fixture
def env(monkeypatch, tmp_path):
    for key in list(os.environ):
        if key.startswith("MICROPLATFORM_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("MICROPLATFORM_INSTANCE", str(tmp_path / "instance"))
    return monkeypatch


def test_upload_limit_and_cookies_come_from_the_environment(env):
    env.setenv("MICROPLATFORM_MAX_UPLOAD_MB", "5")
    env.setenv("MICROPLATFORM_COOKIE_SECURE", "1")
    env.setenv("MICROPLATFORM_JOBS", "external")
    app = create_app()
    assert app.config["MAX_CONTENT_LENGTH"] == 5 * 1024 * 1024
    assert app.config["SESSION_COOKIE_SECURE"] and app.config["SESSION_COOKIE_HTTPONLY"]
    response = app.test_client().get("/")
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")


def test_pages_are_never_cached_but_static_files_are(env):
    env.setenv("MICROPLATFORM_JOBS", "external")
    client = create_app().test_client()
    assert client.get("/").headers["Cache-Control"] == "no-store"
    static = client.get("/static/style.css")
    assert "no-store" not in static.headers.get("Cache-Control", "") and "max-age=3600" in static.headers["Cache-Control"]
    static.close()


def test_behind_a_proxy_results_links_use_its_https_address(env):
    env.setenv("MICROPLATFORM_JOBS", "external")
    env.setenv("MICROPLATFORM_TRUST_PROXY", "1")
    client = create_app().test_client()
    headers = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "microbiome.lab.example", "X-Forwarded-For": "10.0.0.7"}
    url = client.post("/example", headers=headers).headers["Location"]
    client.post(f"{url}/run", data={"goal": "preprocess"}, headers=headers)
    run_id = url.rstrip("/").split("/")[-1]
    meta = json.loads((Path(os.environ["MICROPLATFORM_INSTANCE"]) / "runs" / run_id / "meta.json").read_text())
    assert meta["results_url"] == f"https://microbiome.lab.example/runs/{run_id}"


def test_queue_only_mode_leaves_runs_for_the_separate_worker(env, tmp_path):
    env.setenv("MICROPLATFORM_JOBS", "external")
    app = create_app()
    assert "microplatform.worker" not in app.extensions  # the website runs nothing itself
    client = app.test_client()
    url = client.post("/example").headers["Location"]
    client.post(f"{url}/run", data={"goal": "preprocess"})
    assert "Waiting to start" in client.get(url).get_data(as_text=True)
    runs_dir = app.config["RUNS_DIR"]
    processed = jobs.Worker(runs_dir, app.config["CACHE_DIR"]).run_once()  # what the worker service does
    assert processed is not None and processed.status == "done"


# --- graceful stop of the worker ------------------------------------------------------------

class _Slow(MipmlpEngine):
    def run(self, data, work_dir, choices=None):
        time.sleep(2)
        return super().run(data, work_dir, choices)


def test_stopping_the_worker_finishes_the_run_in_progress(tmp_path, monkeypatch):
    monkeypatch.setitem(ENGINES, "preprocess", _Slow())
    worker = jobs.Worker(tmp_path / "runs", tmp_path / "cache", poll_seconds=0.1)
    run = workflows.start_example_run(tmp_path / "runs")
    jobs.submit(run, "preprocess")
    thread = threading.Thread(target=worker.run_forever)
    thread.start()
    deadline = time.time() + 120
    while run.status != "running" and time.time() < deadline:
        time.sleep(0.05)
    worker.stop()  # what SIGTERM does
    thread.join(timeout=300)
    assert not thread.is_alive()
    assert run.status == "done"  # finished, not abandoned


def test_sigterm_and_ctrl_c_request_a_graceful_stop(monkeypatch):
    import signal

    handlers = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))
    worker = jobs.Worker(Path("unused"))
    install_graceful_stop(worker)
    assert set(handlers) == {signal.SIGTERM, signal.SIGINT}
    handlers[signal.SIGTERM](signal.SIGTERM, None)
    assert worker._stop.is_set()


# --- retention: list by default, delete only on request, log it ----------------------------

@pytest.fixture
def aged_runs(tmp_path):
    root = tmp_path / "instance" / "runs"
    old_done, old_running, recent = (workflows.start_example_run(root) for _ in range(3))
    long_ago = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(timespec="seconds")
    old_done.update_meta(created=long_ago, status="done")
    old_running.update_meta(created=long_ago, status="running")
    return tmp_path / "instance", old_done, old_running, recent


def test_listing_deletes_nothing(aged_runs, capsys):
    instance, old_done, old_running, recent = aged_runs
    assert retention.main(["--instance", str(instance), "--older-than", "90"]) == 0
    out = capsys.readouterr().out
    assert old_done.id in out and old_running.id not in out and recent.id not in out
    assert "Nothing deleted" in out and old_done.path.exists()


def test_delete_needs_confirmation(aged_runs, monkeypatch):
    instance, old_done, _, _ = aged_runs
    monkeypatch.setattr("sys.stdin", io.StringIO("no\n"))
    assert retention.main(["--instance", str(instance), "--older-than", "90", "--delete"]) == 1
    assert old_done.path.exists()


def test_delete_removes_only_old_finished_runs_and_logs_without_file_names(aged_runs):
    instance, old_done, old_running, recent = aged_runs
    assert retention.main(["--instance", str(instance), "--older-than", "90", "--delete", "--yes"]) == 0
    assert not old_done.path.exists()
    assert old_running.path.exists() and recent.path.exists()  # running and recent are never touched
    [entry] = [json.loads(line) for line in (instance / "retention.log").read_text().splitlines()]
    assert entry["run_id"] == old_done.id and entry["status"] == "done" and entry["by"]
    assert "example" not in json.dumps(entry).lower()  # no file names or data in the log


def test_retention_refuses_a_zero_age(tmp_path):
    with pytest.raises(ValueError):
        retention.find_old_runs(tmp_path, 0)


# --- permissions (Linux servers) ---------------------------------------------------------------

@pytest.mark.skipif(os.name != "posix", reason="folder permissions are a Linux/macOS concept")
def test_run_folders_are_private_to_the_service_account(tmp_path):
    run = workflows.start_example_run(tmp_path / "runs")
    assert (run.path.stat().st_mode & 0o777) == 0o700


# --- the deployment files ---------------------------------------------------------------------

def test_every_setting_the_code_reads_is_in_the_template():
    template = (DEPLOY / "microplatform.env.example").read_text(encoding="utf-8")
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py"))
    code += (DEPLOY / "gunicorn.conf.py").read_text(encoding="utf-8")
    used = set(re.findall(r"MICROPLATFORM_[A-Z_]+[A-Z]", code)) - {"MICROPLATFORM_SMTP"}  # "SMTP_*" in prose
    missing = {name for name in used if f"{name}=" not in template}
    assert not missing, f"add to deploy/microplatform.env.example: {sorted(missing)}"
    assert re.search(r"^MICROPLATFORM_JOBS=external$", template, re.M)
    assert re.search(r"^MICROPLATFORM_SECRET_KEY=$", template, re.M)  # empty: never a real secret in Git
    assert re.search(r"^MICROPLATFORM_SMTP_HOST=$", template, re.M)  # email off until the lab provides it


def test_service_files_start_the_right_programs():
    web = (DEPLOY / "systemd" / "microplatform-web.service").read_text(encoding="utf-8")
    worker = (DEPLOY / "systemd" / "microplatform-worker.service").read_text(encoding="utf-8")
    assert "gunicorn -c /opt/microplatform/deploy/gunicorn.conf.py microplatform.web.wsgi:app" in web
    assert "-m microplatform.worker --instance /var/lib/microplatform" in worker
    for unit in (web, worker):
        assert "Restart=" in unit and "WantedBy=multi-user.target" in unit
        assert "UMask=0077" in unit and "EnvironmentFile=/etc/microplatform/microplatform.env" in unit
    assert "TimeoutStopSec=4h" in worker  # time to finish the run in progress, even a long one


def test_gunicorn_settings_listen_locally_and_keep_addresses_out_of_logs():
    settings = {}
    exec((DEPLOY / "gunicorn.conf.py").read_text(encoding="utf-8"), settings)
    assert settings["bind"].startswith("127.0.0.1:")
    assert "%(r)s" not in settings["access_log_format"] and "%(U)s" not in settings["access_log_format"]


def test_nginx_template_is_https_and_restricted_by_default():
    nginx = (DEPLOY / "nginx" / "microplatform.conf").read_text(encoding="utf-8")
    assert "listen 443 ssl" in nginx and "return 301 https://" in nginx
    assert "deny  all;" in nginx and "allow <LAB_NETWORK_CIDR>;" in nginx
    assert "$request_uri" not in nginx.split("log_format", 1)[1].split(";", 1)[0]  # no addresses in logs
    assert "client_max_body_size 100m" in nginx


def test_admin_sheet_interim_certificate_and_narrow_ranges():
    """peptibase10's admin sheet: the interim self-signed certificate signs step 2's own request
    (same key, so IT's certificate later replaces one file), with -extfile, which works on OpenSSL
    1.1 and 3 (-copy_extensions does not exist in 1.1); an empty VPN range drops its allow line
    (an empty "allow ;" breaks nginx -t); a range added later goes into nginx and the firewall."""
    sheet = (DEPLOY.parent / "docs" / "admin-peptibase10.md").read_text(encoding="utf-8")
    assert "## 2b. Interim: a self-signed certificate" in sheet
    assert "-in /root/$HOST.csr -signkey /etc/pki/tls/private/$HOST.key" in sheet
    assert "-extfile /root/$HOST.ext" in sheet and "-copy_extensions" not in sheet
    assert "-fingerprint -sha256" in sheet and "Swapping in IT's certificate" in sheet
    assert """[ -z "$VPN" ] && sudo sed -i '/<VPN_CIDR>/d'""" in sheet
    assert 'sudo sed -i "/^ *deny  all;/i\\    allow $NEW;"' in sheet
    assert 'source address=\\"$NEW\\"' in sheet
    assert "**Never** a wide range" in sheet


def test_almalinux_nginx_template_is_https_only_and_restricted():
    """The AlmaLinux/RHEL template (peptibase10): port 443 on the server's address only, no port 80
    (another service may hold it), lab/VPN ranges only, the private log and the upload limit."""
    nginx = (DEPLOY / "nginx" / "microplatform.almalinux.conf").read_text(encoding="utf-8")
    listens = [line.strip() for line in nginx.splitlines() if line.strip().startswith("listen")]
    assert listens == ["listen <SERVER_IP>:443 ssl http2;"]
    assert "deny  all;" in nginx and "allow <LAB_NETWORK_CIDR>;" in nginx and "allow <VPN_CIDR>;" in nginx
    assert "$request_uri" not in nginx.split("log_format", 1)[1].split(";", 1)[0]
    assert "client_max_body_size 100m" in nginx and "proxy_pass http://127.0.0.1:8000;" in nginx
    assert "/etc/pki/tls/private/<HOSTNAME>.key" in nginx
