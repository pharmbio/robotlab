from __future__ import annotations
from dataclasses import *
from typing import *

from pathlib import Path
import json

from .nub import nub, asdict_shallow

from datetime import datetime, timedelta

@dataclass(frozen=True)
class Serializer:
    classes: dict[str, Any] = field(default_factory=dict)
    def register(self, classes: dict[str, Any]):
        self.classes.update({k: v for k, v in classes.items() if is_dataclass(v)})

    def from_json(self, x: Any) -> Any:
        if isinstance(x, dict):
            x = cast(dict[str, Any], x)
            type = x.get('type')
            if type == 'datetime':
                return datetime.fromisoformat(x['value'])
            elif type == 'timedelta':
                return timedelta(seconds=x['total_seconds'])
            elif type:
                cls = self.classes[type]
                return cls(**{k: self.from_json(v) for k, v in x.items() if k != 'type'})
            else:
                return {k: self.from_json(v) for k, v in x.items()}
        elif isinstance(x, list):
            return [self.from_json(v) for v in cast(list[Any], x)]
        elif isinstance(x, None | float | int | bool | str):
            return x
        else:
            raise ValueError()

    def to_json(self, x: Any, with_nub: bool=True) -> dict[str, Any] | list[Any] | None | float | int | bool | str:
        if isinstance(x, datetime):
            return {
                'type': 'datetime',
                'value': x.isoformat(sep=' '),
            }
        elif isinstance(x, timedelta):
            return {
                'type': 'timedelta',
                'total_seconds': x.total_seconds(),
            }
        elif is_dataclass(x):
            if with_nub:
                d = nub(x)
            else:
                d = asdict_shallow(x)
            cls = x.__class__
            type = cls.__name__
            if type not in self.classes:
                raise KeyError(f'{type=} {x=}')
            assert self.classes[type] == cls
            assert 'type' not in d
            return self.to_json({'type': type, **d}, with_nub=with_nub)
        elif isinstance(x, dict):
            return {k: self.to_json(v, with_nub=with_nub) for k, v in cast(dict[str, Any], x).items()}
        elif isinstance(x, list):
            return [self.to_json(v, with_nub=with_nub) for v in cast(list[Any], x)]
        elif isinstance(x, None | float | int | bool | str):
            return x
        else:
            raise ValueError()

    def dumps(self, x: Any, with_nub: bool=True) -> str:
        return json.dumps(self.to_json(x, with_nub=with_nub))

    def loads(self, s: str) -> Any:
        return self.from_json(json.loads(s))

    def read_jsonl(self, path: str | Path) -> Iterator[Any]:
        with open(path, 'r') as f:
            for line in f:
                yield self.loads(line)

    def read_json(self, path: str | Path) -> Any:
        with open(path, 'r') as f:
            return self.from_json(json.load(f))

    def write_jsonl(self, xs: Iterable[Any], path: str | Path, mode: Literal['w', 'a']='w'):
        with open(path, mode) as f:
            for x in xs:
                json.dump(self.to_json(x), f, separators=(',', ':'))
                f.write('\n')

    def write_json(self, x: Any, path: str | Path, indent: int | None = None):
        with open(path, 'w') as f:
            json.dump(self.to_json(x), f, indent=indent)

serializer = Serializer()
from_json = serializer.from_json
to_json = serializer.to_json
