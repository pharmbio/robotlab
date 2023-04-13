from __future__ import annotations
from typing import *
from dataclasses import *

from datetime import datetime
from subprocess import check_output, run
from threading import RLock
from typing_extensions import Self
from urllib.request import urlopen, Request
from pathlib import Path
import contextlib
import inspect
import json
import sqlite3
import textwrap
import time
import platform
import traceback as tb

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
    rlock: RLock = field(default_factory=RLock)

    @contextlib.contextmanager
    def ensure_available(self):
        ok = self.rlock.acquire(blocking=False)
        if not ok:
            raise ValueError('Resource not available')
        try:
            yield
        finally:
            self.rlock.release()

@dataclass(frozen=True)
class Log:
    _log: Callable[..., None]
    def __call__(self, *args: Any, **kwargs: Any):
        self._log(*args, **kwargs)

    @classmethod
    def make(cls, name: str, xs: List[str] | None = None, stdout: bool=True) -> Log:
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
        id: None | int = None
        def log(*args: Any, **kwargs: Any):
            nonlocal id
            msg = ' '.join(map(str, args))
            if msg:
                if stdout:
                    print(f'{name}:', msg)
                if xs is not None:
                    xs.append(msg)
            with sqlite3.connect('io.db', isolation_level=None) as con:
                con.executescript('''
                    pragma synchronous=OFF;
                    pragma journal_mode=WAL;
                ''')
                if msg:
                    data = {'msg': msg, **kwargs}
                else:
                    data = kwargs
                needs_commit = False
                if id is None:
                    con.execute('begin exclusive')
                    [id] = con.execute('select ifnull(max(id) + 1, 0) from io where name = ?', [name]).fetchone()
                    needs_commit = True
                con.execute(
                    'insert into io (name, id, data) values (?, ?, json(?));',
                    [name, id, try_json_dumps(data)],
                )
                if needs_commit:
                    con.execute('commit')
        return Log(log)

system_default_log = Log.make('system')

@dataclass(frozen=False)
class Cell(Generic[A]):
    '''
    A mutable cell.
    '''
    value: A

@dataclass(frozen=True, kw_only=True)
class Machine:
    log_cell: Cell[Log] = field(default_factory=lambda: Cell(Machine.default_log), repr=False)
    resource_lock: ResourceLock = field(default_factory=ResourceLock, repr=False)

    def init(self):
        pass

    @property
    def log(self) -> Log:
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
        return getattr(flask.g, 'log', self.default_log)

    default_log: ClassVar[Log] = system_default_log

    @contextlib.contextmanager
    def atomic(self):
        with self.resource_lock.ensure_available():
            yield

    def help(self):
        out: dict[str, list[str]] = {}
        for name in dir(self):
            fn = getattr(self, name)
            if not callable(fn):
                continue
            if name.startswith('_'):
                continue
            if name in 'init help remote routes timeit default_log log atomic'.split():
                continue
            sig = inspect.signature(fn)
            doc = fn.__doc__ or ""
            doc = textwrap.dedent(doc).strip()
            help = f'{name}{sig}\n\n{doc}'
            help = help.strip().splitlines()
            out[name] = help
        return out

    def timeit(self, desc: str=''):
        @contextlib.contextmanager
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

        def call(cmd: str, *args: Any, **kwargs: Any):
            xs: List[str] = []
            flask.g.log = Log.make(name, xs)
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
    def remote(cls, name: str, host: str, skip_up_check: bool) -> Self:
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
            # print(url)
            req = Request(
                url,
                data=json.dumps(data).encode(),
                headers={'Content-type': 'application/json'},
            )
            # from pprint import pp
            # pp((url, data, '...'))
            res = json.loads(urlopen(req, timeout=ten_minutes).read())
            # pp((url, data, '=', res))
            if 'value' in res:
                return res['value']
            else:
                raise ValueError(res['error'])
        if not skip_up_check:
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
            self.log(datetime.now().isoformat(sep=' '))
            time.sleep(float(secs))
            self.log(datetime.now().isoformat(sep=' '))

import functools

@functools.cache
def git_head_show_at_startup():
    try:
        return (
            check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            check_output(['git', 'show', '--stat'], text=True).strip(),
        )
    except Exception as e:
        return (str(e), str(e))

git_head_show_at_startup()

