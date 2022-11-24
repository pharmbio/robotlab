from __future__ import annotations
from dataclasses import *
from typing import *

import os
import pickle
import re
import secrets
import sys
import traceback
import time
import functools
import json
import base64
from pathlib import Path

from flask import request, jsonify, make_response, Flask
from flask.wrappers import Response
from itsdangerous import Serializer, URLSafeSerializer

from pbutils import TODO

from .tags import Node, Tag, Tags, raw
from .minifier import minify
from .call_js import CallJS
from .provenance import add_request_data, request_data

def is_true(x: str | bool | int | None):
    return str(x).lower() in 'true y yes 1'.split()

@dataclass(frozen=True)
class Env:
    VIABLE_DEV: bool = is_true(os.environ.get('VIABLE_DEV', True))
    VIABLE_RUN: bool = is_true(os.environ.get('VIABLE_RUN', True))
    VIABLE_HOST: str | None = os.environ.get('VIABLE_HOST')
    VIABLE_PORT: int | None = int(port) if (port := os.environ.get('VIABLE_PORT')) else None

@functools.cache
def get_viable_js(env: Env):
    from .viable_js import viable_js
    res = viable_js
    if env.VIABLE_DEV:
        res += '\npoll()'
    if not env.VIABLE_DEV:
        res = minify(res)
    return res

def serializer_factory() -> Serializer:
    secret = secrets.token_hex(32)
    return URLSafeSerializer(secret, serializer=pickle)

P = ParamSpec('P')
R = TypeVar('R')

@dataclass
class Serve:
    app: Flask
    env: Env = field(default_factory=Env)
    _routes_added: list[Any] = field(default_factory=list)
    _call_js: CallJS = field(default_factory=lambda: CallJS(serializer_factory()))

    def call(self, f: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> str:
        return self._call_js.store_call(f, *args, **kwargs)

    def __post_init__(self):
        @self.app.post('/call') # type: ignore
        def call_route():
            assert request.json is not None
            body = request.json
            enc, *js_args_vals = body['args']
            add_request_data(self._call_js)
            try:
                self._call_js.handle_call(enc, js_args_vals)
                return jsonify(request_data().updates())
            except:
                traceback.print_exc()
                return '', 400

        @self.app.route('/viable.js') # type: ignore
        def viable_js_route():
            return get_viable_js(self.env), {'Content-Type': 'application/javascript'}

        @self.app.post('/ping') # type: ignore
        def ping_route():
            time.sleep(115)
            return jsonify({})

    def route(self, rule: str = '/'):
        def inner(f: Callable[..., Iterable[Node | str | dict[str, str]]]):

            self._routes_added.append(f)
            endpoint = f'viable_{f.__name__}_{len(self._routes_added)}' # flask insists on getting an endpoint name
            self.app.add_url_rule( # type: ignore
                rule,
                endpoint=endpoint,
                view_func=lambda *args, **kws: self.view(f, *args, **kws), # type: ignore
                methods='GET POST'.split(),
            )
            return f
        return inner

    def one(self, rule: str = '/', host: str | None = None, port: int | None = None):
        def inner(f: Callable[..., Iterable[Node | str | dict[str, str]]]):
            self.route(rule)(f)
            self.run(host, port)
        return inner

    def view(self, f: Callable[..., Iterable[Node | str | dict[str, str]]], *args: Any, **kws: Any) -> Response:

        add_request_data(self._call_js)

        try:
            parts = f(*args, **kws)
            body_node = Tags.body(*cast(Any, parts))
            title_str = f.__name__
        except:
            title_str = 'error'
            body_node = Tags.body()
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
            body_node += Tags.pre(traceback.format_exc())
        return self.view_body(body_node, title_str=title_str)

    def view_body(self, body_node: Tag, title_str: str) -> Response:
        head_node = Tags.head()
        for i, node in enumerate(body_node.children):
            if isinstance(node, Tags.head):
                head_node = node
                body_node.children.pop(i)
                break

        has_title = False
        has_charset = False
        has_viewport = False
        has_icon = False
        for node in head_node.children:
            has_title = has_title or isinstance(node, Tags.title)
            has_charset = has_charset or isinstance(node, Tags.meta) and node.attrs.get('charset')
            has_viewport = has_viewport or isinstance(node, Tags.meta) and node.attrs.get('viewport')
            has_icon = has_icon or isinstance(node, Tags.link) and node.attrs.get('rel') == 'icon'

        if not has_title:
            head_node += Tags.title(title_str)
        if not has_charset:
            head_node += Tags.meta(charset='utf-8')
        if not has_viewport:
            head_node += Tags.meta(name="viewport", content="width=device-width,initial-scale=1")
        if not has_icon:
            # favicon because of chromium bug, see https://stackoverflow.com/a/36104057
            head_node += Tags.link(rel="icon", type="image/png", href="data:image/png;base64,iVBORw0KGgo=")

        if self.env.VIABLE_DEV:
            compress = False
        else:
            compress = bool(re.search('gzip|br|deflate', cast(Any, request).headers.get('Accept-encoding', '')))
        indent = 0 if compress else 2
        newline = '' if compress else '\n'

        classes = body_node.make_classes({})

        if classes:
            head_node += Tags.style(raw('\n'.join(inst for _, inst in classes.values())))

        head_node += Tags.script(src='/viable.js') # , defer=True)

        req_data = request_data()
        if updates := req_data.updates():
            updates_json = json.dumps(updates, ensure_ascii=True, separators=(',', ':'))
            code = f'update({updates_json})'.replace('<', r'\x3C')
            body_node += Tags.script(raw(code), eval=True)
        elif not req_data.session_provided and req_data.did_request_session():
            body_node += Tags.script('refresh()', eval=True)

        html_str = (
            f'<!doctype html>{newline}' +
            Tags.html(head_node, body_node, lang='en').to_str(indent)
        )
        if compress:
            html_str = minify(html_str, 'html')

        resp = make_response(html_str)
        return resp

    def run(self, host: str | None = None, port: int | None = None):
        print(' *', self.env)

        if not self.env.VIABLE_DEV:
            try:
                from flask_compress import Compress # type: ignore
                Compress(self.app)
            except Exception as e:
                print('Not using flask_compress:', str(e), file=sys.stderr)

        if self.env.VIABLE_RUN:
            HOST = self.env.VIABLE_HOST or host
            PORT = self.env.VIABLE_PORT or port
            self.app.run(host=HOST, port=PORT, threaded=True)

    def suppress_flask_logging(self):
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
