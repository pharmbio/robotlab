from __future__ import annotations
from dataclasses import *
from typing import *

from pprint import pformat
import re

import color

prims: tuple[Any, ...] = (int, float, bool, str, bytes, type(None))

try:
    import pandas as pd # type: ignore
    prims = (*prims, pd.DataFrame, pd.Series)
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

def show(x: Any, show_key: Any=show_key, width: int=80) -> str:

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

def pr(x: A) -> A:
    print(show(x))
    return x

def flatten(xss: Iterable[list[A]]) -> list[A]:
    return sum(xss, cast(list[A], []))

@dataclass(frozen=False)
class Mutable(Generic[A]):
    value: A

def skip(n: int, xs: Iterable[A]) -> Iterable[A]:
    for i, x in enumerate(xs):
        if i >= n:
            yield x

def context(xs: Iterable[A]) -> list[tuple[A | None, A, A | None]]:
    return list(zip(
        [None, None] + xs,        # type: ignore
        [None] + xs + [None],     # type: ignore
        xs + [None, None]))[1:-1] # type: ignore

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

