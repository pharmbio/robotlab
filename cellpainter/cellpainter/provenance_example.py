from __future__ import annotations
from typing import *
from dataclasses import dataclass, field, replace

from flask import request
from functools import lru_cache
from pprint import pprint
from sorcery import spell, no_spells
import abc
import ast
import inspect
import json
import re

from .provenance import Var, Int, Str, Store, DB
from .utils.viable import js, serve, button, input, div, span, pre, label, app
from .utils import viable as V

from . import utils

def form(m: Store, *vs: Int | Str):
    d = div()
    for v in vs:
        d += label(
            span(f"{v.desc or v.name or ''}:"),
            v.input(m).extend(id_=v.name),
        )
    return d

def view(m: Store):
    x = m.var(Str(desc='x'))
    y = m.var(Str(desc='y'))
    yield button('y:="hoho" (1)', onclick=m.update({y: "hoho"}).goto())
    yield button('y:="hoho" (2)', onclick=m.update_untyped({y: js(json.dumps("hoho"))}).goto())
    yield button('y:=x (1)', onclick=m.update_untyped({y: js(f'document.querySelector("input#{x.name}").value')}).goto())
    yield button('y:=x (2)', onclick=m.update_untyped({y: x.value}).goto())
    yield button('y:=x (3)', onclick=m.update_untyped({y: js(json.dumps(x.value))}).goto())
    yield button('reset', onclick=m.defaults().goto())
    yield form(m, x, y)

def twins(m: Store):
    n = m.var(Int(1, type='number', min=0, max=5))
    yield form(m, n)
    for i in range(n.value):
        with m.sub(f'a{i}') as ma: yield div(*view(ma),
            b='1px #d8d8d8 solid',
            border_radius='0 0 6px 0',
            width='fit-content',
            p=12,
            css='''
                & button:not(:first-child) {
                    margin-left: 9px;
                }
            ''')
    yield button('reset all', onclick=m.defaults().goto())

import sys
print(sys.version)

@serve.route()
def index():
    yield {'sheet': '''
        body > *, label { margin: 10px 5px 0 0; }
        label { display: grid; grid-template-columns: 100px 100px; grid-gap: 10px; }
        label > span { place-self: center right; }
    '''}
    m = Store(default_provenance='server')
    # yield from view(m)
    a = m.var(Int(type='range'))
    b = m.var(Int(type='number'))
    yield pre(str(dict(a=a.value, b=b.value)))
    yield form(m, a, b)
    yield from twins(m)

from threading import Lock

import base64
import io
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

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

def b64svg(data: str | bytes | io.BytesIO):
    return b64(data, mime='image/svg+xml')

mpl_lock = Lock()

@serve.route('/plot')
def plot():
    m = Store()
    elev = m.var(Int(22, type='range', min=-90, max=90, provenance='cookie'))
    azim = m.var(Int(77, type='range', max=360, provenance='query'))
    spin = m.var(Int(80, type='range', provenance='server'))

    yield form(m, elev, azim, spin)
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
        r = (z-float(spin.value)/100)**2
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

    spinner = div(
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
            & div:nth-child(1) { left: 4px;  animation: -&-1 0.6s infinite; }
            & div:nth-child(2) { left: 4px;  animation: -&-2 0.6s infinite; }
            & div:nth-child(3) { left: 16px; animation: -&-2 0.6s infinite; }
            & div:nth-child(4) { left: 28px; animation: -&-3 0.6s infinite; }
            @keyframes -&-1 { 0% { transform: scale(0);        } 100% { transform: scale(1);           } }
            @keyframes -&-3 { 0% { transform: scale(1);        } 100% { transform: scale(0);           } }
            @keyframes -&-2 { 0% { transform: translate(0, 0); } 100% { transform: translate(12px, 0); } }
        ''')

    yield div(
        spinner,
        css='''
            & {
                position: fixed;
                bottom: 5px;
                right: 5px;
                opacity: 0;
                transition: opacity 50ms 0;
            }
            [loading="1"] & {
                opacity: 1;
                transition: opacity 50ms 400ms;
            }
        '''
    )

    # yield V.img(src=plt_src)

    # plt.show()

if __name__ == '__main__':
    serve.run()
