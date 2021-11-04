from __future__ import annotations
from typing import *

from contextlib import contextmanager
from dataclasses import *
from threading import Event
import abc
import os
import pickle
import re
import secrets
import sys
import textwrap
import time
import traceback

from flask import Flask, request, jsonify
from itsdangerous import Serializer, URLSafeSerializer

def trim(s: str, soft: bool=False, sep: str=' '):
    if soft:
        return textwrap.dedent(s).strip()
    else:
        return re.sub(r'\s*\n\s*', sep, s, flags=re.MULTILINE).strip()

def esc(txt: str, __table: dict[int, str] = str.maketrans({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    "'": "&apos;",
    '"': "&quot;",
    '`': "&#96;",
})) -> str:
    return txt.translate(__table)

def css_esc(txt: str, __table: dict[int, str] = str.maketrans({
    "<": r"\<",
    ">": r"\>",
    "&": r"\&",
    "'": r"\'",
    '"': r"\❞",
    '\\': "\\\\",
})) -> str:
    return txt.translate(__table)

class IAddable:
    def __init__(self):
        self.value = None

    def __iadd__(self, value: str):
        self.value = value
        return self

class Node(abc.ABC):
    @abc.abstractmethod
    def to_strs(self, *, indent: int=0, i: int=0) -> Iterable[str]:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.to_str()

    def to_str(self, indent: int=2) -> str:
        sep = '' if indent == 0 else '\n'
        return sep.join(self.to_strs(indent=indent))

class Tag(Node):
    _attributes_ = {'children', 'attrs', 'inline_css', 'inline_sheet'}
    def __init__(self, *children: Node | str | dict[str, str | bool | None], **attrs: str | bool | None):
        self.children: list[Node] = []
        self.attrs: dict[str, str | bool | None] = {}
        self.inline_css: list[str] = []
        self.inline_sheet: list[str] = []
        self.append(*children)
        self.extend(attrs)

    def append(self, *children: Node | str | dict[str, str | bool | None], **kws: str | bool | None) -> Tag:
        self.children += [
            text(child) if isinstance(child, str) else child
            for child in children
            if not isinstance(child, dict)
        ]
        for child in children:
            if isinstance(child, dict):
                self.extend(child)
        self.extend(kws)
        return self

    def extend(self, attrs: dict[str, str | bool | None] = {}, **kws: str | bool | None) -> Tag:
        for k, v in {**attrs, **kws}.items():
            if k == 'css':
                assert isinstance(v, str), 'inline css must be str'
                self.inline_css += [v]
                continue
            if k == 'sheet':
                assert isinstance(v, str), 'inline css must be str'
                self.inline_sheet += [v]
                continue
            k = k.strip("_").replace("_", "-")
            if k == 'className':
                k = 'class'
            if k == 'htmlFor':
                k = 'for'
            if k in self.attrs:
                if k == 'style':
                    sep = ';'
                elif k.startswith('on'):
                    sep = ';'
                elif k == 'class':
                    sep = ' '
                else:
                    raise ValueError(f'only event handlers, styles and classes can be combined, not {k}')
                if not isinstance(v, str):
                    raise ValueError(f'attribute {k}={v} not str' )
                self.attrs[k] = str(self.attrs[k]).rstrip(sep) + sep + v.lstrip(sep)
            else:
                self.attrs[k] = v
        return self

    def __iadd__(self, other: str | Tag) -> Tag:
        return self.append(other)

    def __getattr__(self, attr: str) -> IAddable:
        if attr in self._attributes_:
            return self.__dict__[attr]
        return IAddable()

    def __setattr__(self, attr: str, value: IAddable):
        if attr in self._attributes_:
            self.__dict__[attr] = value
        else:
            assert isinstance(value, IAddable)
            self.extend({attr: value.value})

    def tag_name(self) -> str:
        return self.__class__.__name__

    def to_strs(self, *, indent: int=2, i: int=0) -> Iterable[str]:
        if self.attrs:
            attrs = ' ' + ' '.join(
                k if v is True else
                f'{k}={v}' if
                    # https://html.spec.whatwg.org/multipage/syntax.html#unquoted
                    re.match(r'[\w\-\.,:;/+@#?(){}[\]]+$', v)
                else f'{k}="{esc(v)}"'
                for k, v in sorted(self.attrs.items())
                if v is not False
                if v is not None
            )
        else:
            attrs = ''
        name = self.tag_name()
        if len(self.children) == 0:
            yield ' ' * i + f'<{name}{attrs}></{name}>'
        elif len(self.children) == 1 and isinstance(self.children[0], text):
            yield ' ' * i + f'<{name}{attrs}>{self.children[0].to_str()}</{name}>'
        else:
            yield ' ' * i + f'<{name}{attrs}>'
            for child in self.children:
                if child:
                    yield from child.to_strs(indent=indent, i=i+indent)
            yield ' ' * i + f'</{name}>'

    def make_classes(self, classes: dict[str, tuple[str, str]], minify: bool=True) -> dict[str, tuple[str, str]]:
        for decls in self.inline_sheet:
            if decls not in classes:
                norm = trim(decls, soft=not minify, sep=' ')
                classes[decls] = '', norm
        self.inline_sheet.clear()
        for decls in self.inline_css:
            if decls in classes:
                name, _ = classes[decls]
            else:
                name = f'css-{len(classes)}'
                norm = trim(decls, soft=not minify, sep=' ')
                if '&' in norm:
                    inst = norm.replace('&', f'[{name}]')
                else:
                    if minify:
                        inst = f'[{name}]{{{norm}}}'
                    else:
                        norm = '\n' + textwrap.indent(norm, prefix='    ') + '\n'
                        inst = f'[{name}] {{{norm}}}'
                classes[decls] = name, inst
            self.extend({name: True})
        self.inline_css.clear()
        for child in self.children:
            if isinstance(child, Tag):
                child.make_classes(classes, minify)
        return classes

