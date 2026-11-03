"""Background runs (microplatform.jobs), the worker, and the optional email."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import pytest

from microplatform import jobs, runs, workflows
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import InputError
from microplatform.engines import ENGINES
from microplatform.engines.mipmlp import MipmlpEngine
from microplatform.examples import EXAMPLE_COUNTS, EXAMPLE_TAGS
from microplatform.notify import EmailNotifier, EmailSettings, finished_message


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("cache")  # shared: MIPMLP runs once for the whole module


@pytest.fixture
def root(tmp_path):
    return tmp_path / "runs"


@pytest.fixture
def new_run(root):
    return lambda: workflows.start_example_run(root)


class FakeNotifier:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, to, subject, body):
        if self.fail:
            raise ConnectionError("mail server down")
        self.sent.append((to, subject, body))


# --- submitting ------------------------------------------------------------------------

def test_submit_queues_the_run(new_run):
    run = new_run()
    jobs.submit(run, "preprocess", results_url="http://x/runs/1")
    meta = run.meta()
    assert run.status == "queued" and meta["goal"] == "preprocess" and meta["queued"]
    assert meta["results_url"] == "http://x/runs/1" and meta["notify"] is None


def test_submit_refuses_a_task_that_cannot_run(new_run):
    with pytest.raises(InputError, match="cannot run"):
        jobs.submit(new_run(), "metabolites")


def test_submit_refuses_a_second_click(new_run):
    run = new_run()
    jobs.submit(run, "preprocess")
    with pytest.raises(InputError, match="already running") as info:
        jobs.submit(run, "preprocess")
    assert "updates by itself" in info.value.fix


def test_email_is_refused_while_email_is_off(new_run):
    with pytest.raises(InputError, match="not switched on"):
        jobs.submit(new_run(), "preprocess", email="me@lab.ac.il", email_enabled=False)


def test_an_invalid_email_is_explained(new_run):
    with pytest.raises(InputError, match="does not look like an email"):
        jobs.submit(new_run(), "preprocess", email="not-an-address", email_enabled=True)


def test_resubmitting_clears_old_outputs(new_run, cache):
    run = new_run()
    jobs.submit(run, "preprocess")
    jobs.run_now(run, cache)
    assert run.processed_file.exists()
    run.set_status("failed", error={"message": "x", "fix": "y"})
    jobs.submit(run, "preprocess")
    assert not run.processed_file.exists() and not run.figures_dir.exists()
    assert run.meta()["error"] is None


# --- claiming and processing ------------------------------------------------------------

def test_only_one_worker_can_claim_a_run(new_run):
    run = new_run()
    jobs.submit(run, "preprocess")
    assert jobs.claim(run, "worker-a") is True
    assert jobs.claim(run, "worker-b") is False


def test_claims_happen_once_even_when_racing(new_run):
    run = new_run()
    jobs.submit(run, "preprocess")
    wins = []
    threads = [threading.Thread(target=lambda n=n: wins.append(jobs.claim(run, f"w{n}"))) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert wins.count(True) == 1


def test_worker_processes_the_oldest_queued_run(root, new_run, cache):
    first, second = new_run(), new_run()
    jobs.submit(first, "preprocess")
    time.sleep(1.1)  # queued times have one-second resolution
    jobs.submit(second, "preprocess")
    worker = jobs.Worker(root, cache)
    assert worker.run_once() == first
    assert first.status == "done" and second.status == "queued"
    assert first.processed_file.exists() and not first.lock_file.exists()
    assert worker.run_once() == second and second.status == "done"
    assert worker.run_once() is None  # nothing left


class _UserProblem(MipmlpEngine):
    def run(self, data, work_dir, choices=None):
        raise UserFacingError("Your data broke the tool.", "Try other data.")


class _Bug(MipmlpEngine):
    def run(self, data, work_dir, choices=None):
        raise RuntimeError("a bug in our code")


def test_a_data_problem_fails_the_run_with_its_fix(root, new_run, cache, monkeypatch):
    monkeypatch.setitem(ENGINES, "preprocess", _UserProblem())
    run = new_run()
    jobs.submit(run, "preprocess")
    jobs.Worker(root, cache).run_once()
    assert run.status == "failed"
    assert run.meta()["error"] == {"message": "Your data broke the tool.", "fix": "Try other data."}
    assert not run.lock_file.exists()


def test_a_bug_fails_the_run_politely_and_keeps_the_details(root, new_run, cache, monkeypatch):
    monkeypatch.setitem(ENGINES, "preprocess", _Bug())
    run = new_run()
    jobs.submit(run, "preprocess")
    jobs.Worker(root, cache).run_once()  # does not raise: the worker keeps going
    assert run.status == "failed"
    assert "on our side" in run.meta()["error"]["message"]
    assert "a bug in our code" in (run.path / "error.log").read_text(encoding="utf-8")
    assert not run.lock_file.exists()


# --- interrupted runs and the heartbeat ---------------------------------------------------

def _lock(run, age_seconds):
    run.lock_file.write_text(json.dumps({"worker": "gone", "heartbeat": time.time() - age_seconds}))


def test_a_run_whose_worker_has_gone_is_marked_interrupted(root, new_run):
    run = new_run()
    jobs.submit(run, "preprocess", email="me@lab.ac.il", email_enabled=True)
    run.set_status("running")
    _lock(run, jobs.STALE_AFTER_SECONDS + 5)
    assert jobs.recover_stale(root) == [run]
    assert run.status == "failed" and "interrupted" in run.meta()["error"]["message"]
    assert not run.lock_file.exists()
    assert run.meta()["notify"] is None  # the address is forgotten


def test_a_running_run_without_a_lock_is_interrupted(root, new_run):
    run = new_run()
    jobs.submit(run, "preprocess")
    run.set_status("running")  # e.g. the worker was stopped with Ctrl+C
    assert jobs.recover_stale(root) == [run]


def test_live_and_waiting_runs_are_left_alone(root, new_run):
    live, waiting = new_run(), new_run()
    jobs.submit(live, "preprocess")
    live.set_status("running")
    _lock(live, 1)
    jobs.submit(waiting, "preprocess")
    assert jobs.recover_stale(root) == []
    assert live.status == "running" and waiting.status == "queued"


# --- a late heartbeat is not a gone worker ------------------------------------------------

def _claimed_by(run, pid, started, age_seconds, host=None):
    run.lock_file.write_text(json.dumps({
        "worker": "w", "heartbeat": time.time() - age_seconds, "host": host or socket.gethostname(),
        "pid": pid, "started": started,
    }))


def test_a_busy_worker_with_a_late_heartbeat_is_never_marked_interrupted(root, new_run):
    """E.g. a long computation holding the GIL: the process is alive, so the run is left alone."""
    run = new_run()
    jobs.submit(run, "preprocess")
    run.set_status("running")
    me = os.getpid()
    _claimed_by(run, me, jobs._process_started(me), jobs.STALE_AFTER_SECONDS * 100)
    assert jobs._process_started(me) is not None  # this system can be checked
    assert jobs.recover_stale(root) == []
    assert run.status == "running" and run.lock_file.exists()


def test_a_claim_records_the_process_that_can_be_checked(root, new_run):
    run = new_run()
    jobs.submit(run, "preprocess")
    assert jobs.claim(run, "me")
    lock = json.loads(run.lock_file.read_text())
    assert lock["pid"] == os.getpid() and lock["host"] == socket.gethostname()
    assert lock["started"] == jobs._process_started(os.getpid())
    run.lock_file.write_text(json.dumps(lock | {"heartbeat": 0}))
    run.set_status("running")
    assert jobs.recover_stale(root) == []  # claimed by this live process


def test_a_worker_process_that_has_exited_is_recovered(root, new_run):
    gone = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True, check=True)
    pid = int(gone.stdout)
    assert jobs._process_started(pid) is None
    run = new_run()
    jobs.submit(run, "preprocess")
    run.set_status("running")
    _claimed_by(run, pid, "12345", jobs.STALE_AFTER_SECONDS + 5)
    assert jobs.recover_stale(root) == [run]


def test_a_reused_process_id_is_not_mistaken_for_the_worker(root, new_run):
    """The ID now belongs to another process (a different start time): the worker is gone."""
    run = new_run()
    jobs.submit(run, "preprocess")
    run.set_status("running")
    _claimed_by(run, os.getpid(), "not-this-process", jobs.STALE_AFTER_SECONDS + 5)
    assert jobs.recover_stale(root) == [run]


def test_a_worker_on_another_machine_falls_back_to_the_heartbeat(root, new_run):
    late, fresh = new_run(), new_run()
    for run, age in ((late, jobs.STALE_AFTER_SECONDS + 5), (fresh, 1)):
        jobs.submit(run, "preprocess")
        run.set_status("running")
        _claimed_by(run, os.getpid(), jobs._process_started(os.getpid()), age, host="another-machine")
    assert jobs.recover_stale(root) == [late]


class _Slow(MipmlpEngine):
    def run(self, data, work_dir, choices=None):
        time.sleep(1.5)
        return super().run(data, work_dir, choices)


def test_the_heartbeat_is_refreshed_while_working(root, new_run, cache, monkeypatch):
    monkeypatch.setattr(jobs, "HEARTBEAT_SECONDS", 0.2)
    monkeypatch.setitem(ENGINES, "preprocess", _Slow())
    run = new_run()
    jobs.submit(run, "preprocess")
    assert jobs.claim(run, "me")
    claimed = json.loads(run.lock_file.read_text())["heartbeat"]
    seen = []
    watcher = threading.Thread(target=lambda: (time.sleep(1.0), seen.append(
        json.loads(run.lock_file.read_text())["heartbeat"]) if run.lock_file.exists() else None))
    watcher.start()
    jobs.process(run, cache)
    watcher.join()
    assert seen and seen[0] > claimed
    assert run.status == "done"


# --- email ------------------------------------------------------------------------------

def test_email_holds_only_the_link_and_the_address_is_deleted(root, new_run, cache):
    notifier = FakeNotifier()
    run = new_run()
    jobs.submit(run, "preprocess", email="me@lab.ac.il", results_url="https://site/runs/abc", email_enabled=True)
    jobs.Worker(root, cache, notifier).run_once()
    [(to, subject, body)] = notifier.sent
    assert to == "me@lab.ac.il" and "ready" in subject
    assert "https://site/runs/abc" in body
    samples = pd.read_csv(EXAMPLE_TAGS, index_col=0).index.astype(str)
    assert not any(s in body for s in samples)  # no data in the email
    assert "Bacteria" not in body and "Grouped" not in body  # nor results
    meta = run.meta()
    assert meta["notify"] is None and meta["notified"]
    assert "me@lab.ac.il" not in run.path.joinpath("meta.json").read_text()


def test_a_failed_run_also_emails_the_link(root, new_run, cache, monkeypatch):
    monkeypatch.setitem(ENGINES, "preprocess", _UserProblem())
    notifier = FakeNotifier()
    run = new_run()
    jobs.submit(run, "preprocess", email="me@lab.ac.il", results_url="https://site/runs/abc", email_enabled=True)
    jobs.Worker(root, cache, notifier).run_once()
    [(_, subject, body)] = notifier.sent
    assert "did not finish" in subject and "https://site/runs/abc" in body


def test_a_mail_server_failure_does_not_break_the_run(root, new_run, cache):
    run = new_run()
    jobs.submit(run, "preprocess", email="me@lab.ac.il", results_url="https://site/r", email_enabled=True)
    jobs.Worker(root, cache, FakeNotifier(fail=True)).run_once()
    assert run.status == "done"
    assert run.meta()["notify"] is None and run.meta()["notified"] == "failed"


def test_email_settings_come_from_the_environment():
    assert EmailSettings.from_env({}) is None
    assert EmailSettings.from_env({"MICROPLATFORM_SMTP_HOST": "smtp.x"}) is None  # no sender
    settings = EmailSettings.from_env({
        "MICROPLATFORM_SMTP_HOST": "smtp.lab.ac.il", "MICROPLATFORM_SMTP_SENDER": "platform@lab.ac.il",
        "MICROPLATFORM_SMTP_PORT": "2525", "MICROPLATFORM_SMTP_USER": "u", "MICROPLATFORM_SMTP_PASSWORD": "p",
        "MICROPLATFORM_SMTP_TLS": "0",
    })
    assert settings == EmailSettings("smtp.lab.ac.il", "platform@lab.ac.il", 2525, "u", "p", False)


def test_email_notifier_talks_to_the_mail_server(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            calls.append(("quit",))

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["From"], message["To"], message["Subject"], message.get_content()))

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    subject, body = finished_message("data.csv", "done", "https://site/runs/abc")
    EmailNotifier(EmailSettings("smtp.lab", "from@lab", 587, "u", "p")).send("to@lab", subject, body)
    assert calls[0] == ("connect", "smtp.lab", 587)
    assert ("starttls",) in calls and ("login", "u", "p") in calls
    send = next(c for c in calls if c[0] == "send")
    assert send[1:4] == ("from@lab", "to@lab", "Your microbiome analysis is ready")
    assert "https://site/runs/abc" in send[4]


# --- the worker as a thread and as a program ----------------------------------------------

def test_worker_thread_runs_queued_work_in_the_background(root, new_run, cache):
    worker = jobs.Worker(root, cache, poll_seconds=0.2)
    worker.start_thread()
    try:
        run = new_run()
        jobs.submit(run, "preprocess")
        deadline = time.time() + 300
        while run.status != "done" and time.time() < deadline:
            time.sleep(0.2)
        assert run.status == "done" and run.processed_file.exists()
    finally:
        worker.stop()


def test_worker_program_starts():
    result = subprocess.run([sys.executable, "-m", "microplatform.worker", "--help"],
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0 and "--instance" in result.stdout


def test_analyze_still_runs_directly_without_a_worker(tmp_path, cache):
    view = workflows.analyze(EXAMPLE_COUNTS, goal="preprocess", out_dir=tmp_path, cache_dir=cache)
    assert view.status == "done" and not runs.load(tmp_path, view.run.id).lock_file.exists()


def test_the_linux_process_start_time_is_read_from_proc(monkeypatch):
    """The lab server runs Linux: field 22 of /proc/<pid>/stat, after a name that may hold spaces and ')'."""
    files = {
        "/proc/42/stat": "42 (python -m x) y) S 1 42 42 0 -1 4194560 100 0 0 0 5 2 0 0 20 0 3 0 987654 123 456\n",
        "/proc/sys/kernel/random/boot_id": "boot-abc\n",
    }

    def read_text(path, *args, **kwargs):
        try:
            return files[Path(path).as_posix()]
        except KeyError:
            raise FileNotFoundError(path) from None

    monkeypatch.setattr(jobs.sys, "platform", "linux")
    monkeypatch.setattr(jobs.Path, "read_text", read_text)
    assert jobs._process_started(42) == "boot-abc:987654"
    assert jobs._process_started(43) is None  # no such process
