"""Background runs: a queue on disk, worked through one run at a time.

The queue *is* the run folders (see runs.py): ``submit`` marks a run "queued";
a ``Worker`` claims the oldest queued run by creating its ``worker.lock`` file
(only one worker can create it), runs the analysis with the same
``workflows.run_goal`` the website and ``mp.analyze`` use, and marks it "done"
or "failed". The run's page is its results link: it works with or without email.

A worker runs either inside the website (a background thread, for local use) or
as its own process: ``python -m microplatform.worker`` (for a server, so long
runs survive website restarts). Both share this module.

While it works, the worker refreshes a heartbeat in the lock file. A run whose
heartbeat has stopped (for example after a restart) is marked as interrupted,
so nothing says "running" forever. But a silent heartbeat alone is not proof:
a long computation can hold Python's GIL and delay it. So the lock also records
the worker's host, process ID and process start time, and a run is never marked
interrupted while that very process is still alive on this machine. (A worker
on another machine sharing the folder cannot be checked; there the heartbeat
decides.)
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from microplatform import runs, workflows
from microplatform.core.errors import UserFacingError
from microplatform.core.inputs import InputError
from microplatform.notify import EmailNotifier, finished_message, is_valid_email, mask_address

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 10
STALE_AFTER_SECONDS = 120  # no heartbeat for this long: the worker has gone


def submit(
    run: runs.Run,
    goal_id: str,
    email: str | None = None,
    results_url: str | None = None,
    email_enabled: bool = False,
    choices: dict | None = None,
) -> None:
    """Queue ``goal_id`` for ``run``; raises ``InputError`` (with a fix) if it cannot be queued.

    ``choices`` are the engine's advanced settings; they are checked now, not in the background.
    """
    if run.status in ("queued", "running"):
        raise InputError("This analysis is already running.",
                         "Wait for it to finish; its page updates by itself.")
    choices = workflows.check_goal(run, goal_id).resolve(choices)
    email = (email or "").strip() or None
    if email and not email_enabled:
        raise InputError("Email notifications are not switched on on this server.",
                         "Leave the email empty and bookmark this page instead.")
    if email and not is_valid_email(email):
        raise InputError(f"'{email}' does not look like an email address.",
                         "Check the address, or leave it empty and bookmark this page.")
    run.clear_results()
    run.set_status("queued", goal=goal_id, error=None, queued=_now_iso(),
                   notify=email, results_url=results_url, choices=choices)


def queued(root: Path) -> list[runs.Run]:
    """Queued runs, oldest first."""
    found = []
    for folder in Path(root).iterdir() if Path(root).is_dir() else []:
        run = runs.load(root, folder.name)
        if run is not None and run.status == "queued":
            found.append(run)
    return sorted(found, key=lambda r: r.meta().get("queued", ""))


def claim(run: runs.Run, worker: str) -> bool:
    """Take ownership of a queued run. Exactly one worker can succeed."""
    try:
        fd = os.open(run.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"worker": worker, "claimed": time.time(), "heartbeat": time.time(),
                   "host": socket.gethostname(), "pid": os.getpid(), "started": _process_started(os.getpid())}, f)
    if run.status != "queued":  # it changed between listing and claiming
        run.lock_file.unlink(missing_ok=True)
        return False
    return True


def process(run: runs.Run, cache_dir: Path | None = None, notifier: EmailNotifier | None = None) -> None:
    """Run a claimed run's goal to the end; never raises. Releases the lock and sends any email."""
    meta = run.meta()
    beat = _Heartbeat(run.lock_file)
    beat.start()
    try:
        workflows.run_goal(run, meta["goal"], cache_dir, meta.get("choices"))
    except UserFacingError:
        pass  # run_goal has recorded the message and fix
    except Exception:  # a bug, not the user's data: keep the details for us, tell the user plainly
        (run.path / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        log.exception("run %s failed", run.id)
        run.set_status("failed", error={
            "message": "Something went wrong on our side while running this analysis.",
            "fix": "Please click Run again. If it keeps failing, send the data to the lab.",
        })
    finally:
        beat.stop()
        run.lock_file.unlink(missing_ok=True)
        _notify(run, notifier)


def run_now(run: runs.Run, cache_dir: Path | None = None, notifier: EmailNotifier | None = None) -> None:
    """Process a just-submitted run immediately, through the same claim and lock (for tests)."""
    if claim(run, "inline"):
        process(run, cache_dir, notifier)


def recover_stale(root: Path) -> list[runs.Run]:
    """Mark runs whose worker has gone (no heartbeat) as interrupted. Returns them."""
    recovered = []
    for folder in Path(root).iterdir() if Path(root).is_dir() else []:
        run = runs.load(root, folder.name)
        if run is None or run.status not in ("queued", "running"):
            continue
        if run.status == "queued" and not run.lock_file.exists():
            continue  # waiting its turn, not abandoned
        if _heartbeat_age(run) < STALE_AFTER_SECONDS:
            continue
        if _owner_alive(run):
            continue  # busy: its worker process is still running, only the heartbeat is late
        run.lock_file.unlink(missing_ok=True)
        run.set_status("failed", error={
            "message": "This analysis was interrupted (the server stopped while it was running).",
            "fix": "Please click Run again.",
        })
        _notify(run, None)  # forget any email address; there is no notifier to tell
        recovered.append(run)
    return recovered


class Worker:
    """Works through the queue in ``root``, one run at a time."""

    def __init__(self, root: Path, cache_dir: Path | None = None, notifier: EmailNotifier | None = None,
                 poll_seconds: float = 2.0, name: str | None = None) -> None:
        self.root, self.cache_dir, self.notifier = Path(root), cache_dir, notifier
        self.poll_seconds = poll_seconds
        self.name = name or f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"
        self._stop = threading.Event()

    def run_once(self) -> runs.Run | None:
        """Process the oldest queued run, if any. Returns it."""
        recover_stale(self.root)
        for run in queued(self.root):
            if claim(run, self.name):
                process(run, self.cache_dir, self.notifier)
                return run
        return None

    def run_forever(self) -> None:
        log.info("worker %s watching %s", self.name, self.root)
        while not self._stop.is_set():
            try:
                if self.run_once() is None:
                    self._stop.wait(self.poll_seconds)
            except Exception:  # keep the worker alive whatever happens to one run
                log.exception("worker loop error")
                self._stop.wait(self.poll_seconds)

    def start_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.run_forever, name="microplatform-worker", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()


# --- helpers -----------------------------------------------------------------------

class _Heartbeat:
    """Refreshes the lock file's heartbeat while a run is processed."""

    def __init__(self, lock_file: Path) -> None:
        self.lock_file, self._stop = lock_file, threading.Event()
        self._thread = threading.Thread(target=self._beat, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                data = json.loads(self.lock_file.read_text(encoding="utf-8"))
                data["heartbeat"] = time.time()
                self.lock_file.write_text(json.dumps(data), encoding="utf-8")
            except (OSError, ValueError):
                return


def _heartbeat_age(run: runs.Run) -> float:
    """Seconds since the owning worker last showed signs of life (infinite if there is no worker)."""
    try:
        return time.time() - json.loads(run.lock_file.read_text(encoding="utf-8"))["heartbeat"]
    except (OSError, ValueError, KeyError):
        return float("inf")


def _owner_alive(run: runs.Run) -> bool:
    """True only if the process that claimed the run is certainly still running.

    It must be on this machine, and the process with that ID must have the same start time
    as the one recorded at claim time (a new process can reuse an old ID). Anything that
    cannot be checked (another machine, an old lock, an unsupported system) gives False, so
    the heartbeat decides, as before.
    """
    try:
        lock = json.loads(run.lock_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if lock.get("host") != socket.gethostname() or not lock.get("pid") or lock.get("started") is None:
        return False
    return _process_started(int(lock["pid"])) == lock["started"]


def _process_started(pid: int) -> str | None:
    """When process ``pid`` started, as an opaque text; None if it is not running or this cannot be read."""
    if sys.platform.startswith("linux"):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        except OSError:
            return None
        # Field 22 (start time in clock ticks since boot) comes after the name, which may hold spaces.
        return f"{boot}:{stat.rsplit(')', 1)[1].split()[19]}"
    if sys.platform == "win32":
        return _windows_process_started(pid)
    return None


def _windows_process_started(pid: int) -> str | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return None
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                        ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


def _notify(run: runs.Run, notifier: EmailNotifier | None) -> None:
    """Email the results link if asked for, then delete the address from the run (always)."""
    meta = run.meta()
    address = meta.get("notify")
    if not address:
        return
    masked = mask_address(address)  # logs never hold the full address
    try:
        if notifier is not None and meta.get("results_url"):
            subject, body = finished_message(meta["counts_name"], meta["status"], meta["results_url"])
            notifier.send(address, subject, body)
            run.update_meta(notify=None, notified=_now_iso())
            log.info("emailed the results link for run %s to %s (the mail server accepted it)", run.id, masked)
            return
    except Exception:
        log.exception("could not send the email for run %s to %s", run.id, masked)
        run.update_meta(notify=None, notified="failed")
        return
    log.warning("no email for run %s to %s: %s", run.id, masked,
                "email is off in this worker" if notifier is None else "the run has no results link")
    run.update_meta(notify=None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
