from __future__ import annotations
from typing import *

from .viable import app, js
from .viable import serve, trim, button, pre
from .viable import Tag, div, span, label
from . import viable as V

from collections import *
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import lru_cache

from pathlib import Path
from subprocess import Popen, DEVNULL
import json
import math
import os
import pickle
import platform
import signal
import sys

from .log import Log
from .cli import Args

from . import commands
from . import moves
from . import runtime
from . import utils
from .log import LogEntry, Metadata, RuntimeMetadata, Error, countdown
from .moves import RawCode, Move
from .protocol import Locations
from .provenance import Var, Int, Str, Store, DB, Bool
from .runtime import get_robotarm, RuntimeConfig

config: RuntimeConfig
for c in runtime.configs:
    if '--' + c.name in sys.argv:
        config = c
        break
else:
    raise ValueError('Start with one of ' + ', '.join('--' + c.name for c in runtime.configs))

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
def robotarm_set_speed(pct: int):
    '''
    Sets the robotarm speed, in percentages
    '''
    print(pct)
    arm = get_robotarm(config, quiet=False, include_gripper=True)
    arm.set_speed(pct)
    arm.close()

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
    config_name='dry-run' if simulate else config.name
    if incu in {'1200', '20:00', ''} and N >= 8:
        incu = '1200,1200,1200,1200,X'
    log_filename = 'logs/' + utils.now_str_for_filename() + f'-{config_name}-from-gui.jsonl'
    args = Args(
        config_name=config_name,
        log_filename=log_filename,
        cell_paint=batch_sizes,
        interleave=interleave,
        two_final_washes=two_final_washes,
        lockstep=lockstep,
        start_from_pfa=start_from_pfa,
        incu=incu,
        yes=True,
    )
    Path('cache').mkdir(exist_ok=True)
    cmd = [
        'sh', '-c',
        'cellpainter --json-arg "$1" 2>"$2"',
        '--',
        json.dumps(utils.nub(args)),
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
        yes=True,
    )
    Path('cache').mkdir(exist_ok=True)
    cmd = [
        'sh', '-c',
        'cellpainter --json-arg "$1" 2>"$2"',
        '--',
        json.dumps(utils.nub(args)),
        as_stderr(log_filename_new),
    ]
    Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=sys.stderr, stdin=DEVNULL)
    return {
        'goto': log_filename_new,
        'refresh': True,
    }

serve.suppress_flask_logging()
@lru_cache
def load_from_pickle(filepath: str) -> Log:
    with open(filepath, 'rb') as fp:
        res = pickle.load(fp)
    return Log(res).drop_boring()

@lru_cache(maxsize=1)
def _jsonl_to_log(path: str, mtime_ns: int) -> Log | None:
    try:
        return Log.from_jsonl(path).drop_boring()
    except:
        return None

def jsonl_to_log(path: str) -> Log | None:
    p = Path(path)
    try:
        stat = p.stat()
    except FileNotFoundError:
        return None
    return _jsonl_to_log(path, stat.st_mtime_ns)

def pp_secs(secs: int | float, zero: str='0'):
    dt = timedelta(seconds=math.ceil(secs))
    if dt < timedelta(seconds=0):
        return zero
    s = str(dt)
    s = s.lstrip('0:')
    return s or zero

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
            tr += V.td(str(v) or '\u200b')
        body += tr
    return V.table(head, body)

