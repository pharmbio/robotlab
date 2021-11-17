
from __future__ import annotations
from typing import *

from viable import app, js
from viable import head, serve, esc, css_esc, trim, button, pre
from viable import Tag, div, span, label, img, raw, Input, input
import viable as V

from flask import request
from collections import *

import utils

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
import sys

config: RuntimeConfig = config_lookup('live')
if '--simulator' in sys.argv:
    config = config_lookup('simulator')
elif '--forward' in sys.argv:
    config = config_lookup('forward')

@serve.expose
def sigint(pid: int):
    os.kill(pid, signal.SIGINT)

@serve.expose
def robotarm_freedrive():
    '''
    Sets the robotarm in freedrive
    '''
    arm = get_robotarm(config)
    arm.execute_moves([moves.RawCode("freedrive_mode() sleep(3600)")], name='gui', allow_partial_completion=True)
    arm.close()

@serve.expose
def robotarm_to_neutral():
    '''
    Slowly moves in joint space to the neutral position by B21
    '''
    arm = get_robotarm(config)
    arm.execute_moves(moves.movelists['to neu'], name='gui', allow_partial_completion=True)
    arm.close()
    print('ok')

@serve.expose
def start(simulate: bool):
    log_filename = 'logs/' + utils.now_str_for_filename() + '-from-gui.jsonl'
    args = Args(
        config_name='dry-run' if simulate else 'dry-wall',
        cell_paint='6,6,6',
        log_filename=log_filename,
        interleave=True,
        two_final_washes=False,
    )
    cmd = [
        "python3.10",
        "cli.py",
        "--json-arg",
        json.dumps(dataclasses.asdict(args)),
    ]
    Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL)
    return {
        'goto': log_filename,
        'refresh': True,
    }

@serve.expose
def resume(log_filename_in: str):
    log_filename_new = 'logs/' + utils.now_str_for_filename() + '-resume-from-gui.jsonl'
    args = Args(
        config_name='dry-wall',
        resume=log_filename_in,
        log_filename=log_filename_new,
        interleave=False,
        two_final_washes=False,
    )
    cmd = [
        "python3.10",
        "cli.py",
        "--json-arg",
        json.dumps(dataclasses.asdict(args)),
    ]
    Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL)
    return {
        'goto': log_filename_new,
        'refresh': True,
    }

serve.suppress_flask_logging()

stripe_size = 4
stripe_width = 1.2
sz = stripe_size
stripes_up = f'''
  <svg xmlns='http://www.w3.org/2000/svg' width='{sz}' height='{sz}'>
    <path d='
       M{-sz},{1*sz} l{3*sz},{-3*sz}
       M{-sz},{2*sz} l{3*sz},{-3*sz}
       M{-sz},{3*sz} l{3*sz},{-3*sz}
    ' stroke='white' stroke-width='{stripe_width}'/>
  </svg>
'''
stripes_dn = f'''
  <svg xmlns='http://www.w3.org/2000/svg' width='{sz}' height='{sz}'>
    <path d='
       M{-sz},{-0*sz} l{3*sz},{3*sz}
       M{-sz},{-1*sz} l{3*sz},{3*sz}
       M{-sz},{-2*sz} l{3*sz},{3*sz}
    ' stroke='#fff5' stroke-width='{stripe_width}'/>
  </svg>
'''
from base64 import b64encode
def b64svg(s: str):
    return f"url('data:image/svg+xml;base64,{b64encode(s.encode()).decode()}')"

stripes_up = b64svg(stripes_up)
stripes_dn = b64svg(stripes_dn)

import pandas as pd
from datetime import datetime, timedelta
from functools import lru_cache
from dataclasses import dataclass

@lru_cache
def load_from_pickle(filepath: str) -> Any:
    with open(filepath, 'rb') as fp:
        rs = pickle.load(fp)
    return prep(pd.DataFrame.from_records(rs))

