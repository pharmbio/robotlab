from __future__ import annotations
from typing import *

from dataclasses import *

from flask import request
from pathlib import Path
import ast
import math
import re
import textwrap
import threading
import time

from moves import Move, MoveList
from protocol import Event
from robots import Config, configs
from viable import head, serve, esc, make_classes, expose, app
import moves
import protocol
import robotarm
import robots
import utils
from utils import catch

# suppress flask logging
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

import sys

config: Config = configs['live']
if '--no-gripper' in sys.argv:
    config = configs['simulator']
elif '--forward' in sys.argv:
    config = configs['forward']

utils.pr(config)

def spawn(f: Callable[[], None]) -> None:
    threading.Thread(target=f, daemon=True).start()

polled_info: dict[str, list[float]] = {}

from datetime import datetime, timedelta
server_start = datetime.now()

@spawn
def poll() -> None:
    arm = robots.get_robotarm(config, quiet=False)
    while True:
        arm.send(robotarm.reindent('''
            sec poll():
                p = get_actual_tcp_pose()
                rpy = rotvec2rpy([p[3], p[4], p[5]])
                rpy = [r2d(rpy[0]), r2d(rpy[1]), r2d(rpy[2])]
                xyz = [p[0]*1000, p[1]*1000, p[2]*1000]
                q = get_actual_joint_positions()
                q = [r2d(q[0]), r2d(q[1]), r2d(q[2]), r2d(q[3]), r2d(q[4]), r2d(q[5])]
                tick = 1 + read_output_integer_register(1)
                write_output_integer_register(1, tick)
                textmsg("poll {" +
                    "'xyz': " + to_str(xyz) + ", " +
                    "'rpy': " + to_str(rpy) + ", " +
                    "'joints': " + to_str(q) + ", " +
                    "'pos': " + to_str([read_output_integer_register(0)]) + ", " +
                    "'tick': " + to_str([floor(tick / 5) % 9 + 1]) + ", " +
                "} eom")
            end
        '''))
        for b in arm.recv():
            if m := re.search(rb'poll (.*\}) eom', b):
                try:
                    v = m.group(1).decode(errors='replace')
                    polled_info.update(ast.literal_eval(v))
                except:
                    import traceback as tb
                    tb.print_exc()
                break

@expose
def arm_do(*ms: Move):
    arm = robots.get_robotarm(config)
    arm.execute_moves(list(ms), name='gui', allow_partial_completion=True)
    arm.close()

@expose
def edit_at(program_name: str, i: int, changes: dict[str, Any]):
    filename = get_programs()[program_name]
    ml = MoveList.from_json_file(filename)
    m = ml[i]
    for k, v in changes.items():
        if k in 'rpy xyz joints name slow pos tag sections'.split():
            m = replace(m, **{k: v})
        else:
            raise ValueError(k)

    ml = MoveList(ml)
    ml[i] = m
    ml.write_json(filename)

@expose
def keydown(program_name: str, args: dict[str, Any]):
    mm: float = 1.0
    deg: float = 1.0

    Alt = bool(args.get('altKey'))
    Shift = bool(args.get('shiftKey'))
    if Shift:
        mm = 0.25
        deg = 0.25
    if Alt:
        mm = 10.0
        deg = 90.0 / 8
    if Shift and Alt:
        mm = 100.0
        deg = 90.0
    k = str(args['key'])
    keymap = dict(
        ArrowRight = moves.MoveRel(xyz=[ mm, 0, 0], rpy=[0, 0, 0]),
        ArrowLeft  = moves.MoveRel(xyz=[-mm, 0, 0], rpy=[0, 0, 0]),
        ArrowUp    = moves.MoveRel(xyz=[0,  mm, 0], rpy=[0, 0, 0]),
        ArrowDown  = moves.MoveRel(xyz=[0, -mm, 0], rpy=[0, 0, 0]),
        PageUp     = moves.MoveRel(xyz=[0, 0,  mm], rpy=[0, 0, 0]),
        PageDown   = moves.MoveRel(xyz=[0, 0, -mm], rpy=[0, 0, 0]),
        u          = moves.MoveRel(xyz=[0, 0,  mm], rpy=[0, 0, 0]),
        d          = moves.MoveRel(xyz=[0, 0, -mm], rpy=[0, 0, 0]),
        Home       = moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0, -deg]),
        End        = moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0,  deg]),
        Insert     = moves.MoveRel(xyz=[0, 0, 0], rpy=[0, -deg, 0]),
        Delete     = moves.MoveRel(xyz=[0, 0, 0], rpy=[0,  deg, 0]),
        j          = moves.RawCode(f'GripperMove(read_output_integer_register(0) - {int(mm)})'),
        c          = moves.RawCode(f'GripperMove(read_output_integer_register(0) + {int(mm)})'),
        r          = moves.RawCode(f'GripperMove(read_output_integer_register(0) - {int(mm)})'),
        k          = moves.RawCode(f'GripperMove(read_output_integer_register(0) + {int(mm)})'),
    )
    keymap |= {k.upper(): v for k, v in keymap.items()}
    utils.pr(k)
    if m := keymap.get(k):
        utils.pr(m)
        arm_do.call( # type: ignore
            moves.RawCode("EnsureRelPos()"),
            m,
        )

    i = catch(lambda: int(args.pop('selected')))
    if i is not None and k in {'b', 'm'}:
        filename = get_programs()[program_name]
        ml = MoveList.from_json_file(filename)
        m = ml[i]
        if isinstance(m, (moves.MoveLin, moves.MoveRel)):
            v = asdict(m)
            v['xyz'] = [utils.round_nnz(v, 1) for v in polled_info['xyz']]
            v['rpy'] = [utils.round_nnz(v, 1) for v in polled_info['rpy']]
            ml = MoveList(ml)
            ml[i] = moves.MoveLin(**v)
            ml.write_json(filename)
        elif isinstance(m, (moves.GripperMove)):
            v = asdict(m)
            v['pos'] = polled_info['pos'][0]
            ml = MoveList(ml)
            ml[i] = moves.GripperMove(**v)
            ml.write_json(filename)
        elif isinstance(m, (moves.MoveJoint)):
            v = asdict(m)
            v['joints'] = [utils.round_nnz(v, 1) for v in polled_info['joints']]
            ml = MoveList(ml)
            ml[i] = moves.MoveJoint(**v)
            ml.write_json(filename)

