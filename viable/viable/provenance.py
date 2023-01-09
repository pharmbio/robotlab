from __future__ import annotations
from typing import *
from dataclasses import *

from flask import (
    after_this_request,  # type: ignore
    request,
    g,
)
from werkzeug.local import LocalProxy
import abc
import functools
import json

from .tags import Tags
from .call_js import js, JS

@dataclass
class ViableRequestData:
    session_provided: bool
    initial_values: dict[tuple[str, str], Any]
    written_values: dict[tuple[str, str], Any] = field(default_factory=dict)
    created_vars: list[Var[Any]] = field(default_factory=list)
    push: bool = False

    def get(self, provenance: str, name: str, default: Any) -> Any:
        t = provenance, name
        if t in self.written_values:
            return self.written_values[t]
        return self.initial_values.get(t, default)
        raise ValueError(f'Invalid {provenance=}')

    def set(self, provenance: str, name: str, next: Any) -> Any:
        t = provenance, name
        self.written_values[t] = next

    def updates(self):
        g: dict[str, dict[str, Any]] = DefaultDict(dict)
        for (provenance, name), v in self.written_values.items():
            g[provenance][name] = v
        if self.push:
            return {**g, 'push': True}
        else:
            return {**g}

    def did_request_session(self) -> bool:
        return any(v.provenance == 'session' for v in self.created_vars)

def add_request_data():
    query: dict[str, Any] = dict(request.args)
    session: dict[str, Any]
    if (body := request.get_json(force=True, silent=True)) is not None:
        session = body.get('session', {})
        session_provided = True
    else:
        session = {}
        session_provided = False
    initial_values: dict[tuple[str, str], Any] = {}
    initial_values |= {('query', k): v for k, v in query.items()}
    initial_values |= {('session', k): v for k, v in session.items()}
    g.viable_request_data = this = ViableRequestData(
        session_provided=session_provided,
        initial_values=initial_values
    )
    return this

def request_data() -> ViableRequestData:
    if not g.get('viable_request_data'):
        g.viable_request_data = add_request_data()
    return g.viable_request_data

def get_store() -> Store:
    if not g.get('viable_stores'):
        g.viable_stores = [Store()]
    return g.viable_stores[-1]

store: Store = LocalProxy(get_store) # type: ignore

A = TypeVar('A')
B = TypeVar('B')
def None_map(set: A | None, f: Callable[[A], B]) -> B | None:
    if set is None:
        return None
    else:
        return f(set)

@dataclass(frozen=True)
class quiet_repr:
    value: str
    def __repr__(self):
        return self.value

@dataclass
class Var(Generic[A], abc.ABC):
    default: A
    name: str = ''
    _: KW_ONLY
    _sub_prefix: str = ''
    _provenance: str = 'session'
    _did_set_store: bool = False

    @abc.abstractmethod
    def from_str(self, s: str | Any) -> A:
        raise NotImplementedError

    def to_str(self, value: A) -> str:
        return str(value)

    def set_store(self, store: Store):
        if self._did_set_store:
            raise ValueError('Variable already associated with a store.')
        self._did_set_store = True
        self._provenance = store.provenance
        self._sub_prefix = store.sub_prefix
        if not self.name:
            # get number of variables with this prefix
            filtered_count = sum(
                1
                for v in request_data().created_vars
                if v._sub_prefix == store.sub_prefix
            )
            self.name = f'_{filtered_count}'
        request_data().created_vars.append(self)

    def rename(self, new_name: str):
        if not self.name.startswith('_'):
            raise ValueError('Can only rename variables which do not already have a name')
        if new_name.startswith('_'):
            raise ValueError('Name cannot start with underscore')
        self.name = new_name

    @property
    def full_name(self) -> str:
        if self.name == '':
            raise ValueError(f'Variable {self=} has no assigned name')
        return self._sub_prefix + self.name

    @property
    def provenance(self) -> str:
        return self._provenance

    @property
    def value(self) -> A:
        return self.from_str(request_data().get(self._provenance, self.full_name, self.default))

    @value.setter
    def value(self, value: A):
        self.assign(value)

    def update(self, value: A, push: bool=False) -> str:
        if isinstance(value, JS):
            rhs = value.fragment
        else:
            rhs = self.to_str(value)
        q = quiet_repr
        next = {q(self.provenance): {self.full_name: rhs}}
        if push:
            next = {**next, q('push'): q('true')}
        return f'update({next})'

    @property
    def assign(self) -> Callable[[A], None]:
        table = {'query': 0, 'session': 1}
        provenance_int = table[self.provenance]
        full_name = self.full_name
        def set(next: A, provenance_int: int=provenance_int, full_name: str=full_name):
            provenance = 'query session'.split()[provenance_int]
            request_data().set(provenance, full_name, self.to_str(next))
        return set

    def push(self, next: A):
        if self.provenance == 'query':
            request_data().push = True
        return self.assign(next)

    def assign_default(self):
        request_data().set(self._provenance, self.full_name, self.default)

    # def forget(self):
    #     request_data().set(self._provenance, self.full_name, Forget())

SomeVar = TypeVar('SomeVar', bound=Var[Any])

@dataclass
class List(Var[list[A]]):
    default: list[A] = field(default_factory=list)
    options: list[A] = field(default_factory=lambda: cast(Any, 'specify some options!'[404]))

    def from_str(self, s: str | Any) -> list[A]:
        return [self.options[i] for i in self._indicies(s)]

    def to_str(self, value: list[A]) -> str:
        return json.dumps([self.options.index(v) for v in value])

    def _indicies(self, s: str |  Any) -> list[int]:
        try:
            ixs = json.loads(s)
        except:
            return []
        if isinstance(ixs, list):
            return [int(i) for i in ixs] # type: ignore
        else:
            return []

    def select(self, options: list[Tags.option]):
        return Tags.select(
            *options,
            multiple=True,
            onchange=self.update(js('JSON.stringify([...this.selectedOptions].map(o => o.value))')),
        )

