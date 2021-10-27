from __future__ import annotations
from dataclasses import *
from typing import *

from collections import defaultdict
from pprint import pformat
import re
import sys
import json

prims: tuple[Any, ...] = (int, float, bool, str, bytes, type(None))

try:
    import pandas as pd # type: ignore
    prims = (*prims, pd.DataFrame, pd.Series) # type: ignore
except:
    pass

def primlike(x: object) -> bool:
    if isinstance(x, (tuple, list, set, frozenset)):
        return False
        return all(map(primlike, x))
    else:
        return isinstance(x, prims)

def show_key(x: object) -> str:
    if isinstance(x, (str, int)):
        k = str(x)
        if re.match(r'\w*$', k):
            return k
    return repr(x)

def show(x: Any, show_key: Any=show_key, width: int=80, use_color: bool=sys.stdout.isatty()) -> str:
    color = Color(use_color)
    def go(dent: str, pre: str, x: Any, post: str) -> Iterator[str]:
        '''
        only yield (dent +) pre once,
        then yield indent for each subsequent line
        finally yield (dent/indent +) post
        '''
        indent = '  ' + dent
        is_tuple = isinstance(x, tuple)
        is_list = isinstance(x, list)
        is_set = isinstance(x, (set, frozenset))
        has_iter = hasattr(x, '__iter__')
        if is_dataclass(x):
            begin, end = color.none(x.__class__.__name__) + '(', ')'
            if len(fields(x)) == 0:
                yield dent + pre + begin + end + post
            else:
                yield dent + pre + begin
                for field in fields(x):
                    k = field.name
                    v = getattr(x, k)
                    yield from go(indent, color.none(show_key(k)) + '=', v, ',')
                yield dent + end + post
        elif isinstance(x, dict):
            x = cast(dict[Any, Any], x)
            if len(x) == 0:
                yield dent + pre + '{}' + post
            else:
                yield dent + pre + '{'
                for k, v in x.items():
                    yield from go(indent, color.none(show_key(k)) + ': ', v, ',')
                yield dent + '}' + post
        elif (is_tuple or is_list or is_set or has_iter) and not primlike(x):
            if is_list:
                begin, end = '[', ']'
            elif is_tuple:
                begin, end = '(', ')'
            elif is_set:
                begin, end = '{', '}'
            elif has_iter:
                begin, end = '*(', ')'
            else:
                raise ValueError
            values = list(x)
            if len(values) == 0:
                yield dent + pre + begin + end + post
            else:
                yield dent + pre + begin
                for v in values:
                    yield from go(indent, '', v, ',')
                yield dent + end + post
        else:
            # use pformat for all primlike and exotic values
            lines = pformat(
                x,
                sort_dicts=False,
                width=max(width-len(indent), 1),
            ).split('\n')
            if len(lines) == 1:
                if isinstance(x, str):
                    yield dent + pre + color.green(lines[0]) + post
                elif isinstance(x, (bool, type(None))):
                    yield dent + pre + color.purple(lines[0]) + post
                elif isinstance(x, (int, float)):
                    yield dent + pre + color.lightred(lines[0]) + post
                else:
                    yield dent + pre + lines[0] + post
            else:
                *init, last = lines
                yield dent + pre
                for line in init:
                    yield indent + line
                yield indent + last + post


    return '\n'.join(go('', '', x, ''))

A = TypeVar('A')
B = TypeVar('B')

def pr(x: A) -> A:
    print(show(x))
    return x

@dataclass(frozen=False)
class Mutable(Generic[A]):
    value: A
    @classmethod
    def factory(cls, x: A):
        return field(default_factory=lambda: cls(x))

    @classmethod
    def init(cls, f: Callable[[], A]):
        return field(default_factory=lambda: cls(f()))