def get_programs() -> dict[str, Path]:
    return {
        path.with_suffix('').name: path
        for path in sorted(Path('./movelists').glob('*.json'))
    }

@serve
def index() -> Iterator[head | str]:
    programs = get_programs()
    program_name = request.args.get('program', next(iter(programs.keys())))
    section: tuple[str, ...] = tuple(request.args.get('section', "").split())
    ml = MoveList.from_json_file(programs[program_name])

    title = ' '.join([program_name, *section])
    yield head(f'<title>{title}</title>')

    yield r'''
        <body
            onkeydown="
                if (event.target.tagName == 'INPUT') {
                    console.log('keydown event handled by input', event)
                } else if (event.repeat || event.metaKey || event.key.match(/F\d+|^[^dubmjkcr]$|Tab|Enter|Escape|Meta|Control|Alt|Shift/)) {
                    console.log('keydown event passed on', event)
                } else {
                    event.preventDefault()
                    console.log(event)
                    call(''' + keydown(program_name) + ''', {
                        selected: window.selected,
                        key: event.key,
                        altKey: event.altKey,
                        shiftKey: event.shiftKey,
                    })
                }
            "
            css="
                & {
                    font-family: monospace;
                    font-size: 16px;
                    user-select: none;
                    # padding: 0;
                    # margin: 0;
                }
                button {
                    font-family: monospace;
                    font-size: 12px;
                    cursor: pointer;
                }
                ul {
                    list-style-type: none;
                    padding: 0;
                    margin: 0;
                }
                table {
                    table-layout: fixed;
                }
            ">
    '''

    yield '<div css="display: flex; flex-direction: row; flex-wrap: wrap; justify-content: center;">'
    for name in programs.keys():
        yield '''
            <div
                css="
                    text-align: center;
                    cursor: pointer;
                    padding: 5px 10px;
                    margin: 0 5px;
                "
                css="
                    &[selected] {
                        background: #fd9;
                    }
                    &:hover {
                        background: #ecf;
                    }
                "
        ''' + f'''
                {'selected' if name == program_name else ''}
                onclick="{esc(f"set_query({{program: {name!r}}}); refresh()")}"
                >{name}</div>
        '''
    yield '</div>'

    info = {
        k: [utils.round_nnz(v, 1) for v in vs]
        for k, vs in polled_info.items()
    }

    info['server_age'] = round((datetime.now() - server_start).total_seconds()) # type: ignore

    from pprint import pformat

    visible_moves: list[Move] = []

    for i, ((m_section, m), m_abs) in enumerate(zip(ml.with_sections(include_Section=True), ml.to_abs())):
        if section != m_section[:len(section)]:
            continue
        visible_moves += [m]
        yield '''
            <div css="display: flex; flex-direction: row;"
                css="
                    &:nth-child(odd) {
                        background: #eee;
                    }
                    &:hover {
                        background: #fd9;
                    }
                    & > * {
                        flex-grow: 1;
                        flex-basis: 0;
                        margin: 0px;
                        padding: 8px 0;
                    }
                    & [hide] {
                        visibility: hidden;
                    }
                "
                onmouseover="window.selected=Number(this.dataset.index)"
            ''' + f'''
                data-index={i}
            >'''

        if isinstance(m_abs, moves.MoveLin) and (xyz := info.get("xyz")) and (rpy := info.get("rpy")):
            dx, dy, dz = dxyz = utils.zip_sub(m_abs.xyz, xyz, ndigits=6)
            dR, dP, dY = drpy = utils.zip_sub(m_abs.rpy, rpy, ndigits=6)
            dist = math.sqrt(sum(c*c for c in dxyz))
            buttons = [
                (f'{dx: 6.1f}', moves.MoveRel(xyz=[dx, 0, 0], rpy=[0, 0, 0])),
                (f'{dy: 6.1f}', moves.MoveRel(xyz=[0, dy, 0], rpy=[0, 0, 0])),
                (f'{dz: 6.1f}', moves.MoveRel(xyz=[0, 0, dz], rpy=[0, 0, 0])),
                # (f'P', moves.MoveRel(xyz=[0, 0, 0],  rpy=[0, dP, 0])),
                # (f'Y', moves.MoveRel(xyz=[0, 0, 0],  rpy=[0, 0, dY])),
            ]
            if any(abs(d) < 10.0 for d in dxyz):
                for k, v in buttons:
                    yield f'''
                        <pre style="cursor: pointer; flex-grow: 0.8; text-align: right"
                            css="
                                &:hover {{
                                    background: #fff8;
                                    box-shadow:
                                        inset  1px  0px #0006,
                                        inset  0px  1px #0006,
                                        inset -1px  0px #0006,
                                        inset  0px -1px #0006;
                                }}
                            "
                            onclick=call({arm_do(
                                moves.RawCode("EnsureRelPos()"),
                                v,
                            )})
                        >{k}  </pre>
                    '''
            else:
                # yield f'{dx: 6.1f}, {dy: 6.1f}, {dz: 6.1f}   '
                yield f'<pre style="flex-grow: 2.4; text-align: right">{dist: 5.0f}  </pre>'
        else:
            yield f'<pre style="flex-grow: 2.4"></pre>'

        show_grip_test = catch(lambda:
                isinstance(m, (moves.MoveLin, moves.MoveRel))
            and isinstance(ml[i+1], moves.GripperMove)
        )

        show_go_btn = not isinstance(m, moves.Section)

        yield f'''
            <button tabindex=-1
                {"" if show_go_btn else "hide"}
                css="margin: 0 10px;"
                style="flex-grow: 0.8" onclick=call({arm_do(m)})>go</button>
        '''



        yield f'''
            <input style="flex-grow: 2"
                type=text
                css="
                    &:hover:not([disabled]) {{
                        background: #fff8;
                        box-shadow:
                            inset  1px  0px #0006,
                            inset  0px  1px #0006,
                            inset -1px  0px #0006,
                            inset  0px -1px #0006;
                    }}
                "
                css="
                    padding: 0 10px;
                    margin-right: 10px;
                    border: 0;
                    background: unset;
                    min-width: 0; /* makes flex able to shrink element */
                    font-size: 14px;
                "

                {"" if hasattr(m, "name") else "disabled"}
                value="{esc(catch(lambda: getattr(m, "name"), ""))}"
                oninput=call({edit_at(program_name, i)},{{name:event.target.value}}).then(refresh)
            >
        '''
        if isinstance(m, moves.Section):
            yield '''<div style="flex-grow: 5; display: flex; margin-top: 12px; padding-bottom: 4px;"
                css="
                    & button {
                        padding: 1px 14px 5px;
                        margin-right: 6px;
                        font-family: sans;
                        font-size: 16px;
                    }
                ">'''
            yield f'''<button tabindex=-1
                    onclick="update_query({{ section: '' }})"
                    style="cursor: pointer;"
                    >{program_name}</button>'''
            seen: list[str] = []
            for s in m.sections:
                seen += [s]
                yield f'''<button tabindex=-1
                    onclick="update_query({{ section: {' '.join(seen)!r} }})"
                    style="cursor: pointer;"
                    >{s}</button>'''
                    # {m.to_script()}
            yield f'''</div>'''
        else:
            yield f'''
                <code style="flex-grow: 5">{m.to_script()}</code>
            '''
        yield '''
            </div>
        '''

    yield '''
        <div css="
            & {
                display: flex;
            }
            & {
                margin-top: 10px;
            }
            & button {
                padding: 10px 20px;
            }
            & button:not(:first-child) {
                margin-left: 10px;
            }
        ">
    ''' + f'''
        <button tabindex=-1
            onclick=call({
                arm_do(
                    moves.RawCode("freedrive_mode() sleep(3600)")
                )
            })>freedrive</button>

        <div style="flex-grow: 1"></div>

        <button tabindex=-1 onclick=call({arm_do(*visible_moves)}).then(refresh)>run program</button>
        <button tabindex=-1 onclick=call({arm_do()}).then(refresh)>stop robot</button>

        <div style="flex-grow: 1"></div>

        <button tabindex=-1
            onclick=call({
                arm_do(
                    moves.RawCode("EnsureRelPos() GripperTest()"),
                )
            })>grip test</button>
        </div>
    '''

    yield '''
        <script eval>
            window.requestAnimationFrame(() => {
                if (window.rt) window.clearTimeout(window.rt)
                window.rt = window.setTimeout(() => refresh(0, () => 0), 100)
            })
        </script>
    '''

    yield f'''
        <pre style="user-select: text; text-align: center">{info}</pre>
    '''

