from __future__ import annotations

from .minifier import minify
from .tags import *
from .core import (
    Node,    # type: ignore
    JS,      # type: ignore
    app,     # type: ignore
    Serve,   # type: ignore
    serve,   # type: ignore
    call,    # type: ignore
    js,      # type: ignore
)

from .check import check

def queue_refresh(after_ms: float=100):
    js = minify(f'''
        clearTimeout(window._qrt)
        window._qrt = setTimeout(
            () => requestAnimationFrame(() => refresh()),
            {after_ms}
        )
    ''')
    return script(raw(js), eval=True)

