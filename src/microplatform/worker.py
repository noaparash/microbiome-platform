"""Run the background worker as its own process (for a server).

    python -m microplatform.worker --instance /var/lib/microplatform

It works through the runs queued by the website in ``<instance>/runs``.

Stopping is graceful: on SIGTERM (``systemctl stop``/``restart``) or Ctrl+C it
takes no new runs and **finishes the one in progress** before exiting, so long
runs are not lost. (Give the service enough stop time; see deploy/systemd.) If
the process is killed outright, the interrupted run is marked "interrupted,
please run again" when a worker next starts. Email settings are read from the
environment (see microplatform.notify).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
from pathlib import Path

from microplatform.jobs import Worker
from microplatform.notify import EmailNotifier, EmailSettings

log = logging.getLogger("microplatform.worker")


def install_graceful_stop(worker: Worker) -> None:
    """On SIGTERM or SIGINT: finish the current run, then stop."""

    def stop(signum, _frame):
        log.info("received %s: finishing the current run, then stopping", signal.Signals(signum).name)
        worker.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m microplatform.worker", description=__doc__.split("\n\n")[0])
    parser.add_argument("--instance", type=Path,
                        default=Path(os.environ.get("MICROPLATFORM_INSTANCE", "instance")),
                        help="the website's instance folder (default: $MICROPLATFORM_INSTANCE or ./instance)")
    parser.add_argument("--poll", type=float, default=2.0, help="seconds between checks for new runs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no screen on a server
    os.environ.setdefault("MPLBACKEND", "Agg")
    instance = args.instance.resolve()
    settings = EmailSettings.load(instance)
    log.info("email notifications: %s", f"on, {settings.describe()}" if settings else "off (no SMTP settings)")
    worker = Worker(instance / "runs", instance / "cache",
                    EmailNotifier(settings) if settings else None, poll_seconds=args.poll)
    install_graceful_stop(worker)
    log.info("watching %s (one run at a time)", instance / "runs")
    worker.run_forever()
    log.info("stopped")


if __name__ == "__main__":
    main()
