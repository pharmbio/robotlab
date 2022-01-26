
from __future__ import annotations
from typing import *

from viable import app, js
from viable import head, serve, esc, css_esc, trim, button, pre
from viable import Tag, div, span, label, img, raw, Input, input
import viable as V

from flask import request
from collections import *

import utils
import random

import threading

from cli import Args
import dataclasses
import json

from subprocess import Popen, DEVNULL, check_output
import pickle
import signal
import os
from runtime import config_lookup, get_robotarm, RuntimeConfig
import moves
from moves import RawCode, Move
import sys
import platform

from provenance import Var, Int, Str, Store, DB, Bool
from protocol import Incu_locs, A_locs, B_locs, C_locs

if '--live' in sys.argv:
    config: RuntimeConfig = config_lookup('live')
elif '--live-no-incu' in sys.argv:
    config: RuntimeConfig = config_lookup('live-no-incu')
elif '--simulator' in sys.argv:
    config = config_lookup('simulator')
elif '--dry-wall' in sys.argv:
    config = config_lookup('dry-wall')
else:
    raise ValueError('Start with --live, --simulator or --dry-wall')

print(f'Running with {config.name=}')

@serve.expose
def sigint(pid: int):
    os.kill(pid, signal.SIGINT)

def robotarm_do(ms: list[Move]):
    arm = get_robotarm(config, quiet=False, include_gripper=True)
    arm.execute_moves(ms, name='gui', allow_partial_completion=True)
    arm.close()

@serve.expose
def robotarm_freedrive():
    '''
    Sets the robotarm in freedrive
    '''
    robotarm_do([RawCode("freedrive_mode() sleep(3600)")])

@serve.expose
def robotarm_to_neutral():
    '''
    Slowly moves in joint space to the neutral position by B21
    '''
    robotarm_do(moves.movelists['to neu'])

@serve.expose
def robotarm_open_gripper():
    '''
    Opens the robotarm gripper
    '''
    robotarm_do([RawCode("GripperMove(88)")])

def as_stderr(log_path: str):
    p = Path('cache') / Path(log_path).stem
    p = p.with_suffix('.stderr')
    return p

@serve.expose
def start(batch_sizes: str, start_from_pfa: bool, simulate: bool, incu: str):
    N = max(utils.read_commasep(batch_sizes, int))
    interleave = N >= 7
    two_final_washes = N >= 8
    lockstep = N >= 10
    if incu in {'1200', '20:00', ''} and N >= 8:
        incu = '1200,1200,1200,1200,X'
    log_filename = 'logs/' + utils.now_str_for_filename() + '-from-gui.jsonl'
    args = Args(
        config_name='dry-run' if simulate else config.name,
        log_filename=log_filename,
        cell_paint=batch_sizes,
        interleave=interleave,
        two_final_washes=two_final_washes,
        lockstep=lockstep,
        start_from_pfa=start_from_pfa,
        incu=incu,
        # load_incu=11,
    )
    cmd = [
        'sh', '-c',
        'yes | python3.10 cli.py --json-arg "$1" 2>"$2"',
        '--',
        json.dumps(dataclasses.asdict(args)),
        as_stderr(log_filename),
    ]
    Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL)
    return {
        'goto': log_filename,
        'refresh': True,
    }

@serve.expose
def resume(log_filename_in: str, skip: list[str], drop: list[str]):
    log_filename_new = 'logs/' + utils.now_str_for_filename() + '-resume-from-gui.jsonl'
    args = Args(
        config_name=config.name,
        resume=log_filename_in,
        log_filename=log_filename_new,
        resume_skip=','.join(skip),
        resume_drop=','.join(drop),
    )
    cmd = [
        'sh', '-c',
        'python3.10 cli.py --json-arg "$1" 2>"$2"',
        '--',
        json.dumps(dataclasses.asdict(args)),
        as_stderr(log_filename_new),
    ]
    Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=sys.stderr, stdin=DEVNULL)
    return {
        'goto': log_filename_new,
        'refresh': True,
    }

serve.suppress_flask_logging()
import pandas as pd

import numpy as np
from datetime import datetime, timedelta
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

