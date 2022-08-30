from __future__ import annotations
from typing import TypeVar, Callable, Literal, Generic, Any
from dataclasses import dataclass, field, replace

from collections import defaultdict
from contextlib import contextmanager
from flask import after_this_request, jsonify, request, g
from flask.wrappers import Response
from werkzeug.local import LocalProxy
import abc
import json

from . import js, serve, input
from . import tags as V
from .db_con import get_viable_db

def get_store() -> Store:
    if not g.get('viable_stores'):
        g.viable_stores = [Store()]
    return g.viable_stores[-1]

@contextmanager
def _focus_store(s: Store):
    assert g.viable_stores
    g.viable_stores.append(s)
    yield
    res = g.viable_stores.pop()
    assert res is s

store: Store = LocalProxy(get_store) # type: ignore

A = TypeVar('A')
B = TypeVar('B')
def None_map(x: A | None, f: Callable[[A], B]) -> B | None:
    if x is None:
        return None
    else:
        return f(x)

@dataclass(frozen=True)
class Var(Generic[A], abc.ABC):
    default: A
    name: str = ''

    @abc.abstractmethod
    def from_str(self, s: str | Any) -> A:
        raise NotImplementedError

    def __post_init__(self):
        store.init_var(self)

    @property
    def value(self) -> A:
        return store.value(self)

    @property
    def full_name(self) -> str:
        return store[self].full_name

    @property
    def provenance(self) -> str:
        return store[self].provenance

@dataclass(frozen=True)
class Int(Var[int]):
    default: int=0
    min: int|None=None
    max: int|None=None

    def from_str(self, s: str):
        try:
            ret = int(s)
        except:
            ret = self.default
        if self.min is not None and ret < self.min:
            ret = self.min
        if self.max is not None and ret > self.max:
            ret = self.max
        return ret

    def input(self, type: Literal['input', 'range', 'number'] = 'input'):
        return input(
            value=str(self.value),
            oninput=store.update(self, js('this.value')).goto(),
            min=None_map(self.min, str),
            max=None_map(self.max, str),
        )

    def range(self):
        return self.input(type='range')

    def number(self):
        return self.input(type='number')

@dataclass(frozen=True)
class Bool(Var[bool]):
    default: bool=False

    def from_str(self, s: str):
        if isinstance(s, bool):
            return s
        else:
            return s.lower() == 'true'

    def input(self):
        return input(
            checked=self.value,
            oninput=store.update(self, js('this.checked')).goto(),
            type='checkbox',
        )

@dataclass(frozen=True)
class Str(Var[str]):
    default: str=''
    options: None | tuple[str] | list[str] = None

    def from_str(self, s: str) -> str:
        if self.options is not None:
            if s in self.options:
                return s
            else:
                return self.options[0]
        else:
            return s

    def input(self, iff:str|None=None):
        if self.options:
            return V.select(
                *[
                    V.option(
                        key,
                        selected=self.value == key,
                        data_key=key,
                    )
                    for key in self.options
                ],
                oninput=store.update(self, js('this.selectedOptions[0].dataset.key')).goto(iff=iff),
            )
        else:
            return input(**self.bind(iff))

    def textarea(self):
        return V.textarea(**self.bind())

    def bind(self, iff:str|None=None):
        return {
            'value': str(self.value),
            'oninput': store.update(self, js('this.value')).goto(iff),
        }

@dataclass(frozen=False)
class StoredValue:
    goto_value: Any | js
    updated: bool
    var: Var[Any]
    provenance: str
    sub_prefix: str
    name: str

    @property
    def full_name(self) -> str:
        return self.sub_prefix + self.name

    @property
    def initial_value(self) -> Any:
        return self.var.value

    @property
    def default_value(self) -> Any:
        return self.var.default

def update_query(kvs: dict[str, Any | js]):
    s = js.convert_dict(kvs).fragment
    return f'update_query({s})'

def update_cookies(kvs: dict[str, str]) -> Any:
    prev = json.loads(request.cookies.get('v', '{}'))
    next = {**prev, **kvs}
    if prev == next:
        return {}
    else:
        @after_this_request
        def later(response: Response) -> Response:
            response.set_cookie('v', json.dumps(next))
            return response
        return {'refresh': True}

@dataclass(frozen=True)
class Provenance:
    js_side: None | Callable[[dict[str, Any | js]], str] = None
    py_side: None | Callable[[dict[str, str]], dict[str, Any]] = None
    get: Callable[[str, Any], Any] = lambda k, d: d

