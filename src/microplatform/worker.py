"""Run the background worker as its own process (for a server).

    python -m microplatform.worker --instance instance

It works through the runs queued by the website in ``<instance>/runs``. Stop it
with Ctrl+C; a run it was working on is marked as interrupted the next time a
worker starts. Email settings are read from the environment (see microplatform.notify).
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from microplatform.jobs import Worker
from microplatform.notify import EmailNotifier, EmailSettings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m microplatform.worker", description=__doc__.split("\n\n")[0])
    parser.add_argument("--instance", type=Path,
                        default=Path(os.environ.get("MICROPLATFORM_INSTANCE", "instance")),
                        help="the website's instance folder (default: ./instance)")
    parser.add_argument("--poll", type=float, default=2.0, help="seconds between checks for new runs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = EmailSettings.from_env()
    logging.info("email notifications: %s", "on" if settings else "off (no SMTP settings)")
    worker = Worker(args.instance.resolve() / "runs", args.instance.resolve() / "cache",
                    EmailNotifier(settings) if settings else None, poll_seconds=args.poll)
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        logging.info("stopped")


if __name__ == "__main__":
    main()
