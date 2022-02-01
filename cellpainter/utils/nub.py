from __future__ import annotations
from dataclasses import *
from typing import *

def nub(x: Any) -> dict[str, Any]:
    assert is_dataclass(x)
    out: dict[str, Any] = {}
    for f in fields(x):
        a = getattr(x, f.name)
        if (
            isinstance(a, dict | set | list)
            and not a
            and f.default_factory is not MISSING
            and not f.default_factory()
        ):
            continue
        if a != f.default:
            out[f.name] = a
    return out