class tag(Tag):
    _attributes_ = {*Tag._attributes_, 'name'}
    def __init__(self, name: str, *children: Node | str, **attrs: str | int | bool | None | float):
        super(tag, self).__init__(*children, **attrs)
        self.name = name

    def tag_name(self) -> str:
        return self.name

class text(Node):
    def __init__(self, txt: str, raw: bool=False):
        super(text, self).__init__()
        self.raw = raw
        if raw:
            self.txt = txt
        else:
            self.txt = esc(txt)

    def tag_name(self) -> str:
        return ''

    def to_strs(self, *, indent: int=0, i: int=0) -> Iterable[str]:
        if self.raw:
            yield self.txt
        else:
            yield ' ' * i + self.txt

def raw(txt: str) -> text:
    return text(txt, raw=True)

def throw(e: Exception):
    raise e

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

def function_name(f: Callable[..., Any]) -> str:
    if f.__module__ == '__main__':
        return f.__qualname__
    else:
        return f.__module__ + '.' + f.__qualname__

@dataclass(frozen=True)
class Exposed:
    _f: Callable[..., Any]
    _serializer: Serializer

    def __call__(self, *args: Any, **kws: Any) -> Any:
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

    def call(self, *args: Any, **kws: Any) -> str:
        '''
        The handler, optionally already applied to some arguments, which may be javascript fragments.

        >>> @serve.expose
        ... def Sum(*args: str | int | float) -> float
        ...     res = sum(map(float, args))
        ...     print(res)
        ...     return res
        >>> elem = input(onclick=Sum.call(1, js('this.value')))
        '''
        py_args: list[Any] = []
        js_args: list[Any] = []
        for arg in args:
            if isinstance(arg, js):
                js_args += [arg.fragment]
            else:
                assert not js_args
                py_args += [arg]
        name = function_name(self._f)
        payload_tuple = (name, *py_args, kws)
        payload = self._serializer.dumps(payload_tuple)
        if isinstance(payload, bytes):
            payload = payload.decode()
        args_csv = ",".join((repr(name), repr(payload), *js_args))
        return f'call({args_csv})'

app = Flask(__name__)

