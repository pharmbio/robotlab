from __future__ import annotations
from dataclasses import dataclass
from types import FunctionType, CellType, MethodType, CodeType
from typing import Any, Callable
import marshal
import sys

@dataclass(frozen=True, slots=True)
class Box:
    value: Any

@dataclass(frozen=True, slots=True)
class FrozenFunction:
    marshalled_code: bytes
    module: str
    name: str
    defaults: Any
    closure: tuple[Box | FrozenFunction, ...]
    kwdefaults: dict[str, Any]
    qualname: str
    has_self: bool
    bound_self: Any

    @staticmethod
    def freeze(f: Callable[..., Any], __seen: None | set[int] = None) -> FrozenFunction:
        if __seen is None:
            __seen = set()
        if id(f) in __seen:
            raise ValueError(f'Cannot freeze recursive local function {f}')
        __seen.add(id(f))
        closure: list[Box | FrozenFunction] = []
        for cell in f.__closure__ or ():
            c = cell.cell_contents
            if FrozenFunction.is_function(c):
                closure += [FrozenFunction.freeze(c, __seen)]
            else:
                closure += [Box(c)]
        return FrozenFunction(
            marshal.dumps(f.__code__),
            f.__module__,
            f.__name__,
            f.__defaults__,
            tuple(closure),
            f.__kwdefaults__,
            f.__qualname__,
            hasattr(f, '__self__'),
            getattr(f, '__self__', None),
        )

    @staticmethod
    def is_function(f: Any):
        return isinstance(getattr(f, '__code__', None), CodeType)

    def thaw(self) -> Callable[..., Any]:
        code = marshal.loads(self.marshalled_code)
        g = sys.modules[self.module].__dict__
        closure: list[Any] = [
            FrozenFunction._make_cell(c.thaw() if isinstance(c, FrozenFunction) else c.value)
            for c in self.closure
        ]
        f = FunctionType(code, g, self.name, self.defaults, tuple(closure))
        f.__kwdefaults__ = self.kwdefaults
        f.__qualname__ = self.qualname
        if self.has_self:
            return MethodType(f, self.bound_self)
        return f

    @staticmethod
    def _make_cell(co: Any) -> CellType:
        c = CellType()
        c.cell_contents = co
        return c

__test: int = 0

@dataclass
class __Test:
    value: int = 8
    def f(self, i: int):
        return i + self.value

@dataclass
class __TestCallable:
    def __call__(self, i: int):
        return i + 1

def main():
    import pickle

    global __test

    def H1(xs: list[int]) -> Callable[[int], int]:
        def inner(i: int):
            return sum(xs) + i
        return lambda a: a + __test + inner(a)

    def H2(xs: list[int]) -> Callable[[int], int]:
        def inner(i: int):
            return sum(xs) + i
        def outer(a: int, b: int = 4, *, c: int = 9):
            return a + __test + inner(a)
        return outer

    def f1(i: int):
        def g(j: int):
            return j + i + __test
        def h(j: int):
            return g(j) + i + __test
        return g(i) + h(i) + __test

    f2 = H1([4, 5, 6])
    f3 = H2([4, 5, 6])
    f3: Callable[[int], int] = lambda y: __test + y

    def f4(i: int):
        return i + __test

    t = __Test(7)
    f5 = t.f

    def H3():
        f = __TestCallable()
        g = __Test().f
        def h(i: int) -> int:
            return f(i) + g(i)
        return h

    f6 = H3()

    f7: Callable[[int], int] = lambda x=1: x+1

    fs: list[Callable[[int], int]] = [f1, f2, f3, f4, f5, f6, f7]

    def assert_same(x: Any, y: Any):
        print(x, y)
        assert x == y

    for f in fs:
        b = FrozenFunction.freeze(f)
        f_copy = b.thaw()
        print(f.__name__, f_copy.__name__)
        print(f.__module__, f_copy.__module__)
        print(f.__qualname__, f_copy.__qualname__)
        print(f(1), f_copy(1))
        __test += 1
        t.value += 1
        print(f(1), f_copy(1))
        print('bytes:', len(pickle.dumps(b)))
        print('---')

    def G():
        def f(i: int) -> int:
            return 0 if i == 0 else f(i-1)
        return f

    f_err = G()
    try:
        FrozenFunction.freeze(f_err)
    except ValueError as e:
        print('OK, expected failure:', e)
    else:
        raise ValueError

if __name__ == '__main__':
    main()
