from __future__ import annotations
from dataclasses import *
from typing import *
from types import FunctionType, CellType, MethodType, CodeType
import pickle

from pbutils import p

P = ParamSpec('P')
R = TypeVar('R')

Fn: TypeAlias = Callable[..., Any]
FrozenId: TypeAlias = int
Cell: TypeAlias = Union[
    tuple[Any],
    None,
    Any, # Frozen
]
Frozen: TypeAlias = Union[
    # pickled builtin
    bytes,

    # function
    FrozenId,

    # bound method
    tuple[FrozenId, Any],

    # function with closure
    tuple[FrozenId, None, tuple[Cell, ...]]
]

_reg_co_to_id: dict[CodeType, FrozenId] = {}
_reg_id_to_fn: dict[FrozenId, Fn] = {}

def is_function(f: Any) -> TypeGuard[FunctionType]:
    return isinstance(getattr(f, '__code__', None), CodeType)

def frozen_id(f: Fn) -> FrozenId:
    co = f.__code__
    if co not in _reg_co_to_id:
        given_id = len(_reg_co_to_id)
        _reg_co_to_id[co] = given_id
        _reg_id_to_fn[given_id] = f
    return _reg_co_to_id[co]

def freeze(f: Fn, __seen : None | set[int] = None) -> Frozen:
    assert callable(f)
    if not is_function(f):
        # happens for builtins like print
        return pickle.dumps(f)
    if __seen is None:
        __seen = set()
    co = f.__code__
    if id(co) in __seen:
        raise ValueError(f'Cannot freeze recursive local function {f}')
    __seen.add(id(co))
    if hasattr(f, '__self__'):
        bound_self = getattr(f, '__self__', None)
        func = getattr(f, '__func__')
        return (frozen_id(func), bound_self)

    elif f.__closure__:
        closure: list[tuple[Any] | None | Frozen] = []
        for cell in f.__closure__:
            try:
                c = cell.cell_contents
            except:
                closure += [None]
                continue
            if is_function(c):
                closure += [freeze(c, __seen)]
            else:
                closure += [(c,)]
        return (frozen_id(f), None, tuple(closure))

    else:
        return frozen_id(f)

def _make_cell(co: Any) -> CellType:
    c = CellType()
    c.cell_contents = co
    return c

_empty_cell = CellType()

def thaw(frozen: Frozen) -> Fn:
    match frozen:
        case (i, bound_self):
            f = _reg_id_to_fn[i]
            return MethodType(f, bound_self)
        case (i, None, frozen_closure):
            closure: list[Any] = []
            for c in frozen_closure:
                match c:
                    case None:
                        closure += [_empty_cell]
                    case (v,):
                        closure += [_make_cell(v)]
                    case _:
                        closure += [_make_cell(thaw(c))]
            f = _reg_id_to_fn[i]
            return FunctionType(
                f.__code__,
                f.__globals__,
                f.__name__,
                None, # defaults
                tuple(closure)
            )
        case bytes(bs):
            return pickle.loads(bs)
        case i:
            f = _reg_id_to_fn[i]
            return FunctionType(
                f.__code__,
                f.__globals__,
                f.__name__,
                None, # defaults
            )

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

def G1(i: int):
    return i + 1

def G2(i: int):
    return i + 1 + __test

def test_freeze():
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

    tt = __Test(6)

    def H11() -> Callable[[int], int]:
        g = __Test(8).f
        h = G2
        return lambda i: g(i) + h(i) + __test

    def H12() -> Callable[[int], int]:
        g = lambda x: tt.f(x)
        h = lambda x: G2(x)
        return lambda i: g(i) + h(i) + __test

    f11 = H11()
    f12 = H12()

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

    f7s: list[Callable[[int], int]] = []
    for i in range(3):
        f7s += [(lambda o: lambda x=1: x+1+i+o)(i)]

    fs: list[Callable[[int], int]] = [
        G1, G2,
        f1,
        f11, f12,
        f2, f3, f4,
        f5,
        f6,
        *f7s,
        print, # type: ignore
        int.bit_count,
    ]

    for f in fs:
        f_frozen = freeze(f)
        f_frozen | p
        b = pickle.dumps(f_frozen)
        # b | p
        f_copy = thaw(pickle.loads(b))
        assert f.__name__ == f_copy.__name__
        assert getattr(f, '__module__', None) == getattr(f_copy, '__module__' , None)
        assert f(1) == f_copy(1)
        __test += 1
        # t.value += 1
        assert f(1) == f_copy(1)

    def G():
        def f(i: int) -> int:
            return 0 if i == 0 else f(i-1)
        return f

    f_err = G()
    import pytest
    with pytest.raises(ValueError) as exc:
        freeze(f_err)

    assert 'recursive' in exc.value.args[0]