@dataclass
class Serve:
    # Routes
    routes: dict[str, Callable[..., Iterable[Tag | str | dict[str, str]]]] = field(default_factory=dict)

    # Exposed functions
    exposed: dict[str, Exposed] = field(default_factory=dict)
    _serializer: Serializer = field(default_factory=serializer_factory)

    # State for reloading
    notify_reload: Event = field(default_factory=Event)

    def expose(self, f: Callable[..., Any]) -> Exposed:
        name = function_name(f)
        assert name != '<lambda>'
        if name in self.exposed:
            assert self.exposed[name].f == f # type: ignore
        res = Exposed(f, self._serializer)
        self.exposed[name] = res
        return res

    def route(self, rule: str = '/'):
        def inner(f: Callable[..., Iterable[Tag | str | dict[str, str]]]):
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
        def inner(f: Callable[..., Iterable[Tag | str | dict[str, str]]]):
            self.route(rule)(f)
            self.run()
        return inner

    def saveas(self, path: str):
        def inner(f: Callable[..., Iterable[Tag | str | dict[str, str]]]):
            with app.test_request_context():
                with open(path, 'w') as fp:
                    fp.write(self.view_callable(f, include_hot=False))
                print(path, 'written')
            return f
        return inner

    def reload(self) -> None:
        self.notify_reload.set()
        self.notify_reload.clear()

    def view(self, rule: str, *args: Any, **kws: Any) -> str:
        return self.view_callable(self.routes[rule], *args, **kws)

    def view_callable(self, f: Callable[..., Iterable[Tag | str | dict[str, str]]], *args: Any, include_hot: bool=True, **kws: Any) -> str:
        try:
            parts = f(*args, **kws)
            body_node = body(*cast(Any, parts))
            title_str = f.__name__
        except BaseException as e:
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

        minify = bool(re.search('gzip|br|deflate', cast(Any, request).headers.get('Accept-encoding', '')))
        indent = 0 if minify else 2
        newline = '' if minify else '\n'

        classes = body_node.make_classes({}, minify=minify)

        if classes:
            head_node += style(*[raw(inst) for name, inst in classes.values()])

        if include_hot:
            head_node += script(src="/hot.js", defer=True)

        return (
            f'<!doctype html>{newline}' +
            html(head_node, body_node, lang='en').to_str(indent)
        )

    def run(self):
        @app.post('/reload')
        def reload():
            self.reload()
            return self.last_err or '', {'Content-Type': 'text/plain'}

        @app.post('/call/<name>')
        def call(name: str):
            try:
                payload = request.json["payload"]                      # type: ignore
                msg_name, *args, kws = self._serializer.loads(payload) # type: ignore
                assert name == msg_name
                more_args = request.json["args"]                       # type: ignore
                ret = self.exposed[msg_name](*args, *more_args, **kws) # type: ignore
                return jsonify(ret)
            except:
                traceback.print_exc()
                return '', 400

        @app.route('/hot.js')
        def hot_js_route():
            return hot_js, {'Content-Type': 'application/javascript'}

        @app.route('/ping')
        def ping():
            return jsonify({'refresh': self.notify_reload.wait(115)})

        try:
            from flask_compress import Compress # type: ignore
            Compress(app)
        except Exception as e:
            print('Not using flask_compress:', str(e), file=sys.stderr)

        if sys.argv[0].endswith('.py'):
            print('Running app...')
            # use flask's SERVER_NAME instead
            app.config['SERVER_NAME'] = os.environ.get('SERVER_NAME')
            app.run()

serve = Serve()