@dataclass(frozen=True)
class Git(Machine):
    def head(self) -> str:
        '''git rev-parse HEAD'''
        return check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()

    def head_at_startup(self) -> str:
        return git_head_show_at_startup()[0]

    def show(self) -> list[str]:
        '''git show --stat'''
        return check_output(['git', 'show', '--stat'], text=True).strip().splitlines()

    def show_at_startup(self) -> list[str]:
        return git_head_show_at_startup()[1].splitlines()

    def branch(self) -> str:
        '''git branch --show-current'''
        return check_output(['git', 'branch', '--show-current'], text=True).strip()

    def status(self) -> list[str]:
        '''git status -s'''
        return check_output(['git', 'status', '-s'], text=True).strip().splitlines()

    def checkout(self, branch: str):
        '''git checkout -B {branch}; git branch --set-upstream-to origin/{branch} {branch}; git pull && kill -TERM {os.getpid()}'''
        self.log(res := run(['git', 'fetch'], text=True, capture_output=True))
        res.check_returncode()
        self.log(res := run(['git', 'checkout', '-B', branch], text=True, capture_output=True))
        res.check_returncode()
        self.log(res := run(['git', 'branch', '--set-upstream-to', f'origin/{branch}', branch], text=True, capture_output=True))
        res.check_returncode()
        self.pull_and_shutdown()

    def pull_and_shutdown(self):
        '''git pull && kill -TERM {os.getpid()}'''
        self.log(res := check_output(['git', 'pull'], text=True))
        if res.strip() != 'Already up to date.':
            self.shutdown()

    def shutdown(self):
        '''kill -TERM {os.getpid()}'''
        import os
        import signal
        self.log('killing process...')
        os.kill(os.getpid(), signal.SIGTERM)
        self.log('killed.')

@dataclass
class Machines:
    ip: ClassVar[str]
    node_name: ClassVar[str]
    skip_up_check: ClassVar[bool] = False
    echo: Echo = Echo()
    git: Git = Git()

    @staticmethod
    def lookup_node_name(node_name: str | None=None) -> Machines:
        if node_name is None:
            node_name = platform.node()
        for m in Machines.__subclasses__():
            if m.node_name == node_name:
                return m()
        raise ValueError(f'{node_name} not configured (did you want to run with --test?)')

    @staticmethod
    def ip_from_node_name(node_name: str | None=None) -> str | None:
        try:
            return Machines.lookup_node_name(node_name=node_name).ip
        except ValueError:
            return None

    @classmethod
    def remote(cls, host: str | None = None, port: int = 5050) -> Self:
        if host is None:
            url = f'http://{cls.ip}:{port}'
        else:
            url = f'http://{host}:{port}'
        d = {}
        for f in fields(cls):
            d[f.name] = f.default.__class__.remote(f.name, url, skip_up_check=cls.skip_up_check) # type: ignore
        return cls(**d)

    def items(self) -> list[tuple[str, Machine]]:
        return list(self.__dict__.items())

    def serve(self, host: str | None = None, port: int = 5050):
        print('machines:')
        for k, v in self.items():
            print('    ' + k + ':', v)

        app = Flask(__name__)
        try:
            app.json.compact = False    # type: ignore
            app.json.sort_keys = False  # type: ignore
        except AttributeError:
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
            app.config['JSON_SORT_KEYS'] = False             # type: ignore

        for name, m in self.items():
            m.init()
            m.routes(name, app)

        @app.route('/<string:name>.db')
        def get_db(name: str):
            assert name.isascii() and name.isidentifier()
            name_db = f'{name}.db'
            with contextlib.closing(sqlite3.connect(name_db)) as con:
                con.execute('pragma wal_checkpoint(full);')
                return flask.send_file( # type: ignore
                    Path(name_db).resolve(),
                    download_name=name_db,
                    as_attachment=True
                )

        @app.route('/<string:name>.sql')
        def get_sql(name: str):
            assert name.isascii() and name.isidentifier()
            with contextlib.closing(sqlite3.connect(f'{name}.db')) as con:
                return '\n'.join(con.iterdump()) + '\n'

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
            lengths[-1] = 0
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
            d[url + '/io.sql'] = 'Download the IO database as sqlite dump'
            d[url + '/io.db'] = 'Download the IO database in binary sqlite'
            d[url + '/tail'] = 'Show last 10 lines from the IO database'
            d[url + '/tail/<N>'] = 'Show last N lines from the IO database'
            return jsonify(d)

        if host is None:
            host = self.ip
        app.run(host=host, port=port, threaded=True, processes=1)
