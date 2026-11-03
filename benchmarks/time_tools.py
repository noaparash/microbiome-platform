"""Time one analysis exactly as the website runs it (``mp.analyze``), and append the result as one JSON line.

Usage: python time_tools.py <dataset name> <goal> <out_dir> <cache_dir> <results.jsonl>
                            --counts F [--labels F] [--metabolites F]

The preprocessing time is read from the run's record (0 when the table came from the cache), so
"tool" time = total − preprocessing. Run one analysis per process (run_all.sh), so a crash or a
time-out in one tool cannot affect the others.
"""

import json
import platform
import sys
import threading
import time
from pathlib import Path

import microplatform as mp

name, goal, out_dir, cache_dir, results = sys.argv[1:6]
args = dict(zip(sys.argv[6::2], sys.argv[7::2]))


def peak_memory_gb() -> float | None:
    """The most memory this process has used so far (Windows), in GB; None if it cannot be read."""
    try:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        # Declared types are required: an untyped call passes the 64-bit process handle as a 32-bit int,
        # fails with "invalid handle" and leaves every counter at 0 (seen in the first benchmark run).
        kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        counters = Counters(cb=ctypes.sizeof(Counters))
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return round(counters.PeakWorkingSetSize / 1e9, 2)
    except (AttributeError, OSError):
        return None


# Every 10 s, save the peak so far: if the run is stopped at the time limit, run_all.sh reports it.
PEAK_FILE = Path(f"{results}.{name}-{goal}.peak")
stop = threading.Event()


def _keep_peak():
    while not stop.wait(10):
        PEAK_FILE.write_text(json.dumps(peak_memory_gb()), encoding="utf-8")


threading.Thread(target=_keep_peak, daemon=True).start()

start = time.perf_counter()
row = {"dataset": name, "goal": goal, "python": platform.python_version(), "microplatform": mp.__version__}
try:
    view = mp.analyze(args["--counts"], args.get("--labels"), goal=goal, out_dir=out_dir, cache_dir=cache_dir,
                      metabolites=args.get("--metabolites"))
    total = time.perf_counter() - start
    record = view.record or {}
    pre = 0.0 if record.get("from_cache") else float(record.get("seconds", 0.0))
    row.update(status="done", total_s=round(total, 1), preprocessing_s=round(pre, 1),
               tool_s=round(total - pre, 1), from_cache=bool(record.get("from_cache")),
               samples=record.get("samples"), taxa=record.get("input_taxa"),
               features=record.get("output_features"),
               metabolites=view.metabolites.n_metabolites if view.metabolites else None)
except mp.UserFacingError as error:
    row.update(status="refused", message=error.message, total_s=round(time.perf_counter() - start, 1))
except MemoryError:
    row.update(status="out of memory", total_s=round(time.perf_counter() - start, 1))

row["peak_memory_gb"] = peak_memory_gb()
stop.set()
with Path(results).open("a", encoding="utf-8") as f:
    f.write(json.dumps(row) + "\n")
print(json.dumps(row))
