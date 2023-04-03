from __future__ import annotations
from typing import *

from pathlib import Path
from ..log import Log
from datetime import timedelta
import math
import os
import signal
import json

import viable as V
import viable.provenance as Vp
from viable import label, span
from viable.provenance import Int, Str, Bool

import pbutils

def sigint(pid: int):
    os.kill(pid, signal.SIGINT)

def sigkill(pid: int):
    os.kill(pid, signal.SIGKILL)

def path_to_log(path: str) -> Log | None:
    try:
        return Log.connect(path)
    except:
        return None

def as_stderr(log_path: str):
    p = Path('cache') / Path(log_path).stem
    p = p.with_suffix('.stderr')
    return p

def pp_secs(secs: int | float, zero: str='0'):
    dt = timedelta(seconds=math.ceil(secs))
    if dt < timedelta(seconds=0):
        return zero
    s = str(dt)
    s = s.lstrip('0:')
    return s or zero

def get_argv(pid: int) -> list[str]:
    try:
        with open(f'/proc/{pid}/cmdline', 'r') as fp:
            cmdline = fp.read()
            return cmdline.rstrip('\0').split('\0')
    except FileNotFoundError:
        return []

def get_json_arg_from_argv(pid: int) -> dict[str, Any]:
    argv = get_argv(pid)
    for this, next in pbutils.iterate_with_next(argv):
        if this == '--json-arg' and next:
            return json.loads(next)
    return {}

def process_is_alive(pid: int, log_filename: str) -> bool:
    if pid:
        args = get_json_arg_from_argv(pid)
        return args.get("log_filename") == log_filename
    else:
        return False

def make_table(rows: list[dict[str, Any]], header: bool=True):
    columns = list({
        k: ()
        for row in rows
        for k, _ in row.items()
    }.keys())
    head_tr = V.tr()
    head = V.thead(head_tr)
    for c in columns:
        head_tr += V.th(c)
    body = V.tbody()
    for row in rows:
        tr = V.tr()
        for c in columns:
            v = row.get(c)
            if v is None:
                v = ''
            if isinstance(v, V.Node):
                tr += V.td(v)
            else:
                tr += V.td(str(v) or '\u200b')
        body += tr
    if header:
        return V.table(head, body)
    else:
        return V.table(body)

def form(*vs: Int | Str | Bool | Vp.List[str]):
    for v in vs:
        if isinstance(v, Vp.List):
            inp = v.select([
                V.option(x, value=x, selected=x in v.value)
                for x in v.options
            ])
            inp.extend(grid_column='1 / -1', width='100%', height='100%', grid_row='span 4')
            yield inp
        else:
            inp = v.input()
            inp.extend(id_=v.name, spellcheck="false", autocomplete="off")
            if len(getattr(v, 'options', []) or []) == 2:
                inp.extend(
                    class_='two',
                    size='2',
                    overflow='hidden'
                )
            yield label(
                span(f"{v.name or ''}:"),
                inp,
                title=v.desc,
            )

path_var = Str(name='log', _provenance='query')

def path_var_value():
    if path_var.value:
        return 'logs/' + path_var.value
    else:
        return ''

def path_var_assign(path: str, push_state: bool=True):
    if push_state:
        path_var.push(path.removeprefix('logs/'))
    else:
        path_var.assign(path.removeprefix('logs/'))

def alert(s: str):
    return V.Action(f'alert({json.dumps(s)})')


inverted_inputs_css = '''
    & input[type=range] {
        transform: translateY(3px);
        margin: 0 8px;
        filter: invert(83%) hue-rotate(135deg);
    }
    & input[type=checkbox] {
        filter: invert(83%) hue-rotate(180deg);
        transform: translateY(2px);
        cursor: pointer;
    }
'''

def triangle() -> V.tag:
    return V.svg(
        V.raw('<polygon points="1,1 1,14 14,7"/>'),
        css='''
            & {
                margin-right: 6px;
                width: 16px;
                height: 16px;
                transform: translateY(4px);
            }
            & polygon {
                fill: var(--green);
            }
        '''
    )

