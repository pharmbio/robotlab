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

# suppress flask logging
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

config: Config = configs['live_robotarm_no_gripper']

def spawn(f: Callable[[], None]) -> None:
    threading.Thread(target=f, daemon=True).start()

polled_info: dict[str, list[float]] = {}

@spawn
def poll() -> None:
    arm = robots.get_robotarm(config, quiet=True)
    while True:
        arm.send(robotarm.reindent('''
            sec poll():
                p = get_actual_tcp_pose()
                rpy = rotvec2rpy([p[3], p[4], p[5]])
                rpy = [r2d(rpy[0]), r2d(rpy[1]), r2d(rpy[2])]
                xyz = [p[0]*1000, p[1]*1000, p[2]*1000]
                q = get_actual_joint_positions()
                q = [r2d(q[0]), r2d(q[1]), r2d(q[2]), r2d(q[3]), r2d(q[4]), r2d(q[5])]
                textmsg("poll {" +
                    "'xyz': " + to_str(xyz) + ", " +
                    "'rpy': " + to_str(rpy) + ", " +
                    "'joints': " + to_str(q) + ", " +
                "}")
            end
        '''))
        for b in arm.recv():
            if m := re.search(rb'poll (.*\})', b):
                v = m.group(1).decode()
                # print('poll:', v)
                polled_info.update(ast.literal_eval(v))
                break
        # arm.close()
        # time.sleep(0.1)

_A = TypeVar('_A')

def catch(m: Callable[[], _A], default: _A=None) -> _A:
    try:
        return m()
    except:
        return default

@expose
def arm_do(*ms: dict[str, Any]):
    arm = robots.get_robotarm(config)
    arm.set_speed(80)
    arm.execute_moves([Move.from_dict(m) for m in ms], name='gui')
    arm.close()

@expose
def edit_at(program_name: str, i: int, changes: dict[str, Any]):
    filename = get_programs()[program_name]
    ml = MoveList.from_json_file(filename)
    m = ml[i]
    for k, v in changes.items():
        if k in 'rpy xyz joints name slow pos tag sections'.split():
            m = replace(m, **{k: v})
        elif k in 'dxyz drpy djoints'.split():
            key = k[1:]
            now = getattr(m, key)
            next = [ round(a + b, 2) for a, b in zip(now, v) ]
            m = replace(m, **{key: next})
        elif k in 'dpos'.split():
            key = k[1:]
            now = getattr(m, key)
            next = now + v
            if key in 'pos'.split():
                next = min(next, 255)
                next = max(next, 0)
            m = replace(m, **{key: next})
        elif k == 'to_abs':
            ml = ml.to_abs()
        elif k == 'to_rel':
            ml = ml.to_rel()
        else:
            raise ValueError(k)

    ml = MoveList(ml)
    ml[i] = m
    ml.write_json(filename)

def get_programs() -> dict[str, Path]:
    return {
        path.with_suffix('').name: path
        for path in sorted(Path('./movelists').glob('*.json'))
    }

