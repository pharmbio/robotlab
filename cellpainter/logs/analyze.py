from collections import defaultdict
from pathlib import Path
from pprint import pp
from typing import *
import json
import sys
import re

from cellpainter.log import CommandState, Metadata, RuntimeMetadata, ExperimentMetadata, Log
from cellpainter.commands import BiotekCmd, ProgramMetadata

from pbutils.mixins import DB, DBMixin

import pbutils

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

def universe(x: Any) -> Iterator[Any]:
    yield x
    if isinstance(x, dict):
        for _, v in x.items():
            yield from universe(v)
    elif isinstance(x, (list, tuple, set)):
        for v in x:
            yield from universe(v)

def items(x: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(k, str):
                yield k, v
            yield from items(v)
    elif isinstance(x, (list, tuple, set)):
        for v in x:
            yield from items(v)

def universe_with_parent(x: Any, p: Any = None) -> Iterator[tuple[Any, Any]]:
    yield x, p
    if isinstance(x, dict):
        for _, v in x.items():
            yield from universe_with_parent(v, x)
    elif isinstance(x, (list, tuple, set)):
        for v in x:
            yield from universe_with_parent(v, x)

def keys(x: Any) -> set[Any]:
    return set(
        k
        for v in universe(x)
        if isinstance(v, dict)
        for k in v.keys()
    )

def pairs(x: Any) -> dict[str, list[Any]]:
    res = DefaultDict[str, list[Any]](list)
    for d in universe(x):
        if isinstance(d, dict):
            for k, v in d.items():
                res[k] += [v]
    return res

from datetime import datetime

weekdays = 'Mon Tue Wed Thu Fri Sat Sun'.split()

out: list[dict[str, int | str]] = []

full_bioteks: list[dict[str, Any]] = []
for path in paths:
    if 'incu' in path:
        continue
    if 'time_protocols' in path:
        continue
    x = [json.loads(s) for s in open(path).read().splitlines()]
    bioteks: list[dict[str, Any]] = []
    css: list[CommandState] = []
    batch_indicies = sorted(
        set(
            int(v)
            for k, v in items(x)
            if 'batch_index' in k
        )
    )
    for d, p in universe_with_parent(x):
        if isinstance(d, dict):
            d = cast(dict[str, Any], d)
            p = cast(dict[str, Any] | list[Any], p)
            strs = [
                s
                for _, s in d.items()
                if isinstance(s, str)
            ]
            if any('Validate ' in s for s in strs):
                continue
            if any('Validate' == s for s in strs):
                continue
            if 'delay' in str(d.get('source')):
                continue
            if 'wait' == str(d.get('source')):
                continue
            if 'begin' == str(d.get('kind')):
                continue
            if 'stop' == str(d.get('kind')):
                continue
            if 'start' == str(d.get('kind')):
                continue
            if p and isinstance(p, dict) and len(p) < 20:
                dp = p
            else:
                dp = d
            if isinstance(md := dp.get('metadata'), dict):
                del dp['metadata']
                dp |= {f'metadata.{k}': v for k, v in md.items()}
            if 'LogEntry' == str(dp.get('type')) and 't0' not in dp:
                continue
            for s in strs:
                if (m := re.search(r'\S*\.LHC', s)):
                    protocol = m.group(0)
                    machine = {x for x in universe(dp) if x == 'disp' or x == 'wash'}
                    log_time = datetime.fromisoformat(d.get('log_time', dp.get('log_time')))
                    t = d.get('t', dp.get('t'))
                    t0 = d.get('t0', dp.get('t0'))
                    if t is None:
                        exp_time = datetime.fromisoformat(d.get('experiment_time'))
                        t = (log_time - exp_time).total_seconds()
                        t0: float = t - d.get('duration')
                    plate_id = ''
                    for k, v in items(dp):
                        if 'plate_id' in k:
                            plate_id = v
                    predispense = False
                    for k, v in items(dp):
                        if 'predisp' in k:
                            predispense |= bool(v)
                    step = ''
                    for k, v in items(dp):
                        if re.search(r'\bstep', k):
                            step = v
                    batch_index = 0
                    for k, v in items(dp):
                        if 'batch_index' in k:
                            batch_index = batch_indicies.index(int(v))
                    if isinstance(plate_id, str):
                        plate_id = plate_id.lstrip('pP0')
                    res = {
                        't': t,
                        't0': t0,
                        'log_time': log_time,
                        'protocol': protocol,
                        'machine': ' or '.join(machine),
                        'plate_id': plate_id,
                        'predispense': predispense,
                        'batch_index': batch_index,
                    }
                    if any(v is None for k, v in res.items()):
                        pp(('INCOMPLETE', path, res, dp))
                        quit()
                        continue
                    cs = CommandState(
                        t0=t0,
                        t=t,
                        cmd=BiotekCmd(
                            machine=cast(Any, ' or '.join(machine)),
                            protocol_path=protocol,
                            action='Run',
                        ),
                        metadata=Metadata(
                            plate_id=plate_id,
                            predispense=predispense,
                            batch_index=batch_index,
                            step=step,
                            id=len(css),
                        ),
                        state='completed',
                        id=len(css),
                    )
                    css += [cs]
                    res |= {
                        'step': step,
                    }
                    bioteks += [res]
    print()
    print('=' * 80)
    print(path, len(bioteks))
    summary = {}
    for k in keys(bioteks):
        summary[k] = Counter(b[k] for b in bioteks).most_common(2 if k in 't t0 log_time'.split() else 9)
    pp(summary)

    plate_ids = {
        p
        for cs in css
        if (p := cs.metadata.plate_id)
    }
    batch_sizes = [
        len({
            p
            for cs in css
            if (p := cs.metadata.plate_id)
            if cs.metadata.batch_index == i
        })
        for i in sorted({
            cs.metadata.batch_index
            for cs in css
        })
    ]
    for k, v in items(x):
        if k == 'batch_sizes':
            batch_sizes = pbutils.read_commasep(v, int)
    num_plates = len(plate_ids)

    t0: datetime = min(map(datetime.fromisoformat, find("log_time", x)))
    t1: datetime = max(map(datetime.fromisoformat, find("log_time", x)))
    meta = dict(
        date=str(t0.date()),
        weekday=weekdays[t0.weekday()],
        start=t0.time().strftime("%H:%M"),
        end=t1.time().strftime("%H:%M"),
        plates=num_plates,
        batches=len(batch_sizes),
        batch_sizes=batch_sizes,
        protocols=(find1("protocol_path", x) or '').partition('/')[0],
    )
    bs = ','.join(map(str, batch_sizes))
    new_path = f'logs/{t0.strftime("%Y-%m-%d_%H.%M")}-cell-paint-{bs}-migrated.db'
    from pathlib import Path
    print(Path.cwd())
    data = [
        RuntimeMetadata(
            start_time=t0,
            num_plates=num_plates,
            config_name='live',
            log_filename=new_path,
            pid = 0,
            host = 'NUC-robotlab',
            git_HEAD = 'TBD',
            completed = t1,
        ),
        ExperimentMetadata(),
        ProgramMetadata(
            protocol='cell-paint',
            num_plates=num_plates,
            batch_sizes=batch_sizes,
        ),
    ]
    pp(meta)
    pbutils.pr(data)

    if 0:
        print('Making', new_path)
        Path(new_path).unlink(missing_ok=True)
        with DB.open(new_path) as db:
            with db.transaction:
                for cs in css:
                    cs.save(db)
                for d in data:
                    d.save(db)

    full_bioteks += bioteks

    # pp(out[-1])

print()
print('=' * 80)

summary = {}
for k in keys(full_bioteks):
    summary[k] = Counter(b[k] for b in full_bioteks).most_common(3 if k in 't t0 log_time'.split() else 20)
pp(summary)

g = sorted(
    list(group_by(out, key=lambda d: d['start']).items()),
    key=lambda kv: kv[1][-1]['date'],
)

header = False

quit()

for _, vs in g:
    v = vs[-1]
    if not header:
        print(*v.keys(), sep='\t')
        header = True
    if v['plates'] and v['batches']:
        print(*v.values(), sep='\t')
    else:
        print(v)
