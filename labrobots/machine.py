from __future__ import annotations
import socket
import traceback
import re
from dataclasses import dataclass, field, replace
from typing import Union, Tuple, Dict, Callable, Any
import typing as t
import typing_extensions as te
import json
from threading import Thread, Lock
from contextlib import contextmanager
from urllib.request import urlopen, Request
import traceback as tb
import inspect

from flask import jsonify, request

R = t.TypeVar('R')

@dataclass(frozen=True)
class Proxy(t.Generic[R]):
    wrapped: Callable[..., R]
    call: Callable[..., Any]
    attr_path: list[str] = field(default_factory=list)

    def __getattr__(self, name: str) -> Proxy[R]:
        return replace(self, attr_path=[*self.attr_path, name])

    def __call__(self, *args: Any, **kwargs: Any) -> Proxy[R]:
        return self.call(self.attr_path, *args, **kwargs)

class Machine:
    def serve(self, name: str, app: Any):
        is_ready: bool = True
        is_ready_lock: Lock = Lock()

        @contextmanager
        def ensure_ready():
            nonlocal is_ready
            with is_ready_lock:
                if not is_ready:
                    raise ValueError('not ready')
                is_ready = False
            try:
                yield
            finally:
                with is_ready_lock:
                    is_ready = True

        def call(cmd, *args, **kwargs):
            try:
                return {'value': getattr(self, cmd)(*args, **kwargs)}
            except Exception as e:
                return {'error': str(e), 'traceback': tb.format_exc()}

        @app.get(f'/{name}', endpoint=f'{name}_help')             # type: ignore
        def help(cmd: str="", arg: str=""):
            print(request.url)
            return jsonify({
                request.url.removesuffix('/') + '/' + name: doc
                for name, doc in self.help().items()
            })

        @app.get(f'/{name}/<cmd>', endpoint=f'{name}_get0')             # type: ignore
        def get0(cmd: str="", arg: str=""):
            with ensure_ready():
                arg = arg.replace('/', '\\')
                return jsonify(call(cmd))

        @app.get(f'/{name}/<cmd>/<path:arg>', endpoint=f'{name}_get')  # type: ignore
        def get(cmd: str="", arg: str=""):
            with ensure_ready():
                arg = arg.replace('/', '\\')
                return jsonify(call(cmd, arg))

        @app.post(f'/{name}', endpoint=f'{name}_post') # type: ignore
        def post():
            with ensure_ready():
                if request.form:
                    req = dict(request.form)
                else:
                    req = json.loads(request.data.decode())
                return jsonify(call(req['cmd'], *req['args'], **req['kwargs']))

        @app.post(f'/{name}/<cmd>', endpoint=f'{name}_post_cmd') # type: ignore
        def post_cmd(cmd: str):
            with ensure_ready():
                if request.form:
                    req = dict(request.form)
                else:
                    req = json.loads(request.data.decode())
                return jsonify(call(cmd, **req))

    @classmethod
    def remote(cls, name: str, host: str) -> te.Self:
        def call(attr_path: list[str], *args: Any, **kwargs: Any):
            assert len(attr_path) == 1
            cmd = attr_path[0]
            url = host.rstrip('/') + '/' + name
            ten_minutes = 60 * 10
            data = {
                'cmd': cmd,
                'args': list(args),
                'kwargs': kwargs,
            }
            print(url)
            req = Request(
                url,
                data=json.dumps(data).encode(),
                headers={'Content-type': 'application/json'},
            )
            res = json.loads(urlopen(req, timeout=ten_minutes).read())
            assert isinstance(res, dict)
            if 'value' in res:
                return res
            else:
                raise ValueError(res['error'])
        return Proxy(cls, call) # type: ignore

    def help(self):
        docs: dict[str, list[str]] = {}
        for name, fn in self.__class__.__dict__.items():
            if not callable(fn):
                continue
            if name in 'help remote serve'.split():
                continue
            if name.startswith('_'):
                continue
            sig = inspect.signature(fn)
            doc = f'{name}{sig}\n\n{fn.__doc__ or ""}'
            doc = doc.strip().splitlines()
            docs[name] = doc
        return docs

class Example(Machine):
    def test(self):
        return 'test'

    def error(self, *args: str, **kws: str):
        raise ValueError(f'error {args!r} {kws!r}')

    def echo(self, *args: str, **kws: str) -> str:
        return f'echo {args!r} {kws!r}'

