from __future__ import annotations

from .core import (
    Serve,   # type: ignore
)
from .call_js import (
    JS,      # type: ignore
    js,      # type: ignore
    Action,  # type: ignore
)
from .provenance import (
    store, # type: ignore
    call,  # type: ignore
    Var,   # type: ignore
    Int,   # type: ignore
    Str,   # type: ignore
    Bool,  # type: ignore
)
from .tags import *
import flask
Flask = flask.Flask # reexport

def queue_refresh(after_ms: float=100):
    assert str(after_ms).isdigit()
    return script(f'queue_refresh({after_ms})', eval=True)

