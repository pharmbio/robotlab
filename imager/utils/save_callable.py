from __future__ import annotations
from dataclasses import dataclass
from types import FunctionType, CellType, MethodType
from typing import Any, Callable
import marshal
import sys

@dataclass(frozen=True, slots=True)
class Box:
    value: Any

@dataclass(frozen=True, slots=True)
class Function:
    marshalled_code: bytes
    module: str
    name: str
    defaults: Any
    closure: tuple[Box | Function, ...]
    kwdefaults: dict[str, Any]
    qualname: str
    has_self: bool
    bound_self: Any

    @staticmethod
    def freeze(f: Callable[..., Any]):
        closure: list[Box | Function] = []
        for cell in f.__closure__ or ():
            c = cell.cell_contents
            if hasattr(c, '__code__') and hasattr(c, '__closure__'):
                closure += [Function.freeze(c)]
            else:
                closure += [Box(c)]
        return Function(
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

    def thaw(self) -> Callable[..., Any]:
        code = marshal.loads(self.marshalled_code)
        g = sys.modules[self.module].__dict__
        closure: list[Any] = [
            Function._make_cell(c.thaw() if isinstance(c, Function) else c.value)
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

