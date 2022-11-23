from __future__ import annotations
from dataclasses import *
from typing import *

from itsdangerous import Serializer
from inspect import signature

import json
import re

from .freeze_function import FrozenFunction

from pbutils import TODO

@dataclass(frozen=True)
class JS:
    fragment: str

    @staticmethod
    def convert_dict(d: dict[str, Any | JS]) -> JS:
        TODO('remove deprecated')
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
        TODO('remove deprecated')
        return JS.convert_dict({k: JS.convert_dict(vs) for k, vs in d.items()})

def js(fragment: str) -> Any:
    return JS(fragment)

P = ParamSpec('P')
R = TypeVar('R')

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
        func = FrozenFunction.freeze(f)
        js_args_keys = [k for k, _ in js_args.items()]
        js_args_vals = [v for _, v in js_args.items()]
        func_and_py_args_and_js_args_keys = (func, py_args, js_args_keys)
        enc = self.serializer.dumps(func_and_py_args_and_js_args_keys)
        if isinstance(enc, bytes):
            enc = enc.decode()
        call_args = ','.join([
            json.dumps(enc),
            *js_args_vals,
        ])
        return f'call({call_args})\n/* {f} {py_args} {js_args_keys} */'

    def handle_call(self, enc: str, js_args_vals: list[Any]) -> None:
        func: FrozenFunction
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
        f = func.thaw()
        _ret = f(*args, **kwargs)
        TODO('should we add support for return values? example evaluate some JS to interface with 3rd party lib')
        return
        # if isinstance(ret, Response):
        #     return ret
        # else:
        #     return jsonify(refresh=True)

