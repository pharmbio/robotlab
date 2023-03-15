from __future__ import annotations

from contextlib import contextmanager
from dataclasses import *
from datetime import datetime
from subprocess import run, check_output
from threading import Lock
from typing_extensions import Self
from typing import *
from urllib.request import urlopen, Request
from pathlib import Path
import inspect
import json
import traceback as tb
import textwrap
import time
import sqlite3

from flask import Flask, jsonify, request
import flask

R = TypeVar('R')
A = TypeVar('A')

def try_json_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except:
        return s

def try_json_dumps(s: Any) -> str:
    try:
        return json.dumps(s)
    except:
        return json.dumps({'repr': repr(s)})

def small(x: Any) -> Any:
    if len(try_json_dumps(x)) > 80:
        return repr(x)[:80] + '...'
    else:
        return x

def json_request_args() -> dict[str, Any]:
    return {k: try_json_loads(v) for k, v in request.args.items()}

def make_sig(fn_name: str, *args: Any, **kwargs: Any):
    xs: list[str] = []
    for k, arg in (*enumerate(args), *kwargs.items()):
        if isinstance(k, str):
            ke = k + '='
        else:
            ke = ''
        xs += [f'{ke}{arg!r}']
    return fn_name + '(' + ', '.join(xs) + ')'

@dataclass(frozen=True)
class Proxy(Generic[R]):
    wrapped: Callable[..., R]
    call: Callable[..., Any]
    attr_path: list[str] = field(default_factory=list)

    def __getattr__(self, name: str) -> Proxy[R]:
        return replace(self, attr_path=[*self.attr_path, name])

    def __call__(self, *args: Any, **kwargs: Any) -> Proxy[R]:
        return self.call(self.attr_path, *args, **kwargs)

@dataclass(frozen=False)
class ResourceLock:
    lock: Lock = field(default_factory=Lock)
    is_avail: bool = True

    @contextmanager
    def ensure_available(self):
        with self.lock:
            if not self.is_avail:
                raise ValueError('Resource not available')
            self.is_avail = False
        try:
            yield
        finally:
            self.is_avail = True

def make_redirect_log_to(name: str, xs: List[str]):
    with sqlite3.connect('io.db') as con:
        con.executescript('''
            pragma synchronous=OFF;
            pragma journal_mode=WAL;
            create table if not exists io (
                t     timestamp default (strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime')),
                name  text,
                id    int,
                data  json
            );
            create index if not exists io_name_id on io(name, id);
        ''')
        [id] = con.execute('select ifnull(max(id) + 1, 0) from io where name = ?', [name]).fetchone()
    def log(*args: Any, **kwargs: Any):
        msg = ' '.join(map(str, args))
        if msg:
            print(f'{name}:', msg)
            xs.append(msg)
        with sqlite3.connect('io.db') as con:
            con.executescript('''
                pragma synchronous=OFF;
                pragma journal_mode=WAL;
            ''')
            if msg:
                data = {'msg': msg, **kwargs}
            else:
                data = kwargs
            con.execute(
                'insert into io (name, id, data) values (?, ?, json(?));',
                [name, id, try_json_dumps(data)],
            )
    return log

system_default_log = make_redirect_log_to('system', [])

@dataclass(frozen=False)
class Cell(Generic[A]):
    '''
    A mutable cell.
    '''
    value: A