provenances: dict[str, Provenance] = {
    'query':  Provenance(update_query, None,                                                   lambda k, d: request.args.get(k, d)),
    'cookie': Provenance(None,         update_cookies,                                         lambda k, d: json.loads(request.cookies.get('v', '{}')).get(k, d)),
    'shared': Provenance(None,         lambda kvs: get_viable_db().update(kvs, shared=True),   lambda k, d: get_viable_db().get(k, d, shared=True)),
    'db':     Provenance(None,         lambda kvs: get_viable_db().update(kvs, shared=False),  lambda k, d: get_viable_db().get(k, d, shared=False)),
}

@serve.expose
def update_py_side(pkvs: dict[str, dict[str, Any]]) -> Response:
    out: dict[str, Any] = {}
    for p_name, kvs in pkvs.items():
        p = provenances[p_name]
        assert p.py_side
        out |= p.py_side(kvs)
    return jsonify(out)

from contextlib import contextmanager
from typing import ClassVar

@dataclass(frozen=True)
class Store:
    default_provenance: str = 'cookie'
    values: dict[int, StoredValue] = field(default_factory=dict)
    sub_prefix: str = ''

    int: ClassVar = Int
    str: ClassVar = Str
    bool: ClassVar = Bool

    @property
    def cookie(self):
        return self.at('cookie')

    @property
    def query(self):
        return self.at('query')

    @property
    def shared(self):
        return self.at('shared')

    @property
    def db(self):
        return self.at('db')

    @contextmanager
    def at(self, provenance: str):
        next = replace(self, default_provenance=provenance)
        with _focus_store(next):
            yield

    @contextmanager
    def sub(self, prefix: str):
        full_prefix = self.sub_prefix + prefix + '_'
        next = replace(self, sub_prefix=full_prefix)
        with _focus_store(next):
            yield

    def init_var(self, x: Var[Any]):
        provenance = self.default_provenance
        name = x.name
        if not name:
            name = f'_{len(self.values)}'
        self.values[id(x)] = StoredValue(
            goto_value=None,
            updated=False,
            var=x,
            provenance=provenance,
            sub_prefix=self.sub_prefix,
            name=name,
        )

    def value(self, x: Var[A]) -> A:
        sv = self[x]
        s = provenances[sv.provenance].get(sv.full_name, sv.default_value)
        return sv.var.from_str(s)

    def __getitem__(self, x: Var[Any]) -> StoredValue:
        return self.values[id(x)]

    def __setitem__(self, x: Var[Any], sv: StoredValue):
        self.values[id(x)] = sv

    def assign_names(self, names: dict[str, Var[Any] | Any]):
        for k, v in names.items():
            if isinstance(v, Var) and not v.name and (sv := self.values.get(id(v))):
                self[v] = replace(sv, name=k)

    def update(self, var: Var[A], val: A | js) -> Store:
        return self.update_untyped((var, val))

    def update_untyped(self, *to: tuple[Var[Any], Any | js]) -> Store:
        next = replace(self, values=self.values.copy())
        for var, goto in to:
            next[var] = replace(
                next[var],
                goto_value=goto,
                updated=True
            )
        return next

    @property
    def defaults(self) -> Store:
        values = {
            var: replace(sv, goto_value=sv.default_value, updated=True)
            for var, sv in self.values.items()
        }
        return replace(self, values=values)

    def goto(self, iff: str | None=None) -> str:
        by_provenance: dict[str, dict[str, Any | js]] = defaultdict(dict)
        for _v, sv in self.values.items():
            if sv.updated and sv.goto_value != sv.initial_value:
                by_provenance[sv.provenance][sv.full_name] = sv.goto_value
        out_parts: list[str] = []
        py_side: dict[str, dict[str, Any | js]] = {}
        for p_name, kvs in by_provenance.items():
            p = provenances[p_name]
            if p.js_side:
                out_parts += [p.js_side(kvs).strip(';')]
            if p.py_side:
                py_side[p_name] = kvs
        if py_side:
            out_parts += [update_py_side.call(js.convert_dicts(py_side))]
        out = ';'.join(out_parts)
        if iff:
            return 'if(' + iff + '){' + out + '}'
        else:
            return out

    def goto_script(self) -> V.Node:
        script = self.goto()
        if script:
            return V.script(V.raw(script), eval=True)
        else:
            return V.text('')
