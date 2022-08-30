from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Callable, ParamSpec, TypeVar, Generic

import os
import pickle
import re
import secrets
import sys
import json
import traceback
from queue import Queue, Empty
from threading import RLock

from flask import Flask, request, jsonify, make_response
from flask.wrappers import Response
from itsdangerous import Serializer, URLSafeSerializer

from .tags import *
from .minifier import minify

def is_true(x: str | bool | int):
    return str(x).lower() in 'true y yes 1'.split()

def get_viable_js():
    from .viable_js import viable_js
    res = viable_js
    if is_true(os.environ.get('VIABLE_HOT', 'true')):
        res += 'poll()'
    res = minify(res)
    return res

viable_js = get_viable_js()

def serializer_factory() -> Serializer:
    secret_from_env = os.environ.get('VIABLE_SECRET')
    try:
        with open('.viable-secret', 'r') as fp:
            secret_from_file = fp.read()
    except:
        secret_from_file = None
    if secret_from_file:
        print('Using secret from file .viable-secret')
        secret = secret_from_file
    elif secret_from_env:
        print('Using secret from environment variable VIABLE_SECRET')
        secret = secret_from_env
    else:
        secret = secrets.token_hex(32)
    return URLSafeSerializer(secret, serializer=pickle)

@dataclass(frozen=True)
class js:
    fragment: str

    @staticmethod
    def convert_dict(d: dict[str, Any | js]) -> js:
        out = ','.join(
            f'''{
                k if re.match('^(0|[1-9][0-9]*|[_a-zA-Z][_a-zA-Z0-9]*)$', k)
                else json.dumps(k)
            }:{
                v.fragment if isinstance(v, js) else json.dumps(v)
            }'''
            for k, v in d.items()
        )
        return js('{' + out + '}')

    @staticmethod
    def convert_dicts(d: dict[str, dict[str, Any | js]]) -> js:
        return js.convert_dict({k: js.convert_dict(vs) for k, vs in d.items()})

P = ParamSpec('P')
R = TypeVar('R')

@dataclass(frozen=True)
class Exposed(Generic[P, R]):
    _f: Callable[P, R]
    _serializer: Serializer

    def __call__(self, *args: P.args, **kws: P.kwargs) -> R:
        '''
        Call from python.

        >>> @serve.expose
        ... def Sum(*args: str | int | float) -> float
        ...     res = sum(map(float, args))
        ...     print(res)
        ...     return res
        >>> print('{Sum(1,2)=}')
        3.0
        Sum(1,2)=3.0
        '''
        return self._f(*args, **kws)

    # def call(self, *args: P.args | js, **kws: P.kwargs | js) -> str:
    def call(self, *args: Any | js, **kws: Any | js) -> str:
        '''
        The handler, optionally already applied to some arguments, which may be javascript fragments.

        >>> @serve.expose
        ... def Sum(*args: str | int | float) -> float
        ...     res = sum(map(float, args))
        ...     print(res)
        ...     return res
        >>> elem = input(onclick=Sum.call(1, js('this.value')))
        '''
        py_args: dict[str | int, Any] = {}
        js_args: dict[str, js] = {}
        for k, arg in (dict(enumerate(args)) | kws).items():
            if isinstance(arg, js):
                js_args[str(k)] = arg
            else:
                py_args[k] = arg
        name = Exposed.function_name(self._f)
        py_name_and_args = self._serializer.dumps((name, py_args))
        if isinstance(py_name_and_args, bytes):
            py_name_and_args = py_name_and_args.decode()
        call_args = ','.join([
            json.dumps(py_name_and_args),
            js.convert_dict(js_args).fragment,
        ])
        return f'call({call_args}) // {name} {py_args}'

    def from_request(self, py_args: dict[str | int, Any], js_args: dict[str, Any]) -> Response:
        arg_dict: dict[int, Any] = {}
        kws: dict[str, Any] = {}
        for k, v in (py_args | js_args).items():
            if isinstance(k, int) or k.isdigit():
                k = int(k)
                arg_dict[k] = v
            else:
                assert isinstance(k, str)
                kws[k] = v
        args: list[Any] = [v for _, v in sorted(arg_dict.items(), key=lambda kv: kv[0])]
        ret = self(*args, **kws)
        if isinstance(ret, Response):
            return ret
        else:
            return jsonify(ret)

    @staticmethod
    def function_name(f: Callable[..., Any]) -> str:
        if f.__module__ == '__main__':
            return f.__qualname__
        else:
            return f.__module__ + '.' + f.__qualname__

app = Flask(__name__)