@serve
def index() -> Iterator[head | str]:
    yield '''
        <body
            onkeydown="console.log(event)"
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

    program_name = request.args.get('program', next(iter(get_programs().keys())))
    programs = get_programs()
    ml = MoveList.from_json_file(programs[program_name])

    yield '<div css="display: flex; flex-direction: row; flex-wrap: wrap;">'
    for name in programs.keys():
        yield '''
            <div
                css="
                    text-align: center;
                    cursor: pointer;
                    padding: 5px 10px;
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

    from pprint import pformat

    for i, (m, m_abs) in enumerate(zip(ml, ml.to_abs())):
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
                        padding: 8px;
                    }
                    input {
                        border: 0;
                        background: unset;
                        min-width: 0; /* makes flex able to shrink element */
                    }
                    & [hide] {
                        visibility: hidden;
                    }
                "
            >
        '''

        yield '<pre style="flex-grow: 3; text-align: center">'
        if isinstance(m_abs, moves.MoveLin) and (xyz := info.get("xyz")) and (rpy := info.get("rpy")):
            dx, dy, dz = dxyz = utils.zip_sub(m_abs.xyz, xyz, ndigits=6)
            drpy = utils.zip_sub(m_abs.rpy, rpy, ndigits=6)
            dist = math.sqrt(sum(c*c for c in dxyz))
            yield f'({dx: 4.0f}, {dy: 4.0f}, {dz: 4.0f})' #   {dist: 5.0f}  '
        yield '</pre>'

        show_grip_test = catch(lambda: isinstance(ml[i+1], moves.GripperMove))
        yield f'''
            <button
                style="flex-grow: 2"
                {"" if show_grip_test else "hide"}
                onclick=call({
                    arm_do(
                        m.to_dict(),
                        moves.RawCode(textwrap.dedent("""
                            def Shake():
                                w = 0.25
                                MoveRel(-0.5,    0, w, w, w, w) w = -w
                                MoveRel(   0, -0.5, w, w, w, w) w = -w
                                MoveRel(   1,    0, w, w, w, w) w = -w
                                MoveRel(   0,    1, w, w, w, w) w = -w
                                MoveRel(  -1,    0, w, w, w, w) w = -w
                                MoveRel(   0,   -1, w, w, w, w) w = -w
                                MoveRel( 0.5,    0, w, w, w, w) w = -w
                                MoveRel(   0,  0.5, w, w, w, w) w = -w
                            end

                            GripperClose() MoveRel(0, 0,  21, 0, 0, 0)
                            Shake()        MoveRel(0, 0, -20, 0, 0, 0)
                            GripperOpen()  MoveRel(0, 0,  20, 0, 0, 0)
                            Shake()        MoveRel(0, 0, -21, 0, 0, 0)
                        """)).to_dict()
                    )
                })
            >grip test</button>
            <button onclick=call({arm_do(m.to_dict())})>go</button>
            <input style="flex-grow: 3"
                type=text
                {"" if hasattr(m, "name") else "disabled"}
                value="{esc(catch(lambda: getattr(m, "name"), ""))}"
                oninput=call({edit_at(program_name, i)},{{name:event.target.value}}).then(refresh)
            >
            <pre style="flex-grow: 8">{m.to_script()}</pre>
        '''

        buttons = {
            'x -': dict(dxyz=[-1, 0, 0]),
            'x +': dict(dxyz=[ 1, 0, 0]),
            'y -': dict(dxyz=[0, -1, 0]),
            'y +': dict(dxyz=[0,  1, 0]),
            'z -': dict(dxyz=[0, 0, -1]),
            'z +': dict(dxyz=[0, 0,  1]),
            'Y -': dict(drpy=[0, 0, -1]),
            'Y +': dict(drpy=[0, 0,  1]),
            # 'yaw N': dict(drpy=[0, 0, 0]),
            # 'yaw E': dict(drpy=[0, 0, 90]),
            # 'yaw W': dict(drpy=[0, 0, 180]),
            # 'yaw S': dict(drpy=[0, 0, 270]),
            'P -': dict(drpy=[0, -1, 0]),
            'P +': dict(drpy=[0,  1, 0]),
        }
        buttons.clear()
        for label, changes in buttons.items():
            yield f'''
                <button onclick=call({edit_at(program_name, i, changes)}).then(refresh)>{label}</button>
            '''
        yield '</div>'

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
        <button onclick=call({edit_at(program_name, 0, dict(to_rel=True))}).then(refresh)>to_rel</button>
        <button onclick=call({edit_at(program_name, 0, dict(to_abs=True))}).then(refresh)>to_abs</button>

        <div style="flex-grow: 1"></div>

        <button onclick=call({arm_do(*[m.to_dict() for m in ml])}).then(refresh)>run program</button>
        <button onclick=call({arm_do()}).then(refresh)>stop robot</button>

        <div style="flex-grow: 1"></div>

        <button onclick=call({arm_do(moves.RawCode("freedrive_mode()").to_dict())}).then(refresh)>enter freedrive</button>
        <button onclick=call({arm_do(moves.RawCode("end_freedrive_mode()").to_dict())}).then(refresh)>exit freedrive</button>
        </div>
        <pre style="user-select: text">{pformat(info, sort_dicts=False)}</pre>
        <script eval>
            if (window.rt) window.clearTimeout(window.rt)
            window.rt = window.setTimeout(() => refresh(0, () => 0), 150)
        </script>
    '''

