from __future__ import annotations
from typing import *

from viable import store, js, call, Serve, Flask, Int, Str, Bool
from viable import Tag, div, span, label, button, pre
import viable as V

from collections import *
from dataclasses import *
from datetime import datetime, timedelta

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

from .log import ExperimentMetadata, Log
from .cli import Args
from . import cli

from . import commands
from .commands import IncuCmd, BiotekCmd, ProgramMetadata
from . import moves
from . import runtime
import pbutils
from .log import CommandState, Message, VisRow, Metadata, RuntimeMetadata, Error, countdown
from .moves import RawCode, Move
from .small_protocols import small_protocols_dict, SmallProtocolData
from .runtime import get_robotarm, RuntimeConfig

from pbutils.mixins import DBMixin, DB

config: RuntimeConfig
for c in runtime.configs:
    if '--' + c.name in sys.argv:
        config = c
        break
else:
    raise ValueError('Start with one of ' + ', '.join('--' + c.name for c in runtime.configs))

print(f'Running with {config.name=}')

serve = Serve(Flask(__name__))
serve.suppress_flask_logging()

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

def start(args: Args, simulate: bool, push_state: bool=True):
    config_name = 'simulate' if simulate else config.name
    log_filename = cli.args_to_filename(replace(args, config_name=config_name))
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
    path_var_assign(log_filename, push_state=push_state)

def path_to_log(path: str) -> Log | None:
    try:
        return Log.connect(path)
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
            if isinstance(v, V.Node):
                tr += V.td(v)
            else:
                tr += V.td(str(v) or '\u200b')
        body += tr
    if header:
        return V.table(head, body)
    else:
        return V.table(body)

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
    experiment_metadata: ExperimentMetadata
    program_metadata: ProgramMetadata
    completed: bool
    running_state: list[CommandState]
    errors: list[Message]
    world: dict[str, str]
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
            t_now = m.time_end() + 0.01

        alive = process_is_alive(runtime_metadata.pid, runtime_metadata.log_filename)

        if not alive:
            t_now = m.time_end() + 0.01

        errors = m.errors()
        if errors:
            t_now = max([e.t for e in errors], default = m.time_end()) + 1

        if drop_after is not None:
            # completed = False
            t_now = drop_after

        running_state = m.running(t=drop_after)
        world = m.world(t=drop_after)
        sections = m.section_starts_with_endpoints()
        program_metadata = m.program_metadata() or ProgramMetadata()

        return AnalyzeResult(
            zero_time=zero_time,
            t_now=t_now,
            completed=completed,
            runtime_metadata=runtime_metadata,
            experiment_metadata=m.experiment_metadata() or ExperimentMetadata(),
            program_metadata=program_metadata,
            running_state=running_state,
            errors=errors,
            world=world,
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
                # onclick=None if t_end is None else call(t_end.assign, int(row.t0 + 1)),
                css__='cursor: pointer' if t_end is not None else '',
                data_t0=str(row.t0),
                data_t=str(row.t),
            )

        if t_end:
            cmd = js(f'''
                if (!event.buttons) return
                let frac = (event.offsetY - 2) / event.target.clientHeight
                let t = Number(event.target.dataset.t)
                let t0 = Number(event.target.dataset.t0)
                let d = t - t0
                let T = t0 + frac * d
                if (!isFinite(T)) return
                T = Math.round(T)
                {t_end.update(js('T'))}
            ''').iife().fragment
            area.onmousemove += cmd
            area.onmousedown += cmd

        return area

triangle = '''
  <svg xmlns="http://www.w3.org/2000/svg" class="svg-triangle" width=16 height=16>
    <polygon points="1,1 1,14 14,7"/>
  </svg>
'''

sheet = '''
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
        -background: #d3d0c866;
        background: #69c6;
    }
    table td, table th, table tr, table {
        border: none;
    }
    table td, table th {
        padding: 2px 8px 0px;
        margin: 1px 2px;
        background: var(--bg);
        min-width: 70px;
    }
    table thead td,
    table thead th
    {
        background: #333c;
        -background: var(--bg-bright);
    }
    table {
        border-spacing: 1px;
        transform: translateY(-1px);
    }
    body {
        display: grid;
        grid:
            "pad-left form      form      pad-right" auto
            "pad-left vis       info      pad-right" 1fr
            "pad-left vis       stop      pad-right" auto
            "pad-left info-foot info-foot pad-right" auto
          / 1fr auto minmax(min-content, 800px) 1fr;
        grid-gap: 10px;
        padding: 4px;
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
    button {
        user-select: none;
    }
'''

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