@dataclass(frozen=True, kw_only=True)
class Machine:
    log_cell: Cell[Callable[..., None]] = field(default_factory=lambda: Cell(Machine.default_log), repr=False)
    resource_lock: ResourceLock = field(default_factory=ResourceLock, repr=False)

    def init(self):
        pass

    def log(self, *args: Any, **kwargs: Any):
        '''
        Make a log message.

        The positional arguments (*args) are joined and printed on stdout and included in the http response.
        The keywoard arguments (**kwargs) are saved as json (or repr if not possible), together with the
        message from the positional arguments (with key "msg") to the sqlite IO database io.db.

        Example. Assume the machine name is 'robotarm':

            self.log('speed', 100, speed_value=1.0)

        On stdout:

            robotarm: speed 100

        In the response:

            "log": [
                "speed 100",
                ...
            ]

        In the database:

            t                   | name     | id  | data
            --------------------+----------+-----+-----------------------------------------
            2023-03-15 15:55:18 | robotarm | 429 | {"msg": "speed 100", "speed_value": 1.0}

        If there are no positional arguments it is not printed to stdout nor included in the http response.
        '''
        return self.log_cell.value(*args, **kwargs)

    @staticmethod
    def default_log(*args: Any, **kwargs: Any):
        system_default_log(*args, **kwargs)

    @contextmanager
    def atomic(self):
        with self.resource_lock.ensure_available():
            yield

    def help(self):
        out: dict[str, list[str]] = {}
        for name, fn in self.__class__.__dict__.items():
            if not callable(fn):
                continue
            if name.startswith('_'):
                continue
            if name == 'init':
                continue
            sig = inspect.signature(fn)
            doc = fn.__doc__ or ""
            doc = textwrap.dedent(doc).strip()
            help = f'{name}{sig}\n\n{doc}'
            help = help.strip().splitlines()
            out[name] = help
        return out

    def timeit(self, desc: str=''):
        @contextmanager
        def worker():
            t0 = time.monotonic_ns()
            yield
            T = time.monotonic_ns() - t0
            self.log(f'{T/1e6:.1f}ms {desc}', secs=T/1e9)
        return worker()

    def routes(self, name: str, app: Any):
        from itertools import count
        unique = count(1).__next__

        def make_endpoint_name():
            return f'{name}{unique()}'

        @contextmanager
        def redirect_log(xs: List[str]):
            self.log_cell.value = make_redirect_log_to(name, xs)
            try:
                yield
            finally:
                self.log_cell.value = Machine.default_log

        def call(cmd: str, *args: Any, **kwargs: Any):
            xs: List[str] = []
            with redirect_log(xs):
                data = dict(cmd=cmd, args=args) | kwargs

                sig = make_sig(cmd, *args, **kwargs)
                self.log(sig, **data, type='call')
                try:
                    if cmd in Machine.__dict__.keys() or cmd.startswith('_') or cmd == 'init':
                        raise ValueError(f'Cannot call {cmd!r} on {name} remotely')
                    if cmd == 'up?':
                        return {'value': True}
                    fn = getattr(self, cmd, None)
                    if fn is None:
                        raise ValueError(f'No such command {cmd} on {name}')
                    with self.timeit(sig):
                        value = fn(*args, **kwargs)
                    if value is None:
                        self.log('return', **data, type='return', value=small(value))
                    else:
                        self.log('return', repr(small(value)), **data, type='return', value=small(value))
                    return {
                        'value': value,
                        'log': xs,
                    }
                except Exception as e:
                    for line in tb.format_exc().splitlines():
                        self.log(line)
                    self.log(**data, type='error', error=repr(e))
                    return {
                        'error': repr(e),
                        'log': xs,
                    }

        @app.get(f'/{name}/', endpoint=make_endpoint_name()) # type: ignore
        @app.get(f'/{name}', endpoint=make_endpoint_name()) # type: ignore
        def root(cmd: str="", arg: str=""):
            args = json_request_args()
            if args:
                cmd = args.pop('cmd')
                return jsonify(call(cmd, **args))
            else:
                url = request.url
                while url.endswith('/'):
                    url = url[:-1]
                return jsonify({url + '/' + name: doc for name, doc in self.help().items()})

        @app.get(f'/{name}/<string:cmd>', endpoint=make_endpoint_name()) # type: ignore
        def get0(cmd: str):
            return jsonify(call(cmd, **json_request_args()))

        @app.get(f'/{name}/<cmd>/<path:arg>', endpoint=make_endpoint_name()) # type: ignore
        def get(cmd: str, arg: str):
            return jsonify(call(cmd, *map(try_json_loads, arg.split('/')), **json_request_args()))

        @app.post(f'/{name}', endpoint=make_endpoint_name()) # type: ignore
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

        @app.post(f'/{name}/<cmd>', endpoint=make_endpoint_name()) # type: ignore
        def post_cmd(cmd: str):
            if request.form:
                req = dict(request.form)
            else:
                req = json.loads(request.data.decode())
            return jsonify(call(cmd, **req))

    @classmethod
    def remote(cls, name: str, host: str) -> Self:
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
        assert call(['up?'])
        return Proxy(cls, call) # type: ignore

