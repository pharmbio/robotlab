# type: ignore
from __future__ import annotations
from dataclasses import *
from typing import *
from contextlib import contextmanager

__dataclasses: dict[str, Any] = {}

@contextmanager
def temp_scope():
    global __dataclasses
    saved = __dataclasses
    __dataclasses = __dataclasses.copy()
    yield
    __dataclasses = saved

# this could be done automatically by looking at imported modules ...
def add_dataclass(t: Any):
    assert is_dataclass(t)
    assert t.__name__ not in __dataclasses
    __dataclasses[t.__name__] = t

def add_abc(t: Any):
    for c in t.__subclasses__():
        add_dataclass(c)

def to_json(x: Any) -> Any:
    if isinstance(x, (str, bool, int, float, type(None))):
        return x
    elif isinstance(x, dict):
        if any(not isinstance(k, str) for k in x.keys()):
            return {
                'type': 'dict_tuples',
                'items': [to_json([k, v]) for k, v in x.items()]
            }
        elif 'type' in x:
            return {
                'type': 'dict',
                'items': {k: to_json(v) for k, v in x.items()}
            }
        else:
            return {k: to_json(v) for k, v in x.items()}
    elif isinstance(x, (tuple, set)):
        type_name = type(x).__name__
        return {
            'type': type_name,
            'items': [to_json(v) for v in x]
        }
    elif isinstance(x, list):
        return [to_json(v) for v in x]
    elif is_dataclass(x):
        data = {
            k: to_json(v)
            for field in fields(x)
            for k in [field.name]
            for v in [getattr(x, k)]
            if v != field.default
        }
        if 'type' in data:
            return {
                'type': 'dataclass',
                'name': type_name,
                'data': data,
            }
        else:
            type_name = type(x).__name__
            return {'type': type_name, **data}
    else:
        raise ValueError(f'Cannot serialize {x}')

def from_json(x: Any) -> Any:
    if isinstance(x, (str, bool, int, float, type(None))):
        return x
    elif isinstance(x, list):
        return [from_json(v) for v in x]
    elif isinstance(x, dict):
        type_name = x.get('type')
        if type_name == 'dict_tuples':
            return dict(from_json(x['items']))
        elif type_name == 'dict':
            return {k: from_json(v) for k, v in x['items'].items()}
        elif type_name == 'tuple':
            return tuple(from_json(v) for v in x['items'])
        elif type_name == 'set':
            return set(from_json(v) for v in x['items'])
        elif type_name == 'dataclass':
            data = {k: from_json(v) for k, v in x['data'].items()}
            return __dataclasses[x['name']](**data)
        elif type_name:
            data = {k: from_json(v) for k, v in x.items() if k != 'type'}
            return __dataclasses[type_name](**data)
        else:
            return {k: from_json(v) for k, v in x.items()}
    else:
        raise ValueError(f'Cannot deserialize {x}')

