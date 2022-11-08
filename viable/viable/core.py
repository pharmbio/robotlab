from __future__ import annotations
from dataclasses import *
from typing import *

import os
import pickle
import re
import secrets
import sys
import json
import traceback
import functools
from inspect import signature
from queue import Queue, Empty
from threading import RLock

from flask import Flask, request, jsonify, make_response
from flask.wrappers import Response
from itsdangerous import Serializer, URLSafeSerializer

from .freeze_function import FrozenFunction

from .tags import *
from .minifier import minify

def is_true(x: str | bool | int | None):
    return str(x).lower() in 'true y yes 1'.split()

@functools.cache
def get_viable_js():
    from .viable_js import viable_js
    res = viable_js
    if is_true(os.environ.get('VIABLE_HOT', 'true')):
        res += 'poll()'
    res = minify(res)
    return res

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
class JS:
    fragment: str

    @staticmethod
    def convert_dict(d: dict[str, Any | JS]) -> JS:
        out = ','.join(
            f'''{
                k if re.match('^(0|[1-9][0-9]*|[_a-zA-Z][_a-zA-Z0-9]*)$', k)
                else json.dumps(k)
            }:{
                v.fragment if isinstance(v, JS) else json.dumps(v)
            }'''
            for k, v in d.items()
        )
        return JS('{' + out + '}')

    @staticmethod
    def convert_dicts(d: dict[str, dict[str, Any | JS]]) -> JS:
        return JS.convert_dict({k: JS.convert_dict(vs) for k, vs in d.items()})

def js(fragment: str) -> Any:
    return JS(fragment)

P = ParamSpec('P')
R = TypeVar('R')

app = Flask(__name__)

@dataclass
class Serve:
    # Routes
    routes: dict[str, Callable[..., Iterable[Node | str | dict[str, str]]]] = field(default_factory=dict)

    _serializer: Serializer = field(default_factory=serializer_factory)

    # State for reloading
    notify_reload_lock: RLock = field(default_factory=RLock)
    notify_reload: list[Queue[None]] = field(default_factory=list)
    generation: int = 1

    def call(self, f: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> str:
        # apply any defaults to the arguments now so that js fragments get evaluated
        sig = signature(f)
        b = sig.bind(*args, **kwargs)
        b.apply_defaults()
        py_args: dict[str | int, Any] = {}
        js_args: dict[str | int, str] = {}
        all_args: dict[str | int, Any | JS] = {**dict(enumerate(b.args)), **b.kwargs}
        for k, arg in all_args.items():
            if isinstance(arg, JS):
                js_args[k] = arg.fragment
            else:
                py_args[k] = arg
        func = FrozenFunction.freeze(f)
        js_args_keys = [k for k, _ in js_args.items()]
        js_args_vals = [v for _, v in js_args.items()]
        func_and_py_args_and_js_args_keys = (func, py_args, js_args_keys)
        enc = self._serializer.dumps(func_and_py_args_and_js_args_keys)
        if isinstance(enc, bytes):
            enc = enc.decode()
        call_args = ','.join([
            json.dumps(enc),
            *js_args_vals,
        ])
        return f'call({call_args})\n/* {f} {py_args} {js_args_keys} */'

    def handle_call(self, enc: str, js_args_vals: list[Any]) -> Response:
        func: FrozenFunction;
        py_args: dict[str | int, Any]
        js_args_keys: list[str | int]
        func, py_args, js_args_keys = self._serializer.loads(enc)
        js_args = dict(zip(js_args_keys, js_args_vals))
        assert js_args.keys().isdisjoint(py_args.keys())
        arg_dict: dict[int, Any] = {}
        kwargs: dict[str, Any] = {}
        for k, v in (py_args | js_args).items():
            if isinstance(k, int) or k.isdigit():
                k = int(k)
                arg_dict[k] = v
            else:
                assert isinstance(k, str)
                kwargs[k] = v
        args: list[Any] = [v for _, v in sorted(arg_dict.items(), key=lambda kv: kv[0])]
        f = func.thaw()
        ret = f(*args, **kwargs)
        if isinstance(ret, Response):
            return ret
        else:
            return jsonify(refresh=True)

    def __post_init__(self):
        @app.post('/call') # type: ignore
        def call():
            assert request.json is not None
            enc, *js_args_vals = request.json
            try:
                return self.handle_call(enc, js_args_vals)
            except:
                traceback.print_exc()
                return '', 400

        @app.route('/viable.js') # type: ignore
        def viable_js_route():
            return get_viable_js(), {'Content-Type': 'application/javascript'}

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
            head_node += script(src=f"/viable.js", defer=True)

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
            HOST = os.environ.get('VIABLE_HOST', host)
            PORT = os.environ.get('VIABLE_PORT', port)
            PORT = int(PORT) if PORT else None
            if HOST and PORT:
                print(f'Running app on http://{HOST}:{PORT}')
            app.run(host=HOST, port=PORT, threaded=True)

    def suppress_flask_logging(self):
        # suppress flask logging
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

serve = Serve()
call = serve.call
