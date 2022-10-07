from collections import defaultdict
from pathlib import Path
from pprint import pp
from typing import *
import json
import sys

A = TypeVar('A')
B = TypeVar('B')

def group_by(xs: Iterable[A], key: Callable[[A], B]) -> defaultdict[B, list[A]]:
    d: dict[B, list[A]] = defaultdict(list)
    for x in xs:
        d[key(x)] += [x]
    return d

paths: list[str] = sys.argv[1:]

def find(k: str, x: Any) -> Iterator[Any]:
    if isinstance(x, dict):
        for kk, v in x.items():
            if k == kk:
                yield v
            yield from find(k, v)
    elif isinstance(x, list):
        for v in x:
            yield from find(k, v)

def find1(k: str, x: Any):
    for v in find(k, x):
        if v:
            return v
    return None

def find_last(k: str, x: Any):
    for v in reversed(list(find(k, x))):
        if v:
            return v
    return None

from datetime import datetime

weekdays = 'Mon Tue Wed Thu Fri Sat Sun'.split()

out: list[dict[str, int | str]] = []

for path in paths:
    x = [json.loads(s) for s in open(path).read().splitlines()]
    t0 = min(map(datetime.fromisoformat, find("log_time", x)))
    t1 = max(map(datetime.fromisoformat, find("log_time", x)))
    out += [dict(
        date=str(t0.date()),
        weekday=weekdays[t0.weekday()],
        start=t0.time().strftime("%H:%M"),
        end=t1.time().strftime("%H:%M"),
        plates=max((int(p or '0') for p in find("plate_id", x)), default=0),
        batches=max(find("batch_index", x), default=0),
        protocols=(find1("protocol_path", x) or '').partition('/')[0],
    )]

g = sorted(
    list(group_by(out, key=lambda d: d['start']).items()),
    key=lambda kv: kv[1][-1]['date'],
)

header = False

for _, vs in g:
    v = vs[-1]
    if not header:
        print(*v.keys(), sep='\t')
        header = True
    if v['plates'] and v['batches']:
        print(*v.values(), sep='\t')
