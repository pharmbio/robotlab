from __future__ import annotations
from typing import *
from dataclasses import dataclass, field, replace

from collections import defaultdict
from contextlib import contextmanager
from flask import after_this_request, jsonify, request, g
from flask.wrappers import Response
from typing import *
from werkzeug.local import LocalProxy
import abc
import functools
import json

from . import JS, serve, input
from . import tags as V
from .core import is_true
from .db_con import get_viable_db
from .check import check

def get_store() -> Store:
    if not g.get('viable_stores'):
        g.viable_stores = [Store()]
    return g.viable_stores[-1]

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

    @property
    def value(self) -> A:
        return store.value(self)

    @property
    def full_name(self) -> str:
        return store[self].full_name

    @property
    def provenance(self) -> str:
        return store[self].provenance

SomeVar = TypeVar('SomeVar', bound=Var[Any])

import typing

class Serializer(typing.Protocol):
    def loads(self, s: str) -> Any:
        ...

    def dumps(self, obj: Any) -> str:
        ...

@dataclass(frozen=True)
class List(Var[list[A]]):
    default: list[A] = field(default_factory=list)
    options: list[A] = field(default_factory=lambda: typing.cast(Any, 'specify some options!'[404]))

    def from_str(self, s: str | Any) -> list[A]:
        return [self.options[i] for i in self._indicies(s)]

    def _indicies(self, s: str |  Any) -> list[int]:
        try:
            ixs = json.loads(s)
        except:
            return []
        if isinstance(ixs, list):
            return [int(i) for i in ixs] # type: ignore
        else:
            return []

    def selected_indicies(self):
        return self._indicies(store.str_value(self))

    def select_options(self) -> list[tuple[A, V.option]]:
        ixs = self.selected_indicies()
        return [
            (a, V.option(value=str(i), selected=i in ixs))
            for i, a in enumerate(self.options)
        ]

    def select(self, options: list[V.option]):
        return V.select(
            *options,
            multiple=True,
            onchange=store.update(self, JS('''
                JSON.stringify([...this.selectedOptions].map(o => o.value))
            ''')).goto(),
        )

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
            oninput=store.update(self, JS('this.value')).goto(),
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
            return is_true(s)

    def input(self):
        return input(
            checked=self.value,
            oninput=store.update(self, JS('this.checked')).goto(),
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
                oninput=store.update(self, JS('this.selectedOptions[0].dataset.key')).goto(iff=iff),
            )
        else:
            return input(**self.bind(iff))

    def textarea(self):
        b = self.bind()
        return V.textarea(b['value'], oninput=b['oninput'])

    def bind(self, iff:str|None=None):
        return {
            'value': str(self.value),
            'oninput': store.update(self, JS('this.value')).goto(iff),
        }

@dataclass(frozen=False)
class StoredValue:
    goto_value: Any | JS
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

def update_query(kvs: dict[str, Any | JS]):
    s = JS.convert_dict(kvs).fragment
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
    js_side: None | Callable[[dict[str, Any | JS]], str] = None
    py_side: None | Callable[[dict[str, str]], dict[str, Any]] = None
    get: Callable[[str, Any], Any] = lambda k, d: d

provenances: dict[str, Provenance] = {
    'query':  Provenance(update_query, None,                                                   lambda k, d: request.args.get(k, d)),
    'cookie': Provenance(None,         update_cookies,                                         lambda k, d: json.loads(request.cookies.get('v', '{}')).get(k, d)),
    'shared': Provenance(None,         lambda kvs: get_viable_db().update(kvs, shared=True),   lambda k, d: get_viable_db().get(k, d, shared=True)),
    'db':     Provenance(None,         lambda kvs: get_viable_db().update(kvs, shared=False),  lambda k, d: get_viable_db().get(k, d, shared=False)),
}

P = typing.ParamSpec('P')

