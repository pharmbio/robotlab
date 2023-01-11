from __future__ import annotations
from typing import *
from dataclasses import *

from viable import store, js, call, Serve, Flask, Int, Str, Bool
from viable import Tag, div, span, label, button, pre
import viable as V

from pathlib import Path

from pbutils.mixins import DB, DBMixin

D = TypeVar('D')
R = TypeVar('R')
A = TypeVar('A')

@dataclass
class Intercept:
    last_attr: None | str = None
    def __getattr__(self, attr: str):
        self.last_attr = attr
        return self

@dataclass(frozen=True)
class Edit(Generic[D]):
    db_path: str | Path
    obj: D
    tabindexes: dict[str, int] | None = None
    enable_edit: bool = True
    echo: bool = False

    @property
    def attr(self) -> D:
        return Intercept() # type: ignore

    def __call__(self, attr: A, from_str: Callable[[str], A] = str, textarea: bool=False, enable_edit: bool = True) -> Tag:
        assert isinstance(intercept := attr, Intercept)
        field = intercept.last_attr
        assert field is not None
        if self.tabindexes is not None:
            if field not in self.tabindexes:
                self.tabindexes[field] = len(self.tabindexes) + 1
            tabindex = str(self.tabindexes.get(field, 0))
        else:
            tabindex = None
        value = getattr(self.obj, field)
        if not self.enable_edit or not enable_edit:
            if value:
                return div(
                    str(value),
                )
            else:
                return div()
        def update(next: str=js('this.value'), db_path: str | Path =self.db_path, obj: D=self.obj):
            next_conv = from_str(next)
            with DB.open(db_path) as db:
                ob = obj.reload(db)
                ob = ob.replace(**{field: next_conv}) # type: ignore
                ob.save(db)
        if textarea:
            inp = V.textarea(
                str(value),
                oninput=call(update),
                tabindex=tabindex,
            )
        else:
            inp = V.input(
                value=str(value),
                oninput=call(update, js('this.value')),
                width='100%',
                spellcheck='false',
                tabindex=tabindex,
                min_width=f'{len(str(value)) + 3}ch',
            )
        if self.echo:
            return div(
                div(
                    repr(value),
                    class_='echo',
                ),
                inp,
            )
        else:
            return inp


