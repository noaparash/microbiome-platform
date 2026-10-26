"""Data retention: list, and on request delete, analyses older than a chosen age.

Never automatic. Run it by hand, for example once a month:

    python -m microplatform.retention --instance /var/lib/microplatform --older-than 90
    python -m microplatform.retention --instance /var/lib/microplatform --older-than 90 --delete

Without ``--delete`` it only lists what would be deleted. With ``--delete`` it
asks for confirmation (skip with ``--yes``), deletes, and appends one line per
deleted run to ``<instance>/retention.log`` (run ID, creation date, size, who
ran it, when) — never file names or data, which may be sensitive. Runs that are
queued or running are never deleted. The preprocessing cache (derived from
uploads) can be cleared too with ``--include-cache``.
"""

from __future__ import annotations

import argparse
import getpass
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from microplatform import runs


@dataclass(frozen=True)
class Candidate:
    run: runs.Run
    created: datetime
    status: str
    size_bytes: int


def find_old_runs(root: Path, older_than_days: int, now: datetime | None = None) -> list[Candidate]:
    """Finished or failed runs created more than ``older_than_days`` ago (never queued/running)."""
    if older_than_days < 1:
        raise ValueError("--older-than must be at least 1 day")
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=older_than_days)
    found = []
    for folder in sorted(Path(root).iterdir()) if Path(root).is_dir() else []:
        run = runs.load(root, folder.name)
        if run is None:
            continue
        meta = run.meta()
        created = datetime.fromisoformat(meta["created"])
        status = meta.get("status", "uploaded")
        if created < cutoff and status not in ("queued", "running"):
            found.append(Candidate(run, created, status, _size(run.path)))
    return found


def delete_runs(candidates: list[Candidate], log_file: Path, now: datetime | None = None) -> int:
    """Delete these runs and log each one. Returns the number deleted."""
    now = now or datetime.now(timezone.utc)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    deleted = 0
    with log_file.open("a", encoding="utf-8") as log:
        for c in candidates:
            if c.run.status in ("queued", "running"):  # re-check: it may have been restarted meanwhile
                continue
            shutil.rmtree(c.run.path)
            log.write(json.dumps({
                "deleted_at": now.isoformat(timespec="seconds"), "run_id": c.run.id,
                "created": c.created.isoformat(timespec="seconds"), "status": c.status,
                "size_bytes": c.size_bytes, "by": _who(),
            }) + "\n")
            deleted += 1
    return deleted


def clear_cache(cache_dir: Path, log_file: Path) -> int:
    """Remove the preprocessing cache (it is rebuilt when needed). Returns files removed."""
    files = [p for p in Path(cache_dir).glob("*") if p.is_file()] if Path(cache_dir).is_dir() else []
    for p in files:
        p.unlink()
    with log_file.open("a", encoding="utf-8") as log:
        log.write(json.dumps({"deleted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "cache_files": len(files), "by": _who()}) + "\n")
    return len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m microplatform.retention",
                                     description="List (and on request delete) old analyses. Never automatic.")
    parser.add_argument("--instance", type=Path, required=True, help="the instance folder, e.g. /var/lib/microplatform")
    parser.add_argument("--older-than", type=int, required=True, metavar="DAYS", help="age in days")
    parser.add_argument("--delete", action="store_true", help="actually delete (otherwise only list)")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation (with --delete)")
    parser.add_argument("--include-cache", action="store_true", help="also clear the preprocessing cache")
    args = parser.parse_args(argv)

    instance = args.instance.resolve()
    candidates = find_old_runs(instance / "runs", args.older_than)
    total_mb = sum(c.size_bytes for c in candidates) / 1e6
    print(f"{len(candidates)} analyses older than {args.older_than} days ({total_mb:.1f} MB):")
    for c in candidates:
        print(f"  {c.run.id}  created {c.created:%Y-%m-%d}  {c.status:<8} {c.size_bytes / 1e6:6.1f} MB")
    if not args.delete:
        print("Nothing deleted (this was a listing). Add --delete to delete them.")
        return 0
    if candidates or args.include_cache:
        if not args.yes and input("Delete these permanently? Type 'delete' to confirm: ").strip() != "delete":
            print("Cancelled; nothing deleted.")
            return 1
    log_file = instance / "retention.log"
    deleted = delete_runs(candidates, log_file)
    print(f"Deleted {deleted} analyses; logged in {log_file}.")
    if args.include_cache:
        print(f"Cleared {clear_cache(instance / 'cache', log_file)} cache files.")
    return 0


def _size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _who() -> str:
    try:
        return getpass.getuser()
    except Exception:  # no login name available (e.g. some services)
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