def start_form():
    options = {
        'cell-paint': 'cell-paint',
        **{
            k.replace('_', '-'): v
            for k, v in small_protocols_dict.items()
        }
    }

    protocol = store.str(default='cell-paint', options=tuple(options.keys()))
    store.assign_names(locals())

    desc = store.str(name='description', desc='Example: "specs395-v1"')
    operators = store.str(name='operators', desc='Example: "Amelie and Christa"')
    incu = store.str(name='incubation times', default='20:00', desc='The incubation times in seconds or minutes:seconds, separated by comma. If too few values are specified, the last value is repeated. Example: 21:00,20:00')
    batch_sizes = store.str(default='6', name='batch sizes', desc='The number of plates per batch, separated by comma. Example: 6,6')
    protocol_dir = store.str(default='automation_v5.0', name='protocol dir', desc='Directory on the windows computer to read biotek LHC files from')
    final_washes = store.str(name='final wash rounds', options=['auto', 'one', 'two'], desc='Number of final wash rounds. Either run 9_W_*.LHC once or run 9_10_W_*.LHC twice.')

    num_plates = store.str(name='plates', desc='The number of plates')
    params = store.str(name='params', desc=f'Additional parameters to protocol "{protocol.value}"')
    store.assign_names(locals())

    small_data = options.get(protocol.value)

    form_fields: list[Str | Bool] = []
    if protocol.value == 'cell-paint':
        form_fields = [
            desc,
            operators,
            batch_sizes,
            incu,
            protocol_dir,
            final_washes,
        ]
        bs = batch_sizes.value
        N = pbutils.catch(lambda: max(pbutils.read_commasep(bs.strip(' ,'), int)), 0)
        interleave = N >= 7
        if final_washes.value == 'one':
            two_final_washes = False
        elif final_washes.value == 'two':
            two_final_washes = True
        else:
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
            cell_paint=bs,
            incu=incu_csv,
            interleave=interleave,
            two_final_washes=two_final_washes,
            lockstep=lockstep,
            protocol_dir=protocol_dir.value,
            desc=desc.value,
            operators=operators.value,
        )
    elif isinstance(small_data, SmallProtocolData):
        if 'num_plates' in small_data.args:
            form_fields += [num_plates]
        if 'params' in small_data.args:
            form_fields += [params]
        if 'protocol_dir' in small_data.args:
            form_fields += [protocol_dir]
        args = Args(
            small_protocol=small_data.name,
            num_plates=pbutils.catch(lambda: int(num_plates.value), 0),
            params=pbutils.catch(lambda: shlex.split(params.value), []),
            protocol_dir=protocol_dir.value,
        )
    else:
        form_fields = []
        args = None

    if args:
        try:
            stages = cli.args_to_stages(args)
        except:
            stages = []
        if stages:
            start_from_stage = store.str(
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
        doc_divs = [
            div(
                # fill
                grid_column='1 / span 2',
                grid_row='2 / span 2',
            ),
            div(
                doc_header,
                title=doc_full,
                grid_column='2 / span 1',
                grid_row='2 / span 2',
                css='''
                    max-width: fit-content;
                    padding: 5px 12px;
                    place-self: start;
                ''',
            ),
        ]
    else:
        doc_full = ''
        doc_divs = []

    confirm = ''
    if 'required' in doc_full.lower():
        confirm = doc_full
    if not confirm and args and args.cell_paint:
        if not args.desc:
            confirm += 'Not specified: description.\n'
        if not args.operators:
            confirm += 'Not specified: operators.\n'
        if confirm:
            confirm += '\nStart anyway?'
    yield div(
        *form(protocol),
        *doc_divs,
        *form(*form_fields),
        button(
            'simulate',
            onclick=call(start, args=args, simulate=True),
            grid_row='-1',
        ) if args else '',
        button(
            V.raw(triangle.strip()), ' ', 'start',
            data_doc=doc_full,
            data_confirm=confirm,
            onclick=
                (
                    'confirm(this.dataset.confirm) && '
                    if confirm
                    else ''
                )
                +
                call(start, args=args, simulate=False),
            grid_row='-1',
        ) if args else '',
        height='100%',
        padding='80px 0',
        grid_area='form',
        user_select='none',
        css_=form_css,
        css='''
            & {
                grid-template-rows: repeat(8, 40px);
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
    running_processes: list[tuple[int, str]] = []
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
                running_processes += [(pid, v)]
        except:
            pass

    info = div(
        grid_area='info',
        z_index='1',
        css='''
            & li {
                margin: 8px 0;
            }
            & > div {
                margin: 16px 0;
            }
        '''
    )
    if running_processes:
        ul = V.ul()
        for pid, arg in running_processes:
            ul += V.li(
                V.span(
                    arg,
                    onclick=call(path_var_assign, arg),
                    text_decoration='underline',
                    cursor='pointer'
                ),
                V.button(
                    'kill',
                    data_arg=arg,
                    onclick=
                        'window.confirm("Really kill " + this.dataset.arg + "?") && ' +
                        call(sigkill, pid),
                    py=5, mx=8, my=0,
                    border_radius=3,
                    border_width=1,
                    border_color='var(--red)',
                ),
            )
        info += div('Running processes:', ul)
    info += div(
        'More:',
        V.ul(
            # V.li(V.a('show timings', href='/timings')),
            V.li(V.a('show logs', href='/logs')),
        ),
    )
    yield info
    yield div(
        f'Running on {platform.node()} with config {config.name}',
        grid_area='info-foot',
        opacity='0.85',
        margin='0 auto',
    )

def alert(s: str):
    return V.Action(f'alert({json.dumps(s)})')

def show_timings() -> Iterator[Tag | V.Node | dict[str, str]]:
    yield div('timings TODO')

A = TypeVar('A')
B = TypeVar('B')
class dotdict(Generic[A, B], dict[A, B]):
    __getattr__ = dict.__getitem__ # type: ignore
    __setattr__ = dict.__setitem__ # type: ignore
    __delattr__ = dict.__delitem__ # type: ignore

from pbutils import p

tab_indexes: dict[str, int] = {}

def edit(db_path: str | Path, obj: DBMixin, field: str, from_str: Callable[[str], Any] = str):
    if field not in tab_indexes:
        tab_indexes[field] = len(tab_indexes) + 1
    value = getattr(obj, field)
    do_edit = store.bool(name='edit')
    if not do_edit.value:
        if value:
            return div(str(value))
        else:
            return div()
    def update(next: str):
        next_conv = from_str(next)
        with DB.open(db_path) as db:
            ob = obj.reload(db)
            ob = ob.replace(**{field: next_conv}) # type: ignore
            ob.save(db)
    return div(
        div(
            repr(value),
            px=0,
        ),
        V.input(
            padding_left='7.5px',
            value=str(value),
            oninput=call(update, js('this.value')),
            tabindex=str(tab_indexes.get(field, 0)),
            width='100%',
        )
    )

def show_logs() -> Iterator[Tag | V.Node | dict[str, str]]:
    do_edit = store.bool(name='edit')
    logs: list[dict[str, Any]] = []
    for log in sorted(Path('logs').glob('*.db')):
        if 'simulate' in str(log):
            continue
        row: dict[str, Any] = dotdict()
        g = Log.connect(log)
        pm = g.program_metadata() or ProgramMetadata().save(g.db)
        em = g.experiment_metadata() or ExperimentMetadata().save(g.db)
        try:
            if (rt := g.runtime_metadata()):
                row.wkd = rt.start_time.strftime('%a')
                row.datetime = rt.start_time.strftime('%Y-%m-%d %H:%M') + '-' + (rt.start_time + timedelta(seconds=g.time_end(only_completed=True))).strftime('%H:%M')
                row.desc = edit(log, em, 'desc')
                row.operators = edit(log, em, 'operators')
                # row.plates = edit(log, pm, 'num_plates', int)
                row.batch_sizes = edit(log, pm, 'batch_sizes').extend(css='' if do_edit.value else 'text-align: right')
                if rt.config_name != 'live':
                    row.live = rt.config_name
                if pm.protocol != 'cell-paint':
                    row.protocol = edit(log, pm, 'protocol')
                row.from_stage = edit(log, pm, 'from_stage', lambda x: x or None)
                row.open = V.a('open', href='', onclick='event.preventDefault();' + call(path_var_assign, str(log)))
        except BaseException as e:
            row.err = repr(e)
        else:
            pass
            # row.err = ''
        if 0:
            row.path = pre(
                str(log),
                onclick=call(path_var_assign, str(log)),
                title=
                    '\n'.join([
                        sql
                        for sql, in g.db.con.execute('select sql from sqlite_master').fetchall()
                    ] +
                    [
                        table_name + ': ' + str(g.db.con.execute(f'select * from {table_name}').fetchone())
                        for table_name, in g.db.con.execute('select name from sqlite_master').fetchall()
                    ])
            )
        if 0:
            row.mtime = pre(
                str(datetime.fromtimestamp(log.stat().st_mtime).replace(microsecond=0)),
                title=str(log),
            )
        if 'id' in row:
            del row.id
        logs += [row]
    logs = sorted(logs, key=lambda g: g.get('start_time', '1999'), reverse=False)
    yield div(
        make_table(logs),
        grid_area='info',
        css='''
            & input {
                border-width: 1px;
                padding: 4px;
                padding-bottom: 2px;
                margin-bottom: 1px;
                border-radius: 2px;
            }
            & * {
                white-space: pre;
                min-width: unset;
            }
        '''
    )
    yield div(
        label(do_edit.input().extend(transform='translateY(3px)'), 'enable edit'),
        grid_area='form',
        place_self='center',
        css=inverted_inputs_css,
    )
@serve.route('/')
@serve.route('/<path:path_from_route>')
def index(path_from_route: str | None = None) -> Iterator[Tag | V.Node | dict[str, str]]:
    yield dict(sheet=sheet)

    path = path_var_value() or path_from_route

    path_is_latest = False
    if path == 'latest':
        logs = [
            (log, log.stat().st_mtime)
            for log in Path('logs').glob('*.db')
        ]
        logfile, _ = max(logs, key=lambda ab: ab[1], default=(None, None))
        if logfile:
            path_is_latest = True
            path = str(logfile)
        else:
            path = None
    if path == 'timings':
        yield from show_timings()
        return
    if path == 'logs':
        yield from show_logs()
        return

    if path:
        yield V.head(V.title('cell painter: ', path.removeprefix('logs/').removesuffix('.db')))
    else:
        yield V.head(V.title('cell painter'))

    if not path:
        yield from start_form()
    info = div(
        grid_area='info',
        css='''
            & {
                display: flex;
                flex-direction: column;
                row-gap: 18px;
            }
            & > * {
                width: 100%;
            }
        '''
    )
    error_box: None | Tag = None
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
                t_end = store.int(t_high, name='t_end')
                if t_end.value != t_high:
                    t_end.value = t_high
            elif rt.completed:
                simulation_completed = True
                t_min = 0
                t_max = int(log.time_end()) + 1
                t_end = store.int(t_max, name='t_end', min=t_min, max=t_max)
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
                    z_index='1',
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
        vis = ar.make_vis(t_end)

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
        def world_key(d: dict[str, str]):
            loc = d.get('loc', '')
            s = ''.join(re.findall(r'\D', loc))
            i = int(''.join(re.findall(r'\d', loc)) or '0')
            return not s, s.isupper(), s, -i
        world = [
            dict(
                loc=loc,
                plate=plate,
            )
            for loc, plate in ar.world.items()
        ]
        lids = len([row for row in world if 'lid' in row['plate']])
        if lids == 0:
            world += [{}, {}]
        elif lids == 1:
            world += [{}]
        world_table = make_table(
            sorted(
                world,
                key=world_key
            )
        ).extend(css='& tbody td { text-align: right }')
        info += div(
            world_table,
            sections(ar),
            css='''
                & {
                    display: flex;
                    column-gap: 18px;
                }
                & > * {
                    margin: auto;
                }
            '''
        )
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
                box += pre(f'{err.msg} {"(...)" if tb else ""}', title=tb)
            if not ar.process_is_alive:
                box += pre('Controller process has terminated.')
            error_box = box
        desc = ar.experiment_metadata.desc
        if len(desc) > 120:
            desc = desc[:120] + '...'
        if desc:
            desc = f'{desc}, '
        if ar.completed:
            text = desc.strip(', ')
            if t_end_form:
                yield t_end_form.extend(
                    grid_area='info-foot',
                )
        elif ar.process_is_alive and ar.runtime_metadata:
            text = f'{desc}pid: {ar.runtime_metadata.pid} on {platform.node()} with config {config.name}'
        else:
            text = f'{desc}pid: - on {platform.node()} with config {config.name}'
        if text:
            yield V.pre(text,
                grid_area='info-foot',
                padding_top='0.5em',
                user_select='text',
                opacity='0.85',
                background='none',
            )
        if ar.completed and not ar.has_error():
            confirm = ''
            if not ar.experiment_metadata.desc:
                confirm += 'Not specified: description.\n'
            if not ar.experiment_metadata.operators:
                confirm += 'Not specified: operators.\n'
            if confirm:
                confirm += '\nStart anyway?'
            if path:
                start_button = button(
                    V.raw(triangle.strip()), ' ', 'start',
                    data_confirm=confirm,
                    onclick=
                        (
                            'confirm(this.dataset.confirm) && '
                            if confirm
                            else ''
                        )
                        +
                        call(
                            start,
                            args=Args(run_program_in_log_filename=path),
                            simulate=False,
                            push_state=False,
                        ),
                    css='''
                        padding: 8px 20px;
                        border-radius: 3px;
                        background: var(--bg);
                        color: var(--fg);
                        margin-left: 36px;
                    ''',
                    css_='''&:focus, &:focus-within {
                        outline: 2px var(--fg) solid;
                        outline-offset: -1px;
                    }'''
                )
            else:
                start_button = ''
            if log and simulation_completed:
                G = log.group_durations()
                incubation = [times for event_name, times in G.items() if 'incubation' in event_name][0]
                incu_table = make_table([
                    dict(event='incubation times:') | {str(i): t for i, t in enumerate(incubation)}
                ], header=False)
                info += incu_table
            info += div(
                div(
                    span(
                        'Simulation finished.',
                        start_button,
                    )
                    if simulation_completed else
                    'Finished successfully!'
                ),
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
            yield div(
                div(
                    'robotarm speed: ',
                    *[
                        button(name, title=f'{pct}%', onclick=call(robotarm_set_speed, pct))
                        for name, pct in {
                            'normal': 100,
                            'slow': 25,
                            'slowest': 1,
                        }.items()
                    ],
                    css='''
                        & {
                            margin-top: 8px;
                        }
                        & button {
                            margin: 10px;
                            margin-bottom: 18px;
                            margin-left: 0;
                            margin-top: 0;
                            padding: 10px;
                            min-width: 78px;
                            outline-color: var(--fg);
                            color:         var(--fg);
                            border-color:  var(--fg);
                            border-radius: 4px;
                            opacity: 0.8;
                        }
                        & button:focus {
                            outline: 2px var(--cyan) solid;
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
                css_='''
                    && button {
                        padding: 10px 25px;
                        margin: 10px;
                        margin-right: 0;
                        border-radius: 4px;
                        outline-color: var(--fg);
                        color: var(--fg);
                        border-color: var(--fg);
                        outline-width: 2px;
                        outline-offset: -1px;
                        border-width: 1px;
                    }
                    & button:hover {
                        opacity: 1.0;
                    }
                    & button:focus {
                        outline-style: solid;
                    }
                    & {
                        text-align: center;
                        padding: 0;
                        margin: 0;
                    }
                ''',
            )

    yield vis.extend(grid_area='vis')

    if ar and not simulation:
        # TODO: hook this up with ExperimentMetadata.long_desc
        long_desc = store.str(name='long_desc')
        info += long_desc.textarea().extend(
            flex_grow='1',
            spellcheck="false",
            css='''
                outline: 0;
            '''
        )
        print(long_desc.value)

    if error_box is not None:
        info += error_box

    if path and not (ar and ar.completed):
        if ar and ar.completed:
            pass
        elif ar and not ar.process_is_alive:
            pass
        else:
            # new events can still happen
            yield V.queue_refresh(100)
    elif path_is_latest:
        # simulation finished: start a slower poll
        yield V.queue_refresh(1000)

def form(*vs: Int | Str | Bool):
    for v in vs:
        yield label(
            span(f"{v.name or ''}:"),
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
