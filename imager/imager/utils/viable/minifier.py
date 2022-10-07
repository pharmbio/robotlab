from __future__ import annotations
from functools import lru_cache
import sys
from typing import Callable

@lru_cache
def minify_string() -> Callable[[str, str], str]:
    try:
        import minify           # type: ignore
        return minify.string    # type: ignore
    except Exception as e:
        print('Not using tdewolff-minify:', str(e), file=sys.stderr)
        return lambda _, s: s

def minify(s: str, loader: str='js') -> str:
    if loader in ('js', 'javascript'):
        loader = 'application/javascript'
    elif loader in ('html', 'css'):
        loader = 'text/' + loader
    else:
        print('???', loader)
        return(s)
    return minify_string()(loader, s)
