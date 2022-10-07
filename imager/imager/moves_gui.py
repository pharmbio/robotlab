from __future__ import annotations
from typing import *

from dataclasses import *

from flask import request
from pathlib import Path
import math
import json

from .moves import Move, MoveList
from . import moves
from .robotarm import Robotarm

from . import utils

from .utils.viable import serve, button, pre, call, js
from .utils.viable import Tag, div, input
from .utils import viable as V

import time

serve.suppress_flask_logging()
polled_info: dict[str, Any] = {}

@utils.spawn
def poll() -> None:
    arm = Robotarm.init(port=10000, quiet=True)
    while True:
        info_str = arm.execute('wherejson')
        info = json.loads(info_str)
        polled_info.update(info)

arm = Robotarm.init()
arm.execute('mode 0')
arm.execute('attach 1')

def arm_init():
    arm.execute('hp 1')
    arm.execute('attach 1')
    arm.execute('home')

def arm_do(*ms: Move):
    arm.execute_moves(list(ms))

def arm_set_speed(value: int) -> None:
    arm.set_speed(value)

def edit_at(program_name: str, i: int, changes: dict[str, Any]):
    filename = get_programs()[program_name]
    ml = MoveList.from_jsonl_file(filename)
    m = ml[i]
    for k, v in changes.items():
        if k in 'yaw xyz joints name pos tag sections'.split():
            m = replace(m, **{k: v})
        else:
            raise ValueError(k)

    ml = MoveList(ml)
    ml[i] = m
    ml.write_jsonl(filename)
    return {'refresh': True}

def cos(deg: float) -> float:
    return math.cos(deg / 180 * math.pi)

def sin(deg: float) -> float:
    return math.sin(deg / 180 * math.pi)

def keydown(program_name: str, args: dict[str, Any]):
    mm: float = 1.0
    deg: float = 1.0
    yaw: float = polled_info.get('yaw', 0.0)

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
    keymap = {
        'Home':       moves.MoveC_Rel(xyz=[0,  mm, 0], yaw=0),
        'End':        moves.MoveC_Rel(xyz=[0, -mm, 0], yaw=0),
        'Insert':     moves.MoveC_Rel(xyz=[-mm, 0, 0], yaw=0),
        'Delete':     moves.MoveC_Rel(xyz=[ mm, 0, 0], yaw=0),
        'ArrowDown':  moves.MoveC_Rel(xyz=[mm * cos(yaw + 180), mm * sin(yaw + 180), 0], yaw=0),
        'ArrowUp':    moves.MoveC_Rel(xyz=[mm * cos(yaw),       mm * sin(yaw),       0], yaw=0),
        'ArrowLeft': moves.MoveC_Rel(xyz=[mm * cos(yaw + 90),  mm * sin(yaw + 90),  0], yaw=0),
        'ArrowRight':  moves.MoveC_Rel(xyz=[mm * cos(yaw - 90),  mm * sin(yaw - 90),  0], yaw=0),
        'PageUp':     moves.MoveC_Rel(xyz=[0, 0,  mm], yaw=0),
        'PageDown':   moves.MoveC_Rel(xyz=[0, 0, -mm], yaw=0),
        '[':          moves.MoveC_Rel(xyz=[0, 0, 0], yaw=-deg),
        ']':          moves.MoveC_Rel(xyz=[0, 0, 0], yaw= deg),
        '.':          moves.MoveC_Rel(xyz=[0, 0, 0], yaw=-deg),
        ',':          moves.MoveC_Rel(xyz=[0, 0, 0], yaw= deg),
        '-':          moves.RawCode(f'MoveJ_Rel 1 0 0 0 0 {-int(mm)}'),
        '+':          moves.RawCode(f'MoveJ_Rel 1 0 0 0 0 {int(mm)}'),
    }
    def norm(k: str):
        tr: dict[str, str] = cast(Any, dict)(['[{', ']}', '+=', '-_', ',<', '.>'])
        return tr.get(k) or k.upper()
    keymap |= {norm(k): v for k, v in keymap.items()}
    print(k)
    if m := keymap.get(k):
        print(m)
        arm_do(m)

def update(program_name: str, i: int):
    if i is None:
        return

    filename = get_programs()[program_name]
    ml = MoveList.from_jsonl_file(filename)
    m = ml[i]
    if isinstance(m, (moves.MoveC, moves.MoveC_Rel)):
        v = asdict(m)
        xyz = [polled_info[k] for k in 'xyz']
        v['xyz'] = [utils.round_nnz(v, 3) for v in xyz]
        v['yaw'] = utils.round_nnz(polled_info['yaw'], 3)
        ml = MoveList(ml)
        ml[i] = moves.MoveC(**v)
        ml.write_jsonl(filename)
    elif isinstance(m, (moves.MoveGripper)):
        v = asdict(m)
        v['pos'] = utils.round_nnz(polled_info['q5'], 3)
        ml = MoveList(ml)
        ml[i] = moves.MoveGripper(**v)
        ml.write_jsonl(filename)
    elif isinstance(m, (moves.MoveJ)):
        v = asdict(m)
        joints = [polled_info[k] for k in 'q1 q2 q3 q4'.split()]
        v['joints'] = [utils.round_nnz(v, 3) for v in joints]
        ml = MoveList(ml)
        ml[i] = moves.MoveJ(**v)
        ml.write_jsonl(filename)

