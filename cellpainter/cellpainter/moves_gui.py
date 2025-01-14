from __future__ import annotations
from typing import *

from dataclasses import *

from datetime import datetime
from pathlib import Path
from threading import Lock
import ast
import json
import math
import re
import time

from .moves import Move, MoveList, guess_robot
from .runtime import Runtime, RuntimeConfig, UR, PF
from . import moves
from .ur_script import URScript
import pbutils

from viable import store, js, call, Serve, Flask
from viable import Tag, div, button, pre, input
import viable as V

import labrobots

@dataclass(frozen=False)
class MovesGuiState:
    init_done: bool = False
    lock: Lock = field(default_factory=Lock)
    ur: UR | None = None
    pf: PF | None = None
    config: RuntimeConfig = RuntimeConfig.simulate()

    def set_config(self, config: RuntimeConfig):
        with self.lock:
            self.init_done = False
            self.config = config

    def init(self):
        if self.init_done:
            return

        with self.lock:
            if self.init_done:
                return

            runtime = Runtime.init(self.config.only_arm())
            self.ur = runtime.ur
            self.pf = runtime.pf

            @pbutils.spawn
            def poll() -> None:
                self.ur and poll_ur(self.ur)
                self.pf and poll_pf(self.pf)

            self.init_done = True

state = MovesGuiState()

polled_info: dict[str, list[float]] = {}

server_start = datetime.now()

def round_array(xs: list[float]):
    return [pbutils.round_nnz(v, 2) for v in xs]

def poll_pf(pf: PF):
    i = 0
    while True:
        i += 1
        with pf.connect(quiet=bool(i >= 3), write_to_log_db=bool(i < 3), mode='ro') as arm:
            info_str = arm.send_and_recv('wherejson')
            info = json.loads(info_str)
            info['xyz'] = [info[k] for k in 'xyz']
            info['rpy'] = [0, 0, info['yaw']]
            info['joints'] = [info[k] for k in 'q1 q2 q3 q4'.split()]
            info['pos'] = [info['q5']]
            polled_info.update(info)
        time.sleep(0.1)