@dataclass(frozen=True)
class Store:
    default_provenance: str = 'cookie'
    values: dict[int, StoredValue] = field(default_factory=dict)
    sub_prefix: str = ''

    @staticmethod
    def _wrap_init_var(t: Callable[P, SomeVar]) -> Callable[P, SomeVar]:
        @functools.wraps(t)
        def wrapped(self: Store, *a: P.args, **kw: P.kwargs):
            return self.init_var(t(*a, **kw))
        return wrapped # type: ignore

    int: ClassVar = _wrap_init_var(Int)
    str: ClassVar = _wrap_init_var(Str)
    bool: ClassVar = _wrap_init_var(Bool)

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

    def __enter__(self):
        assert g.viable_stores
        g.viable_stores.append(self)

    def __exit__(self, *_exc: Any):
        res = g.viable_stores.pop()
        assert res is self

    def at(self, provenance: str):
        return replace(self, default_provenance=provenance)

    def sub(self, prefix: str):
        full_prefix = self.sub_prefix + prefix + '_'
        return replace(self, sub_prefix=full_prefix)

    def init_var(self, x: SomeVar) -> SomeVar:
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
        return x

    def str_value(self, x: Var[Any]) -> str:
        sv = self[x]
        s = provenances[sv.provenance].get(sv.full_name, sv.default_value)
        return s

    def value(self, x: Var[A]) -> A:
        sv = self[x]
        return sv.var.from_str(self.str_value(x))

    def __getitem__(self, x: Var[Any]) -> StoredValue:
        return self.values[id(x)]

    def __setitem__(self, x: Var[Any], sv: StoredValue):
        self.values[id(x)] = sv

    def assign_names(self, names: dict[str, Var[Any] | Any]):
        for k, v in names.items():
            try:
                i = isinstance(v, Var)
            except:
                i = False
            if i and not v.name and (sv := self.values.get(id(v))):
                self[v] = replace(sv, name=k)

    def update(self, var: Var[A], val: A | JS) -> Store:
        return self.update_untyped((var, val))

    def update_untyped(self, *to: tuple[Var[Any], Any | JS]) -> Store:
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

    def goto_script(self) -> V.Node:
        script = self.goto()
        if script:
            return V.script(V.raw(script), eval=True)
        else:
            return V.text('')

    def goto(self, iff: str | None=None) -> str:
        by_provenance: dict[str, dict[str, Any | JS]] = defaultdict(dict)
        for _v, sv in self.values.items():
            if sv.updated and sv.goto_value != sv.initial_value:
                by_provenance[sv.provenance][sv.full_name] = sv.goto_value
        out_parts: list[str] = []
        py_side_kvs: list[tuple[tuple[str, str], Any | JS]] = []
        for p_name, kvs in by_provenance.items():
            p = provenances[p_name]
            if p.js_side:
                out_parts += [p.js_side(kvs).strip(';')]
            if p.py_side:
                for k, v in kvs.items():
                    py_side_kvs += [((p_name, k), v)]
        if py_side_kvs:
            py_side_keys   = [k for k, _ in py_side_kvs]
            py_side_values = [v for _, v in py_side_kvs]
            out_parts += [serve.call(update_py_side, py_side_keys, *py_side_values)]
        out = ';'.join(out_parts)
        if iff:
            return 'if(' + iff + '){' + out + '}'
        else:
            return out

def update_py_side(keys: list[tuple[str, str]], *values: Any) -> Response:
    pkvs: dict[str, dict[str, Any]] = defaultdict(dict)
    assert len(keys) == len(values)
    for (p, k), v in zip(keys, values):
        pkvs[p][k] = v
    out: dict[str, Any] = {}
    for p_name, kvs in pkvs.items():
        p = provenances[p_name]
        assert p.py_side
        out |= p.py_side(kvs)
    return jsonify(out)

@check.test
def test():
    s = Store()
    x = s.int()
    sx = s[x]
    check(sx.provenance == 'cookie')
    check(sx.name == '_0')
    s.assign_names(globals() | locals())
    sx = s[x]
    check(sx.provenance == 'cookie')
    check(sx.name == 'x')

    y = s.query.bool()
    check(s[y].provenance == 'query')

@check.test
def test_app():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context(path='http://localhost:5050?a_y=ayay'):
        x = store.cookie.str(default='xoxo')

        with store.query:
            with store.sub('a'):
                y = store.str(name='y', default='ynone')

        with store.query.sub('b').sub('c'):
            z = store.sub('d').str(name='z')

        store.assign_names(locals())

        check(store[x].provenance == 'cookie')
        check(store[y].provenance == 'query')
        check(store[z].provenance == 'query')
        check(store[x].full_name == 'x')
        check(store[y].full_name == 'a_y')
        check(store[z].full_name == 'b_c_d_z')
        check(x.value == 'xoxo')
        check(y.value == 'ayay')
        check(store[y].default_value == 'ynone')
        check(store[y].initial_value == 'ayay')
        check(store[y].goto_value is None)
        check(store.update(y, 'yaya')[y].goto_value == 'yaya')
        check(store.goto() == '')
        check(store.update(y, 'yaya').goto() == 'update_query({a_y:"yaya"})')

@check.test
def test_List():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context(path='http://localhost:5050?xs=[1,2]'):
        xs = store.query.init_var(List(options=['a', 'b', 'c']))
        store.assign_names(locals())
        check(xs.selected_indicies() == [1, 2])
        check(xs.value == ['b', 'c'])