def get_programs() -> dict[str, Path]:
    return {
        path.with_suffix('').name: path
        for path in sorted(Path('./movelists').glob('*.jsonl'))
    }

@serve.route('/')
def index() -> Iterator[Tag | dict[str, str]]:
    programs = get_programs()
    program_name = request.args.get('program', list(programs.keys())[0])
    section: tuple[str, ...] = tuple(request.args.get('section', "").split())
    ml = MoveList.from_jsonl_file(programs[program_name])

    yield V.title(' '.join([program_name, *section]))

    yield dict(
        onkeydown=r'''
            const re = /^\w$|Tab|Enter|Escape|Meta|Control|Alt|Shift/
            if (event.target.tagName == 'INPUT') {
                console.log('by input', event)
            } else if (event.repeat || event.metaKey || event.ctrlKey || event.key.match(re)) {
                console.log('to browser', event)
            } else {
                event.preventDefault()
                console.log('to backend', event)
                const arg = {
                    selected: window.selected,
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
            onclick=f'''
                set_query({{program: {name!r}}}); refresh()
            ''')
    yield header

    info: dict[str, float] = {
        k: utils.round_nnz(float(v), 2)
        for k, v in polled_info.items()
        if isinstance(v, float | int | bool)
    }

    grid = div(css='''
        display: grid;
        grid-gap: 3px 0;
        grid-template-columns:
            [run] 130px
            [value] 1fr
            [update] 90px
            [x] 100px
            [y] 100px
            [z] 100px
            [go] 90px
            [name] 180px
        ;
    ''')
    yield grid

    visible_moves: list[tuple[int, Move]] = []
    for i, (m_section, m) in enumerate(ml.with_sections(include_Section=True)):
        if section != m_section[:len(section)]:
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
            sect += button(program_name,
                tabindex='-1',
                onclick="update_query({ section: '' })",
                style="cursor: pointer;"
            )
            seen: list[str] = []
            for s in m.sections:
                seen += [s]
                sect += button(s,
                    tabindex='-1',
                    onclick=f"update_query({{ section: {' '.join(seen)!r} }})",
                    style="cursor: pointer;"
                )
            continue

        try:
            xyz = [polled_info[k] for k in 'xyz']
        except:
            xyz = None
        if isinstance(m, moves.MoveC) and xyz is not None:
            dx, dy, dz = dxyz = utils.zip_sub(m.xyz, xyz, ndigits=6)
            dist = math.sqrt(sum(c*c for c in dxyz))
            buttons = [
                ('x', f'{dx: 6.1f}', moves.MoveC_Rel(xyz=[dx, 0, 0], yaw=0)),
                ('y', f'{dy: 6.1f}', moves.MoveC_Rel(xyz=[0, dy, 0], yaw=0)),
                ('z', f'{dz: 6.1f}', moves.MoveC_Rel(xyz=[0, 0, dz], yaw=0)),
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
                        onclick=call(arm_do, v),
                    )
            else:
                row += div(f'{dist: 5.0f}',
                    style=f'grid-column: z',
                    css='''
                        text-align: right;
                        padding-right: 10px;
                    '''
                )

        if isinstance(m, moves.MoveGripper):
            row += div(
                f'gripper {m.pos}',
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
        to_here= [m for _, m in visible_moves[:row_index+1] if not isinstance(m, moves.Section)]

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
            style=f'grid-column: run; display: flex; margin 0 10px;',
        )


        row += button('update',
            tabindex='-1',
            style=f'grid-column: update',
            css='margin: 0 10px;',
            onclick=call(update, program_name, i),
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
            oninput=call(edit_at, program_name, i, js('{"name":event.target.value}')),
        )
        if not isinstance(m, moves.Section):
            row += V.code(m.desc(),
                style=f'grid-column: value',
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
            button('init arm',      tabindex='-1', onclick=call(arm_init, )),
            button('run program',   tabindex='-1', onclick=call(arm_do, *visible_program)                   , css='width: 160px'),
            button('freedrive',     tabindex='-1', onclick=call(arm_do, moves.RawCode("Freedrive"))),
            button('stop robot',    tabindex='-1', onclick=call(arm_do, moves.RawCode("halt"), moves.RawCode("StopFreedrive")), css='flex-grow: 1; color: red; font-size: 48px'),
            button('gripper open',  tabindex='-1', onclick=call(arm_do, moves.MoveGripper(100))),
            button('gripper close', tabindex='-1', onclick=call(arm_do, moves.MoveGripper(75))),
    )

    foot = div(css='''
        & {
            display: flex;
            margin-top: 10px;
        }
    ''')
    yield foot

    for deg in [0, 90, 180, 270]:
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
        btns += button(
            f'yaw -> {deg}°',
            tabindex='-1',
            onclick=call(arm_do, moves.MoveC_Rel([0,0,0], -polled_info['yaw'] + deg))
        )
        foot += btns

    from pprint import pformat

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
    for speed in [5, 10, 15, 20, 40, 60, 80, 100]:
        speed_btns += button(f'set speed to {speed}', tabindex='-1', onclick=call(arm_set_speed, speed))
    foot += speed_btns

    yield V.queue_refresh(150)

def main():
    serve.run()

if __name__ == '__main__':
    main()