def poll_ur(ur: UR):
    with ur.connect(quiet=False, write_to_log_db=False) as arm:
        arm.send('write_output_integer_register(1, 0)\n')
        arm.recv_until('PROGRAM_XXX_STOPPED')
    i = 0
    while True:
        i += 1
        with ur.connect(quiet=bool(i >= 3), write_to_log_db=bool(i < 3)) as arm:
            arm.send(URScript.reindent('''
                sec poll():
                    def round(x):
                        return floor(x * 100 + 0.5) / 100
                    end
                    def r2d_round(rad):
                        deg = r2d(rad)
                        return round(deg)
                    end
                    p = get_actual_tcp_pose()
                    rpy = rotvec2rpy([p[3], p[4], p[5]])
                    rpy = [r2d_round(rpy[0]), r2d_round(rpy[1]), r2d_round(rpy[2])]
                    xyz = [round(p[0]*1000), round(p[1]*1000), round(p[2]*1000)]
                    q = get_actual_joint_positions()
                    q = [r2d_round(q[0]), r2d_round(q[1]), r2d_round(q[2]), r2d_round(q[3]), r2d_round(q[4]), r2d_round(q[5])]
                    tick = 1 + read_output_integer_register(1)
                    write_output_integer_register(1, tick)
                    textmsg("poll {" +
                        "'xyz': " + to_str(xyz) + ", " +
                        "'rpy': " + to_str(rpy) + ", " +
                        "'joints': " + to_str(q) + ", " +
                        "'pos': " + to_str([read_output_integer_register(0)]) + ", " +
                        "'tick': " + to_str([floor(tick / 10) + 1]) + ", " +
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

def arm_do(*ms: Move):
    state.ur and state.ur.execute_moves(list(ms), name='gui', allow_partial_completion=True)
    state.pf and state.pf.execute_moves(list(ms))

def arm_set_speed(value: int) -> None:
    state.ur and state.ur.set_speed(value)
    state.pf and state.pf.set_speed(value)

def edit_at(program_name: str, i: int, changes: dict[str, Any], action: None | Literal['duplicate', 'delete']=None):
    filename = get_programs()[program_name]
    ml = MoveList.read_jsonl(filename)
    m = ml[i]
    for k, v in changes.items():
        if k in 'rpy xyz joints name slow pos tag section'.split():
            m: Move = replace(cast(Any, m), **{k: v})
        else:
            raise ValueError(k)

    ml = MoveList(ml)
    ml[i] = m
    if action == 'delete':
        ml = MoveList(ml[:i] + ml[i+1:])
    if action == 'duplicate':
        ml = MoveList(ml[:i] + [m] + ml[i:])
    ml.write_jsonl(filename)
    return {'refresh': True}

def cos(deg: float) -> float:
    return math.cos(deg / 180 * math.pi)

def sin(deg: float) -> float:
    return math.sin(deg / 180 * math.pi)

def keydown(program_name: str, args: dict[str, Any]):
    mm: float = 1.0
    deg: float = 1.0

    Alt = bool(args.get('altKey'))
    Shift = bool(args.get('shiftKey'))
    if Shift:
        mm = 0.25
        deg = 0.125
    if Alt:
        mm = 10.0
        deg = 90.0 / 8
    if Shift and Alt:
        mm = 100.0
        deg = 90.0
    k = str(args['key'])
    _, _, yaw = polled_info.get('rpy', [0, 0, 0])
    if state.pf:
        keymap = {
            'ArrowDown':  moves.MoveRel(xyz=[mm * cos(yaw + 180), mm * sin(yaw + 180), 0], rpy=[0, 0, 0]),
            'ArrowUp':    moves.MoveRel(xyz=[mm * cos(yaw),       mm * sin(yaw),       0], rpy=[0, 0, 0]),
            'ArrowLeft':  moves.MoveRel(xyz=[mm * cos(yaw + 90),  mm * sin(yaw + 90),  0], rpy=[0, 0, 0]),
            'ArrowRight': moves.MoveRel(xyz=[mm * cos(yaw - 90),  mm * sin(yaw - 90),  0], rpy=[0, 0, 0]),
            'PageUp':     moves.MoveRel(xyz=[0, 0,  mm], rpy=[0, 0, 0]),
            'PageDown':   moves.MoveRel(xyz=[0, 0, -mm], rpy=[0, 0, 0]),
            '[':          moves.MoveRel(xyz=[0, 0, 0],   rpy=[0, 0,  deg]),
            ']':          moves.MoveRel(xyz=[0, 0, 0],   rpy=[0, 0, -deg]),
            ',':          moves.MoveRel(xyz=[0, 0, 0],   rpy=[0, 0,  deg]),
            '.':          moves.MoveRel(xyz=[0, 0, 0],   rpy=[0, 0, -deg]),
            '-':          moves.RawCode(f'MoveJ_Rel 1 0 0 0 0 {-int(mm)}'),
            '+':          moves.RawCode(f'MoveJ_Rel 1 0 0 0 0 {int(mm)}'),
        }
    else:
        yaw += 180
        keymap = {
            'ArrowDown':  moves.MoveRel(xyz=[mm * cos(yaw + 180), mm * sin(yaw + 180), 0], rpy=[0, 0, 0]),
            'ArrowUp':    moves.MoveRel(xyz=[mm * cos(yaw),       mm * sin(yaw),       0], rpy=[0, 0, 0]),
            'ArrowLeft':  moves.MoveRel(xyz=[mm * cos(yaw + 90),  mm * sin(yaw + 90),  0], rpy=[0, 0, 0]),
            'ArrowRight': moves.MoveRel(xyz=[mm * cos(yaw - 90),  mm * sin(yaw - 90),  0], rpy=[0, 0, 0]),
            'PageUp':     moves.MoveRel(xyz=[0, 0,  mm], rpy=[0, 0, 0]),
            'PageDown':   moves.MoveRel(xyz=[0, 0, -mm], rpy=[0, 0, 0]),
            'F7':         moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0,  deg]),
            'F8':         moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0, -deg]),
            'F9':         moves.MoveRel(xyz=[0, 0, 0], rpy=[ deg, 0, 0]),
            'F10':        moves.MoveRel(xyz=[0, 0, 0], rpy=[-deg, 0, 0]),
            '[':          moves.MoveRel(xyz=[0, 0, 0], rpy=[ deg, 0, 0]),
            ']':          moves.MoveRel(xyz=[0, 0, 0], rpy=[-deg, 0, 0]),
            '-':          moves.RawCode(f'GripperMove(read_output_integer_register(0) - {int(mm)})'),
            '+':          moves.RawCode(f'GripperMove(read_output_integer_register(0) + {int(mm)})'),
            'Home':       moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0,  deg]),
            'End':        moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0, -deg]),
            'Delete':     moves.MoveRel(xyz=[0, 0, 0], rpy=[0,  deg, 0]),
            'Insert':     moves.MoveRel(xyz=[0, 0, 0], rpy=[0, -deg, 0]),
        }
    def norm(k: str):
        tr: dict[str, str] = cast(Any, dict)(['[{', ']}', '+=', '-_', ',;', '.:'])
        return tr.get(k) or k.upper()
    keymap |= {norm(k): v for k, v in keymap.items()}
    pbutils.pr(k)
    if m := keymap.get(k):
        pbutils.pr(m)
        ms = [m]
        if state.ur:
            ms = [moves.RawCode("EnsureRelPos()")] + ms
        arm_do(*ms)

def update(program_name: str, i: int | None, grouped: bool=False):
    if i is None:
        return

    filename = get_programs()[program_name]
    ml = MoveList.read_jsonl(filename)
    m = ml[i]
    if isinstance(m, (moves.MoveLin, moves.MoveRel)):
        v = asdict(m)
        v['xyz'] = [pbutils.round_nnz(v, 1) for v in polled_info['xyz']]
        v['rpy'] = [pbutils.round_nnz(v, 1) for v in polled_info['rpy']]
        ml = MoveList(ml)
        ml[i] = moves.MoveLin(**v)
    elif isinstance(m, (moves.GripperMove)):
        v = asdict(m)
        v['pos'] = polled_info['pos'][0]
        ml = MoveList(ml)
        ml[i] = moves.GripperMove(**v)
    elif isinstance(m, (moves.MoveJoint)):
        v = asdict(m)
        v['joints'] = [pbutils.round_nnz(v, 2) for v in polled_info['joints']]
        ml = MoveList(ml)
        ml[i] = moves.MoveJoint(**v)
    else:
        return

    if grouped:
        for j, _ in enumerate(ml):
            if j == i:
                continue
            if isinstance(ml[j], type(ml[i])) and ml[j].try_name() == ml[i].try_name():
                print(i, j, ml[i], ml[j], ml[i].try_name(), ml[j].try_name())
                ml[j] = ml[i]
    ml.write_jsonl(filename)

def get_programs() -> dict[str, Path]:
    if state.pf:
        filter = 'pf'
    elif state.ur:
        filter = 'ur'
    else:
        filter = ''
    return {
        path.with_suffix('').name: path
        for path in sorted(Path('./movelists').glob('*.jsonl'))
        if filter in guess_robot(path.stem)
    }

def index() -> Iterator[Tag | dict[str, str]]:
    state.init()
    programs = get_programs()
    program_var = store.query.str(name='program')
    section_var = store.query.str(name='section')
    program_name = program_var.value or list(programs.keys())[0]
    section: str = section_var.value
    ml = MoveList.read_jsonl(programs[program_name])

    yield V.title(program_name + ' ' + section)

    yield dict(
        onkeydown='''
            if (event.key == 'Escape') {
                console.log('escape pressed, stopping robot...', event)
                ''' + call(arm_do) + r'''
                event.preventDefault()
            } else if (event.target.tagName == 'INPUT') {
                console.log('by input', event)
            } else if (event.metaKey || event.ctrlKey || event.key.match(/^\w$|Tab|Enter|Meta|Control|Alt|Shift/)) {
                console.log('to browser', event)
            } else if (event.repeat) {
                console.log('ignoring repeat', event)
                event.preventDefault()
            } else {
                event.preventDefault()
                console.log('to backend', event)
                const arg = {
                    key: event.key,
                    altKey: event.altKey,
                    shiftKey: event.shiftKey,
                }
                ''' + call(keydown, program_name, js('arg')) + '''
            }
        ''',
        sheet ='''
            body {
                font-family: monospace;
                font-size: 16px;
                user-select: none;
                -padding: 0;
                -margin: 0;
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
        '''
    )

    header = div(css='''
        display: flex;
        flex-direction: row;
        flex-wrap: wrap;
        justify-content: center;
        padding: 8px 0 16px;
    ''')
    for name in programs.keys():
        header += div(
            name,
            selected=name == program_name,
            css='''
                & {
                    text-align: center;
                    cursor: pointer;
                    padding: 5px 10px;
                    margin: 0 5px;
                }
                &[selected] {
                    background: #fd9;
                }
                &:hover {
                    background: #ecf;
                }
            ''',
            onclick=call(lambda: [
                program_var.assign(name),
                section_var.assign(''),
            ]))
    yield header

    info = {
        k: [pbutils.round_nnz(v, 2) for v in vs]
        for k, vs in polled_info.items()
        if isinstance(cast(Any, vs), list)
    }

    # info['server_age'] = round((datetime.now() - server_start).total_seconds()) # type: ignore

    from pprint import pformat

    grid = div(css='''
        display: grid;
        grid-gap: 3px 0;
        max-width: fit-content;
        margin: 0 auto;
        grid-template-columns:
            [run] 160px
            [value] 1fr
            [Y] 80px
            [update] 90px
            [x] 90px
            [y] 90px
            [z] 90px
            [go] 90px
            [name] 180px
        ;
    ''')
    yield grid

    visible_moves: list[tuple[int, Move]] = []
    for i, (m_section, m) in enumerate(ml.with_sections(include_Section=True)):
        if section and section != m_section[:len(section)]:
            continue
        visible_moves += [(i, m)]

    visible_program = [m for _, m in visible_moves if not isinstance(m, moves.Section)]

    for row_index, (i, m) in enumerate(visible_moves):
        row = div(
            style=f'--grid-row: {row_index+1}',
            css='''
                & > * {
                    grid-row: var(--grid-row);
                    padding: 5px 0;
                }
                & {
                    display: contents
                }
                &&:hover > * {
                    background: #fd9
                }
            ''')
        row += div(
            style=f'grid-column: 1 / -1',
            css='''
                :nth-child(even) > & {
                    background: #f4f4f4
                }
            ''')
        grid += row

        if isinstance(m, moves.Section):
            sect = div(
                css="""
                    & {
                        grid-column: x / -1;
                        margin-top: 12px;
                        padding-bottom: 4px;
                    }
                    & button {
                        padding: 1px 14px 5px;
                        margin-right: 6px;
                        font-family: sans;
                        font-size: 14px;
                    }
                """
            )
            row += sect
            sect += button(m.section,
                tabindex='-1',
                onclick=call(section_var.assign, m.section),
                style="cursor: pointer;"
            )
            continue

        if isinstance(m, moves.MoveLin) and (xyz := info.get("xyz")) and (rpy := info.get("rpy")):
            dx, dy, dz =  dxyz = pbutils.zip_sub(m.xyz, xyz, ndigits=6)
            dR, dP, dY = _drpy = pbutils.zip_sub(m.rpy, rpy, ndigits=6)
            dist = math.sqrt(sum(c*c for c in dxyz))
            buttons = [
                ('x', f'{dx: 6.1f}', moves.MoveRel(xyz=[dx, 0, 0], rpy=[0, 0, 0])),
                ('y', f'{dy: 6.1f}', moves.MoveRel(xyz=[0, dy, 0], rpy=[0, 0, 0])),
                ('z', f'{dz: 6.1f}', moves.MoveRel(xyz=[0, 0, dz], rpy=[0, 0, 0])),
                # ('r', f'{dR: 5.1f}', moves.MoveRel(xyz=[0, 0, 0],  rpy=[dR, 0, 0])),
                # ('p', f'{dP: 5.1f}', moves.MoveRel(xyz=[0, 0, 0],  rpy=[0, dP, 0])),
                ('Y', f'{dY: 5.1f}', moves.MoveRel(xyz=[0, 0, 0],  rpy=[0, 0, dY])),
            ]
            if any(abs(d) < 10.0 for d in dxyz):
                for col, k, v in buttons:
                    row += div(k,
                        style=f'grid-column: {col}',
                        css='''
                            & {
                                cursor: pointer;
                                padding-right: 10px;
                                text-align: right
                            }
                            &:hover {
                                background: #fff8;
                                box-shadow:
                                    inset  1px  0px #0006,
                                    inset  0px  1px #0006,
                                    inset -1px  0px #0006,
                                    inset  0px -1px #0006;
                            }
                        ''',
                        title=col,
                        onclick=
                            call(arm_do, moves.RawCode("EnsureRelPos()"), v) if state.ur else
                            call(arm_do, v)
                        ,
                    )
            else:
                row += div(f'{dist: 5.0f}',
                    style=f'grid-column: z',
                    css='''
                        text-align: right;
                        padding-right: 10px;
                    '''
                )

        if m.is_gripper():
            row += div(
                'gripper close' if m.is_close() else 'gripper open',
                css='''
                    grid-column: x / span 3;
                    justify-self: end;
                    font-family: sans;
                    font-size: 13px;
                    font-style: italic;
                '''
            )

        row += button('go',
            tabindex='-1',
            style=f'grid-column: go',
            css='margin: 0 10px;',
            onclick=call(arm_do, m),
        )

        from_here = [m for _, m in visible_moves[row_index:] if not isinstance(m, moves.Section)]
        to_here = [m for _, m in visible_moves[:row_index+1] if not isinstance(m, moves.Section)]

        row += div(
            button('run from here',
                tabindex='-1',
                css='margin: 0;',
                onclick=call(arm_do, *from_here),
                title=', '.join(m.try_name() or m.__class__.__name__ for m in from_here)
            ),
            button('to',
                tabindex='-1',
                css='margin: 0;',
                onclick=call(arm_do, *to_here),
                title=', '.join(m.try_name() or m.__class__.__name__ for m in to_here)
            ),
            style=f'grid-column: run',
            css='margin: 0 10px; display: flex;',
        )

        row += button('update',
            tabindex='-1',
            style=f'grid-column: update',
            css='margin: 0 10px;',
            onclick=call(update, program_name, i),
            oncontextmenu='event.preventDefault();' + call(update, program_name, i, grouped=True),
        )

        row += input(
            style=f'grid-column: name',
            type='text',
            css='''
                &:hover:not([disabled]) {
                    background: #fff8;
                    box-shadow:
                        inset  1px  0px #0006,
                        inset  0px  1px #0006,
                        inset -1px  0px #0006,
                        inset  0px -1px #0006;
                }
                & {
                    padding: 0 10px;
                    margin-right: 10px;
                    border: 0;
                    background: unset;
                    min-width: 0; /* makes flex able to shrink element */
                    font-size: 14px;
                }
            ''',
            disabled=not hasattr(m, 'name'),
            value=getattr(m, 'name', ''),
            oninput=call(edit_at, program_name, i, js("{name:event.target.value}")),
        )
        if not isinstance(m, moves.Section):
            script = m.to_ur_script()
            if isinstance(m, moves.MoveLin):
                script = f'''MoveLin({
                    m.xyz[0]:7.1f},{
                    m.xyz[1]:7.1f},{
                    m.xyz[2]:7.1f},{
                    m.rpy[0]:5.1f},{
                    m.rpy[1]:5.1f},{
                    m.rpy[2]:6.1f})'''
                if m.in_joint_space:
                    script += 'J'
                if m.tag:
                    script += '*'
            row += V.pre(script,
                style=f'grid-column: value',
                css='margin: unset',
                title=repr(m),
                onclick=call(edit_at, program_name, i, {}, action='duplicate'),
                oncontextmenu='event.preventDefault();confirm("Delete?")&&' + call(edit_at, program_name, i, {}, action='delete')
            )

    yield div(
        css="""
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
        """).append(
            button('run program',   tabindex='-1', onclick=call(arm_do, *visible_program),
                                                   oncontextmenu='event.preventDefault();' + call(arm_do, *(visible_program * 100)), css='width: 160px'),
            button('init arm',      tabindex='-1', onclick=call(state.pf.init)) if state.pf else '',
            button('freedrive',     tabindex='-1', onclick=call(arm_do, moves.RawCode("freedrive_mode() sleep(3600)" if state.ur else "Freedrive"))),
            # button('snap',          tabindex='-1', onclick=call(snap)),
            # button('snap many',     tabindex='-1', onclick=call(snap_many, js('prompt("desc", "")'))),
            button('stop robot',    tabindex='-1', onclick=call(arm_do, *([] if state.ur else [moves.RawCode("StopFreedrive")])), css='flex-grow: 1; color: red; font-size: 48px'),
            button('gripper open',  tabindex='-1', onclick=call(arm_do, moves.RawCode("GripperMove(88)") if state.ur else moves.GripperMove(100))),
            button('gripper close', tabindex='-1', onclick=call(arm_do, moves.RawCode("GripperMove(255)") if state.ur else moves.GripperMove(75))),
            button('grip test',     tabindex='-1', onclick=call(arm_do, moves.RawCode("GripperTest()"))),
    )

    foot = div(css='''
        & {
            display: flex;
            margin-top: 10px;
        }
    ''')
    yield foot

    if rpy := info.get('rpy'):
        r, p, y = rpy
        EnsureRelPos = moves.RawCode("EnsureRelPos()")
        btns = div(css="""
            & {
                display: flex;
                flex-direction: column;
            }
            & > button {
                display: block;
                padding: 10px 20px;
                margin: 5px 10px;
                font-family: sans-serif;
                text-align: left;
            }
        """)
        if state.ur:
            btns += button('roll -> 0° (level roll)',                  tabindex='-1', onclick=call(arm_do, EnsureRelPos, moves.MoveRel([0, 0, 0], [-r,  0,       0     ])))
            btns += button('pitch -> 0° (face horizontally)',          tabindex='-1', onclick=call(arm_do, EnsureRelPos, moves.MoveRel([0, 0, 0], [ 0, -p,       0     ])))
            btns += button('yaw -> 0° (towards washer and dispenser)', tabindex='-1', onclick=call(arm_do, EnsureRelPos, moves.MoveRel([0, 0, 0], [ 0,  0,      -y     ])))
            btns += button('yaw -> 90° (towards hotels and incu)',     tabindex='-1', onclick=call(arm_do, EnsureRelPos, moves.MoveRel([0, 0, 0], [ 0,  0,      -y + 90])))
        if state.pf:
            for deg in [0, 90, 180, 270]:
                btns += button(
                    f'yaw -> {deg}°',
                    tabindex='-1',
                    onclick=call(arm_do, moves.MoveRel([0,0,0], [0,0,-polled_info.get('rpy', [0,0,0])[-1] + deg]))
                )
        foot += btns

    foot += pre(
        pformat(info, sort_dicts=False),
        css='''
            user-select: text;
            text-align: left;
            width: fit-content;
            flex-grow: 1;
        ''')

    speed_btns = div(css="""
        & {
            display: flex;
            flex-direction: column;
        }
        & > button {
            display: block;
            padding: 10px 20px;
            margin: 5px 10px;
            font-family: sans-serif;
            text-align: left;
        }
    """)
    for speed in [25, 50, 80, 100]:
        speed_btns += button(f'set speed to {speed}', tabindex='-1', onclick=call(arm_set_speed, speed))

    if state.ur:
        def blue_run(program: str):
            from labrobots import WindowsNUC
            nuc = WindowsNUC.remote()
            blue = nuc.blue
            blue.run_program(program)
        def blue_runservprog(ix: int):
            from labrobots import WindowsNUC
            nuc = WindowsNUC.remote()
            blue = nuc.blue
            blue.run_servprog(ix)
        speed_btns += button('blue init',      onclick=call(blue_runservprog, 1))
        speed_btns += button('blue balance',   onclick=call(blue_runservprog, 2))
        speed_btns += button('blue working',   onclick=call(blue_runservprog, 3))
        speed_btns += button('blue open',      onclick=call(blue_run, 'dooropen'))
        speed_btns += button('blue close',     onclick=call(blue_run, 'doorclose'))
        speed_btns += button('blue openclose', onclick=call(blue_run, 'dooropen\ndoorclose'))
        speed_btns += button('blue closeopen', onclick=call(blue_run, 'doorclose\ndooropen'))
    foot += speed_btns

    yield V.queue_refresh(150)

def main():
    config = RuntimeConfig.from_argv()

    host = labrobots.Machines.ip_from_node_name() or 'localhost'

    serve = Serve(_app := Flask(__name__))
    serve.suppress_flask_logging()

    add_to_serve(serve, config)

    serve.run(
        port=5000,
        host=host,
    )

def add_to_serve(serve: Serve, config: RuntimeConfig, route: str='/'):
    state.set_config(config)
    serve.route(route)(index)

if __name__ == '__main__':
    main()
