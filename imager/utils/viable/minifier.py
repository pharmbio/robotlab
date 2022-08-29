from __future__ import annotations
from functools import lru_cache
from subprocess import run
import shutil
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

def minify(s: str, loader: str='js') -> str:
    s = s.strip()
    if loader == 'js' and '\n' not in s:
        return s
    elif esbuild_missing():
        return s
    else:
        return minify_nontrivial(s, loader)

@lru_cache
def esbuild_missing():
    if shutil.which("esbuild") is None:
        print('esbuild not found, skipping minifying', file=sys.stderr)
        return True
    else:
        return False

@lru_cache
def minify_nontrivial(s: str, loader: str='js') -> str:
    try:
        with timeit(f'esbuild {loader}'):
            res = run(
                ['esbuild', '--minify', f'--loader={loader}'],
                capture_output=True, input=s, encoding='utf-8'
            )
            if res.stderr:
                print(loader, s, res.stderr, file=sys.stderr)
                return s
            # print(f'minify({s[:80]!r}, {loader=})\n  = {res.stdout[:80]!r}')
            return res.stdout.strip()
    except:
        return s
