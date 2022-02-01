from __future__ import annotations
from dataclasses import *
from typing import *

from pathlib import Path
import json

from .nub import nub

@dataclass(frozen=True)
class Serializer:
    classes: dict[str, Any] = field(default_factory=dict)
    def register(self, classes: dict[str, Any]):
        self.classes.update({k: v for k, v in classes.items() if is_dataclass(v)})

    def from_json(self, x: Any) -> Any:
        if isinstance(x, dict):
            x = cast(dict[str, Any], x)
            if type := x.get('type'):
                cls = self.classes[type]
                return cls(**{k: self.from_json(v) for k, v in x.items() if k != "type"})
            else:
                return {k: self.from_json(v) for k, v in x.items()}
        elif isinstance(x, list):
            return [self.from_json(v) for v in cast(list[Any], x)]
        elif isinstance(x, None | float | int | bool | str):
            return x
        else:
            raise ValueError()

    def to_json(self, x: Any) -> dict[str, Any] | list[Any] | None | float | int | bool | str:
        if is_dataclass(x):
            d = nub(x)
            cls = x.__class__
            type = cls.__name__
            assert self.classes[type] == cls
            return self.to_json({'type': type, **d})
        elif isinstance(x, dict):
            return {k: self.to_json(v) for k, v in cast(dict[str, Any], x).items()}
        elif isinstance(x, list):
            return [self.to_json(v) for v in cast(list[Any], x)]
        elif isinstance(x, None | float | int | bool | str):
            return x
        else:
            raise ValueError()

    def from_jsonl(self, path: str | Path) -> Iterator[Any]:
        with open(path, 'r') as f:
            for line in f:
                yield self.from_json(json.loads(line))

    def write_jsonl(self, xs: Iterable[Any], path: str | Path):
        with open(path, 'w') as f:
            for x in xs:
                json.dump(self.to_json(x), f)
                f.write('\n')

serializer = Serializer()
from_json = serializer.from_json
to_json = serializer.to_json