@lru_cache
def load_from_pickle(filepath: str) -> Any:
    with open(filepath, 'rb') as fp:
        rs = pickle.load(fp)
    return prep(pd.DataFrame.from_records(rs))

@lru_cache(maxsize=1)
def _jsonl_to_df(path: str, mtime_ns: int) -> pd.DataFrame | None:
    try:
        df = pd.read_json(path, lines=True)
    except:
        return None
    return prep(df)

def jsonl_to_df(path: str) -> pd.DataFrame | None:
    p = Path(path)
    try:
        stat = p.stat()
    except FileNotFoundError:
        return None
    df = _jsonl_to_df(path, stat.st_mtime_ns)
    if df is not None:
        return df.copy()
    else:
        return None

def to_int(s: pd.Series, fill: int=0) -> pd.Series:
    return pd.to_numeric(s, errors='coerce').fillna(fill).astype(int)

def prep(df: pd.DataFrame):
    if 'id' in df:
        df.id = to_int(df.id, fill=-1)
    else:
        df.id = -1
    if 'plate_id' in df:
        df.plate_id = to_int(df.plate_id)
    else:
        df['plate_id'] = 0
    if 'batch_index' in df:
        df.batch_index = to_int(df.batch_index)
    else:
        df['batch_index'] = 0
    if 'simple_id' not in df:
        df['simple_id'] = None
    if 'report_behind_time' in df:
        df.report_behind_time = df.report_behind_time.fillna(0.0) == 1.0
    else:
        df['report_behind_time'] = False
    if 'incu_loc' in df:
        df.loc[~df.incu_loc.isna(), 'arg'] = df.arg + ' ' + df.incu_loc
    if 'section' not in df:
        df['section'] = None
    if 'resource' in df:
        df.resource = df.resource.fillna('main')
    else:
        df['resource'] = 'main'
    if 'step' not in df:
        df['step'] = None
    return df

def cleanup(d):
    d = d[~d.arg.fillna('').str.contains('Validate ')].copy()
    d.arg = d.arg.str.replace('RunValidated ', '', regex=False)
    d.arg = d.arg.str.replace('Run ', '', regex=False)
    d.arg = d.arg.str.replace(r'automation_v[\d\.]+/', '', regex=True)
    return d

def countdown_str(s: Series):
    if s.isna().all():
        return s
    s = s.clip(0)
    s = pd.to_datetime(s, unit='s')
    s = s.dt.strftime('%H:%M:%S')
    s = s.str.lstrip('0:')
    s[s == ''] = '0'
    return s

