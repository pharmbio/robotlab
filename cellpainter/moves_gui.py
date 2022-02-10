from __future__ import annotations
from typing import *

from dataclasses import *

from flask import request
from pathlib import Path
import ast
import math
import re

from .moves import Move, MoveList
from .runtime import RuntimeConfig
from . import moves
from . import robotarm
from . import runtime
from . import utils

from .viable import head, serve, esc, css_esc, trim, button, pre, js
from .viable import Tag, div, span, label, img, raw, input
from . import viable as V

serve.suppress_flask_logging()

import sys

config: RuntimeConfig
for c in runtime.configs:
    if '--' + c.name in sys.argv:
        config = c
        break
else:
    raise ValueError('Start with one of ' + ', '.join('--' + c.name for c in runtime.configs))

print(f'Running with {config.name=}')

polled_info: dict[str, list[float]] = {}

from datetime import datetime, timedelta
server_start = datetime.now()

@utils.spawn
def poll() -> None:
    if config.robotarm_mode == 'noop':
        return None
    arm = runtime.get_robotarm(config, quiet=False)
    arm.send('write_output_integer_register(1, 0)\n')
    arm.recv_until('PROGRAM_XXX_STOPPED')
    while True:
        arm.send(robotarm.reindent('''
            sec poll():
                def round(x):
                    return floor(x * 10 + 0.5) / 10
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
                    prev = polled_info.copy()
                    polled_info.update(ast.literal_eval(v))
                    if prev != polled_info:
                        serve.reload()
                except:
                    import traceback as tb
                    tb.print_exc()
                break

@serve.expose
def arm_do(*ms: Move):
    arm = runtime.get_robotarm(config)
    arm.execute_moves(list(ms), name='gui', allow_partial_completion=True)
    arm.close()

@serve.expose
def arm_set_speed(value: int) -> None:
    arm = runtime.get_robotarm(config, quiet=False)
    arm.set_speed(value)
    arm.close()

@serve.expose
def edit_at(program_name: str, i: int, changes: dict[str, Any]):
    filename = get_programs()[program_name]
    ml = MoveList.read_jsonl(filename)
    m = ml[i]
    for k, v in changes.items():
        if k in 'rpy xyz joints name slow pos tag sections'.split():
            m = replace(m, **{k: v})
        else:
            raise ValueError(k)

    ml = MoveList(ml)
    ml[i] = m
    ml.write_jsonl(filename)
    return {'refresh': True}

@serve.expose
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
    keymap = {
        'ArrowRight': moves.MoveRel(xyz=[ mm, 0, 0], rpy=[0, 0, 0]),
        'ArrowLeft':  moves.MoveRel(xyz=[-mm, 0, 0], rpy=[0, 0, 0]),
        'ArrowUp':    moves.MoveRel(xyz=[0,  mm, 0], rpy=[0, 0, 0]),
        'ArrowDown':  moves.MoveRel(xyz=[0, -mm, 0], rpy=[0, 0, 0]),
        'PageUp':     moves.MoveRel(xyz=[0, 0,  mm], rpy=[0, 0, 0]),
        'PageDown':   moves.MoveRel(xyz=[0, 0, -mm], rpy=[0, 0, 0]),
        'Home':       moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0, -deg]),
        'End':        moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0,  deg]),
        '[':          moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0, -deg]),
        ']':          moves.MoveRel(xyz=[0, 0, 0], rpy=[0, 0,  deg]),
        ',':          moves.MoveRel(xyz=[0, 0, 0], rpy=[-deg, 0, 0]),
        '.':          moves.MoveRel(xyz=[0, 0, 0], rpy=[ deg, 0, 0]),
        'Insert':     moves.MoveRel(xyz=[0, 0, 0], rpy=[0, -deg, 0]),
        'Delete':     moves.MoveRel(xyz=[0, 0, 0], rpy=[0,  deg, 0]),
        '-':          moves.RawCode(f'GripperMove(read_output_integer_register(0) - {int(mm)})'),
        '+':          moves.RawCode(f'GripperMove(read_output_integer_register(0) + {int(mm)})'),
    }
    def norm(k: str):
        tr: dict[str, str] = cast(Any, dict)(['[{', ']}', '+=', '-_', ',<', '.>'])
        return tr.get(k) or k.upper()
    keymap |= {norm(k): v for k, v in keymap.items()}
    utils.pr(k)
    if m := keymap.get(k):
        utils.pr(m)
        arm_do( # type: ignore
            moves.RawCode("EnsureRelPos()"),
            m,
        )

@serve.expose
def update(program_name: str, i: int):
    if i is None:
        return

    filename = get_programs()[program_name]
    ml = MoveList.read_jsonl(filename)
    m = ml[i]
    if isinstance(m, (moves.MoveLin, moves.MoveRel)):
        v = asdict(m)
        v['xyz'] = [utils.round_nnz(v, 1) for v in polled_info['xyz']]
        v['rpy'] = [utils.round_nnz(v, 1) for v in polled_info['rpy']]
        ml = MoveList(ml)
        ml[i] = moves.MoveLin(**v)
        ml.write_jsonl(filename)
    elif isinstance(m, (moves.GripperMove)):
        v = asdict(m)
        v['pos'] = polled_info['pos'][0]
        ml = MoveList(ml)
        ml[i] = moves.GripperMove(**v)
        ml.write_jsonl(filename)
    elif isinstance(m, (moves.MoveJoint)):
        v = asdict(m)
        v['joints'] = [utils.round_nnz(v, 2) for v in polled_info['joints']]
        ml = MoveList(ml)
        ml[i] = moves.MoveJoint(**v)
        ml.write_jsonl(filename)

def get_programs() -> dict[str, Path]:
    return {
        path.with_suffix('').name: path
        for path in sorted(Path('./movelists').glob('*.jsonl'))
    }

@serve.route('/')
def index() -> Iterator[Tag | dict[str, str]]:
    programs = get_programs()
    program_name = request.args.get('program', next(iter(programs.keys())))
    section: tuple[str, ...] = tuple(request.args.get('section', "").split())
    ml = MoveList.read_jsonl(programs[program_name])

    yield V.title(' '.join([program_name, *section]))

    yield dict(
        onkeydown='''
            if (event.key == 'Escape') {
                console.log('escape pressed, stopping robot...', event)
                ''' + arm_do.call() + r'''
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
                ''' + keydown.call(program_name, js('arg')) + '''
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

    info = {
        k: [utils.round_nnz(v, 2) for v in vs]
        for k, vs in polled_info.items()
    }

    # info['server_age'] = round((datetime.now() - server_start).total_seconds()) # type: ignore

    from pprint import pformat

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

        if isinstance(m, moves.MoveLin) and (xyz := info.get("xyz")) and (rpy := info.get("rpy")):
            dx, dy, dz = dxyz = utils.zip_sub(m.xyz, xyz, ndigits=6)
            dR, dP, dY = drpy = utils.zip_sub(m.rpy, rpy, ndigits=6)
            dist = math.sqrt(sum(c*c for c in dxyz))
            buttons = [
                ('x', f'{dx: 6.1f}', moves.MoveRel(xyz=[dx, 0, 0], rpy=[0, 0, 0])),
                ('y', f'{dy: 6.1f}', moves.MoveRel(xyz=[0, dy, 0], rpy=[0, 0, 0])),
                ('z', f'{dz: 6.1f}', moves.MoveRel(xyz=[0, 0, dz], rpy=[0, 0, 0])),
                # (f'P', moves.MoveRel(xyz=[0, 0, 0],  rpy=[0, dP, 0])),
                # (f'Y', moves.MoveRel(xyz=[0, 0, 0],  rpy=[0, 0, dY])),
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
                        onclick=arm_do.call(moves.RawCode("EnsureRelPos()"), v),
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


        show_go_btn = not isinstance(m, moves.Section)

        row += button('go',
            tabindex='-1',
            style=f'grid-column: go',
            css='margin: 0 10px;',
            onclick=arm_do.call(m),
        )

        from_here = [m for _, m in visible_moves[row_index:] if not isinstance(m, moves.Section)]

        row += button('run from here',
            tabindex='-1',
            style=f'grid-column: run',
            css='margin: 0 10px;',
            onclick=arm_do.call(*from_here),
            title=', '.join(m.try_name() or m.__class__.__name__ for m in from_here)
        )


        row += button('update',
            tabindex='-1',
            style=f'grid-column: update',
            css='margin: 0 10px;',
            onclick=update.call(program_name, i),
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
            oninput=edit_at.call(program_name, i, js("{name:event.target.value}")),
        )
        if not isinstance(m, moves.Section):
            row += V.code(m.to_script(),
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
            button('run program',   tabindex='-1', onclick=arm_do.call(*visible_program)                              , css='width: 160px'),
            button('freedrive',     tabindex='-1', onclick=arm_do.call(moves.RawCode("freedrive_mode() sleep(3600)"))),
            button('stop robot',    tabindex='-1', onclick=arm_do.call()                                              , css='flex-grow: 1; color: red; font-size: 48px'),
            button('gripper open',  tabindex='-1', onclick=arm_do.call(moves.RawCode("GripperMove(88)"))),
            button('gripper close', tabindex='-1', onclick=arm_do.call(moves.RawCode("GripperMove(255)"))),
            button('grip test',     tabindex='-1', onclick=arm_do.call(moves.RawCode("GripperTest()"))),
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
        btns += button('roll -> 0° (level roll)',                  tabindex='-1', onclick=arm_do.call(EnsureRelPos, moves.MoveRel([0, 0, 0], [-r,  0,       0     ])))
        btns += button('pitch -> 0° (face horizontally)',          tabindex='-1', onclick=arm_do.call(EnsureRelPos, moves.MoveRel([0, 0, 0], [ 0, -p,       0     ])))
        btns += button('pitch -> -90° (face the floor)',           tabindex='-1', onclick=arm_do.call(EnsureRelPos, moves.MoveRel([0, 0, 0], [ 0, -p - 90,  0     ])))
        btns += button('yaw -> 0° (towards washer and dispenser)', tabindex='-1', onclick=arm_do.call(EnsureRelPos, moves.MoveRel([0, 0, 0], [ 0,  0,      -y     ])))
        btns += button('yaw -> 90° (towards hotels and incu)',     tabindex='-1', onclick=arm_do.call(EnsureRelPos, moves.MoveRel([0, 0, 0], [ 0,  0,      -y + 90])))
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
    for speed in [20, 40, 60, 80, 100]:
        speed_btns += button(f'set speed to {speed}', tabindex='-1', onclick=arm_set_speed.call(speed))
    foot += speed_btns

def main():
    serve.run()

if __name__ == '__main__':
    main()
