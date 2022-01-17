from __future__ import annotations
from typing import *
from dataclasses import dataclass, field, replace

from collections import defaultdict
from contextlib import contextmanager
from flask import jsonify, request
from flask.wrappers import Response
from sorcery import spell, no_spells
import abc
import json

from .viable import js, serve, button, input, div, span, pre, label, app
from . import viable as V
from flask import after_this_request

from . import utils

def lhs() -> str:
    @spell
    def inner(frame_info) -> str:
        xs, _ = frame_info.assigned_names(allow_one=True)
        return xs[0]
    return inner()

no_spells(lhs)

A = TypeVar('A')

Provenance = Literal['query', 'cookie', 'server']

@dataclass(frozen=True)
class Var(Generic[A], abc.ABC):
    value: A
    name: str|None = None
    provenance: Provenance = cast(Provenance, None)

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
            ret = int(s)
        except:
            ret = self.value
        if self.min is not None and ret < self.min:
            ret = self.min
        if self.max is not None and ret > self.max:
            ret = self.max
        return ret

    def input(self, m: Store):
        return input(
            value=str(self.value),
            oninput=m.update_untyped({self: js('this.value')}).goto(),
            type=self.type,
            min=utils.maybe(self.min, str),
            max=utils.maybe(self.max, str),
        )

@dataclass(frozen=True)
class Bool(Var[bool]):
    value: bool=False
    desc: str|None=None
    help: str|None=None

    def from_str(self, s: str):
        if isinstance(s, bool):
            return s
        else:
            return s.lower() == 'true'

    def input(self, m: Store):
        return input(
            checked=self.value,
            oninput=m.update_untyped({self: js('this.checked')}).goto(),
            type='checkbox',
        )


@dataclass(frozen=True)
class Str(Var[str]):
    value: str=''
    desc: str|None=None
    help: str|None=None

    def from_str(self, s: str):
        return s

    def update_handler(self, m: Store, iff:str|None=None):
        return m.update_untyped({self: js('this.value')}).goto(iff=iff)

    def input(self, m: Store, iff:str|None=None):
        return input(
            value=str(self.value),
            oninput=self.update_handler(m, iff=iff),
        )

@dataclass(frozen=True)
class StoredValue:
    goto_value: Any | js
    initial_value: Any
    default_value: Any

DB: dict[str, Any] = {}

def init_store() -> dict[Provenance, Callable[[str, Any], Any]]:
    return {
        'server': DB.get,
        'cookie': json.loads(request.cookies.get('kaka', "{}")).get,
        'query': request.args.get,
    }

def empty() -> dict[Provenance, Callable[[str, Any], Any]]:
    return {
        'server': lambda _a, _b: None,
        'cookie': lambda _a, _b: None,
        'query':  lambda _a, _b: None,
    }

@dataclass(frozen=True)
class Store:
    default_provenance: Provenance = 'cookie'
    store: dict[Provenance, Callable[[str, Any], Any]] = field(default_factory=init_store)
    values: dict[Var[Any], StoredValue] = field(default_factory=dict)
    sub_prefix: str = ''

    @staticmethod
    def empty(default_provenance: Provenance = 'cookie'):
        return Store(default_provenance=default_provenance, store=empty())

    def __post_init__(self):
        no_spells(Store.var)

    def var(self, x: VarAny) -> VarAny:
        if x.provenance is None:
            x = replace(x, provenance=self.default_provenance)
        if x.name:
            name = x.name
        else:
            name = lhs()
        assert name is not None
        if self.sub_prefix:
            name = self.sub_prefix + name
        default = x.value
        xx = replace(x, name=name, value=x.from_str(self.store[x.provenance](name, default)))
        self.values[xx] = StoredValue(xx.value, xx.value, default)
        return xx

    def update(self, to: dict[Var[A], A]) -> Store:
        return self.update_untyped(cast(dict[Any, Any], to))

    def update_untyped(self, to: dict[Var[Any], Any | js]) -> Store:
        values = {
            k: replace(v, goto_value=to.get(k, v.goto_value))
            for k, v in self.values.items()
        }
        return Store(self.default_provenance, self.store, values, self.sub_prefix)

    def defaults(self) -> Store:
        values = {
            k: replace(v, goto_value=v.default_value)
            for k, v in self.values.items()
        }
        return Store(self.default_provenance, self.store, values, self.sub_prefix)

    @contextmanager
    def sub(self, prefix: str):
        full_prefix = self.sub_prefix + prefix + '_'
        for x, _ in self.values.items():
            assert x.name is not None
            assert not x.name.startswith(full_prefix)
        st = Store(self.default_provenance, self.store, {}, full_prefix)
        yield st
        self.values.update(st.values)

    def full_name(self, x: Var[Any]) -> str:
        assert x.name is not None
        return x.name

    def goto(self, iff: str | None=None) -> str:
        updated = [
            (k, v)
            for k, v in self.values.items()
            if v.goto_value is not v.initial_value
        ]
        q = {
            k.name: v.goto_value
            for k, v in updated
            if k.provenance == 'query'
        }
        updated = [
            (k, v)
            for k, v in self.values.items()
            if v.goto_value is not v.initial_value
            if k.provenance != 'query'
        ]
        if q:
            kvs = ','.join(
                json.dumps(k)+':'+(v.fragment if isinstance(v, js) else json.dumps(v))
                for k, v in q.items()
            )
            kvs = '{' + kvs + '}'
            q_str = f'update_query({kvs});refresh()'
        else:
            q_str = ''
        if updated:
            s_str = cook.call(
                *(v.goto_value for _, v in updated),
                keys=[(k.provenance, k.name) for k, _ in updated]
            )
        else:
            s_str = ''
        out = (q_str + ';' + s_str).strip(';')
        if iff:
            return 'if (' + iff + ') {' + out + '}'
        else:
            return out

    def goto_script(self) -> V.Node:
        script = self.goto()
        if script:
            return V.script(V.raw(script), eval=True)
        else:
            return V.text('')

@serve.expose
def cook(*values: Any, keys: list[tuple[Provenance, str]]) -> Response:
    next: defaultdict[Provenance, dict[str, Any]] = defaultdict(dict)
    for (p, n), v in zip(keys, values):
        next[p][n] = v
    assert not next['query']
    kaka = None
    gen = None
    refresh = False
    if next_DB := next['server']:
        DB.update(next_DB)
        serve.reload()
        gen = serve.generation
    if next_cookie := next['cookie']:
        prev = json.loads(request.cookies.get('kaka', "{}"))
        kaka = json.dumps({**prev, **next_cookie})
        refresh = True
    resp = jsonify({'refresh': refresh, 'gen': gen})
    if kaka: resp.set_cookie('kaka', kaka)
    if gen: resp.set_cookie('gen', str(gen))
    return resp