def prep(df: pd.DataFrame):
    if 'id' in df:
        df.id = pd.to_numeric(df.id, errors='coerce').fillna(-1).astype(int)
    if 'plate_id' in df:
        df.plate_id = pd.to_numeric(df.plate_id, errors='coerce').fillna(0).astype(int)
    else:
        df['plate_id'] = 0
    if 'batch_index' in df:
        df.batch_index = pd.to_numeric(df.batch_index, errors='coerce').fillna(0).astype(int)
    else:
        df['batch_index'] = 0
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
    return df

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

    def has_error(self):
        if self.completed:
            return False
        return not self.process_is_alive or self.errors.size > 0

    @staticmethod
    def init(df: Any) -> AnalyzeResult:
        df = prep(df)
        completed = 'completed' in df and df.completed.any()

        meta = df.runtime_metadata # .iloc[-1]
        meta = meta[~meta.isna()]
        runtime_metadata = meta.iloc[-1]

        df['current'] = df.index >= meta.index[-1]

        first_row = df.iloc[meta.index[-1], :]
        zero_time = first_row.log_time.to_pydatetime() - timedelta(seconds=first_row.t)
        t_now = (datetime.now() - zero_time).total_seconds()
        t_now *= runtime_metadata['speedup']

        if completed:
            t_now = df.t.max()

        estimates = load_from_pickle(runtime_metadata['estimates_pickle_file'])
        estimates['finished'] = True
        estimates['running'] = False
        pid = runtime_metadata['pid']
        log_filename = runtime_metadata['log_filename']

        errors = df[(df.kind == 'error') & df.current]

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
        r = r.drop(columns='log_time substep slot'.split(), errors='ignore')
        r_sections = r[~r.section.isna()]
        r = r[r.kind.isin(('begin', 'end'))]
        r['finished'] = r.id.isin(r[r.kind == 'end'].id)
        r['running'] = (r.kind == 'begin') & ~r.finished & r.current
        r = r[
            r.source.isin(('wash', 'disp', 'incu', 'main'))
            | r.report_behind_time
            | ((r.source == 'robotarm') & r.running)
        ]
        r = r[~r.arg.str.contains('Validate ')]
        r = r.dropna(axis='columns', how='all')
        if 'secs' not in r:
            r['secs'] = float('NaN')
        r.loc[~r.finished, 't0'] = r.t
        r.loc[~r.finished, 't'] = r.t + r.est.fillna(r.secs)
        r.loc[~r.finished, 'duration'] = r.t - r.t0
        r.loc[~r.finished, 'elapsed'] = -(r.t0 - t_now)
        r.loc[~r.finished, 'countdown'] = (r.t.round() - t_now)
        r.loc[~r.finished, 'pct'] = r.elapsed / r.duration * 100.0
        r = r[~r.finished | (r.kind == 'end')]
        r.t = r.t.round(1)
        if 't0' not in r:
            r['t0'] = r.t
        r['is_estimate'] = False
        r.loc[r.running, 'is_estimate'] = True
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

        def cleanup(d):
            d = d[~d.arg.str.contains('Validate ')].copy()
            d.arg = d.arg.str.replace('RunValidated ', '', regex=False)
            d.arg = d.arg.str.replace('Run ', '', regex=False)
            d.arg = d.arg.str.replace('automation_v3.1/', '', regex=False)
            return d

        r = cleanup(r)
        vis = cleanup(vis)

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
        sections.loc[~sections.finished, 'countdown'] = (sections.t0.round() - t_now)

        cols = '''
            step
            t0
            t
            source
            resource
            arg
            elapsed
            countdown
            pct
            is_estimate
            batch_index
            plate_id
            id
            running
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
        )

    def durations(self) -> pd.DataFrame:
        d = self.df
        d = d[d.source == 'duration']
        d = pd.concat([d, d.arg.str.extract(r'plate \d+ (?P<checkpoint>.*)$')], axis=1)
        d = d[~d.checkpoint.isna()]
        d = d['t0 t duration arg id step plate_id checkpoint'.split()]
        d = d[~d.checkpoint.str.contains('pre disp done')]
        d = d[
              (d.checkpoint == '37C')
            | d.checkpoint.str.contains('incubation')
            # | d.checkpoint.str.contains('transfer')
        ]
        d.checkpoint = d.checkpoint.str.replace('incubation', 'incu', regex=False)
        d.duration = pd.to_datetime(d.duration, unit='s')
        d.duration = d.duration.dt.strftime('%M:%S')
        d = d.rename(columns={'plate_id': 'plate'})
        pivot = d.pivot(index=['plate'], columns='checkpoint')
        if not pivot.empty:
            return pivot.duration.fillna('')
        else:
            return None

    def running(self) -> pd.DataFrame:
        r = self.r
        zero_time = self.zero_time
        r.resource = r.resource.str.replace('main', 'arm', regex=False)
        r = r[r.running]
        r = r['resource t countdown arg plate_id'.split()]
        r.t = zero_time + pd.to_timedelta(r.t, unit='seconds')
        r.t = r.t.dt.strftime('%H:%M:%S')
        r.countdown = pd.to_datetime(r.countdown.clip(-1) + 1, unit='s')
        r.countdown = r.countdown.dt.strftime('%M:%S')
        try:
            r.countdown = r.countdown.str.lstrip('0:')
        except:
            pass
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
        sections = self.sections
        sections.section = sections.section.replace(' \d*$', '', regex=True)
        sections.t0 = zero_time + pd.to_timedelta(sections.t0, unit='seconds')
        sections.t0 = sections.t0.dt.strftime('%H:%M:%S')
        sections.countdown = pd.to_datetime(sections.countdown.clip(-1) + 1, unit='s')
        sections.countdown = sections.countdown.dt.strftime('%H:%M:%S')
        try:
            sections.countdown = sections.countdown.str.lstrip('0:')
        except:
            pass
        sections.length = pd.to_datetime(sections.length, unit='s')
        sections.length = sections.length.dt.strftime('%M:%S')
        sections = sections.fillna('')
        return sections

    def make_vis(self) -> tuple[Tag, Tag]:
        t_now = self.t_now
        r = self.vis
        sections = self.sections
        area = div(css='''
            position: relative;
            user-select: none;
        ''')

        area.onmousemove += """
            console.log(event)
            if (event.target.dataset.info)
                document.querySelector('#info').innerHTML = event.target.dataset.info.trim()
        """

        area.onmouseout += """
            if (event.target.dataset.info)
                document.querySelector('#info').innerHTML = ''
        """

        info = pre(id="info", nodiff=True)

        start_times = sections.t0
        max_length = sections.length.max()

        r = r[r.source.isin(('wash', 'disp'))]
        r = r[~r.batch_index.isna()]
        if 0 <= t_now <= start_times.max() and not self.completed:
            r = r.append({
                't0': t_now,
                't': t_now,
                'is_estimate': False,
                'source': 'now',
                'arg': '',
                'plate_id': 0,
            }, ignore_index=True)
        r['slot'] = 0
        for (i, (_, section)) in enumerate(sections.iterrows()):
            if not pd.isna(section.length):
                r = r.append({
                    't0': section.t0,
                    't': section.t,
                    'is_estimate': False,
                    'source': 'marker',
                    'arg': '',
                    'plate_id': 0,
                }, ignore_index=True)
                r.loc[r.t0 >= section.t0, 'slot'] = i
                r.loc[r.t0 >= section.t0, 'section'] = section.section

        r['slot_start'] = r.slot.replace(start_times)

        r['color'] = r.source.replace({
            'wash': 'var(--cyan)',
            'disp': 'var(--purple)',
            'incu': 'var(--green)',
            'now': '#fff',
            'marker': '#383838',
        })
        r['zindex'] = r.source.replace({
            'wash': 2,
            'disp': 2,
            'incu': 2,
            'now': 3,
            'marker': 1,
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

        r['y0'] = (r.t0 - r.slot_start) / max_length
        r['y1'] = (r.t - r.slot_start) / max_length
        r['h'] = r.y1 - r.y0

        width = 23
        for _, row in r.iterrows():
            est = 1 if row.is_estimate else 0
            area += div(
                str(row.plate_id) if row.plate_id else '',
                css=f'''
                    color: var(--bg);
                    position: absolute;
                    border-radius: 0px;
                    outline: 1px #0005 solid;
                    display: grid;
                    place-items: center;
                    font-size: 0.8em;
                    min-height: 1px;
                ''',
                css_=f'''
                    width: {row.machine_width * width - 2}px;
                    background: {row.color};
                    opacity: {1.0 - 0.22*est};
                    z-index: {row.zindex};
                ''',
                style=trim(f'''
                    left:{(row.slot*2.3 + row.machine_slot) * width:.0f}px;
                    top:calc({row.y0 * 100:.1f}% + 1px);
                    height:calc({row.h * 100:.1f}% + 1px);
                ''', sep=''),
                data_info=row.arg or ''
            )

        area.width += f'{width*(r.slot.max()+1)*2.3}px'
        area.height += '100%'

        return info, area

@serve.route('/')
@serve.route('/<path:path>')
def index(path: str | None = None) -> Iterator[Tag | dict[str, str]]:
    yield {
        'sheet': '''
            html {
                box-sizing: border-box;
            }
            * {
                box-sizing: inherit;
            }
            body, button {
                background: var(--bg);
                color:      var(--fg);
                font-family: monospace;
                font-size: 18px;
            }
            table td, table th, table tr, table {
                border: none;
            }
            table td, table th {
                padding: 2px 8px;
                margin: 1px 2px;
                background: #383838;
                min-width: 4em;
            }
            table tr:nth-child(even) :where(td, th) {
                background: #584838;
            }
            table {
                border-spacing: 1px;
            }
            body {
                display: grid;
                grid:
                    "header    header"     auto
                    "vis       info"       1fr
                    "vis       button"     minmax(min-content, 5em)
                    "vis-foot  vis-foot"   2em
                    "info-foot info-foot"  2em
                  / auto       1fr;
                grid-gap: 10px;
                padding: 10px;
            }
            body > pre {
                margin: 0;
            }
            html, body {
                height: 100%;
                width: 100%;
                margin: 0;
            }
            html {
                --bg:     #2d2d2d;
                --fg:     #d3d0c8;
                --red:    #f2777a;
                --brown:  #d27b53;
                --green:  #99cc99;
                --yellow: #ffcc66;
                --blue:   #6699cc;
                --purple: #cc99cc;
                --cyan:   #66cccc;
                --orange: #f99157;
            }
            .red    { color: var(--red);    }
            .brown  { color: var(--brown);  }
            .green  { color: var(--green);  }
            .yellow { color: var(--yellow); }
            .blue   { color: var(--blue);   }
            .purple { color: var(--purple); }
            .cyan   { color: var(--cyan);   }
            .orange { color: var(--orange); }
        '''
    }
    yield V.head(V.title('cell painter - ', path or ''))
    yield div(
        button('start', onclick=start.call(simulate=False)),
        button('simulate', onclick=start.call(simulate=True)),
        grid_area='header',
        css='& *+* { margin-left: 8px }',
    )
    info = div(
        grid_area='info',
        font_size='1rem',
        css='''
            & *+* {
                margin-top: 1em;
                margin-left: auto;
                margin-right: auto;
            }
            & table {
                background: #0005;
            }
        ''')
    yield info
    df = None
    vis = div()
    vis_foot = div()
    if path:
        try:
            df = pd.read_json(path, lines=True)
        except:
            pass
    if df is not None:
        ar = AnalyzeResult.init(df)
        if 1:
            r = ar.running()
            r = r['resource countdown arg plate'.split()]
            info += div(
                V.raw(
                    r.to_html(index=False, border=0)
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
        if 1:
            vis_foot, vis = ar.make_vis()
        if 1:
            sections = ar.pretty_sections()
            sections = sections['batch_index section countdown t0 length'.split()]
            sections = sections.rename(columns={'batch_index': 'batch'})
            sections.batch += 1
            info += div(
                V.raw(
                    sections.to_html(index=False, border=0)
                ),
                css='''
                    & table {
                        margin: auto;
                    }
                    & table td:nth-child(1),
                    & table td:nth-child(3)
                    {
                        text-align: right
                    }
                '''
            )
        if ar.has_error():
            box = div(
                border='2px var(--red) solid',
                px=8, py=4, border_radius=2,
                color='#fff',
                css='''
                    & > pre {
                        line-height: 1.5;
                        margin: 0;
                    }
                '''
            )
            lines: list[str] = []
            for i, row in ar.errors.iterrows():
                tb = row.traceback
                if not isinstance(tb, str):
                    tb = None
                box += pre(f'[{row.log_time.strftime("%H:%M:%S")}] {row.arg} {"(...)" if tb else ""}', title=tb)
            if not ar.process_is_alive:
                box += pre('Controller process has terminated.')
            info += box
        else:
            r = ar.durations()
            if r is not None:
                info += div(
                    V.raw(
                        r.to_html(border=0)
                    ),
                    css='''
                        & table {
                            margin: auto;
                        }
                        & table td, & table th {
                            text-align: right;
                        }
                    '''
                )

        if ar.completed:
            text = 'completed'
        elif ar.process_is_alive:
            text = f'pid: {ar.pid}'
        else:
            text = f'pid: -'
        yield V.pre(text, overflow_x='hidden', grid_area='info-foot')

        buttons: list[Tag] = []

        if not ar.has_error():
            buttons = [
                button('stop', onclick='confirm("Stop?")&&' + sigint.call(ar.pid), style='--color: var(--red)')
            ]
        else:
            buttons = [
                button('set robot in freedrive', onclick=robotarm_freedrive.call()),
                button('move robot to neutral', onclick='confirm("Move robot to neutral?")&&' + robotarm_to_neutral.call()),
                button('resume', onclick='confirm("Resume?")&&' + resume.call(ar.log_filename)),
            ]
        yield div(
            *buttons,
            display='flex',
            grid_area='button',
            margin='auto',
            width='100%',
            height='100%',
            gap=10,
            css='''
                & button {
                    flex: 1 0 0;
                    color: var(--color, var(--fg));
                    border-color: var(--color, var(--fg));
                    border-radius: 4px;
                    font-size: 2rem;
                }
                & button:focus {
                    outline: 3px var(--color, var(--blue)) solid;
                }
            '''
        )


    yield vis.extend(grid_area='vis')

    yield vis_foot.extend(grid_area='vis-foot')

    yield V.queue_refresh(200)
    # yield V.script(raw(queue_refresh.call()), eval=True, defer=True)

import time

# @utils.spawn
# def refresher():
#     ms = 1000
#     while True:
#         time.sleep(ms/1000.0)
#         serve.reload()

serve.run()