@dataclass(frozen=True)
class Echo(Machine):
    def error(self, *args: str, **kwargs: Any):
        raise ValueError(f'error {args!r} {kwargs!r}')

    def echo(self, *args: str, **kwargs: Any) -> str:
        '''
        Returns the arguments.

        Example:
            curl -s http://localhost:5050/echo/echo/some/arguments?keywords=supported
        '''
        return f'echo {args!r} {kwargs!r}'

    def write_log(self, *args: str, **kwargs: Any):
        '''
        Writes to the log
        '''
        self.log(*args, **kwargs)

    def sleep(self, secs: int | float):
        with self.atomic():
            with self.timeit('sleep'):
                self.log(datetime.now().isoformat(sep=' '))
                time.sleep(float(secs))
                self.log(datetime.now().isoformat(sep=' '))

@dataclass(frozen=True)
class Git(Machine):
    def pull_and_shutdown(self):
        import os
        import signal
        run(['git', 'pull'])
        self.log('killing process...')
        os.kill(os.getpid(), signal.SIGTERM)
        self.log('killed.')

    def head(self) -> str:
        return check_output(['git', 'rev-parse', 'HEAD']).decode().strip()

    def show(self) -> list[str]:
        return check_output(['git', 'show', '--stat']).decode().strip().splitlines()

@dataclass
class Machines:
    ip: ClassVar[str]
    node_name: ClassVar[str]
    echo: Echo = Echo()
    git: Git = Git()

    @staticmethod
    def lookup_node_name(node_name: str) -> Machines:
        for m in Machines.__subclasses__():
            if m.node_name == node_name:
                return m()
        raise ValueError(f'{node_name} not configured (did you want to run with --test?)')

    @classmethod
    def remote(cls, host: str | None = None, port: int = 5050) -> Self:
        if host is None:
            url = f'http://{cls.ip}:{port}'
        else:
            url = f'http://{host}:{port}'
        d = {}
        for f in fields(cls):
            d[f.name] = f.default.__class__.remote(f.name, url) # type: ignore
        return cls(**d)

    def items(self) -> list[tuple[str, Machine]]:
        return list(self.__dict__.items())

    def serve(self, host: str | None = None, port: int = 5050):
        print('machines:')
        for k, v in self.items():
            print('    ' + k + ':', v)

        app = Flask(__name__)
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
        app.config['JSON_SORT_KEYS'] = False             # type: ignore

        for name, m in self.items():
            m.init()
            m.routes(name, app)

        @app.route('/io.db')
        def io_db():
            return flask.send_file( # type: ignore
                (Path.cwd() / 'io.db').resolve()
            )

        @app.get('/tail/<int:n>') # type: ignore
        @app.get('/tail/') # type: ignore
        @app.get('/tail') # type: ignore
        def tail(n: int=10):
            assert isinstance(n, int)
            args = json_request_args()
            raw = args.pop('raw', None)
            sep = str(args.pop('sep', '  ')).replace('tab', '\t')
            where = ''
            if name := args.pop('name', None):
                where = f'where name = {name!r}'
            if args:
                return f'Unsupported arguments: {", ".join(args.keys())}\n', 400
            if raw is not None:
                select = 'select rowid as row, t, name, id, data'
            else:
                select = 'select rowid as row, t, name, id, coalesce(json_extract(data, "$.msg"), data) as data'
            sql = f'''
                select * from (
                    {select} from io {where} order by t desc limit {n}
                ) order by t asc
            '''
            with sqlite3.connect('io.db') as con:
                rows = ['row t name id data'.split()] + [
                    [str(x) for x in row]
                    for row in con.execute(sql).fetchall()
                ]
            lengths = [
                max(len(x) for x in col)
                for col in zip(*rows)
            ]
            lines = [
                sep.join(x.ljust(n) for n, x in zip(lengths, row))
                for row in rows
            ]
            return '\n'.join(lines) + '\n'

        @app.get('/') # type: ignore
        def root():
            url = request.url
            while url.endswith('/'):
                url = url[:-1]
            d: dict[str, str] = {}
            for name, m in self.items():
                d[url + '/' + name] = str(m)
            d[url + '/io.db'] = 'Download the IO database in binary sqlite'
            d[url + '/tail'] = 'Show last 10 lines from the IO database'
            d[url + '/tail/<N>'] = 'Show last N lines from the IO database'
            return jsonify(d)

        if host is None:
            host = self.ip
        app.run(host=host, port=port, threaded=True, processes=1)
