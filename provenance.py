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
            min=utils.maybe(self.min, str),
            max=utils.maybe(self.max, str),
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
    serve.reload()
    return {"refresh": True}
    # return

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

@serve.route()
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

import matplotlib as mpl
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import matplotlib.pyplot as plt

import io
import base64

from datetime import datetime, timedelta
from contextlib import contextmanager
import sys

def b64(data: str | bytes | io.BytesIO, mime: str | None=None):
    if isinstance(data, io.BytesIO):
        data = data.getvalue()
    if isinstance(data, str):
        data = data.encode()
    data = base64.b64encode(data).decode()
    if mime:
        return f'data:{mime};base64,{data}'
    else:
        return data

def b64png(data: str | bytes | io.BytesIO):
    return b64(data, mime='image/png')

def b64svg(data: str | bytes | io.BytesIO):
    return b64(data, mime='image/svg+xml')

def b64jpg(data: str | bytes | io.BytesIO):
    return b64(data, mime='image/jpeg')

def b64gif(data: str | bytes | io.BytesIO):
    return b64(data, mime='image/gif')

import utils
from threading import Lock

mpl_lock = Lock()

@serve.route('/plot')
def plot():
    m = Store(DB.get)
    elev = m.var(Int(22, type='range', min=-90, max=90))
    azim = m.var(Int(77, type='range', max=360))

    yield form(m, elev, azim)
    with mpl_lock:
        mpl.rcParams['legend.fontsize'] = 10

        fig = plt.figure()
        ax = fig.gca(projection='3d')
        # ax.set_autoscale_on(False)

        # The azimuth is the rotation around the z axis e.g.:
        # 0  means "looking from +x"
        # 90 means "looking from +y"


        ax.view_init(azim=azim.value, elev=elev.value)
        ax.dist=8
        ax.margins(0)
        ax.set_box_aspect((2, 2, 1))
        # ax.set_box_aspect((np.ptp(x), np.ptp(y), np.ptp(z)))  # aspect ratio is 1:1:1 in data space
        # ax.auto_scale_xyz([-1, 1], [-1, 1], [0, 1])
        ax.set_zlim(0, 1)


        theta = np.linspace(-4 * np.pi, 4 * np.pi, 100)
        z = np.linspace(0, 0.8, 100)
        r = (z-0.8)**2
        x = r * np.sin(theta)
        y = r * np.cos(theta)
        # x = np.hstack([x[:10], x[20:]])
        # y = np.hstack([y[:10], y[20:]])
        # z = np.hstack([z[:10], z[20:]])
        # print(x, y, z)
        ax.plot([0, 1], [0, 0], [0, 0], label='x')
        ax.plot([0, 0], [0, 1], [0, 0], label='y')
        ax.plot([0, 0], [0, 0], [0, 1], label='z')
        ax.plot(x*0-1, y, z, label='p1|x=-1')
        ax.plot(x, y*0-1, z, label='p1|y=-1')
        ax.plot(x,  y, z*0, label='p1|z=0')
        ax.plot(x, y, z, label='p1')
        # ax.plot(x[:10], y[:10], z[:10], label='p1')
        # ax.plot(x[20:30], y[20:30], z[20:30], label='p2')

        ax.legend()

        # plt.show()
        fmt = 'svg'
        buf = io.BytesIO()

        with utils.timeit(fmt + ' b64'):
            plt.savefig(buf, format=fmt)
            # print(len(b64(buf)), end='\t', file=sys.stderr)
            # plt_src = b64svg(buf)

        yield div(
            V.raw(buf.getvalue().decode()),
            css='& * { transition: all 800ms }'
        )

    yield div(
        div(
            div(), div(), div(), div(),
            css='''
                & {
                  display: inline-block;
                  position: relative;
                  width: 40px;
                  height: 20px;
                }
                & div {
                  position: absolute;
                  top: 6px;
                  width: 6px;
                  height: 6px;
                  border-radius: 50%;
                  background: #000;
                  animation-timing-function: cubic-bezier(0, 1, 1, 0);
                }
                & div:nth-child(1) {
                  left: 4px;
                  animation: lds-ellipsis1 0.6s infinite;
                }
                & div:nth-child(2) {
                  left: 4px;
                  animation: lds-ellipsis2 0.6s infinite;
                }
                & div:nth-child(3) {
                  left: 16px;
                  animation: lds-ellipsis2 0.6s infinite;
                }
                & div:nth-child(4) {
                  left: 28px;
                  animation: lds-ellipsis3 0.6s infinite;
                }
                @keyframes lds-ellipsis1 {
                  0% {
                    transform: scale(0);
                  }
                  100% {
                    transform: scale(1);
                  }
                }
                @keyframes lds-ellipsis3 {
                  0% {
                    transform: scale(1);
                  }
                  100% {
                    transform: scale(0);
                  }
                }
                @keyframes lds-ellipsis2 {
                  0% {
                    transform: translate(0, 0);
                  }
                  100% {
                    transform: translate(12px, 0);
                  }
                }
            '''
        ),
        css='''
            & {
                position: fixed;
                bottom: 5px;
                right: 5px;
                opacity: 0;
                transition: opacity 50ms 0;
            }
            .loading & {
                opacity: 1;
                transition: opacity 50ms 400ms;
            }
        '''
    )

    # yield V.img(src=plt_src)

    # plt.show()

if __name__ == '__main__':
    serve.run()
