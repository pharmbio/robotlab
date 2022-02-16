from __future__ import annotations
from dataclasses import *
from typing import *

from pprint import pformat

import re
import sys

from .nub import nub

A = TypeVar('A')

prims: tuple[Any, ...] = (int, float, bool, str, bytes, type(None))

def primlike(x: object) -> bool:
    if isinstance(x, (tuple, list, set, frozenset)):
        return False
        return all(map(primlike, x))
    else:
        return isinstance(x, prims)

def show_key(x: object) -> str:
    if isinstance(x, (str, int)):
        k = str(x)
        if re.match(r'\w+$', k):
            return k
    return repr(x)

def show(x: Any, show_key: Any=show_key, width: int=80, use_color: bool=sys.stdout.isatty(), sep: str='\n', indentchars: str='  ') -> str:
    color = Color(use_color)
    def go(dent: str, pre: str, x: Any, post: str) -> Iterator[str]:
        '''
        only yield (dent +) pre once,
        then yield indent for each subsequent line
        finally yield (dent/indent +) post
        '''
        indent = indentchars + dent
        is_tuple = isinstance(x, tuple)
        is_list = isinstance(x, list)
        is_set = isinstance(x, (set, frozenset))
        has_iter = hasattr(x, '__iter__')
        if isinstance(x, type):
            yield dent + pre + repr(x) + post
        elif is_dataclass(x):
            begin, end = color.none(x.__class__.__name__) + '(', ')'
            vals = nub(x)
            if len(vals) == 0:
                yield dent + pre + begin + end + post
            else:
                yield dent + pre + begin
                for k, v in vals.items():
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
        elif not primlike(x) and (is_tuple or is_list or is_set or has_iter):
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
            values: list[Any] = list(cast(Any, x))
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

    return sep.join(go('', '', x, ''))

def pr(x: A, sep: str='\n', indentchars: str='  ') -> A:
    print(show(x, sep=sep, indentchars=indentchars))
    return x

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
