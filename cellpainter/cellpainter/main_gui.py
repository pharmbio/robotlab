from __future__ import annotations
from typing import *

from flask import jsonify

from viable import store, js, call, serve
from viable import Tag, div, span, label, button, pre
import viable as V
from viable.provenance import Int, Str, Bool
from viable import provenance

from collections import *
from dataclasses import *
from datetime import datetime, timedelta
import functools

from pathlib import Path
from subprocess import Popen, DEVNULL
import json
import math
import os
import platform
import signal
import sys
import re
import shlex
import textwrap
import subprocess

from .log import Log
from .cli import Args, args_to_stages
from . import cli

from . import commands
from .commands import IncuCmd, BiotekCmd
from . import moves
from . import runtime
import pbutils
from .log import CommandState, Message, VisRow, Metadata, RuntimeMetadata, Error, countdown
from .moves import RawCode, Move
from .protocol import Locations
from .small_protocols import small_protocols_dict, SmallProtocolData
from .runtime import get_robotarm, RuntimeConfig

config: RuntimeConfig
for c in runtime.configs:
    if '--' + c.name in sys.argv:
        config = c
        break
else:
    raise ValueError('Start with one of ' + ', '.join('--' + c.name for c in runtime.configs))

print(f'Running with {config.name=}')

serve.suppress_flask_logging()

def sigint(pid: int):
    os.kill(pid, signal.SIGINT)

def sigkill(pid: int):
    os.kill(pid, signal.SIGKILL)

def robotarm_do(ms: list[Move]):
    arm = get_robotarm(config, quiet=False, include_gripper=True)
    arm.execute_moves(ms, name='gui', allow_partial_completion=True)
    arm.close()

def robotarm_freedrive():
    '''
    Sets the robotarm in freedrive
    '''
    robotarm_do([RawCode("freedrive_mode() sleep(3600)")])

def robotarm_set_speed(pct: int):
    '''
    Sets the robotarm speed, in percentages
    '''
    print(pct)
    arm = get_robotarm(config, quiet=False, include_gripper=True)
    arm.set_speed(pct)
    arm.close()

def robotarm_to_neutral():
    '''
    Slowly moves in joint space to the neutral position by B21
    '''
    robotarm_do(moves.movelists['to neu'])

def robotarm_open_gripper():
    '''
    Opens the robotarm gripper
    '''
    robotarm_do([RawCode("GripperMove(88)")])

def as_stderr(log_path: str):
    p = Path('cache') / Path(log_path).stem
    p = p.with_suffix('.stderr')
    return p

def start(args: Args, simulate: bool):
    config_name = 'simulate' if simulate else config.name
    if args.run_program_in_log_filename:
        log_filename = re.sub(r'\d{4}[\d_:\.\-]*', pbutils.now_str_for_filename() + '-', args.run_program_in_log_filename)
        log_filename = log_filename.replace('simulate', config_name)
    else:
        program_name = 'cell-paint' if args.cell_paint else args.small_protocol
        log_filename = 'logs/' + pbutils.now_str_for_filename() + f'-{program_name}-{config_name}-from-gui.db'
    args = replace(
        args,
        config_name=config_name,
        log_filename=log_filename,
        force_update_protocol_dir='live' in config.name,
        yes=True,
    )
    Path('cache').mkdir(exist_ok=True)
    cmd = [
        'sh', '-c',
        '''
            echo starting... >"$2"
            cellpainter --json-arg "$1" 2>>"$2"
        ''',
        '--',
        json.dumps(pbutils.nub(args)),
        as_stderr(log_filename),
    ]
    Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL)
    return jsonify({
        'goto': log_filename,
        'refresh': True,
    })

def path_to_log(path: str) -> Log | None:
    try:
        return Log.open(path)
    except:
        return None

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

