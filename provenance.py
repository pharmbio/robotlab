from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import *
import abc
from viable import js, serve, button, input, div, span, pre, label, app
import viable as V
from sorcery import spell, no_spells
import inspect
import ast
import json
from flask import request

from functools import lru_cache

def lhs() -> str:
    @spell
    def inner(frame_info) -> str:
        xs, _ = frame_info.assigned_names(allow_one=True)
        return xs[0]
    return inner()

no_spells(lhs)

A = TypeVar('A')

@dataclass(frozen=True)
class Var(Generic[A], abc.ABC):
    value: A
    name: str|None = None
    provenance: Provenance = 'query'

    @abc.abstractmethod
    def from_str(self, s: str | Any) -> A:
        raise NotImplementedError

    @abc.abstractmethod
    def input(self, m: Store) -> V.Tag:
        raise NotImplementedError

VarAny = TypeVar('VarAny', bound=Var[Any])

@dataclass(frozen=True)
class Int(Var[int]):
    value: int=0
    min: int|None=None
    max: int|None=None
    desc: str|None=None
    help: str|None=None
    type: Literal['range', 'input', 'number'] = 'input'

    def from_str(self, s: str):
        try:
            return int(s)
        except:
            return self.value

    def input(self, m: Store):
        return input(
            value=str(self.value),
            oninput=m.update_untyped({self: js('this.value')}).goto(),
            type=self.type,
        )

@dataclass(frozen=True)
class Str(Var[str]):
    value: str=''
    desc: str|None=None
    help: str|None=None

    def from_str(self, s: str):
        return s

    def input(self, m: Store):
        return input(
            value=str(self.value),
            oninput=m.update_untyped({self: js('this.value')}).goto()
        )

Provenance = Literal['path', 'query', 'local', 'session', 'server']

from contextlib import contextmanager

@dataclass
class Store:
    store: Callable[[str, Any], Any]
    values: dict[Var[Any], Any | js] = field(default_factory=dict)
    initial_values: dict[Var[Any], Any] = field(default_factory=dict)
    default_values: dict[Var[Any], Any] = field(default_factory=dict)
    sub_prefix: str = ''

    def var(self, x: VarAny) -> VarAny:
        assert x.provenance == 'query', 'only query params implemented so far'
        if x.name:
            name = x.name
        else:
            name = lhs()
        assert name is not None
        if self.sub_prefix:
            name = self.sub_prefix + name
        default = x.value
        xx = replace(x, name=name, value=x.from_str(self.store(name, default)))
        self.values[xx] = xx.value
        self.initial_values[xx] = xx.value
        self.default_values[xx] = default
        return xx

    def update(self, to: dict[Var[A], A]) -> Store:
        return self.update_untyped(cast(dict[Any, Any], to))

    def update_untyped(self, to: dict[VarAny, Any | js]) -> Store:
        return Store(self.store, {**self.values, **to}, self.initial_values, self.default_values, self.sub_prefix)

    def defaults(self) -> Store:
        return Store(self.store, self.default_values, {}, self.default_values, self.sub_prefix)

    @contextmanager
    def sub(self, prefix: str):
        full_prefix = self.sub_prefix + prefix + '_'
        for x, _ in self.values.items():
            assert x.name is not None
            assert not x.name.startswith(full_prefix)
        st = Store(self.store, {}, {}, {}, full_prefix)
        yield st
        self.values.update(st.values)
        self.initial_values.update(st.initial_values)
        self.default_values.update(st.default_values)

    def full_name(self, x: Var[Any]) -> str:
        assert x.name is not None
        return x.name

    def goto(self) -> str:
        return cook.call(
            *(
                v if isinstance(v, js) else js(json.dumps(v))
                for x, v in self.values.items()
                if v is not self.initial_values.get(x)
            ),
            keys=[
                x.name
                for x, v in self.values.items()
                if v is not self.initial_values.get(x)
            ]
        )


        # s = ','.join(
        #     ':'.join((
        #         x.name if x.name and re.match(r'\w+$', x.name) else json.dumps(x.name),
        #         v.fragment if isinstance(v, js) else json.dumps(v)
        #     ))
        #     for x, v in self.values.items()
        #     if v is not self.initial_values.get(x)
        # )
        # s = '{' + s + '}'
        # return f'update_query({s})'

from flask import jsonify

DB: dict[str, Any] = {}

@serve.expose
def cook(*values: Any, keys: list[str]=[]):
    # resp = jsonify({"refresh": True})
    # prev = json.loads(request.cookies.get('kaka', "{}"))
    # next = dict(zip(keys, values))
    # print(values, keys)
    # print(prev, next)
    # resp.set_cookie('kaka', json.dumps({**prev, **next}))
    # return resp
    next = dict(zip(keys, values))
    DB.update(next)
    # return {"refresh": True}
    serve.reload()
    return

no_spells(Store.var)

import re

from pprint import pprint
from utils import pr

if 0:
    vals: dict[str, Any] = {}

    m = Store(vals.get)
    # p = m.var(Str(provenance='path'))
    x = m.var(Int())
    y = m.var(Str())
    r = m.var(Str(name='rr'))
    with m.sub('t') as mt:
        z = mt.var(Str())
    print(x)
    print(y)
    pr(m)

def form(m: Store, *vs: Int | Str):
    d = div()
    for v in vs:
        d += label(
            span(f"{v.desc or v.name or ''}:"),
            v.input(m),
        )
    return d

def view(m: Store):
    x = m.var(Str(desc='x'))
    y = m.var(Str(desc='y'))
    yield button('reset', onclick=m.defaults().goto())
    yield button('example 1', onclick=m.update({x: "hoho"}).goto())
    yield button('example 2', onclick=m.update_untyped({y: js('document.querySelector("input").value')}).goto())
    yield button('example 3', onclick=m.update_untyped({y: x.value}).goto())
    yield form(m, x, y)

def twins(m: Store):
    n = m.var(Int(1))
    yield form(m, n)
    for i in range(n.value):
        with m.sub(f'a{i}') as ma: yield from view(ma)
    yield button('reset all', onclick=m.defaults().goto())

import sys
print(sys.version)

@serve.one()
def index():
    yield 'boo'
    yield {'sheet': '''
        body > *, label { margin: 10px 5px 0 0; }
        label { display: grid; grid-template-columns: 100px 100px; grid-gap: 10px; }
        label > span { place-self: center right; }
    '''}
    # m = Store(request.args.get)
    kaka = json.loads(request.cookies.get('kaka', "{}"))
    # m = Store(kaka.get)
    m = Store(DB.get)
    # print(request.args)
    a = m.var(Int(type='range'))
    b = m.var(Int(type='number'))
    yield pre(str(dict(a=a.value, b=b.value)))
    yield form(m, a, b)
    yield from twins(m)

