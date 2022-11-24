from __future__ import annotations
from typing import *
from dataclasses import *

from flask import (
    after_this_request,  # type: ignore
    jsonify,
    request,
    g,
)
from flask.wrappers import Response
from werkzeug.local import LocalProxy
import abc
import functools
import json

from .tags import Tags, Node
from .call_js import CallJS, js
from pbutils import check, p

@dataclass
class ViableRequestData:
    call_js: CallJS
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

def add_request_data(call_js: CallJS):
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
        call_js=call_js,
        session_provided=session_provided,
        initial_values=initial_values
    )
    return this

def request_data() -> ViableRequestData:
    return g.viable_request_data

def get_store() -> Store:
    if not g.get('viable_stores'):
        g.viable_stores = [Store()]
    return g.viable_stores[-1]

store: Store = LocalProxy(get_store) # type: ignore

def get_call():
    return request_data().call_js.store_call

call = LocalProxy(get_call)

A = TypeVar('A')
B = TypeVar('B')
def None_map(set: A | None, f: Callable[[A], B]) -> B | None:
    if set is None:
        return None
    else:
        return f(set)

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

    @property
    def assign(self) -> Callable[[A], None]:
        table = {'query': 0, 'session': 1}
        provenance_int = table[self.provenance]
        full_name = self.full_name
        def set(next: A, provenance_int: int=provenance_int, full_name: str=full_name):
            provenance = 'query session'.split()[provenance_int]
            request_data().set(provenance, full_name, next)
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
        return self._indicies(self.value)

    def select_options(self) -> list[tuple[A, Tags.option]]:
        ixs = self.selected_indicies()
        return [
            (a, Tags.option(value=str(i), selected=i in ixs))
            for i, a in enumerate(self.options)
        ]

    def select(self, options: list[Tags.option]):
        return Tags.select(
            *options,
            multiple=True,
            onchange=call(self.assign, js('JSON.stringify([...this.selectedOptions].map(o => o.value))')),
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
            oninput=call(self.assign, js('this.value')),
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

    def input(self):
        return Tags.input(
            checked=self.value,
            oninput=call(self.assign, js('this.checked')),
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
                    f'({iff or 1}) && ' +
                    call(self.assign, js('this.selectedOptions[0].dataset.key')),
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
                f'({iff or 1}) && ' +
                call(self.assign, js('this.value')),
        }

def main():
    t = store.int(0, name='t')
    t.value
    # each
    def cb():
        t.assign(t.value + 1)

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

'''
@check.test
def test():
    s = Store()
    set = s.int()
    sx = s[set]
    check(sx.provenance == 'cookie')
    check(sx.name == '_0')
    s.assign_names(globals() | locals())
    sx = s[set]
    check(sx.provenance == 'cookie')
    check(sx.name == 'set')

    y = s.query.bool()
    check(s[y].provenance == 'query')

@check.test
def test_app():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context(path='http://localhost:5050?a_y=ayay'):
        set = store.cookie.str(default='xoxo')

        with store.query:
            with store.sub('a'):
                y = store.str(name='y', default='ynone')

        with store.query.sub('b').sub('c'):
            z = store.sub('d').str(name='z')

        store.assign_names(locals())

        check(store[set].provenance == 'cookie')
        check(store[y].provenance == 'query')
        check(store[z].provenance == 'query')
        check(store[set].full_name == 'set')
        check(store[y].full_name == 'a_y')
        check(store[z].full_name == 'b_c_d_z')
        check(set.value == 'xoxo')
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
'''