@dataclass
class Serve:
    # Routes
    routes: dict[str, Callable[..., Iterable[Node | str | dict[str, str]]]] = field(default_factory=dict)

    # Exposed functions
    exposed: dict[str, Exposed[Any, Any]] = field(default_factory=dict)
    _serializer: Serializer = field(default_factory=serializer_factory)

    # State for reloading
    notify_reload_lock: RLock = field(default_factory=RLock)
    notify_reload: list[Queue[None]] = field(default_factory=list)
    generation: int = 1

    def expose(self, f: Callable[P, R]) -> Exposed[P, R]:
        name = Exposed.function_name(f)
        assert name != '<lambda>'
        assert name not in self.exposed
        res = self.exposed[name] = Exposed(f, self._serializer)
        return res

    def __post_init__(self):
        @app.post('/call') # type: ignore
        def call():
            request_json: Any = request.json
            py_name_and_args, js_args = request_json
            py_name, py_args = self._serializer.loads(py_name_and_args)
            try:
                return self.exposed[py_name].from_request(py_args, js_args)
            except:
                traceback.print_exc()
                return '', 400

        @app.route('/viable.js') # type: ignore
        def viable_js_route():
            return viable_js, {'Content-Type': 'application/javascript'}

        @app.post('/ping') # type: ignore
        def ping():
            i = request.cookies.get('g', None)
            if i is not None and i != str(self.generation):
                resp = jsonify({'gen': self.generation})
                resp.set_cookie('g', str(self.generation))
                return resp
            q = Queue[None]()
            with self.notify_reload_lock:
                self.notify_reload.append(q)
            try:
                q.get(timeout=115)
            except Empty:
                with self.notify_reload_lock:
                    self.notify_reload.remove(q)
            resp = jsonify({'gen': self.generation})
            resp.set_cookie('g', str(self.generation))
            return resp

    def route(self, rule: str = '/'):
        def inner(f: Callable[..., Iterable[Node | str | dict[str, str]]]):
            if rule not in self.routes:
                endpoint = f'viable{len(self.routes)+1}'
                app.add_url_rule( # type: ignore
                    rule,
                    endpoint=endpoint,
                    view_func=lambda *args, **kws: self.view(rule, *args, **kws) # type: ignore
                )
            self.routes[rule] = f
            return f
        return inner

    def one(self, rule: str = '/'):
        def inner(f: Callable[..., Iterable[Node | str | dict[str, str]]]):
            self.route(rule)(f)
            self.run()
        return inner

    def saveas(self, path: str):
        def inner(f: Callable[..., Iterable[Node | str | dict[str, str]]]):
            with app.test_request_context():
                resp = self.view_callable(f, include_hot=False)
                resp_data = getattr(resp, 'data', None)
                if isinstance(resp_data, bytes):
                    with open(path, 'wb') as fp:
                        fp.write(resp_data)
                else:
                    assert isinstance(resp, str)
                    with open(path, 'w') as fp:
                        fp.write(resp)
                # print(path, 'written')
            return f
        return inner

    def reload(self) -> None:
        with self.notify_reload_lock:
            self.generation += 1
            for q in self.notify_reload:
                q.put_nowait(None)
            self.notify_reload.clear()

    def view(self, rule: str, *args: Any, **kws: Any) -> Response:
        return self.view_callable(self.routes[rule], *args, **kws)

    def view_callable(self, f: Callable[..., Iterable[Node | str | dict[str, str]]], *args: Any, include_hot: bool=True, **kws: Any) -> Response:
        try:
            parts = f(*args, **kws)
            body_node = body(*cast(Any, parts))
            title_str = f.__name__
        except:
            title_str = 'error'
            body_node = body()
            body_node.sheet += '''
                body {
                    margin: 0 auto;
                    padding: 5px;
                    max-width: 800px;
                    background: #222;
                    color: #f2777a;
                    font-size: 16px;
                }
                pre {
                    white-space: pre-wrap;
                    overflow-wrap: break-word;
                }
            '''
            body_node += pre(traceback.format_exc())
        return self.view_body(body_node, title_str=title_str, include_hot=include_hot)

    def view_body(self, body_node: Tag, title_str: str, include_hot: bool=True) -> Response:
        head_node = head()
        for i, node in enumerate(body_node.children):
            if isinstance(node, head):
                head_node = node
                body_node.children.pop(i)
                break

        has_title = False
        has_charset = False
        has_viewport = False
        has_icon = False
        for node in head_node.children:
            has_title = has_title or isinstance(node, title)
            has_charset = has_charset or isinstance(node, meta) and node.attrs.get('charset')
            has_viewport = has_viewport or isinstance(node, meta) and node.attrs.get('viewport')
            has_icon = has_icon or isinstance(node, link) and node.attrs.get('rel') == 'icon'

        if not has_title:
            head_node += title(title_str)
        if not has_charset:
            head_node += meta(charset='utf-8')
        if not has_viewport:
            head_node += meta(name="viewport", content="width=device-width,initial-scale=1")
        if not has_icon:
            # favicon because of chromium bug, see https://stackoverflow.com/a/36104057
            head_node += link(rel="icon", type="image/png", href="data:image/png;base64,iVBORw0KGgo=")

        compress = bool(re.search('gzip|br|deflate', cast(Any, request).headers.get('Accept-encoding', '')))
        indent = 0 if compress else 2
        newline = '' if compress else '\n'

        classes = body_node.make_classes({})

        if classes:
            head_node += style(raw('\n'.join(inst for _, inst in classes.values())))

        if include_hot:
            head_node += script(src="/viable.js", defer=True)

        html_str = (
            f'<!doctype html>{newline}' +
            html(head_node, body_node, lang='en').to_str(indent)
        )
        if compress:
            html_str = minify(html_str, 'html')

        resp = make_response(html_str)
        resp.set_cookie('g', str(self.generation))
        return resp

    def run(self, host: str | None = None, port: int | None = None):
        try:
            from flask_compress import Compress # type: ignore
            Compress(app)
        except Exception as e:
            print('Not using flask_compress:', str(e), file=sys.stderr)

        if is_true(os.environ.get('VIABLE_RUN', 'true')):
            print('Running app...')
            HOST = os.environ.get('VIABLE_HOST', host)
            PORT = os.environ.get('VIABLE_PORT', port)
            PORT = int(PORT) if PORT else None
            app.run(host=HOST, port=PORT, threaded=True)

    def suppress_flask_logging(self):
        # suppress flask logging
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

serve = Serve()
