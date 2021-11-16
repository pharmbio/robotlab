
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

@serve.expose
def start(simulate: bool):
    log_filename = 'logs/' + utils.now_str_for_filename() + '-from-gui.jsonl'
    args = Args(
        config_name='dry-run' if simulate else 'dry-ff',
        cell_paint='6,6,6',
        log_filename=log_filename,
        interleave=True,
        two_final_washes=True,
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

import pandas as pd
from datetime import datetime, timedelta
from functools import lru_cache

@lru_cache
def load_pickle(filepath: str) -> Any:
    with open(filepath, 'rb') as fp:
        rs = pickle.load(fp)
    return prep(pd.DataFrame.from_records(rs))

def prep(df: Any):
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
    df['finished'] = df.id.isin(df[df.kind == 'end'].id)
    df['running'] = (df.kind == 'begin') & ~df.finished
    return df

def durations(d: Any):
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

def analyze(r: Any) -> tuple[datetime ,float, Any, Any, Any]:
    first_row = r.iloc[0, :]
    zero_time = first_row.log_time.to_pydatetime() - timedelta(seconds=first_row.t)
    t_now = (datetime.now() - zero_time).total_seconds()
    t_now *= first_row.speedup
    estimates = load_pickle(first_row.estimates_pickle_file)
    r = r.drop(columns='log_time substep slot'.split(), errors='ignore')
    r_sections = r[~r.section.isna()]
    r = r[r.kind.isin(('begin', 'end'))]
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
    r.loc[~r.finished, 'countdown'] = (r.t - t_now)
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

    def cleanup(df):
        df = df[~df.arg.str.contains('Validate ')].copy()
        df.arg = df.arg.str.replace('RunValidated ', '', regex=False)
        df.arg = df.arg.str.replace('Run ', '', regex=False)
        df.arg = df.arg.str.replace('automation_v3.1/', '', regex=False)
        return df

    r = cleanup(r)
    vis = cleanup(vis)

    sections = vis[~vis.section.isna()]
    sections = sections['t is_estimate section'.split()]
    sections = sections.append([
        {
            't': 0,
            'is_estimate': False,
            'section': 'begin',
        },
        {
            't': vis.t.max(),
            'is_estimate': True,
            'section': 'end',
        }
    ], ignore_index=True)
    sections = sections.sort_values('t')
    sections = sections.reset_index(drop=True)
    sections['length'] = sections.t.diff()[1:].reset_index(drop=True)
    sections['t0'] = sections.t
    sections['t'] = sections.t0 + sections.length
    sections = sections['t0 t length section is_estimate'.split()]
    sections['finished'] = sections.t0 < t_now
    sections.loc[~sections.finished, 'countdown'] = (sections.t0 - t_now)

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

    return zero_time, t_now, r[cols].fillna(''), vis[cols].fillna(''), sections

def make_vis(t_now: float, r: Any, sections: Any):
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
    if 0 <= t_now <= start_times.max():
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
        area += div(
            str(row.plate_id) if row.plate_id else '',
            css='''
                & {
                    color: var(--bg);
                    position: absolute;
                    border-radius: 1px;
                    outline: 1px #0005 solid;
                    display: grid;
                    place-items: center;
                    font-size: 0.8em;
                }
            ''',
            style=trim(f'''
                top: {row.y0 * 100:.1f}%;
                height: {row.h * 100:.1f}%;
                min-height: 1px;
                left: {(row.slot*2.3 + row.machine_slot) * width:.1f}px;
                width: {row.machine_width * width - 2}px;
                background: {stripes_dn if row.is_estimate else ''} {row.color};
                z-index: {row.zindex};
            '''),
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
            body {
                display: grid;
                grid:
                    "header    header"     auto
                    "vis       info"       1fr
                    "vis       button"     4em
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
        df = prep(df)
        zero_time, t, r, vis, sections = analyze(df)
        if r is not None:
            r.resource = r.resource.str.replace('main', 'arm', regex=False)
            r = r[r.running]
            r = r['resource t countdown arg plate_id'.split()]
            r.t = zero_time + pd.to_timedelta(r.t, unit='seconds')
            r.t = r.t.dt.strftime('%H:%M:%S')
            r.countdown = pd.to_datetime(r.countdown.clip(0), unit='s')
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
        if vis is not None:
            vis_foot, vis = make_vis(t, vis, sections)
        if sections is not None:
            sections = sections['section countdown t0 length'.split()]
            sections.section = sections.section.replace(' \d*$', '', regex=True)
            sections.t0 = zero_time + pd.to_timedelta(sections.t0, unit='seconds')
            sections.t0 = sections.t0.dt.strftime('%H:%M:%S')
            sections.countdown = pd.to_datetime(sections.countdown.clip(0), unit='s')
            sections.countdown = sections.countdown.dt.strftime('%H:%M:%S')
            try:
                sections.countdown = sections.countdown.str.lstrip('0:')
            except:
                pass
            sections.length = pd.to_datetime(sections.length, unit='s')
            sections.length = sections.length.dt.strftime('%M:%S')
            sections = sections.fillna('')
            info += div(
                V.raw(
                    sections.to_html(index=False, border=0)
                ),
                css='''
                    & table {
                        margin: auto;
                    }
                    & table td:nth-child(2) {
                        text-align: right
                    }
                '''
            )
        errors = df[df.kind == 'error']
        if errors.size:
            for i, row in errors.iterrows():
                info += pre(
                    row.log_time.strftime('%H:%M:%S'),
                    ': ',
                    V.raw(row.arg),
                )
        else:
            r = durations(df)
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
                            text-align: right
                        }
                    '''
                )

    yield vis.extend(grid_area='vis')

    yield button(
        'stop', grid_area='button', color='var(--red)', font_size='2rem', border_color='var(--red)',
        onclick='confirm("Stop?")'
    )

    grep = check_output('ps ux | grep python3.10 | grep json-arg | grep -v grep || true', shell=True).decode()
    yield vis_foot.extend(grid_area='vis-foot')
    yield V.pre(grep, overflow_x='hidden', grid_area='info-foot')

    yield V.queue_refresh(250)
    # yield V.script(raw(queue_refresh.call()), eval=True, defer=True)

import time

# @utils.spawn
# def refresher():
#     ms = 1000
#     while True:
#         time.sleep(ms/1000.0)
#         serve.reload()

serve.run()
