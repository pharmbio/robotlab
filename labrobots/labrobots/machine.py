from __future__ import annotations
from typing import *
from dataclasses import *

from datetime import datetime
from threading import RLock
from urllib.request import urlopen, Request
import contextlib
import inspect
import json
import textwrap
import time
import traceback as tb

from flask import jsonify, request
import flask

from .log import Log, try_json_dumps, system_default_log

R = TypeVar('R')
A = TypeVar('A')

def try_json_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except:
        return s

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
class ExclusiveLock:
    '''
    A lock for exclusive use of a resource. If it is already taken raises an error.
    '''
    rlock: RLock = field(default_factory=RLock)

    @contextlib.contextmanager
    def exclusive(self):
        ok = self.rlock.acquire(blocking=False)
        if not ok:
            raise ValueError('Resource not available (exclusive lock taken)')
        try:
            yield
        finally:
            self.rlock.release()

@dataclass(frozen=False)
class Cell(Generic[A]):
    '''
    A mutable cell.
    '''
    value: A

T = TypeVar('T', bound='Machine')

@dataclass(frozen=True, kw_only=True)
class Machine:
    log_cell: Cell[Log] = field(default_factory=lambda: Cell(Machine.default_log), repr=False)
    exclusive_lock: ExclusiveLock = field(default_factory=ExclusiveLock, repr=False)

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
    def exclusive(self):
        '''
        Try to get the exclusive lock or fail if already taken.
        '''
        with self.exclusive_lock.exclusive():
            yield

    def help(self):
        out: dict[str, list[str]] = {}
        for name in dir(self):
            fn = getattr(self, name)
            if not callable(fn):
                continue
            if name.startswith('_'):
                continue
            if name in 'init help remote routes timeit default_log log exclusive'.split():
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
    def remote(cls: Type[T], name: str, host: str, skip_up_check: bool, timeout_secs: int=10 * 60) -> T:
        def call(attr_path: list[str], *args: Any, **kwargs: Any) -> Any:
            assert len(attr_path) == 1
            cmd = attr_path[0]
            url = host.rstrip('/') + '/' + name
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
            try:
                res = json.loads(urlopen(req, timeout=timeout_secs).read())
            except OSError as e:
                raise OSError(f'Communication error with {name}: {getattr(e, "reason", str(e))}')
            # pp((url, data, '=', res))
            if 'value' in res:
                return res['value']
            elif 'error' in res:
                raise ValueError(f'Error from {name}: {res["error"]}')
            else:
                raise ValueError(f'Communication error with {name}: {res=}')
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
        with self.exclusive():
            self.log(datetime.now().isoformat(sep=' '))
            time.sleep(float(secs))
            self.log(datetime.now().isoformat(sep=' '))
