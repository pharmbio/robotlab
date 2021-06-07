from __future__ import annotations
from dataclasses import *
from typing import *

from pprint import pformat
import re
import sys

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
            oneline: str | None = ''
            for v in values:
                if oneline is None:
                    break
                for out in go('', '', v, ', '):
                    if oneline is None:
                        break
                    oneline += out
                    if len(oneline) > 2 * width:
                        # oops lengths are totally wrong because of escape codes
                        # idea: use textwrap.fill if all values are primitive
                        oneline = None
                        break
            if len(values) == 0:
                yield dent + pre + begin + end + post
            elif oneline is not None and len(dent) + len(oneline) < 2 * width:
                yield dent + pre + begin + oneline[:-2] + end + post
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

def flatten(xss: Iterable[list[A]]) -> list[A]:
    return sum(xss, cast(list[A], []))

@dataclass(frozen=False)
class Mutable(Generic[A]):
    value: A
    @classmethod
    def factory(cls, x: A):
        return field(default_factory=lambda: cls(x))


def skip(n: int, xs: Iterable[A]) -> Iterable[A]:
    for i, x in enumerate(xs):
        if i >= n:
            yield x

def iterate_with_context(xs: list[A]) -> list[tuple[A | None, A, A | None]]:
    return [
        (xs[i-1] if i > 0 else None, x, xs[i+1] if i+1 < len(xs) else None)
        for i, x in enumerate(xs)
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

@dataclass
class Color:
    enabled: bool = True

    def do(self, code: str, s: str) -> str:
        if self.enabled:
            reset: str = '\033[0m'
            return code + s + reset
        else:
            return s

    def none       (self, s: str) -> str: return s
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