@dataclass(frozen=True, kw_only=True)
class AnalyzeResult:
    zero_time: datetime
    t_now: float
    pid: int
    process_is_alive: bool
    completed: bool
    log_filename: str
    df: pd.DataFrame
    r: pd.DataFrame
    vis: pd.DataFrame
    sections: pd.DataFrame
    errors: pd.DataFrame
    world: dict[str, Any]
    num_plates: int

    def has_error(self):
        if self.completed:
            return False
        return not self.process_is_alive or self.errors.size > 0

    @staticmethod
    def init(df: Any) -> AnalyzeResult:
        completed = 'completed' in df and df.completed.any()

        meta = df.runtime_metadata # .iloc[-1]
        meta = meta[~meta.isna()]
        runtime_metadata = meta.iloc[-1]

        df['current'] = df.index >= meta.index[-1]

        try:
            world0: dict[str, str] = df.effect.dropna().iloc[0]
        except:
            world0 = {}

        first_row = df.iloc[meta.index[-1], :]
        zero_time = first_row.log_time.to_pydatetime() - timedelta(seconds=first_row.t)
        t_now = (datetime.now() - zero_time).total_seconds()
        t_now *= runtime_metadata['speedup']

        if completed:
            t_now = df.t.max() + 1

        estimates = load_from_pickle(runtime_metadata['estimates_pickle_file'])
        estimates = estimates.copy()
        estimates['finished'] = True
        estimates['running'] = False
        estimates['current'] = False
        pid = runtime_metadata['pid']
        log_filename = runtime_metadata['log_filename']

        errors = df[(df.kind == 'error') & df.current]

        num_plates = max(
            df.plate_id.astype(float).max(),
            estimates.plate_id.astype(float).max(),
        )
        num_plates = int(num_plates)

        if pid:
            try:
                with open(f'/proc/{pid}/cmdline', 'r') as fp:
                    cmdline = fp.read()
            except FileNotFoundError:
                cmdline = ''
            process_is_alive = log_filename in cmdline
        else:
            process_is_alive = False


        if errors.size:
            t_now = df.t.max()

        r = df
        r_sections = r[~r.section.isna()]
        r_sections = r_sections.copy()
        r = r[r.kind.isin(('begin', 'end'))]
        r = r.copy()
        r['finished'] = r.id.isin(r[r.kind == 'end'].id)
        r['running'] = (r.kind == 'begin') & ~r.finished & r.current

        try:
            effects = r[r.finished & r.source.isin(('incu', 'robotarm')) & r.kind.eq('end')].effect.dropna()
            world: dict[str, str] = {**world0}
            for effect in effects:
                world = {
                    k: v
                    for k, v in {**world, **effect}.items()
                    if v is not None
                }
            assert isinstance(world, dict)
        except:
            world = {}

        r = r[
            r.source.isin(('wash', 'disp', 'incu'))
            | r.report_behind_time
            | ((r.source == 'robotarm') & r.running)
        ]
        r = r[~r.arg.str.contains('Validate ')]
        if 'secs' not in r:
            r['secs'] = float('NaN')
        r.loc[~r.finished, 't0'] = r.t
        r.loc[~r.finished, 't'] = r.t + r.est.fillna(r.secs)
        r.loc[~r.finished, 'duration'] = r.t - r.t0
        r.loc[~r.finished, 'countdown'] = np.ceil(r.t) - t_now
        r = r[~r.finished | (r.kind == 'end')]
        r = r.copy()
        if 't0' not in r:
            r['t0'] = r.t
        r['is_estimate'] = False
        r.loc[r.running, 'is_estimate'] = True

        r['t_ts'] = zero_time + pd.to_timedelta(r.t, unit='seconds')
        r.t_ts = r.t_ts.dt.strftime('%H:%M:%S')
        r.loc[~r.secs.isna(), 'arg'] = 'sleeping'
        r.loc[~r.secs.isna(), 'arg'] = r.arg + ' to ' + r.t_ts

        r = r.sort_values('t')
        r = r.reset_index(drop=True)

        r_sections['is_estimate'] = False
        est = estimates
        est['is_estimate'] = True
        est = est[(est.kind == 'end') | est.section]
        est = est[~est.id.isin(r.id)]
        est = est[~est.section.isin(r_sections.section)]
        vis = pd.concat([r, r_sections, est], axis=0).reset_index(drop=True)
        vis = vis.sort_values('t')
        vis = vis.reset_index(drop=True)

        r = cleanup(r)
        vis = cleanup(vis)

        if vis.section.dropna().empty:
            vis.loc[0, 'section'] = 'begin'

        sections = vis[~vis.section.isna()]
        sections = sections['batch_index t is_estimate section'.split()]
        sections = sections.append([
            {
                't': vis.t.max(),
                'is_estimate': True,
                'section': 'end',
                'batch_index': sections.batch_index.max()
            }
        ], ignore_index=True)
        sections.loc[0, 't'] = 0
        sections = sections.sort_values('t')
        sections = sections.reset_index(drop=True)
        sections['length'] = sections.t.diff()[1:].reset_index(drop=True)
        sections['t0'] = sections.t
        sections['t'] = sections.t0 + sections.length
        sections['finished'] = sections.t0 < t_now
        sections.loc[~sections.finished, 'countdown'] = (np.ceil(sections.t0) - t_now)

        cols = '''
            step
            t0
            t
            source
            resource
            arg
            countdown
            is_estimate
            batch_index
            plate_id
            running
            finished
            current
            id
            simple_id
        '''.split()

        return AnalyzeResult(
            zero_time=zero_time,
            t_now=t_now,
            pid=pid,
            process_is_alive=process_is_alive,
            completed=completed,
            log_filename=log_filename,
            df=df,
            r=r[cols].fillna(''),
            vis=vis[cols].fillna(''),
            sections=sections,
            errors=errors,
            world=world,
            num_plates=num_plates,
        )

    def durations(self) -> pd.DataFrame:
        d = self.df.copy()
        d['t_ts'] = self.zero_time + pd.to_timedelta(d.t, unit='seconds')
        d.t_ts = d.t_ts.dt.strftime('%H:%M:%S')
        d0 = d.copy()
        d = d[d.source == 'duration']
        d = pd.concat([d, d.arg.str.extract(r'plate \d+ (?P<checkpoint>.*)$')], axis=1)
        d = d[~d.checkpoint.isna()]
        d = d['t0 t t_ts duration arg step plate_id checkpoint'.split()]
        d = d[~d.checkpoint.str.contains('pre disp done')]
        d = d[
              (d.checkpoint == '37C')
            | d.checkpoint.str.contains('incubation')
            # | d.checkpoint.str.contains('transfer')
        ]
        d.checkpoint = d.checkpoint.str.replace('incubation', 'incu', regex=False)
        d.checkpoint = d.checkpoint.str.replace('transfer', 'xfer', regex=False)
        d = d.rename(columns={'plate_id': 'plate'})
        pivot = d.pivot(index=['plate'], columns='checkpoint')
        d = d.drop(columns=['arg', 't0', 't'])
        d = d.rename(columns={'checkpoint': 'arg'})

        d2 = cleanup(d0)
        d2 = d2[d2.source.isin(('disp', 'wash'))]
        d2 = d2[d2.kind == 'end']
        d2 = d2[d2.plate_id != 0]
        d2.arg = d2.source + ' ' + d2.arg
        d2 = d2.rename(columns={'plate_id': 'plate'})

        d = d.append(d2)

        d = d['t_ts duration arg plate'.split()]
        d.duration = countdown_str(d.duration) #pd.to_datetime(d.duration, unit='s')
        # d.duration = d.duration.dt.strftime('%M:%S')
        d = d.sort_values(['plate', 't_ts'])
        d = d.rename(columns={'t_ts': 't'})
        return d

        # if not pivot.empty:
        #     return pivot.duration.fillna('')
        # else:
        #     return None

    def running(self) -> pd.DataFrame:
        r = self.r
        zero_time = self.zero_time
        r.resource = r.resource.str.replace('main', 'arm', regex=False)
        r = r[r.running]
        r = r['resource t countdown arg plate_id'.split()]
        r.countdown = countdown_str(r.countdown)
        resources = 'arm disp wash incu'.split()
        for resource in resources:
            if not (r.resource == resource).any():
                r = r.append({'resource': resource}, ignore_index=True)
        order = {v: i for i, v in enumerate(resources)}
        r['order'] = r.resource.replace(order)
        r = r.sort_values('order')
        r = r.drop(columns=['order', 't'])
        r = r.rename(columns={'plate_id': 'plate'})
        r.plate = r.plate.fillna(0).astype(int)
        r.loc[r.plate == 0, 'plate'] = pd.NA
        r = r.fillna('')
        return r

    def pretty_sections(self) -> pd.DataFrame:
        zero_time = self.zero_time
        sections = self.sections.copy()
        sections.section = sections.section.replace(r' \d*$', '', regex=True)
        sections.t0 = zero_time + pd.to_timedelta(sections.t0, unit='seconds')
        sections.t0 = sections.t0.dt.strftime('%H:%M:%S')
        sections.countdown = countdown_str(sections.countdown)
        sections.length = pd.to_datetime(sections.length, unit='s')
        sections.length = sections.length.dt.strftime('%M:%S')
        sections = sections.fillna('')
        return sections

    def make_vis(self) -> Tag:
        t_now = self.t_now
        r = self.vis
        sections = self.sections

        start_times = sections.t0
        max_length = sections.length.max()

        r = r[r.source.isin(('wash', 'disp'))]
        r = r[~r.batch_index.isna()]
        r = r[r.finished | r.current]

        bg_rows: list[dict[str, Any]] = []
        for i, (_, section) in enumerate(sections.iterrows()):
            if pd.isna(section.length):
                continue
            bg_rows += [{
                't0': section.t0,
                't': section.t,
                'is_estimate': False,
                'source': 'marker',
                'arg': '',
                'plate_id': 0,
            }]
        bg_rows = pd.DataFrame.from_records(bg_rows)

        now_row: list[dict[str, Any]] = []
        if 0 <= t_now <= start_times.max() and not self.completed:
            now_row += [{
                't0': t_now,
                't': t_now,
                'is_estimate': False,
                'source': 'now',
                'arg': '',
                'plate_id': 0,
            }]
        now_row = pd.DataFrame.from_records(now_row)

        r = pd.concat([bg_rows, r, now_row], ignore_index=True)
        r['slot'] = 0
        for i, (_, section) in enumerate(sections.iterrows()):
            r.loc[r.t0 >= section.t0, 'slot'] = i
            r.loc[r.t0 >= section.t0, 'section'] = section.section

        r['slot_start'] = r.slot.replace(start_times)

        r['color'] = r.source.replace({
            'wash': 'var(--cyan)',
            'disp': 'var(--purple)',
            'incu': 'var(--green)',
            'now': '#fff',
            'marker': 'var(--bg-bright)',
        })
        r['machine_slot'] = r.source.replace({
            'wash': 0,
            'disp': 1,
            'now': 0,
            'marker': 0,
        })
        r['machine_width'] = r.source.replace({
            'wash': 1,
            'disp': 1,
            'now': 2,
            'marker': 2,
        })
        r['can_hover']=~r.source.isin(('now', 'marker'))

        r['y0'] = (r.t0 - r.slot_start) / max_length
        r['y1'] = (r.t - r.slot_start) / max_length
        r['h'] = r.y1 - r.y0

        r.simple_id = r.simple_id.fillna('')

        area = div(css='''
            & {
                position: relative;
                user-select: none;
            }
            & > * {
                color: #000;
                position: absolute;
                border-radius: 0px;
                outline: 1px #0005 solid;
                display: grid;
                place-items: center;
                font-size: 0.9rem;
                min-height: 1px;
                background: var(--row-color);
            }
            & > [is-estimate]:not(:hover)::before {
                position: absolute;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                content: "";
                background: #0005;
            }
            & > [can-hover]:hover::after {
                font-size: 1rem;
                color: #000;
                position: absolute;
                outline: 1px #0005 solid;
                padding: 5px;
                margin: 0;
                border-radius: 0 5px 5px 5px;
                content: var(--info);
                left: 100%;
                transform: translateX(1px);
                opacity: 1.0;
                top: 0;
                background: var(--row-color);
                white-space: pre;
                z-index: 1;
            }
        ''')

        width = 23
        for _, row in r.iterrows():
            est = 1 if row.is_estimate else 0
            area += div(
                str(row.plate_id) if row.plate_id else '',
                is_estimate=row.is_estimate,
                can_hover=row.can_hover,
                style=trim(f'''
                    left:{(row.slot*2.3 + row.machine_slot) * width:.0f}px;
                    top:{  row.y0 * 100:.3f}%;
                    height:{row.h * 100:.3f}%;
                    --row-color:{row.color};
                    --info:{repr(str(row.arg) + ' (' + str(row.simple_id) + ')')};
                ''', sep=''),
                css_=f'''
                    width: {row.machine_width * width - 2}px;
                ''',
                data_simple_id=str(row.simple_id) or None,
                data_plate_id=str(row.plate_id),
            )

        area.width += f'{width*(r.slot.max()+1)*2.3}px'
        area.height += '100%'

        return area

