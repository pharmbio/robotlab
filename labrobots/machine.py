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

from flask import Flask, jsonify, request

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
    def init(self):
        pass

    def help(self):
        docs: dict[str, list[str]] = {}
        for name, fn in self.__class__.__dict__.items():
            if not callable(fn):
                continue
            if name in 'help remote routes init'.split():
                continue
            if name.startswith('_'):
                continue
            sig = inspect.signature(fn)
            doc = f'{name}{sig}\n\n{fn.__doc__ or ""}'
            doc = doc.strip().splitlines()
            docs[name] = doc
        return docs

    def routes(self, name: str, app: Any):
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

        def call(cmd: str, *args: Any, **kwargs: Any):
            try:
                if cmd in 'remote routes init'.split() or cmd.startswith('_'):
                    raise ValueError(f'Cannot call {cmd} on {name} remotely')
                if cmd == 'up?':
                    return {'value': True}
                with ensure_ready():
                    return {'value': getattr(self, cmd)(*args, **kwargs)}
            except Exception as e:
                return {
                    'error': str(e),
                    'traceback': tb.format_exc(),
                    'traceback_lines': tb.format_exc().splitlines()
                }

        @app.get(f'/{name}', endpoint=f'{name}_root')             # type: ignore
        def root(cmd: str="", arg: str=""):
            args = dict(request.args)
            if args:
                cmd = args.pop('cmd')
                return jsonify(call(cmd, **args))
            else:
                url = request.url
                while url.endswith('/'):
                    url = url[:-1]
                return jsonify({url + '/' + name: doc for name, doc in self.help().items()})

        @app.get(f'/{name}/<string:cmd>', endpoint=f'{name}_get0')             # type: ignore
        def get0(cmd: str):
            return jsonify(call(cmd, **request.args))

        @app.get(f'/{name}/<cmd>/<path:arg>', endpoint=f'{name}_get')  # type: ignore
        def get(cmd: str, arg: str):
            return jsonify(call(cmd, arg.split('/'), **request.args))

        @app.post(f'/{name}', endpoint=f'{name}_post') # type: ignore
        def post():
            if request.form:
                req = dict(request.form)
            else:
                req = json.loads(request.data.decode())
            cmd = req['cmd']
            args = req['args']
            kwargs = req['kwargs']
            assert isinstance(kwargs, dict)
            return jsonify(call(cmd, *args, **kwargs))

        @app.post(f'/{name}/<cmd>', endpoint=f'{name}_post_cmd') # type: ignore
        def post_cmd(cmd: str):
            if request.form:
                req = dict(request.form)
            else:
                req = json.loads(request.data.decode())
            return jsonify(call(cmd, **req))

    @classmethod
    def remote(cls, name: str, host: str) -> te.Self:
        def call(attr_path: list[str], *args: Any, **kwargs: Any) -> Any:
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
            if 'value' in res:
                return res['value']
            else:
                raise ValueError(res['error'])
        res = call(['up?'])
        assert res['value']
        return Proxy(cls, call) # type: ignore

class Echo(Machine):
    def test(self):
        return 'test'

    def error(self, *args: str, **kws: str):
        raise ValueError(f'error {args!r} {kws!r}')

    def echo(self, *args: str, **kws: str) -> str:
        return f'echo {args!r} {kws!r}'

from dataclasses import dataclass, field, Field, fields
from typing import Callable, Any, TypeVar
from typing_extensions import Self

A = TypeVar('A')

@dataclass(frozen=True)
class Machines:
    echo: Echo = Echo()

    @classmethod
    def remote(cls, host: str) -> te.Self:
        d = {}
        for f in fields(cls):
            d[f.name] = f.default.__class__.remote(f.name, host)
        return cls(**d)

    def items(self) -> list[tuple[str, Machine]]:
        return list(self.__dict__.items())

    def serve(self, port: int, host: str):
        print('machines:')
        for k, v in self.items():
            print('    ' + k + ':', v)

        app = Flask(__name__)
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
        app.config['JSON_SORT_KEYS'] = False             # type: ignore

        for name, m in self.items():
            m.init()
            m.routes(name, app)

        @app.get('/') # type: ignore
        def root():
            url = request.url
            while url.endswith('/'):
                url = url[:-1]
            d: dict[str, list[str]] = {}
            for name, m in self.items():
                for cmd, doc in m.help().items():
                    d[url + '/' + name + '/' + cmd] = doc
            return jsonify(d)

        app.run(host=host, port=port, threaded=True, processes=1)
