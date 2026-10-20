"""API reference generated from the public API's signatures and docstrings.

Generated, not hand-written, so the documented API can never drift from the code.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass

# Constants have no docstring of their own.
_CONSTANTS = {
    "CANONICAL": "The canonical preprocessing settings (the MIPMLP paper's recommendation, at species level).",
    "GOALS": "The tasks the platform offers, each with its tool and required inputs.",
    "TOOLS": "The five tools: what each does and how to cite it.",
}


@dataclass(frozen=True)
class ApiEntry:
    name: str
    kind: str  # "function", "class" or "constant"
    signature: str
    summary: str  # the first paragraph of the docstring


def api_reference() -> list[ApiEntry]:
    import microplatform

    entries = []
    for name in microplatform.__all__:
        obj = getattr(microplatform, name)
        if name in _CONSTANTS:
            entries.append(ApiEntry(name, "constant", f"mp.{name}", _CONSTANTS[name]))
            continue
        kind = "class" if inspect.isclass(obj) else "function"
        entries.append(ApiEntry(name, kind, f"mp.{name}{_signature(obj)}", _first_paragraph(inspect.getdoc(obj))))
    return entries


def _signature(obj) -> str:
    from microplatform import CANONICAL

    try:
        sig = inspect.signature(obj, eval_str=True)  # real types instead of quoted strings
    except NameError:  # annotations that only exist for type checkers
        sig = inspect.signature(obj)
    text = str(sig).replace(repr(CANONICAL), "CANONICAL")
    text = re.sub(r": '([^']*)'", r": \1", text)  # quoted annotations, if any are left
    text = re.sub(r"\b(pathlib\._local|pathlib|pandas\.core\.\w+|pd|typing|microplatform(\.\w+)*)\.", "", text)
    if inspect.isclass(obj):
        text = text.removesuffix(" -> None")
    return text


def _first_paragraph(doc: str | None) -> str:
    return " ".join((doc or "").strip().split("\n\n")[0].split())
