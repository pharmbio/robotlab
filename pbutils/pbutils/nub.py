from __future__ import annotations
from dataclasses import *
from typing import *
from functools import cache

def asdict_shallow(x: Any) -> dict[str, Any]:
    assert is_dataclass(x)
    return {
        f.name: getattr(x, f.name)
        for f in fields(x)
    }

@cache
def empty_default_factory(f: Field[Any]):
    if f.default is not MISSING:
        return not bool(f.default)
    elif f.default_factory is not MISSING:
        return not f.default_factory()
    else:
        return True

def nub(x: Any) -> dict[str, Any]:
    assert is_dataclass(x)
    out: dict[str, Any] = {}
    for f in fields(x):
        a = getattr(x, f.name)
        if (
            isinstance(a, dict | set | list)
            and not a
            and empty_default_factory(f)
        ):
            continue
        if a != f.default:
            out[f.name] = a
    return out