hot_js = str(r'''
    function get_query() {
        return Object.fromEntries(new URL(location.href).searchParams)
    }
    function update_query(kvs) {
        return set_query({...get_query(), ...kvs})
    }
    function set_query(kvs) {
        let next = new URL(location.href)
        next.search = new URLSearchParams(kvs)
        history.replaceState(null, null, next.href)
    }
    function with_pathname(s) {
        let next = new URL(location.href)
        next.pathname = s
        return next.href
    }
    async function call(name, payload, ...args) {
        const resp = await fetch("/call/" + name, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payload, args }),
        })
        const body = await resp.json()
        if (body && typeof body === 'object') {
            if (body.eval) {
                (0, eval)(body.eval)
            }
            if (body.set_query) {
                set_query(body.set_query)
            }
            if (body.update_query) {
                update_query(body.update_query)
            }
            if (body.replace) {
                history.replaceState(null, null, with_pathname(body.replace))
            }
            if (body.goto) {
                history.pushState(null, null, with_pathname(body.goto))
            }
            if (body.refresh) {
                refresh()
            }
            if (body.log) {
                console.log(body.log)
            }
        }
        return resp
    }
    function morph(prev, next) {
        if (
            prev.nodeType === Node.ELEMENT_NODE &&
            next.nodeType === Node.ELEMENT_NODE &&
            prev.tagName === next.tagName
        ) {
            for (let name of prev.getAttributeNames()) {
                if (!next.hasAttribute(name)) {
                    prev.removeAttribute(name)
                }
            }
            for (let name of next.getAttributeNames()) {
                if (
                    !prev.hasAttribute(name) ||
                    next.getAttribute(name) !== prev.getAttribute(name)
                ) {
                    prev.setAttribute(name, next.getAttribute(name))
                }
            }
            if (prev.tagName === 'INPUT' && (document.activeElement !== prev || next.getAttribute('truth') === 'server')) {
                if (prev.type == 'radio' && document.activeElement.name === prev.name) {
                    // pass
                } else {
                    if (next.value !== prev.value) {
                        prev.value = next.value
                    }
                    if (prev.checked !== next.hasAttribute('checked')) {
                        prev.checked = next.hasAttribute('checked')
                    }
                }
            }
            const pc = [...prev.childNodes]
            const nc = [...next.childNodes]
            const num_max = Math.max(pc.length, nc.length)
            for (let i = 0; i < num_max; ++i) {
                if (i >= nc.length) {
                    prev.removeChild(pc[i])
                } else if (i >= pc.length) {
                    prev.appendChild(nc[i])
                } else {
                    morph(pc[i], nc[i])
                }
            }
        } else if (
            prev.nodeType === Node.TEXT_NODE &&
            next.nodeType === Node.TEXT_NODE
        ) {
            if (prev.textContent !== next.textContent) {
                prev.textContent = next.textContent
            }
        } else {
            prev.replaceWith(next)
        }
    }
    let in_progress = false
    let rejected = false
    async function refresh(i=0, and_then) {
        if (!and_then) {
            if (in_progress) {
                rejected = true
                return
            }
            in_progress = true
        }
        let text = null
        try {
            const resp = await fetch(location.href)
            text = await resp.text()
        } catch (e) {
            if (i > 0) {
                window.setTimeout(() => refresh(i-1, and_then), i < 300 ? 1000 : 50)
            } else {
                console.warn('timeout', e)
            }
        }
        if (text !== null) {
            try {
                const parser = new DOMParser()
                const doc = parser.parseFromString(text, "text/html")
                morph(document.head, doc.head)
                morph(document.body, doc.body)
                for (const script of document.querySelectorAll('script[eval]')) {
                    const global_eval = eval
                    global_eval(script.textContent)
                }
            } catch(e) {
                console.warn(e)
            }
            if (and_then) {
                in_progress = false
                and_then()
            } else if (in_progress) {
                in_progress = false
                if (rejected) {
                    rejected = false
                    refresh()
                }
            }
        }
    }
    async function poll() {
        while (true) {
            try {
                const resp = await fetch('/ping')
                body = await resp.json()
                if (body.refresh) {
                    break
                }
            } catch {
                break
            }
        }
        refresh(600, poll)
    }
    window.onpopstate = () => refresh()
    function input_values() {
        const inputs = document.querySelectorAll('input:not([type=radio]),input[type=radio]:checked,select')
        const vals = {}
        for (let i of inputs) {
            if (i.getAttribute('truth') == 'server') {
                continue
            }
            if (!i.name) {
                console.error(i, 'has no name attribute')
                continue
            }
            if (i.type == 'radio') {
                console.assert(i.checked)
                vals[i.name] = i.value
            } else if (i.type == 'checkbox') {
                vals[i.name] = i.checked
            } else {
                vals[i.name] = i.value
            }
        }
        return vals
    }
''')
if os.environ.get('VIABLE_NO_HOT'):
    pass
else:
    hot_js += 'poll()'
try:
    import utils
    with utils.timeit('esbuild'):
        from subprocess import run
        res = run(["esbuild", "--minify"], capture_output=True, input=hot_js, encoding='utf-8')
        hot_js = res.stdout
        if res.stderr:
            print(res.stderr, file=sys.stderr)
