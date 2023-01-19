from __future__ import annotations
from typing import *
from dataclasses import *

from viable import store, call, Serve, Flask, Int, Str, Bool
from viable import Tag, div, span, label, button, pre
import viable as V

from datetime import timedelta

from pathlib import Path
import platform
import sys
import re

from ..log import Log
from ..cli import Args
from .. import cli
from .. import protocol_vis

from .. import moves
from .. import runtime
from ..moves import RawCode, Move
from ..runtime import get_robotarm, RuntimeConfig

from .start_form import start_form, start
from .vis import AnalyzeResult
from .show_logs import show_logs

from . import common
from .db_edit import Edit

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

protocol_vis.add_to_serve(serve, '', cli.cmdline_to_log, route='/vis')

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
    option:checked {
        color: var(--bg);
        background-color: var(--blue);
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
        -transform: translateY(-1px);
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
    button {
        user-select: none;
    }
'''

@serve.route('/')
@serve.route('/<path:path_from_route>')
def index(path_from_route: str | None = None) -> Iterator[Tag | V.Node | dict[str, str]]:
    yield dict(sheet=sheet)

    path_is_latest = False
    path = common.path_var_value() or path_from_route
    if path == 'latest':
        logs = [
            log
            for log in Path('logs').glob('20*.db')
        ]
        logfile = max(logs, default=None)
        if logfile:
            path_is_latest = True
            path = str(logfile)
        else:
            path = None
    # if path == 'timings':
    #     yield from show_timings()
    #     return
    if path == 'logs':
        yield from show_logs()
        return

    if path:
        yield V.head(V.title('cell painter: ', path.removeprefix('logs/').removesuffix('.db')))
    else:
        yield V.head(V.title('cell painter'))

    if not path:
        yield from start_form(config=config)
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
            common.make_table(ar.pretty_sections()),
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
        log = common.path_to_log(path)
        try:
            stderr = common.as_stderr(path).read_text()
        except:
            stderr = ''
        if log and (rt := log.runtime_metadata()) and rt.config_name == 'simulate':
            simulation = True
            if path_is_latest:
                t_end = None # skip showing for /latest
            elif not rt.completed:
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
                        css=common.inverted_inputs_css,
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
            common.make_table(ar.running()),
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
        world_table = common.make_table(
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
            if path_is_latest:
                # skip showing buttons for endpoint /latest
                start_button = ''
            elif path:
                start_button = button(
                    common.triangle(), ' ', 'start',
                    onclick=
                        call(
                            start,
                            args=Args(run_program_in_log_filename=path),
                            simulate=False,
                            push_state=False,
                            config=config,
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
                incubations = [times for event_name, times in G.items() if 'incubation' in event_name]
                if incubations:
                    incubation = incubations[0]
                    incu_table = common.make_table([
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
                    onclick='confirm("Stop?")&&' + call(common.sigint, ar.runtime_metadata.pid),
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

    if ar and path and not simulation:
        em = ar.experiment_metadata
        edit_em = Edit(path, em, enable_edit=not path_is_latest)
        long_desc = edit_em(edit_em.attr.long_desc, textarea=True)
        info += long_desc.extend(
            flex_grow='1',
            spellcheck='false',
            outline='0',
        )

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