@dataclass
class Int(Var[int]):
    default: int=0
    min: int|None=None
    max: int|None=None
    desc: str | None = None

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
        return Tags.input(
            value=str(self.value),
            oninput=self.update(js('this.value')),
            min=None_map(self.min, str),
            max=None_map(self.max, str),
            title=self.desc,
            type=type,
        )

    def range(self):
        return self.input(type='range')

    def number(self):
        return self.input(type='number')

def is_true(set: str | bool | int | None):
    return str(set).lower() in 'true y yes 1'.split()

@dataclass
class Bool(Var[bool]):
    default: bool=False
    desc: str | None = None

    def from_str(self, s: str):
        if isinstance(s, bool):
            return s
        else:
            return is_true(s)

    def to_str(self, value: bool):
        return json.dumps(value)

    def input(self):
        return Tags.input(
            checked=self.value,
            oninput=self.update(js('this.checked')),
            type='checkbox',
            title=self.desc,
        )

@dataclass
class Str(Var[str]):
    default: str=''
    options: None | tuple[str] | list[str] = None
    desc: str | None = None

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
            if self.value not in self.options:
                self.value = self.options[0]
            return Tags.select(
                *[
                    Tags.option(
                        key,
                        selected=self.value == key,
                        data_key=key,
                    )
                    for key in self.options
                ],
                oninput=
                    (f'({iff})&&' if iff else '') +
                    self.update(js('this.selectedOptions[0].dataset.key')),
            )
        else:
            return Tags.input(
                **self.bind(iff),
                title=self.desc,
            )

    def textarea(self):
        b = self.bind()
        return Tags.textarea(b['value'], oninput=b['oninput'])

    def bind(self, iff:str|None=None):
        return {
            'value': str(self.value),
            'oninput':
                (f'({iff})&&' if iff else '') +
                self.update(js('this.value')),
        }

P = ParamSpec('P')

@dataclass(frozen=True)
class Store:
    provenance: str = 'session'
    sub_prefix: str = ''

    @staticmethod
    def wrap_set_store(factory: Callable[P, SomeVar]) -> Callable[P, SomeVar]:
        @functools.wraps(factory)
        def wrapped(self: Store, *a: P.args, **kw: P.kwargs):
            var = factory(*a, **kw)
            var.set_store(self)
            return var
        return wrapped # type: ignore

    int: ClassVar = wrap_set_store(Int)
    str: ClassVar = wrap_set_store(Str)
    bool: ClassVar = wrap_set_store(Bool)

    def var(self, v: SomeVar) -> SomeVar:
        v.set_store(self)
        return v

    @property
    def session(self):
        return self.at('session')

    @property
    def query(self):
        return self.at('query')

    def __enter__(self):
        assert g.viable_stores
        g.viable_stores.append(self)

    def __exit__(self, *_exc: Any):
        res = g.viable_stores.pop()
        assert res is self

    def at(self, provenance: str):
        return replace(self, provenance=provenance)

    def sub(self, prefix: str):
        full_prefix = self.sub_prefix + prefix + '_'
        return replace(self, sub_prefix=full_prefix)

    def assign_names(self, names: dict[str, Var[Any] | Any]):
        for k, v in names.items():
            try:
                isinst = isinstance(v, Var)
            except:
                continue
            if isinst and v.name.startswith('_'):
                v.rename(k)

import pytest

@pytest.fixture
def with_store():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context(path='http://localhost:5050?a_y=ayay'):
        add_request_data()
        yield

def test_int(with_store: ...):
    x = store.int()
    assert x.provenance == 'session'
    assert x.name == '_0'
    store.assign_names(globals() | locals())
    assert x.provenance == 'session'
    assert x.name == 'x'

    assert x.value == 0
    assert x.update(1) == '''update({session: {'x': '1'}})'''
    x.value = 2
    assert x.value == 2
    assert request_data().updates() == {'session': {'x': '2'}}

def test_bool(with_store: ...):
    y = store.query.bool(name='y')
    assert y.provenance == 'query'

    assert y.value == False
    assert y.update(True) == '''update({query: {'y': 'true'}})'''
    y.value = True
    assert y.value == True
    assert request_data().updates() == {'query': {'y': 'true'}}

def test_app(with_store: ...):
    x = store.session.str(default='xoxo')

    with store.query:
        with store.sub('a'):
            y = store.str(name='y', default='ynone')

    with store.query.sub('b').sub('c'):
        z = store.sub('d').str(name='z')

    store.assign_names(locals())

    assert x.provenance == 'session'
    assert y.provenance == 'query'
    assert z.provenance == 'query'
    assert x.full_name == 'x'
    assert y.full_name == 'a_y'
    assert z.full_name == 'b_c_d_z'
    assert x.value == 'xoxo'
    assert y.value == 'ayay'
    assert y.default == 'ynone'

    assert y.update('yaya') == "update({query: {'a_y': 'yaya'}})"

    y.assign('yaya')
    assert request_data().updates() == {'query': {'a_y': 'yaya'}}

def test_List(with_store: ...):
    xs = store.var(List(options=['a', 'b', 'c']))
    store.assign_names(locals())
    assert xs.value == []
    assert xs.update(['a']) == '''update({session: {'xs': '[0]'}})'''
    xs.value = ['b', 'c']
    assert xs.value == ['b', 'c']
    assert request_data().updates() == {'session': {'xs': '[1, 2]'}}
