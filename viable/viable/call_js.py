from __future__ import annotations
from dataclasses import *
from typing import *

from itsdangerous import Serializer
from inspect import signature

import json

from .freeze_function import freeze, thaw, Frozen

from pbutils import TODO

@dataclass(frozen=True)
class JS:
    fragment: str
    def __repr__(self):
        return f'js({self.fragment!r})'

def js(fragment: str) -> Any:
    return JS(fragment)

P = ParamSpec('P')
R = TypeVar('R')

from pbutils import p
import pickle

@dataclass(frozen=True)
class _star_repr:
    value: Any
    def __repr__(self):
        if not self.value:
            return ''
        else:
            return '**' + repr(self.value)

@dataclass(frozen=True)
class CallJS:
    serializer: Serializer
    def store_call(self, f: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> str:
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
        func = freeze(f)
        js_args_keys = [k for k, _ in js_args.items()]
        js_args_vals = [v for _, v in js_args.items()]
        func_and_py_args_and_js_args_keys = (func, py_args, js_args_keys)

        # pkl = pickle.dumps(func_and_py_args_and_js_args_keys | p)
        # s = pkl.decode('ascii', errors='ignore')
        # s = ' '.join(''.join(c if c.isprintable() else ' ' for c in s).split())
        # (len(pkl), s) | p

        enc = self.serializer.dumps(func_and_py_args_and_js_args_keys)
        if isinstance(enc, bytes):
            enc = enc.decode()
        call_args = ','.join([
            json.dumps(enc),
            *js_args_vals,
        ])
        return f'call({call_args})\n/* {f.__module__}.{f.__qualname__}{(*b.args, _star_repr(b.kwargs))} */'

    def handle_call(self, enc: str, js_args_vals: list[Any]) -> None:
        func: Frozen
        py_args: dict[str | int, Any]
        js_args_keys: list[str | int]
        func, py_args, js_args_keys = self.serializer.loads(enc)
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
        f = thaw(func)
        _ret = f(*args, **kwargs)
        TODO('should we add support for return values? example evaluate some JS to interface with 3rd party lib')
        return
        # if isinstance(ret, Response):
        #     return ret
        # else:
        #     return jsonify(refresh=True)

