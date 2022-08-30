from __future__ import annotations
from functools import lru_cache
import sys
from typing import ContextManager
from contextlib import contextmanager
import time

def timeit(desc: str='') -> ContextManager[None]:
    # The inferred type for the decorated function is wrong hence this wrapper to get the correct type

    @contextmanager
    def worker():
        e = None
        t0 = time.monotonic()
        try:
            yield
        except Exception as exn:
            e = exn
        T = time.monotonic() - t0
        if e:
            print(f'{T:.3f}', desc, repr(e))
            raise e
        else:
            print(f'{T:.3f}', desc)

    return worker()

@lru_cache
def minify_string() -> Callable[[str, str], str]:
    try:
        import minify
        return minify.string
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
    with timeit():
        return minify_string()(loader, s)
