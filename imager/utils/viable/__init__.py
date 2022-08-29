from __future__ import annotations

from .minifier import minify
from .tags import *
from .core import (
    Node,    # type: ignore
    js,      # type: ignore
    Exposed, # type: ignore
    app,     # type: ignore
    Serve,   # type: ignore
    serve,   # type: ignore
)

def queue_refresh(after_ms: float=100):
    js = minify(f'''
        clearTimeout(window._qrt)
        window._qrt = setTimeout(
            () => requestAnimationFrame(() => refresh()),
            {after_ms}
        )
    ''')
    return script(raw(js), eval=True)

def trim(s: str, soft: bool=False, sep: str=' '):
    import textwrap
    if soft:
        return textwrap.dedent(s).strip()
    else:
        return re.sub(r'\s*\n\s*', sep, s, flags=re.MULTILINE).strip()