triangle = '''
  <svg xmlns="http://www.w3.org/2000/svg" class="svg-triangle" width=16 height=16>
    <polygon points="1,1 1,14 14,7"/>
  </svg>
'''

@serve.route('/')
@serve.route('/<path:path>')
def index(path: str | None = None) -> Iterator[Tag | V.Node | dict[str, str]]:
    yield {
        'sheet': '''
            *, *::before, *::after {
                box-sizing: border-box;
            }
            * {
                margin: 0;
            }
            html, body {
                height: 100%;
            }
            input, pre {
                font-family: inherit;
            }
            body, button, input {
                background: var(--bg);
                color:      var(--fg);
                font-family: Consolas, monospace;
                font-size: 18px;
            }
            table {
                background: #0005;
            }
            table td, table th, table tr, table {
                border: none;
            }
            table td, table th {
                padding: 2px 8px;
                margin: 1px 2px;
                background: var(--bg-bright);
                min-width: 70px;
            }
            table:not(.even) tbody tr:nth-child(odd) :where(td, th) {
                background: var(--bg-brown);
            }
            table.even tbody tr:nth-child(even) :where(td, th) {
                background: var(--bg-brown);
            }
            table {
                border-spacing: 1px;
                transform: translateY(-1px);
            }
            body {
                display: grid;
                grid:
                    "pad-left header    header    pad-right" auto
                    "pad-left vis       info      pad-right" 1fr
                    "pad-left vis       stop      pad-right" auto
                    "pad-left info-foot info-foot pad-right" auto
                  / 1fr auto minmax(min-content, 800px) 1fr;
                grid-gap: 10px;
                padding: 10px;
            }
            html {
                --bg:        #2d2d2d;
                --bg-bright: #383838;
                --bg-brown:  #554535;
                --fg:        #d3d0c8;
                --red:       #f2777a;
                --brown:     #d27b53;
                --green:     #99cc99;
                --yellow:    #ffcc66;
                --blue:      #6699cc;
                --purple:    #cc99cc;
                --cyan:      #66cccc;
                --orange:    #f99157;
            }
        '''
    }
    yield V.head(V.title('cell painter - ', path or ''))

    form_css = '''
        & {
            display: grid;
            grid-template-columns: auto auto;
            width: fit-content;
            place-items: center;
            grid-gap: 10px;
            margin: 0 auto;
            user-select: none;
        }
        & input {
            border: 1px #0003 solid;
            border-right-color: #fff2;
            border-bottom-color: #fff2;
        }
        & button {
            border-width: 1px;
        }
        & input, & button {
            padding: 8px;
            border-radius: 2px;
            background: var(--bg);
            color: var(--fg);
        }
        & input:focus-visible, & button:focus-visible {
            outline: 2px  var(--blue) solid;
            outline-color: var(--blue);
        }
        & input:hover {
            border-color: var(--blue);
        }
        & .wide {
            grid-column: 1 / span 2;
        }
        & > button {
            grid-column: 1 / span 2;
            width: 100%;
        }
        & > label {
            display: contents;
            cursor: pointer;
        }
        & > label > span {
            justify-self: right;
        }
        & input {
            width: 300px;
        }
        & > label > span {
            grid-column: 1;
        }
        & [type=checkbox] {
            filter: invert(83%) hue-rotate(180deg);
            width: 36px;
            height: 16px;
            margin-top: 8px;
            margin-bottom: 8px;
            margin-right: auto;
            cursor: pointer;
        }
    '''

    m = Store(default_provenance='cookie')
    if not path:
        plates = m.var(Str(desc='The number of plates per batch, separated by comma. Example: 6,6'))
        start_from_pfa = m.var(Bool(name='start from pfa', desc='Skip mito and start with PFA (from pre-PFA wash). Plates start on their output positions.'))
        simulate = m.var(Bool())
        incu = m.var(Str(name='incubation times', value='20:00', desc='The incubation times in seconds or minutes:seconds, separated by comma. If too few values are specified, the last value is repeated. Example: 21:00,20:00'))

        yield div(
            *form(m, plates, incu, start_from_pfa, simulate),
            button(
                V.raw(triangle.strip()), ' ', 'start',
                onclick=start.call(
                    batch_sizes=plates.value,
                    simulate=simulate.value,
                    start_from_pfa=start_from_pfa.value,
                    incu=incu.value,
                ),
                css='''
                  & .svg-triangle {
                    margin-right: 6px;
                    width: 16px;
                    height: 16px;
                    transform: translateY(4px);
                  }

                  & .svg-triangle polygon {
                    fill: var(--green);
                  }
                '''
            ),
            height='100%',
            # button('simulate', onclick=start.call(simulate=True)),
            padding='80px 0',
            grid_area='header',
            user_select='none',
            css__=form_css,
        )
        yield div(
            f'Running on {platform.node()} with config {config.name}',
            grid_area='info-foot',
            opacity='0.85',
            margin='0 auto',
        )
    info = div(
        grid_area='info',
        font_size='1rem',
        css='''
            & *+* {
                margin-top: 18px;
                margin-left: auto;
                margin-right: auto;
            }
        ''')
    yield info
    df: pd.DataFrame | None = None
    stderr: list[str] = []
    vis = div()
    ar: AnalyzeResult | None = None

    def sections(ar: AnalyzeResult):
        s = ar.pretty_sections()
        s = s['batch_index section countdown t0 length'.split()]
        s = s.rename(columns={'batch_index': 'batch'})
        s.batch += 1
        return div(
            V.raw(
                s.to_html(index=False, border=0)
            ),
            css='''
                & table {
                    margin: auto;
                }
                & table td:nth-child(1),
                & table td:nth-child(3),
                & table td:nth-child(5)
                {
                    text-align: right
                }
            '''
        )

    if path:
        df = jsonl_to_df(path)
        stderr = as_stderr(path).read_text()
        if df is not None:
            ar = AnalyzeResult.init(df)
    if df is None:
        if stderr:
            box = div(
                border='2px var(--red) solid',
                px=8,
                py=4,
                border_radius=2,
                css='''
                    & > pre {
                        line-height: 1.5;
                        margin: 0;
                    }
                '''
            )
            box += pre(stderr)
            info += box
    elif ar is not None:
        if not ar.completed:
            r = ar.running()
            r = r.rename(columns={'arg': 'info', 'resource': 'machine'})
            r = r['machine countdown info plate'.split()]
            info += div(
                V.raw(
                    # d.head(50).to_html(index=False, border=0, justify='left')
                    r.to_html(index=False, border=0, justify='left')
                ),
                css='''
                    & table {
                        width: 100%
                    }
                    & table td:nth-child(3) {
                        width: 100%
                    }
                    & table td:nth-child(2),
                    & table td:nth-child(4)
                    {
                        text-align: right
                    }
                '''
            )
        info += sections(ar)
        if 1:
            vis = ar.make_vis()
        if 1:
            world = ar.world
            world = {k: v if 'lid' in v else 'plate ' + v for k, v in world.items()}
            incu_df = pd.DataFrame.from_records([
                {
                    'location': k,
                    'incu': world.get(k),
                }
                for k in Incu_locs[:ar.num_plates][::-1]
            ], index='location')
            incu_df.index.name = None

            rest_df = pd.DataFrame.from_records([
                {
                    'location': k,
                    'thing': world.get(k),
                }
                for k in 'incu wash disp'.split()
            ], index='location')
            rest_df.index.name = None

            ABC_df = pd.DataFrame.from_records([
                {
                    'z': int(a.strip('A')),
                    'A': world.get(a),
                    'B': world.get(b),
                    'C': world.get(c),
                }
                for a, b, c in zip(A_locs, B_locs, C_locs)
            ], index='z')
            ABC_df.index.name = None

            if ar.num_plates >= 14:
                grid = '''
                    "incu rest" 1fr
                    "incu ABC"  auto
                  / auto auto
                '''
            else:
                grid = '''
                    "incu ABC"  auto
                    "rest rest" auto
                  / auto auto
                '''
            info += div(
                css='display: grid; place-items: center'
            ).append(div(
                V.raw(
                    incu_df.fillna('').to_html(index=1, border=0, table_id='incu', classes='even' if ar.num_plates % 2 == 0 else [])
                ),
                V.raw(
                    ABC_df.fillna('').to_html(index=1, border=0, table_id='ABC')
                ),
                V.raw(
                    rest_df.T.fillna('\u200b').to_html(index=0, border=0, table_id='rest')
                ),
                css='''
                    & {
                        display: grid;
                        grid: ''' + grid + ''';
                        gap: 10px;
                    }
                    & #incu { grid-area: incu;  }
                    & #ABC { grid-area: ABC;  }
                    & #rest { grid-area: rest; }
                    & table {
                        margin-top: auto;
                    }
                    & td, & th {
                        text-align: center
                    }
                    & th {
                        min-width: 50px;
                    }
                    & :where(#incu, #ABC) th:first-child {
                        text-align: right
                    }
                    & td {
                        min-width: 90px;
                    }
                '''
            ))
        if ar.has_error():
            box = div(
                border='2px var(--red) solid',
                px=8,
                py=4,
                border_radius=2,
                css='''
                    & > pre {
                        line-height: 1.5;
                        margin: 0;
                    }
                '''
            )
            for i, row in ar.errors.iterrows():
                try:
                    tb = row.traceback
                except:
                    tb = None
                if not isinstance(tb, str):
                    tb = None
                box += pre(f'[{row.log_time.strftime("%H:%M:%S")}] {row.arg} {"(...)" if tb else ""}', title=tb)
            if not ar.process_is_alive:
                box += pre('Controller process has terminated.')
            info += box

        if ar.completed:
            text = ''
        elif ar.process_is_alive:
            text = f'pid: {ar.pid} on {platform.node()} with config {config.name}'
        else:
            text = f'pid: - on {platform.node()} with config {config.name}'
        if text:
            yield V.pre(text,
                grid_area='info-foot',
                padding_top='0.5em',
                user_select='none',
                opacity='0.85',
            )

        skip = m.var(Str(desc='Single washes and dispenses to skip, separated by comma'))
        drop = m.var(Str(desc='Plates to drop from the rest of the run, separated by comma'))

        if ar.completed:
            pass
        elif not ar.has_error():
            yield m.defaults().goto_script()
            yield button(
                'stop',
                onclick='confirm("Stop?")&&' + sigint.call(ar.pid),
                grid_area='stop',
                css='''
                    & {
                        font-size: 2rem;
                        flex: 1 0 0;
                        color: var(--red);
                        border-color: var(--red);
                        border-radius: 4px;
                        padding: 15px;
                    }
                    &:focus {
                        outline: 3px var(--red) solid;
                    }
                '''
            )
        else:
            buttons: list[Tag] = []

            skipped = utils.read_commasep(skip.value)
            dropped = utils.read_commasep(drop.value)

            vis.data_skipped += json.dumps(skipped)
            vis.onclick += m.update_untyped({
                skip: js('''
                    (() => {
                        let skipped = JSON.parse(this.dataset.skipped)
                        let id = event.target.dataset.simpleId
                        if (!id) {
                            return skipped.join(',')
                        } else if (skipped.includes(id)) {
                            return skipped.filter(i => i != id).join(',')
                        } else {
                            return [...skipped, id].join(',')
                        }
                    })()
                ''')
            }).goto()

            selectors: list[str] = []
            selectors += [f'[data-simple-id={v!r}][is-estimate]' for v in skipped]
            selectors += [f'[data-plate-id={v!r}][is-estimate]' for v in dropped]

            if selectors:
                vis.css += (
                    ', '.join(f'& {selector}' for selector in selectors) + '''{
                        outline: 3px var(--red) solid;
                    }'''
                )

            import textwrap

            resume_text = textwrap.dedent('''
                Robotarm needs to be moved back to the neutral position by B21 hotel.
                All plate positions should be as indicated by the plate table.
            ''')

            yield div(
                button('open gripper', onclick=robotarm_open_gripper.call()),
                button('set robot in freedrive', onclick=robotarm_freedrive.call()),
                button('move robot to neutral', onclick='confirm("Move robot to neutral?")&&' + robotarm_to_neutral.call()),
                *form(m, skip, drop),
                button('resume' ,
                    onclick=
                        f'confirm("Resume?" + {json.dumps(resume_text)})&&' +
                        resume.call(ar.log_filename, skip=skipped, drop=dropped),
                    title=resume_text),
                grid_area='stop',
                css=form_css,
            )

    yield vis.extend(grid_area='vis')

    if ar is not None and ar.completed:
        d = ar.durations()
        if d is not None:
            yield div(
                V.raw(
                    d.to_html(border=0, index=False)
                ),
                div(height=40),
                grid_area='info-foot',
                css='''
                    & table {
                        margin: auto;
                    }
                    & table td, & table th {
                        text-align: left;
                    }
                    & table td:nth-child(2) {
                        text-align: right;
                    }
                '''
            )

    if path:
        yield V.queue_refresh(150)

def form(m: Store, *vs: Int | Str | Bool):
    for v in vs:
        yield label(
            span(f"{v.name or ''}:"),
            v.input(m).extend(id_=v.name, spellcheck="false", autocomplete="off"),
            title=v.desc,
        )

serve.run()