except:
    hot_js = trim(hot_js, sep='\n')

def queue_refresh(after_ms: float=100):
    js = f'clearTimeout(window._qrt); window._qrt = setTimeout(()=>requestAnimationFrame(()=>refresh()),{after_ms})'
    return script(raw(js), eval=True)

class a(Tag): pass
class abbr(Tag): pass
class address(Tag): pass
class area(Tag): pass
class article(Tag): pass
class aside(Tag): pass
class audio(Tag): pass
class b(Tag): pass
class base(Tag): pass
class bdi(Tag): pass
class bdo(Tag): pass
class blockquote(Tag): pass
class body(Tag): pass
class br(Tag): pass
class button(Tag): pass
class canvas(Tag): pass
class caption(Tag): pass
class cite(Tag): pass
class code(Tag): pass
class col(Tag): pass
class colgroup(Tag): pass
class data(Tag): pass
class datalist(Tag): pass
class dd(Tag): pass
# class del(Tag): pass
class details(Tag): pass
class dfn(Tag): pass
class dialog(Tag): pass
class div(Tag): pass
class dl(Tag): pass
class dt(Tag): pass
class em(Tag): pass
class embed(Tag): pass
class fieldset(Tag): pass
class figcaption(Tag): pass
class figure(Tag): pass
class footer(Tag): pass
class form(Tag): pass
class h1(Tag): pass
class h2(Tag): pass
class h3(Tag): pass
class h4(Tag): pass
class h5(Tag): pass
class h6(Tag): pass
class head(Tag): pass
class header(Tag): pass
class hgroup(Tag): pass
class hr(Tag): pass
class html(Tag): pass
class i(Tag): pass
class iframe(Tag): pass
class img(Tag): pass
class input(Tag): pass
class ins(Tag): pass
class kbd(Tag): pass
class label(Tag): pass
class legend(Tag): pass
class li(Tag): pass
class link(Tag): pass
class main(Tag): pass
# class map(Tag): pass
class mark(Tag): pass
class menu(Tag): pass
class meta(Tag): pass
class meter(Tag): pass
class nav(Tag): pass
class noscript(Tag): pass
# class object(Tag): pass
class ol(Tag): pass
class optgroup(Tag): pass
class option(Tag): pass
class output(Tag): pass
class p(Tag): pass
class param(Tag): pass
class picture(Tag): pass
class pre(Tag): pass
class progress(Tag): pass
class q(Tag): pass
class rp(Tag): pass
class rt(Tag): pass
class ruby(Tag): pass
class s(Tag): pass
class samp(Tag): pass
class script(Tag): pass
class section(Tag): pass
class select(Tag): pass
class slot(Tag): pass
class small(Tag): pass
class source(Tag): pass
class span(Tag): pass
class strong(Tag): pass
class style(Tag): pass
class sub(Tag): pass
class summary(Tag): pass
class sup(Tag): pass
class table(Tag): pass
class tbody(Tag): pass
class td(Tag): pass
class template(Tag): pass
class textarea(Tag): pass
class tfoot(Tag): pass
class th(Tag): pass
class thead(Tag): pass
# class time(Tag): pass
class title(Tag): pass
class tr(Tag): pass
class track(Tag): pass
class u(Tag): pass
class ul(Tag): pass
class var(Tag): pass
class video(Tag): pass
class wbr(Tag): pass

def Input(store: dict[str, str | bool], name: str, type: str, value: str | None = None, default: str | bool | None = None, **attrs: str | None) -> input | option:
    if default is None:
        default = ""
    state = request.args.get(name, default)
    if type == 'checkbox':
        state = str(state).lower() == 'true'
    store[name] = state
    if type == 'checkbox':
        return input(type=type, name=name, checked=bool(state), **attrs)
    elif type == 'radio':
        return input(type=type, name=name, value=value, checked=state == value, **attrs)
    elif type == 'option':
        return option(type=type, value=value, selected=state == value, **attrs)
    else:
        return input(type=type, name=name, value=str(state), **attrs)

if 0:
    test = body()
    test += div()
    test.css += 'lol;'
    print(test)
