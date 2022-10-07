
from __future__ import annotations
from dataclasses import *
from typing import *

from collections import defaultdict

from datetime import datetime
import threading

from .serializer import Serializer, serializer, from_json, to_json # type: ignore
from .nub import nub # type: ignore
from .pp import show, pr, Color # type: ignore
from .profiling import timeit, memit # type: ignore
from .args import doc_header # type: ignore

import json
from urllib.request import urlopen, Request

from viable import check

A = TypeVar('A')
B = TypeVar('B')

def curl(url: str) -> Any:
    ten_minutes = 60 * 10
    res = json.loads(urlopen(url, timeout=ten_minutes).read())
    return res

def post_json(url: str, data: dict[str, Any]) -> dict[str, Any]:
    ten_minutes = 60 * 10
    req = Request(
        url,
        data=json.dumps(data).encode(),
        headers={'Content-type': 'application/json'},
    )
    res = json.loads(urlopen(req, timeout=ten_minutes).read())
    return res

def spawn(f: Callable[[], None]) -> None:
    threading.Thread(target=f, daemon=True).start()

def group_by(xs: Iterable[A], key: Callable[[A], B]) -> defaultdict[B, list[A]]:
    d: dict[B, list[A]] = defaultdict(list)
    for x in xs:
        d[key(x)] += [x]
    return d

def uniq(xs: Iterable[A]) -> Iterable[A]:
    return {x: None for x in xs}.keys()

def flatten(xss: Iterable[list[A]]) -> list[A]:
    return sum(xss, cast(list[A], []))

def catch(m: Callable[[], A], default: B) -> A | B:
    try:
        return m()
    except:
        return default

@dataclass(frozen=False)
class Mutable(Generic[A]):
    value: A
    @classmethod
    def factory(cls, x: A):
        return field(default_factory=lambda: cls(x))

    @classmethod
    def init(cls, f: Callable[[], A]):
        return field(default_factory=lambda: cls(f()))

def read_commasep(s: str, p: Callable[[str], A] = lambda x: x) -> list[A]:
    return [p(x.strip()) for x in s.strip().split(',') if x.strip()]

def now_str_for_filename() -> str:
    return str(datetime.now()).split('.')[0].replace(' ', '_')

def iterate_with_full_context(xs: Iterable[A]) -> list[tuple[list[A], A, list[A]]]:
    xs = list(xs)
    return [
        (xs[:i], x, xs[i+1:])
        for i, x in enumerate(xs)
    ]

def iterate_with_context(xs: Iterable[A]) -> list[tuple[A | None, A, A | None]]:
    return [
        (prev[-1] if prev else None, x, next[0] if next else None)
        for prev, x, next in iterate_with_full_context(xs)
    ]

def iterate_with_next(xs: Iterable[A]) -> list[tuple[A, A | None]]:
    return [
        (x, next)
        for _, x, next in iterate_with_context(xs)
    ]

def iterate_with_prev(xs: Iterable[A]) -> list[tuple[A | None, A]]:
    return [
        (prev, x)
        for prev, x, _ in iterate_with_context(xs)
    ]

@check.test
def iterate_tests():
    check(iterate_with_full_context([1,2,3,4]) == [
        ([], 1, [2, 3, 4]),
        ([1], 2, [3, 4]),
        ([1, 2], 3, [4]),
        ([1, 2, 3], 4, []),
    ])

    check(iterate_with_context([1,2,3,4]) == [
        (None, 1, 2),
        (1, 2, 3),
        (2, 3, 4),
        (3, 4, None)
    ])

def git_HEAD() -> str | None:
    from subprocess import run
    try:
        proc = run(['git', 'rev-parse', 'HEAD'], capture_output=True)
        return proc.stdout.decode().strip()[:8]
    except:
        return None

from datetime import timedelta

def pp_secs(seconds: int | float) -> str:
    '''
    Pretty-print seconds.

    >>> pp_secs(0)
    '0.0'
    >>> pp_secs(0.1)
    '0.1'
    >>> pp_secs(0.09)
    '0.0'
    >>> pp_secs(60)
    '1:00.0'
    >>> pp_secs(3600)
    '1:00:00.0'
    >>> pp_secs(3600 + 60 * 2 + 3 + 0.4)
    '1:02:03.4'
    >>> pp_secs(3600 * 24 - 0.1)
    '23:59:59.9'
    >>> pp_secs(3600 * 24)
    '1 day, 0:00:00.0'
    >>> pp_secs(-0)
    '0.0'
    >>> pp_secs(-0.1)
    '-0.1'
    >>> pp_secs(-0.09)
    '-0.0'
    >>> pp_secs(-60)
    '-1:00.0'
    >>> pp_secs(-3600)
    '-1:00:00.0'
    >>> pp_secs(-(3600 + 60 * 2 + 3 + 0.4))
    '-1:02:03.4'
    >>> pp_secs(-(3600 * 24 - 0.1))
    '-23:59:59.9'
    >>> pp_secs(-(3600 * 24))
    '-1 day, 0:00:00.0'
    '''
    if seconds < 0:
        return '-' + pp_secs(-seconds)
    s = str(timedelta(seconds=float(seconds)))
    s = s.lstrip('0:')
    if not s:
        s = '0'
    if s.startswith('.'):
        s = '0' + s
    if '.' in s:
        pre, post = s.split('.')
        return pre + '.' + post[:1]
    else:
        return s + '.0'

def round_nnz(x: float, ndigits: int=1) -> float:
    '''
    Round and normalize negative zero
    '''
    v = round(x, ndigits)
    if v == -0.0:
        return 0.0
    else:
        return v

def zip_with(f: Callable[[float, float], float], xs: list[float], ys: list[float], ndigits: int=1) -> list[float]:
    return [round_nnz(f(a, b), ndigits=ndigits) for a, b in zip(xs, ys)]

def zip_sub(xs: list[float], ys: list[float], ndigits: int=1) -> list[float]:
    return zip_with(lambda a, b: a - b, xs, ys, ndigits=ndigits)

def zip_add(xs: list[float], ys: list[float], ndigits: int=1) -> list[float]:
    return zip_with(lambda a, b: a + b, xs, ys, ndigits=ndigits)

class PP:
    def __call__(self, thing: A) -> A:
        from pprint import pp
        pp(thing)
        return thing

    def __or__(self, thing: A) -> A:
        self(thing)
        return thing

    def __ror__(self, thing: A) -> A:
        self(thing)
        return thing

p = PP()