@dataclass
class Color:
    enabled: bool = True

    def do(self, code: str, s: str) -> str:
        if self.enabled:
            reset: str = '\033[0m'
            return code + s + reset
        else:
            return s

    def none       (self, s: str) -> str: return self.do('', '') + s
    def black      (self, s: str) -> str: return self.do('\033[30m', s)
    def red        (self, s: str) -> str: return self.do('\033[31m', s)
    def green      (self, s: str) -> str: return self.do('\033[32m', s)
    def orange     (self, s: str) -> str: return self.do('\033[33m', s)
    def blue       (self, s: str) -> str: return self.do('\033[34m', s)
    def purple     (self, s: str) -> str: return self.do('\033[35m', s)
    def cyan       (self, s: str) -> str: return self.do('\033[36m', s)
    def lightgrey  (self, s: str) -> str: return self.do('\033[37m', s)
    def darkgrey   (self, s: str) -> str: return self.do('\033[90m', s)
    def lightred   (self, s: str) -> str: return self.do('\033[91m', s)
    def lightgreen (self, s: str) -> str: return self.do('\033[92m', s)
    def yellow     (self, s: str) -> str: return self.do('\033[93m', s)
    def lightblue  (self, s: str) -> str: return self.do('\033[94m', s)
    def pink       (self, s: str) -> str: return self.do('\033[95m', s)
    def lightcyan  (self, s: str) -> str: return self.do('\033[96m', s)

@dataclass(frozen=True)
class test(Generic[A]):
    lhs: A
    def __eq__(self, rhs: A) -> bool:
        if self.lhs == rhs:
            return True
        else:
            print(show(self.lhs))
            print('!=', show(rhs))
            return False

def flatten(xss: Iterable[list[A]]) -> list[A]:
    return sum(xss, cast(list[A], []))

def skip(n: int, xs: Iterable[A]) -> Iterable[A]:
    for i, x in enumerate(xs):
        if i >= n:
            yield x

def iterate_with_full_context(xs: list[A]) -> list[tuple[list[A], A, list[A]]]:
    '''
    >>>
    '''
    return [
        (xs[:i], x, xs[i+1:])
        for i, x in enumerate(xs)
    ]

assert test(iterate_with_full_context([1,2,3,4])) == [
  ([], 1, [2, 3, 4]),
  ([1], 2, [3, 4]),
  ([1, 2], 3, [4]),
  ([1, 2, 3], 4, []),
]

def iterate_with_context(xs: list[A]) -> list[tuple[A | None, A, A | None]]:
    return [
        (prev[-1] if prev else None, x, next[0] if next else None)
        for prev, x, next in iterate_with_full_context(xs)
    ]

assert test(iterate_with_context([1,2,3,4])) == [
    (None, 1, 2),
    (1, 2, 3),
    (2, 3, 4),
    (3, 4, None)
]

def iterate_with_next(xs: list[A]) -> list[tuple[A, A | None]]:
    return [
        (x, next)
        for _, x, next in iterate_with_context(xs)
    ]

def iterate_with_prev(xs: list[A]) -> list[tuple[A | None, A]]:
    return [
        (prev, x)
        for prev, x, _ in iterate_with_context(xs)
    ]

def partition(cs: Iterable[A], by: Callable[[A], bool]) -> tuple[list[A], list[A]]:
    y: list[A]
    n: list[A]
    y, n = [], []
    for c in cs:
        if by(c):
            y += [c]
        else:
            n += [c]
    return y, n

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

def catch(m: Callable[[], A], default: B=None) -> A | B:
    try:
        return m()
    except:
        return default

def git_HEAD() -> str | None:
    from subprocess import run
    try:
        proc = run(['git', 'rev-parse', 'HEAD'], capture_output=True)
        return proc.stdout.decode().strip()[:8]
    except:
        return None

def uniq(xs: Iterable[A]) -> Iterable[A]:
    return {x: None for x in xs}.keys()

def read_json_lines(path: str) -> Iterator[Any]:
    with open(path, 'r') as f:
        for line in f:
            yield json.loads(line)

def group_by(xs: list[A], key: Callable[[A], B]) -> dict[B, list[A]]:
    d: dict[B, list[A]] = defaultdict(list)
    for x in xs:
        d[key(x)] += [x]
    return d

import tty
import termios
import atexit
def getchar():
    '''
    Returns a single character from standard input

    https://gist.github.com/jasonrdsouza/1901709
    '''

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    def cleanup():
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    atexit.register(cleanup)
    try:
        tty.setcbreak(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        atexit.unregister(cleanup)
        cleanup()
    return ch

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

from contextlib import contextmanager
import time
def timeit(desc: str='') -> ContextManager[None]:
    # The inferred type for the decorated function is wrong hence this wrapper to get the correct type

    @contextmanager
    def worker():
        t0 = time.monotonic()
        yield
        T = time.monotonic() - t0
        print(pp_secs(T), desc)

    return worker()

from datetime import datetime

def now_str_for_filename() -> str:
    return str(datetime.now()).split('.')[0].replace(' ', '_')
