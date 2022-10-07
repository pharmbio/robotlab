from __future__ import annotations
from dataclasses import dataclass, field
from contextlib import contextmanager
import typing as t
import executing
import inspect
import ast
import re

@dataclass(frozen=False)
class Check:
    _tests: list[t.Callable[[], None]] = field(default_factory=list)

    def test(self, f: t.Callable[[], None]):
        if f.__module__ == '__main__':
            print(f.__name__ + ':')
            f()
        else:
            self._tests += [f]

    def run_tests(self, matching: str='.*'):
        for f in self._tests:
            name = f.__module__ + '.' + f.__name__
            if re.search(matching, name):
                print(name + ':')
                f()

    @staticmethod
    def red(s: str) -> str:
        return '\033[31m' + s + '\033[0m'

    @staticmethod
    def green(s: str) -> str:
        return '\033[32m' + s + '\033[0m'

    @contextmanager
    def expect_exception(self):
        try:
            yield
        except BaseException as e:
            print(Check.green('✔'), 'Excepted expected exception', type(e).__name__ + ':', str(e))
            return True
        else:
            print(Check.red('✗'), 'No exception raised!')
            assert False

    def __call__(self, e: bool):
        _, fr, *_ = inspect.getouterframes(inspect.currentframe())
        src: str = executing.Source.executing(fr.frame).text() # type: ignore
        lstr, _, rstr = src.removeprefix('check(').removesuffix(')').partition('==')
        rhs = eval(f'({rstr})', fr.frame.f_locals, fr.frame.f_globals)
        lstr = lstr.strip()
        rstr = rstr.strip()
        if e:
            try:
                rstr_val = ast.literal_eval(rstr)
            except:
                rstr_val = object()
            if rstr_val != rhs:
                print(Check.green('✔'), lstr, '==', rstr, '==', repr(rhs))
            else:
                print(Check.green('✔'), lstr, '==', rstr)
        else:
            print(Check.red('✗'), lstr, '!=', rstr)
            lhs = eval(f'({lstr})', fr.frame.f_locals, fr.frame.f_globals)
            print(' ', Check.red('·'), lstr, '==', repr(lhs))
            print(' ', Check.red('·'), rstr, '==', repr(rhs))
            assert False, f'{lstr} != {rstr} ({lhs!r} != {rhs!r})'
        return e

check = Check()