@dataclass(frozen=True, kw_only=True)
class AnalyzeResult:
    zero_time: datetime
    t_now: float
    runtime_metadata: RuntimeMetadata
    completed: bool
    running_state: list[CommandState]
    errors: list[Message]
    world: dict[str, str]
    num_plates: int
    process_is_alive: bool
    sections: dict[str, float]
    time_end: float
    vis: list[VisRow]

    def has_error(self):
        if self.completed:
            return False
        return not self.process_is_alive or self.errors

    @staticmethod
    def init(m: Log, drop_after: float | None = None) -> AnalyzeResult | None:
        runtime_metadata = m.runtime_metadata()
        if not runtime_metadata:
            return None
        completed = runtime_metadata.completed is not None
        zero_time = runtime_metadata.start_time
        t_now = (datetime.now() - zero_time).total_seconds()

        if completed:
            t_now = m.time_end() + 1

        alive = process_is_alive(runtime_metadata.pid, runtime_metadata.log_filename)

        if not alive:
            t_now = m.time_end() + 1

        errors = m.errors()
        if errors:
            t_now = max([e.t for e in errors], default = m.time_end()) + 1

        if drop_after is not None:
            # completed = False
            t_now = drop_after

        running_state = m.running(t=drop_after)
        num_plates = runtime_metadata.num_plates
        world = m.world(t=drop_after)
        sections = m.section_starts_with_endpoints()

        return AnalyzeResult(
            zero_time=zero_time,
            t_now=t_now,
            completed=completed,
            runtime_metadata=runtime_metadata,
            running_state=running_state,
            errors=errors,
            world=world,
            num_plates=num_plates,
            process_is_alive=alive,
            sections=sections,
            time_end=m.time_end(),
            vis=m.vis(t_now),
        )

    def entry_desc_for_hover(self, e: CommandState):
        cmd = e.cmd
        match cmd:
            case BiotekCmd():
                if cmd.protocol_path:
                    if cmd.action == 'Validate':
                        return cmd.action + ' ' + cmd.protocol_path
                    else:
                        return cmd.protocol_path
                else:
                    return cmd.action
            case IncuCmd():
                if cmd.incu_loc:
                    return cmd.action + ' ' + cmd.incu_loc
                else:
                    return cmd.action
            case _:
                return str(cmd)

    def entry_desc_for_table(self, e: CommandState):
        cmd = e.cmd
        match cmd:
            case commands.RobotarmCmd():
                return cmd.program_name
            case BiotekCmd():
                if cmd.action == 'TestCommunications':
                    return cmd.action
                else:
                    return re.sub(r'^automation_|\.LHC$', '', str(cmd.protocol_path))
            case IncuCmd():
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
                return str(e.cmd_type)

    def running(self):
        d: dict[str, CommandState | None] = {}
        resources = 'main disp wash incu'.split()
        G = pbutils.group_by(self.running_state, key=lambda e: e.metadata.thread_resource)
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
                'desc':      e and self.entry_desc_for_table(e),
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
        for name, t in self.sections.items():
            section, _, last = name.rpartition(' ')
            if last.isdigit():
                batch = str(int(last) + 1)
            else:
                section = name
                batch = ''
            table.append({
                'batch':     batch,
                'section':   section,
                'countdown': self.pp_countdown(t, zero=''),
                't0':        self.pp_time_at(t),
                # 'length':    pp_secs(math.ceil(entries.length()), zero=''),
                'total':     pp_secs(math.ceil(self.time_end), zero='') if name == 'end' else '',
            })
        return table

    def make_vis(self, t_end: Int | None = None) -> Tag:
        width = 23

        area = div()
        area.css += f'''
            position: relative;
            user-select: none;
            width: {round(width*(len(self.sections)+1)*2.3, 1)}px;
            transform: translateY(1em);
            height: calc(100% - 1em);
        '''
        area.css += '''
            & > * {
                color: #000;
                position: absolute;
                border-radius: 0px;
                outline: 1px #0005 solid;
                display: grid;
                place-items: center;
                font-size: 14px;
                min-height: 1px;
                background: var(--row-color);
            }
            & > :not(:hover)::before {
                position: absolute;
                left: 0;
                bottom: 0;
                width: 100%;
                height: var(--pct-incomplete);
                content: "";
                background: #0005;
            }
            & > [can-hover]:hover::after {
                font-size: 16px;
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
        '''

        max_length = max([
            row.t - row.t0
            for row in self.vis
        ], default=1.0)

        for row in self.vis:
            slot = 0
            metadata = row.state and row.state.metadata
            if row.state:
                source = row.state.resource or ''
            elif row.bg:
                source = 'bg'
            elif row.now:
                source = 'now'
            else:
                source = ''
            if source == 'disp':
                slot = 1
            my_width = 1
            if source in ('now', 'bg'):
                my_width = 2

            color = {
                'wash': 'var(--cyan)',
                'disp': 'var(--purple)',
                'incu': 'var(--green)',
                'now': '#fff',
                'bg': 'var(--bg-bright)',
            }[source]
            can_hover = source not in ('now', 'bg')

            y0 = (row.t0 - row.section_t0) / (max_length or 1.0)
            y1 = (row.t - row.section_t0) / (max_length or 1.0)
            h = y1 - y0

            if row.state and isinstance(row.state.cmd, BiotekCmd):
                info = row.state.cmd.protocol_path or row.state.cmd.action
            elif row.state and isinstance(row.state.cmd, IncuCmd):
                loc = row.state.cmd.incu_loc
                action = row.state.cmd.action
                if loc:
                    info = f'{action} {loc}'
                else:
                    info = action
            else:
                info = ''
            title: dict[str, Any] | div = {}
            row_title = row.section if row.bg else ''
            if row_title and row_title != 'begin':
                title = div(
                    row_title.strip(' 0123456789'),
                    css='''
                        color: var(--fg);
                        position: absolute;
                        left: 50%;
                        top: 0;
                        transform: translate(-50%, -100%);
                        white-space: nowrap;
                        background: unset;
                    '''
                )
            plate_id = metadata and metadata.plate_id or ''
            duration = row.t - row.t0

            frac_complete = (self.t_now - row.t0) / (duration or 1.0)
            if frac_complete > 1:
                frac_complete = 1.0
            if frac_complete < 0:
                frac_complete = 0.0
            if not row.state:
                frac_complete = 1.0

            if row.state and row.state.state == 'planned':
                frac_complete = 0.0

            area += div(
                title,
                plate_id,
                can_hover=can_hover,
                style=f'''
                    left:{(row.section_column*2.3 + slot) * width:.0f}px;
                    top:{  y0 * 100:.3f}%;
                    height:{h * 100:.3f}%;
                    --row-color:{color};
                    --info:{repr(info)};
                    --pct-incomplete:{100 - frac_complete * 100:.3f}%;
                ''',
                css_=f'''
                    width: {width * my_width - 2}px;
                ''',
                onclick=None if t_end is None else store.update(t_end, int(row.t0 + 1)).goto(),
                css__='cursor: pointer' if t_end is not None else '',
            )

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
            html {
                color:      var(--fg);
                background: var(--bg);
                font-size: 16px;
                font-family: Consolas, monospace;
                letter-spacing: -0.025em;
            }
            * {
                color: inherit;
                background: inherit;
                font-size: inherit;
                font-family: inherit;
                letter-spacing: inherit;
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
            .svg-triangle {
                margin-right: 6px;
                width: 16px;
                height: 16px;
                transform: translateY(4px);
            }
            .svg-triangle polygon {
                fill: var(--green);
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
        & input, & button, & select {
            padding: 8px;
            border-radius: 2px;
            background: var(--bg);
            color: var(--fg);
        }
        & select {
            width: 100%;
            padding-left: 4px;
        }
        & input:focus-visible, & button:focus-visible, & select:focus-visible {
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
            width: 100%;
        }
        & > label {
            display: contents;
            cursor: pointer;
        }
        & > label > span {
            justify-self: right;
        }
        & input, & select {
            width: 300px;
        }
        & > label > span {
            grid-column: 1;
        }
    ''' + inverted_inputs_css

    path_is_latest = False
    if path == 'latest':
        path_is_latest = True
        logs = [
            (log, log.stat().st_mtime)
            for log in Path('logs').glob('*.db')
        ]
        logfile, _ = max(logs, key=lambda ab: ab[1], default=(None, None))
        if logfile:
            path = str(logfile)

    m = store.cookie
    if not path:
        options = {
            'cell-paint': 'cell-paint',
            **{
                k.replace('_', '-'): v
                for k, v in small_protocols_dict.items()
            }
        }

        protocol = m.str(default='cell-paint', options=tuple(options.keys()))

        protocol_dir = m.str(default='automation_v5.0', name='protocol dir', desc='Directory on the windows computer to read biotek LHC files from')
        plates = m.str(desc='The number of plates per batch, separated by comma. Example: 6,6')
        incu = m.str(name='incubation times', default='20:00', desc='The incubation times in seconds or minutes:seconds, separated by comma. If too few values are specified, the last value is repeated. Example: 21:00,20:00')
        params = m.str(name='params', desc=f'Additional parameters to protocol "{protocol.value}"')

        m.assign_names(locals())

        small_data = options.get(protocol.value)

        form_fields: list[Str | Bool] = []
        if protocol.value == 'cell-paint':
            form_fields = [plates, incu, protocol_dir]
            batch_sizes = plates.value
            N = pbutils.catch(lambda: max(pbutils.read_commasep(batch_sizes, int)), 0)
            interleave = N >= 7
            two_final_washes = N >= 8
            lockstep = N >= 10
            incu_csv = incu.value
            if incu_csv == '':
                incu_csv = '1200'
            if incu_csv in ('1200', '20:00') and N >= 8:
                incu_csv = '1200,1200,1200,1200,X'
                if N == 10:
                    incu_csv = '1235,1230,1230,1235,1260'
            args = Args(
                cell_paint=batch_sizes,
                incu=incu_csv,
                interleave=interleave,
                two_final_washes=two_final_washes,
                lockstep=lockstep,
                protocol_dir=protocol_dir.value,
            )
        elif isinstance(small_data, SmallProtocolData):
            if 'num_plates' in small_data.args:
                form_fields += [plates]
            if 'params' in small_data.args:
                form_fields += [params]
            if 'protocol_dir' in small_data.args:
                form_fields += [protocol_dir]
            args = Args(
                small_protocol=small_data.name,
                num_plates=pbutils.catch(lambda: int(plates.value), 0),
                params=pbutils.catch(lambda: shlex.split(params.value), []),
                protocol_dir=protocol_dir.value,
            )
        else:
            form_fields = []
            args = None

        if args:
            stages = cli.args_to_stages(args)
            if stages:
                start_from_stage = m.str(
                    name='start from stage',
                    default='start',
                    desc='Stage to start from',
                    options=stages
                )
                form_fields += [start_from_stage]
                if start_from_stage.value:
                    args = replace(args, start_from_stage=start_from_stage.value)

        if isinstance(small_data, SmallProtocolData):
            doc_full = textwrap.dedent(small_data.make.__doc__ or '').strip()
            doc_header = small_data.doc
        else:
            doc_full = ''
            doc_header = ''

        yield div(
            *form(protocol),
            div(
                doc_header,
                title=doc_full,
                grid_column='2 / span 1',
                css='''
                    max-width: fit-content;
                    padding: 5px 12px;
                    place-self: start;
                ''',
            ),
            *form(*form_fields),
            button(
                'simulate',
                onclick=call(start, args=args, simulate=True),
                grid_row='-1',
            ) if args else '',
            button(
                V.raw(triangle.strip()), ' ', 'start',
                data_doc=doc_full,
                onclick=
                    (
                        'confirm(this.dataset.doc)&&'
                        if 'required' in doc_full.lower()
                        else ''
                    )
                    +
                    call(start, args=args, simulate=False),
                grid_row='-1',
            ) if args else '',
            height='100%',
            padding='80px 0',
            grid_area='header',
            user_select='none',
            css_=form_css,
            css='''
                & {
                    grid-template-rows: 40px 100px repeat(5, 40px);
                    grid-template-columns: 160px 300px;
                }
                & label > span {
                    text-align: right;
                }
                & button {
                    height: 100%;
                }
            '''
        )
        running: list[tuple[int, str]] = []
        try:
            x = subprocess.check_output(['pgrep', '^cellpainter$']).decode()
        except:
            x = ''
        for pid in x.strip().split('\n'):
            try:
                pid = int(pid)
                args = get_json_arg_from_argv(pid)
                if isinstance(v := args.get("log_filename"), str):
                    pbutils.pr(args)
                    running += [(pid, v)]
            except:
                pass
        if running:
            yield div(
                'Running processes:',
                V.ul(
                    *[
                        V.li(
                            V.a(arg, href=arg),
                            V.button(
                                'kill',
                                data_arg=arg,
                                onclick=
                                    'window.confirm("Really kill " + this.dataset.arg + "?") && ' +
                                    call(sigkill, pid),
                                py=5, m=8,
                                border_radius=3,
                                border_width=1,
                                border_color='var(--red)',
                            ),
                            padding_top=8
                        )
                        for pid, arg in running
                    ],
                ),
                grid_area='info',
                z_index='1',
            )
        yield div(
            f'Running on {platform.node()} with config {config.name}',
            grid_area='info-foot',
            opacity='0.85',
            margin='0 auto',
        )
    info = div(
        grid_area='info',
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
    t_end: Int | None = None
    simulation_completed: bool = False
    simulation: bool = False
    if path:
        log = path_to_log(path)
        try:
            stderr = as_stderr(path).read_text()
        except:
            stderr = ''
        if log and (rt := log.runtime_metadata()) and rt.config_name == 'simulate':
            simulation = True
            if not rt.completed:
                t_high = 2**60
                t_end = m.int(t_high, name='t_end')
                yield store.update(t_end, t_high).goto_script()
            elif rt.completed:
                simulation_completed = True
                t_min = 0
                t_max = int(log.time_end()) + 1
                t_end = m.int(t_max, name='t_end', min=t_min, max=t_max)
                spinner = div(
                    div('|'),
                    css='''
                        & {
                          position: relative;
                        }
                        & div {
                          animation: -&-1 1.0s infinite;
                          position: relative;
                        }
                        @keyframes -&-1 { 12% { transform: rotate(0deg);  } 100% { transform: rotate(360deg); } }
                        & {
                            display: inline-block;
                            opacity: 0;
                            transition: opacity 50ms 0ms;
                        }
                        [loading="1"] & {
                            opacity: 1;
                            transition: opacity 50ms 400ms;
                        }
                    ''')

                t_end_form = div(
                    div(spinner, t_end.range(),
                        str(timedelta(seconds=t_end.value)),
                        css=inverted_inputs_css,
                        css_='& input { width: 700px; }'),
                    margin='0 auto',
                )
                ar = AnalyzeResult.init(log, drop_after=float(t_end.value))
        elif log is not None:
            ar = AnalyzeResult.init(log)
    if ar is None or simulation and not simulation_completed:
        if stderr:
            box = div(
                border=(
                    '2px var(--red) solid'
                    if any([
                        'error' in stderr.lower(),
                        'exception' in stderr.lower(),
                    ]) else
                    '2px var(--blue) solid'
                ),
                px=8,
                py=4,
                border_radius=2,
                css='''
                    & > pre {
                        line-height: 1.5;
                        margin: 0;
                        white-space: pre-wrap;
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
            vis = ar.make_vis(t_end)
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
                make_table(ABC_table).extend(id='ABC'),
                make_table(rest_table).extend(id='rest'),
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
                        white-space: pre-wrap;
                    }
                '''
            )
            for err in ar.errors:
                try:
                    tb = err.traceback
                except:
                    tb = None
                if not isinstance(tb, str):
                    tb = None
                # box += pre(f'[{entry.strftime("%H:%M:%S")}] {err.message} {"(...)" if tb else ""}', title=tb)
                box += pre(f'{err.msg} {"(...)" if tb else ""}', title=tb)
            if not ar.process_is_alive:
                box += pre('Controller process has terminated.')
            info += box

        if ar.completed:
            text = ''
            if t_end_form:
                yield t_end_form.extend(
                    grid_area='info-foot',
                )
        elif ar.process_is_alive and ar.runtime_metadata:
            text = f'pid: {ar.runtime_metadata.pid} on {platform.node()} with config {config.name}'
        else:
            text = f'pid: - on {platform.node()} with config {config.name}'
        if text:
            yield V.pre(text,
                grid_area='info-foot',
                padding_top='0.5em',
                user_select='text',
                opacity='0.85',
            )

        if ar.completed and not ar.has_error():
            info += div(
                div(
                    'Simulation finished.' if simulation_completed else
                    'Finished successfully!'
                ),
                button(
                    V.raw(triangle.strip()), ' ', 'start',
                    onclick=call(
                        start,
                        args=Args(run_program_in_log_filename=path),
                        simulate=False
                    ),
                    css='''
                        padding: 8px 20px;
                        border-radius: 2px;
                        background: var(--bg);
                        color: var(--fg);
                    '''
                ) if simulation_completed else '',
                border='2px var(--green) solid',
                color='#eee',
                text_align='center',
                padding='22px',
                border_radius='2px',
            )
        elif path_is_latest:
            # skip showing buttons for endpoint /latest
            pass
        elif ar.process_is_alive:
            yield store.defaults.goto_script()
            yield div(
                div(
                    'robotarm speed: ',
                    *[
                        button(name, title=f'{pct}%', onclick=call(robotarm_set_speed, pct))
                        for name, pct in {
                            'normal': 100,
                            'slow': 40,
                            'slower': 10,
                            'slowest': 1,
                        }.items()
                    ],
                    css='''
                        & {
                            font-size: 18px;
                        }
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
                    onclick='confirm("Stop?")&&' + call(sigint, ar.runtime_metadata.pid),
                    css='''
                        & {
                            font-size: 32px;
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
        elif ar.has_error() and not ar.process_is_alive:
            yield div(
                button('open gripper', onclick=call(robotarm_open_gripper, )),
                button('set robot in freedrive', onclick=call(robotarm_freedrive, )),
                grid_area='stop',
                css=form_css,
                css_='& button { grid-column: 1 / span 2 }',
            )

    yield vis.extend(grid_area='vis')

    if path and not (ar and ar.completed):
        yield V.queue_refresh(100)
    elif path_is_latest:
        # simulation finished or error, start a slower poll
        yield V.queue_refresh(1000)

def form(*vs: Int | Str | Bool):
    for v in vs:
        yield label(
            span(f"{v.given_name or ''}:"),
            v.input().extend(id_=v.name, spellcheck="false", autocomplete="off"),
            title=v.desc,
        )

def main():
    if config.name in ('simulate-wall', 'simulate', 'forward'):
        host = 'localhost'
    else:
        host = '10.10.0.55'
    serve.run(
        port=5000,
        host=host,
    )

if __name__ == '__main__':
    main()
