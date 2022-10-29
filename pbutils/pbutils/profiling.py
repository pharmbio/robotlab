from __future__ import annotations
from typing import *

from collections import defaultdict
from contextlib import contextmanager

import time
import sys

def timeit(desc: str='') -> ContextManager[None]:
    # The inferred type for the decorated function is wrong hence this wrapper to get the correct type

    @contextmanager
    def worker():
        print(f'{desc}...', end='', file=sys.stderr, flush=True)
        e = None
        t0 = time.monotonic()
        try:
            yield
        except Exception as exn:
            e = exn
        T = time.monotonic() - t0
        print(f' ({T:.3f}s)', file=sys.stderr, flush=True)
        if e:
            print(f'{T:.3f}', desc, repr(e))
            raise e
        else:
            print(f'{T:.3f}', desc)

    return worker()

import os
import subprocess

def rss(pid: int = os.getpid()):
    bs = subprocess.check_output(f'ps --no-headers -e -o rss -q {pid}'.split())
    return int(bs)

def memstamp(desc: str='', last_of: dict[str, int] = defaultdict(int)):
    import gc
    a = last_of[desc]
    b = last_of[desc] = rss()
    print(f'{desc: <12} {b: >9} {b-a: >9}', len(gc.get_objects()))

def memit(desc: str='') -> ContextManager[None]:
    # The inferred type for the decorated function is wrong hence this wrapper to get the correct type
    import gc

    @contextmanager
    def worker():
        a = rss()
        yield
        b = rss()
        print(f'{desc: <12} {a: >9} {b: >9} {b-a: >9}', len(gc.get_objects()))

    return worker()

