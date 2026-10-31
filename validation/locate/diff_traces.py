"""Diagnostic: compare two trace_steps.py outputs and show the first event that differs.
The original also calls the discriminator's Adam.step with no gradients (a no-op); those events
are set aside (and counted) so the remaining events can be compared one to one.
Usage: python diff_traces.py <trace A> <trace B>"""

import re
import sys


def events(path):
    rows = [re.sub(r"^\s*\d+ ", "", line.rstrip()) for line in open(path, encoding="utf-8") if line.strip()]
    empty = [r for r in rows if "n_params=4 grads=0" in r]
    return [r for r in rows if "n_params=4 grads=0" not in r], empty


a, empty_a = events(sys.argv[1])
b, empty_b = events(sys.argv[2])
print(f"A: {len(a)} events, plus {len(empty_a)} empty discriminator steps "
      f"(parameters never changed: {len(set(empty_a)) <= 1})")
print(f"B: {len(b)} events, plus {len(empty_b)} empty discriminator steps")
first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
if first is None:
    print("no difference in the", min(len(a), len(b)), "events compared" +
          ("" if len(a) == len(b) else f"; lengths differ ({len(a)} vs {len(b)})"))
else:
    print("first difference at event", first)
    for i in range(max(0, first - 4), min(first + 4, max(len(a), len(b)))):
        mark = "!!" if i < len(a) and i < len(b) and a[i] != b[i] else "  "
        print(f"{mark}{i:5} A: {a[i] if i < len(a) else '-'}")
        print(f"         B: {b[i] if i < len(b) else '-'}")
