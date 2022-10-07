from __future__ import annotations
from dataclasses import *
import typing as t
from contextlib import contextmanager
import executing
import inspect
import ast
import sys

@dataclass(frozen=False)
class Check:
    _reached_main: bool = False

    def test(self, f: t.Callable[[], None]):
        from_main = f.__module__ == '__main__'
        if from_main or '--check-tests' in sys.argv:
            if f.__module__ == '__main__':
                print(f.__name__ + ':')
            else:
                print(f.__module__ + '.' + f.__name__ + ':')
            self._reached_main = True
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
