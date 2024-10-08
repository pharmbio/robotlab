
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
import time

import functools

A = TypeVar('A')
B = TypeVar('B')
P = ParamSpec('P')
R = TypeVar('R')

class dotdict(Generic[A, B], dict[A, B]):
    __getattr__ = dict.__getitem__ # type: ignore
    __setattr__ = dict.__setitem__ # type: ignore
    __delattr__ = dict.__delitem__ # type: ignore

@dataclass(frozen=True, eq=False, order=False)
class Hide(Generic[A]):
    value: A
    def __eq__(self, other: object) -> bool:
        return True

    def __lt__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0

def cache_by(key: Callable[[A], Any]) -> Callable[[Callable[[A], R]], Callable[[A], R]]:
    def inner(f: Callable[[A], R]) -> Callable[[A], R]:
        @functools.cache
        def C(k: Any, v: Hide[A]) -> R:
            return f(v.value)

        @functools.wraps(f)
        def F(v: A) -> R:
            return C(key(v), Hide(v))
        return F
    return inner

def test_cache_by():
    log: list[Any] = []
    @cache_by(lambda x: str(x))
    def fn(x: int):
        log.append(x)
        return x + 1

    assert log == []
    assert fn(1) == 2
    assert log == [1]
    assert fn(1) == 2
    assert log == [1]

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

def throttle(rate_limit_secs: float):
    def inner(f: Callable[P, R]) -> Callable[P, R]:
        last_args: Any = None
        last_called = 0
        last_result: R = cast(Any, None)
        rlock = threading.RLock()

        @functools.wraps(f)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            nonlocal last_called, last_result, last_args
            with rlock:
                elapsed = time.monotonic() - last_called

                current_args = (args, kwargs)

                if elapsed >= rate_limit_secs:
                    last_args = current_args
                    last_result = f(*args, **kwargs)
                    last_called = time.monotonic()
                else:
                    if last_args != current_args:
                        raise ValueError('throttle does not support changing arguments. {last_args=} {current_args=}')

                return last_result

        return wrapper
    return inner

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
    return datetime.now().replace(microsecond=0).isoformat(sep='_').replace(':', '.')

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

def test_iterate():
    assert iterate_with_full_context([1,2,3,4]) == [
        ([], 1, [2, 3, 4]),
        ([1], 2, [3, 4]),
        ([1, 2], 3, [4]),
        ([1, 2, 3], 4, []),
    ]

    assert iterate_with_context([1,2,3,4]) == [
        (None, 1, 2),
        (1, 2, 3),
        (2, 3, 4),
        (3, 4, None)
    ]


def git_HEAD() -> str | None:
    from subprocess import run
    try:
        proc = run(['git', 'rev-parse', 'HEAD'], capture_output=True)
        return proc.stdout.decode().strip()[:12]
    except:
        return None

from datetime import timedelta
import math

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
    if math.isnan(seconds):
        return 'NaN'
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

@dataclass(frozen=True)
class PP:
    show: Literal['data', 'methods', 'dir', 'self'] = 'self'

    hooks: list[Callable[[Any], bool]] = field(default_factory=list)

    @property
    def dir(self):
        return replace(self, show='dir')

    @property
    def methods(self):
        return replace(self, show='methods')

    @property
    def data(self):
        return replace(self, show='data')

    def __call__(self, thing: A) -> A:
        from pprint import pformat
        import executing
        import inspect
        import re
        import textwrap
        from pathlib import Path
        frames = inspect.getouterframes(inspect.currentframe())
        for fr in frames:
            if fr.filename != __file__:
                break
        else:
            return thing
        src: str = executing.Source.executing(fr.frame).text() # type: ignore
        src = re.sub(r'\s*\|\s*p\s*$', '', src, flags=re.MULTILINE)
        src = re.sub(r'^\s*p\s*\|\s*', '', src, flags=re.MULTILINE)
        x = thing
        if self.show != 'self':
            x = {
                k: (
                    catch(lambda: f'{inspect.signature(v)}\n', '') + (v.__doc__ or '').strip().split('\n\n')[0]
                    if self.show == 'methods' else
                    v
                )
                for k in dir(x)
                if k != '__dict__'
                for v in [getattr(x, k)]
                if self.show == 'dir'
                or self.show == 'methods' and callable(v)
                or self.show == 'data' and not callable(v)
            }
        for hook in self.hooks:
            if hook(x):
                return thing
        fmt = pformat(x)
        try:
            filename = Path(fr.filename).relative_to(Path.cwd())
        except:
            filename = fr.filename
        if len(fmt) < 40 and '\n' not in fmt:
            print(f'{filename}:{fr.lineno}:{src} = {fmt}')
        else:
            print(f'{filename}:{fr.lineno}:{src} =\n{textwrap.indent(fmt, "  ")}')
        return thing

    def __or__(self, thing: A) -> A:
        self(thing)
        return thing

    def __ror__(self, thing: A) -> A:
        self(thing)
        return thing

p = PP()

def TODO(*args: Any) -> None:
    from pathlib import Path
    import inspect
    _, fr, *_ = inspect.getouterframes(inspect.currentframe())
    try:
        filename = Path(fr.filename).relative_to(Path.cwd())
    except:
        filename = fr.filename
    header = f'{filename}:{fr.lineno}:{fr.function}:'
    return _TODO(header, *args)

@functools.cache
def _TODO(*args: Any) -> None:
    import sys
    print(Color().red('TODO:'), *args, file=sys.stderr)