@dataclass(frozen=True, kw_only=True)
class AnalyzeResult:
    zero_time: datetime
    t_now: float
    runtime_metadata: RuntimeMetadata
    completed: bool
    sections: dict[str, Log]
    running_entries: list[LogEntry]
    errors: list[tuple[Error, LogEntry]]
    world: dict[str, str]
    num_plates: int

    def has_error(self):
        if self.completed:
            return False
        return not self.process_is_alive() or self.errors

    def process_is_alive(self) -> bool:
        pid = self.runtime_metadata.pid
        log_filename = self.runtime_metadata.log_filename
        if pid:
            try:
                with open(f'/proc/{pid}/cmdline', 'r') as fp:
                    cmdline = fp.read()
            except FileNotFoundError:
                cmdline = ''
            return log_filename in cmdline
        else:
            return False

    @staticmethod
    def init(m: Log, until: float | None = None) -> AnalyzeResult | None:

        completed = m.is_completed()

        runtime_metadata = m.runtime_metadata()
        if not runtime_metadata:
            return None
        zero_time = m.zero_time()
        t_now = (datetime.now() - zero_time).total_seconds()

        if completed:
            t_now = m.max_t() + 1

        errors = m.errors()
        if errors:
            t_now = Log(e for _, e in errors).max_t() + 1

        if until is not None:
            t_now = until
            m = Log([e for e in m if e.t < until])

        running = m.running()
        if not running:
            return None

        estimates = load_from_pickle(runtime_metadata.estimates_pickle_file)
        num_plates = max(m.num_plates(), estimates.num_plates())

        finished_ids = m.finished()
        running_ids = Log(running.entries).ids()
        live_ids = finished_ids | running_ids

        running_entries = [
            e.init(
                log_time=e.log_time,
                t0=e.t,
                t=e.t + (e.metadata.est or e.metadata.sleep_secs or 0.0)
            ).add(Metadata(is_estimate=True))
            for e in running.entries
        ]

        estimates = estimates.where(lambda e: e.is_end_or_inf())
        estimates = estimates.where(lambda e: e.metadata.id not in live_ids)
        estimates = estimates.add(Metadata(is_estimate=True))

        vis = Log(m + running_entries + estimates)
        vis = vis.where(lambda e: e.is_end_or_inf())
        end = LogEntry(t=vis.max_t(), metadata=Metadata(section='end'))
        vis = Log(vis + [end])
        sections = vis.group_by_section()

        return AnalyzeResult(
            zero_time=zero_time,
            t_now=t_now,
            runtime_metadata=runtime_metadata,
            completed=completed,
            running_entries=running_entries,
            sections=sections,
            errors=errors,
            world=running.world,
            num_plates=num_plates,
        )

    def entry_desc(self, e: LogEntry):
        cmd = e.cmd
        match cmd:
            case commands.RobotarmCmd():
                return cmd.program_name
            case commands.BiotekCmd():
                if cmd.action == 'TestCommunications':
                    return cmd.action
                else:
                    return cmd.protocol_path
            case commands.IncuCmd():
                if cmd.incu_loc:
                    return cmd.action + ' ' + cmd.incu_loc
                else:
                    return cmd.action
            case commands.WaitForCheckpoint() if cmd.plus_seconds.unwrap() > 0.5:
                return f'sleeping to {self.pp_time_at(e.t)}'
            case commands.WaitForCheckpoint():
                return f'waiting for {cmd.name}'
            case commands.Idle() if e.t0:
                return f'sleeping to {self.pp_time_at(e.t)}'
            case _:
                return str(e)

    def running(self):
        d: dict[str, LogEntry | None] = {}
        resources = 'main disp wash incu'.split()
        G = utils.group_by(self.running_entries, key=lambda e: e.metadata.thread_resource)
        G['main'] = G[None]
        for resource in resources:
            es = G.get(resource, [])
            if es:
                d[resource] = es[0]
            else:
                d[resource] = None
            if len(es) > 2:
                print(f'{len(es)} from {resource=}?')

        table: list[dict[str, str | float | int | None]] = []
        for resource, e in d.items():
            table.append({
                'resource':  resource,
                'countdown': e and pp_secs(e.countdown(self.t_now)),
                'desc':      e and self.entry_desc(e),
                'plate':     e and e.metadata.plate_id,
            })
        return table

    def time_at(self, secs: float):
        return self.zero_time + timedelta(seconds=secs)

    def pp_time_at(self, secs: float):
        return self.time_at(secs).strftime('%H:%M:%S')

    def countdown(self, to: float):
        return countdown(self.t_now, to)

    def pp_countdown(self, to: float, zero: str=''):
        return pp_secs(self.countdown(to), zero=zero)

    def pretty_sections(self):
        table: list[dict[str, str | float | int]] = []
        for name, entries in self.sections.items():
            if entries:
                table.append({
                    'batch':     entries[-1].metadata.batch_index + 1,
                    'section':   name.strip(' 0123456789'),
                    'countdown': self.pp_countdown(entries.min_t(), zero=''),
                    't0':        self.pp_time_at(entries.min_t()),
                    'length':    pp_secs(math.ceil(entries.length()), zero=''),
                })
        return table

    def make_vis(self) -> Tag:
        t_now = self.t_now
        sections = {
            k: v
            for k, v in self.sections.items()
            if len(v) > 1
        }

        start_times = [s.min_t() for _, s in sections.items()]
        max_length = max(s.length() for _, s in sections.items())

        @dataclass
        class Row:
            t0: float
            t: float
            is_estimate: bool
            source: str
            column: int
            plate_id: str = ''
            simple_id: str = ''
            id: str = ''
            msg: str = ''
            entry: LogEntry | None = None

        bg_rows: list[Row] = []
        for i, (name, section) in enumerate(sections.items()):
            bg_rows += [Row(
                t0          = section.min_t(),
                t           = section.max_t(),
                is_estimate = False,
                source      = 'bg',
                column      = i,
            )]

        now_row: list[Row] = []
        for i, (_section_name, section) in reversed(list(enumerate(sections.items()))):
            if section.min_t() <= t_now <= section.max_t():
                now_row += [Row(
                    t0          = t_now,
                    t           = t_now,
                    is_estimate = False,
                    source      = 'now',
                    column      = i
                )]
                break

        rows: list[Row] = [
            Row(
                t0          = e.t0 or e.t,
                t           = e.t,
                is_estimate = e.metadata.is_estimate,
                source      = e.machine() or '?',
                plate_id    = e.metadata.plate_id or '',
                column      = i,
                id          = e.metadata.id,
                simple_id   = e.metadata.simple_id,
                msg         = getattr(e.cmd, 'protocol_path', ''),
                entry       = e,
            )
            for i, (_, entries) in enumerate(sections.items())
            for e in entries
            if isinstance(e.cmd, commands.BiotekCmd) #  machine() in ('wash', 'disp')
        ]

        rows = bg_rows + rows + now_row

        width = 23

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
                left: calc(100% + 1px);
                opacity: 1.0;
                top: 0;
                background: var(--row-color);
                white-space: pre;
                z-index: 1;
            }
        ''')

        for row in rows:
            slot = 0
            if row.source == 'disp':
                slot = 1
            my_width = 1
            if row.source in ('now', 'bg'):
                my_width = 2

            color = {
                'wash': 'var(--cyan)',
                'disp': 'var(--purple)',
                'incu': 'var(--green)',
                'now': '#fff',
                'bg': 'var(--bg-bright)',
            }[row.source]
            can_hover = row.source not in ('now', 'bg')

            column_start = start_times[row.column]
            y0 = (row.t0 - column_start) / (max_length or 1.0)
            y1 = (row.t - column_start) / (max_length or 1.0)
            h = y1 - y0

            info = f'{row.msg} ({row.simple_id})'
            area += div(
                row.plate_id,
                is_estimate=row.is_estimate,
                can_hover=can_hover,
                style=trim(f'''
                    left:{(row.column*2.3 + slot) * width:.0f}px;
                    top:{  y0 * 100:.3f}%;
                    height:{h * 100:.3f}%;
                    --row-color:{color};
                    --info:{repr(info)};
                ''', sep=''),
                css_=f'''
                    width: {width * my_width - 2}px;
                ''',
                data_simple_id=str(row.simple_id) or None,
                data_plate_id=str(row.plate_id),
            )

        area.width += f'{width*(len(sections)+1)*2.3}px'
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
            table:not(.even) tbody tr:nth-child(odd) td,
            table:not(.even) tbody tr:nth-child(odd) th
            {
                background: var(--bg-brown);
            }
            table.even tbody tr:nth-child(even) td,
            table.even tbody tr:nth-child(even) th
            {
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

    inverted_inputs_css = '''
        & input[type=range] {
            transform: translateY(3px);
            margin: 0 8px;
            filter: invert(83%) hue-rotate(135deg);
        }
        & input[type=checkbox] {
            filter: invert(83%) hue-rotate(180deg);
            cursor: pointer;
            width: 36px;
            height: 16px;
            margin-top: 8px;
            margin-bottom: 8px;
            margin-right: auto;
        }
    '''

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
    ''' + inverted_inputs_css

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
    log: Log | None = None
    stderr: str = ''
    vis = div()
    ar: AnalyzeResult | None = None

    def sections(ar: AnalyzeResult):
        return div(
            make_table(ar.pretty_sections()),
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

    t_end_form: div | None = None
    if path:
        log = jsonl_to_log(path)
        stderr = as_stderr(path).read_text()
        if log is not None:
            ar = AnalyzeResult.init(log)
        if log and ar and ar.completed and 'dry' in config.name:
            t_min = int(log.min_t()) + 1
            t_max = int(log.max_t()) + 1
            t_end = m.var(Int(t_max, type='range', min=t_min, max=t_max))
            t_end_form = div(
                div(*form(m, t_end),
                    str(timedelta(seconds=t_end.value)),
                    css=inverted_inputs_css,
                    css_='& input { width: 700px; }'),
                margin='0 auto',
            )
            ar = AnalyzeResult.init(log, until=float(t_end.value))
    if log is None:
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
        info += div(
            make_table(ar.running()),
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
            incu_table = [
                {
                    'location': k,
                    'incu': world.get(k),
                }
                for k in Locations.Incu[:ar.num_plates][::-1]
            ]
            rest_table = [
                {
                    k: world.get(k)
                    for k in 'incu wash disp'.split()
                }
            ]
            ABC_table = [
                {
                    'z': int(a.strip('A')),
                    'A': world.get(a),
                    'B': world.get(b),
                    'C': world.get(c),
                }
                for a, b, c in zip(Locations.A, Locations.B, Locations.C)
            ]

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
                make_table(incu_table).extend(id='incu', class_='even' if ar.num_plates % 2 == 0 else None),
                # incu_df.fillna('').to_html(index=1, border=0, table_id='incu', classes='even' if ar.num_plates % 2 == 0 else [])
                make_table(ABC_table).extend(id='ABC'),
                # ABC_df.fillna('').to_html(index=1, border=0, table_id='ABC')
                make_table(rest_table).extend(id='rest'),
                # rest_df.T.fillna('\u200b').to_html(index=0, border=0, table_id='rest')
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
            for err, entry in ar.errors:
                try:
                    tb = err.traceback
                except:
                    tb = None
                if not isinstance(tb, str):
                    tb = None
                box += pre(f'[{entry.strftime("%H:%M:%S")}] {err.message} {"(...)" if tb else ""}', title=tb)
            if not ar.process_is_alive():
                box += pre('Controller process has terminated.')
            info += box

        if ar.completed:
            text = ''
            if t_end_form:
                yield t_end_form.extend(
                    grid_area='info-foot',
                )
        elif ar.process_is_alive():
            text = f'pid: {ar.runtime_metadata.pid} on {platform.node()} with config {config.name}'
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
            yield div(
                div(
                    'robotarm speed: ',
                    *[
                        button(name, title=f'{pct}%', onclick=robotarm_set_speed.call(pct))
                        for name, pct in {
                            'normal': 100,
                            'slow': 40,
                            'slower': 10,
                            'slowest': 1,
                        }.items()
                    ],
                    css='''
                        & button {
                            margin: 10px 5px;
                            padding: 10px;
                            min-width: 100px;
                            color:        var(--cyan);
                            border-color: var(--cyan);
                            border-radius: 4px;
                            opacity: 0.8;
                        }
                        & button:hover {
                            opacity: 1.0;
                        }
                        & {
                            text-align: center;
                            margin-bottom:
                        }
                    ''',
                ),
                button(
                    'stop',
                    onclick='confirm("Stop?")&&' + sigint.call(ar.runtime_metadata.pid),
                    css='''
                        & {
                            font-size: 2rem;
                            display: block;
                            width: 100%;
                            color: var(--red);
                            border-color: var(--red);
                            border-radius: 4px;
                            padding: 15px;
                        }
                        &:focus {
                            outline: 3px var(--red) solid;
                        }
                    '''
                ),
                grid_area='stop',
            )
        else:
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
                        resume.call(ar.runtime_metadata.log_filename, skip=skipped, drop=dropped),
                    title=resume_text),
                grid_area='stop',
                css=form_css,
            )

    yield vis.extend(grid_area='vis')

    if ar is not None and ar.completed:
        """
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
        """

    if path and not (ar and ar.completed):
        yield V.queue_refresh(100)

def form(m: Store, *vs: Int | Str | Bool):
    for v in vs:
        yield label(
            span(f"{v.name or ''}:"),
            v.input(m).extend(id_=v.name, spellcheck="false", autocomplete="off"),
            title=v.desc,
        )

def main():
    serve.run()

if __name__ == '__main__':
    main()
