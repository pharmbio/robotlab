from __future__ import annotations
from dataclasses import dataclass, field, replace, astuple
from typing import Any

from utils import show
import snoop # type: ignore
snoop.install(pformat=show)
pp: Any

import ast

import re
from textwrap import dedent, shorten

from utils import dotdict
import sys

from abc import ABC

class Command(ABC):
    pass

@dataclass(frozen=True)
class movel(Command):
    name: str
    dx: None | float = None
    dy: None | float = None
    dz: None | float = None

@dataclass(frozen=True)
class movej(Command):
    name: str
    dx: None | float = None
    dy: None | float = None
    dz: None | float = None

@dataclass(frozen=True)
class gripper(Command):
    name: str

@dataclass(frozen=True)
class comment(Command):
    msg: str

@dataclass
class ParsedScript:
    '''
    The parser extracts and returns a tuple of:
    - cmds: moves and gripper commands,
    - defs: coordinates,
    - subs: dict of extracted gripper subprograms and the header.
    The header sets up the env and gripper.

    The moves are used to generate program stubs which
    are manually rewritten to cut up the program loops to atomic programs.

    The coordinates in these programs are then resolved using the
    parsed coordinates. The gripper commands and the header are
    also resolved using the result from the parser.
    '''
    cmds: list[Command] = field(default_factory=list)
    defs: dict[str, list[float]] = field(default_factory=dict)
    subs: dict[str, list[str]] = field(default_factory=dict)

def parse(filename: str) -> ParsedScript:
    return parse_lines(list(open(filename, 'r')))

def parse_lines(lines: list[str]) -> ParsedScript:
    res = ParsedScript()
    last_header_line_index: None | int = None
    for i, line in enumerate(lines):
        if 'end: URCap Installation Node' in line:
            last_header_line_index = i
        if m := re.match(' *global *(\w*) *= *p?(.*)$', line):
            name, value = m.groups()
            try:
                res.defs[name] = ast.literal_eval(value)
            except:
                pass
        elif m := re.match(' *movel.*?(\w*)_[pq]', line):
            name, = m.groups()
            res.cmds += [movel(name)]
        elif m := re.match(' *movej.*?(\w*)_[pq]', line):
            name, = m.groups()
            res.cmds += [movej(name)]
        elif m := re.match('( *)\$ \d* "(Gripper.*)"', line):
            indent, name = m.groups()
            subprogram = ['# ' + name]
            for line2 in lines[i+1:]:
                subprogram += [line2[len(indent):].rstrip()]
                if '# end: URCap Program Node' in line2:
                    break
            res.subs[name] = subprogram
            res.cmds += [gripper(name)]

    if last_header_line_index is not None:
        header = lines[1:last_header_line_index]
        if m := re.match(' *', header[0]):
            header_indent = m.end()
            res.subs['header'] = [line[header_indent:].rstrip() for line in header]

    return res

def resolve(filename: str, cmds: list[Command]) -> list[str]:
    return resolve_with(parse(filename), cmds)

def resolve_with(script: ParsedScript, cmds: list[Command]) -> list[str]:
    out: list[str] = []
    for cmd in cmds:
        if isinstance(cmd, (movel, movej)):
            q_name = cmd.name + '_q'
            p_name = cmd.name + '_p'
            out += [
                f'{p_name} = p{script.defs[p_name]}',
            ]
            for i, d_name in enumerate('dx dy dz'.split()):
                if offset := getattr(cmd, d_name):
                    out += [
                        f'{p_name}[{i}] = {p_name}[{i}] + {offset}'
                    ]
            if isinstance(cmd, movel):
                out += [
                    f'movel({p_name}, a=1.2, v=0.25)'
                ]
            elif isinstance(cmd, movej):
                out += [
                    f'{q_name} = {script.defs[q_name]}',
                    f'movej(get_inverse_kin({p_name}, qnear={q_name}), a=1.4, v=1.05)',
                ]
        elif isinstance(cmd, gripper):
            out += script.subs[cmd.name]
        elif isinstance(cmd, comment):
            out += [
                f"# {line}"
                for line in cmd.msg.split('\n')
            ]
        else:
            raise ValueError
    return out

@dataclass(frozen=True)
class test:
    lhs: object
    def __eq__(self, rhs: object) -> bool:
        lhs = self.lhs
        true = lhs == rhs
        if not true:
            pp(lhs, rhs)
        elif '-v' in sys.argv:
            print(f'passed test(...) == {shorten(repr(rhs), 60, placeholder=" ...")}')
        return true

def test_parse_and_resolve() -> None:
    example_script = dedent('''
        def example():
            set_gravity([0.0, 0.0, 9.8])
            # end: URCap Installation Node
            global h21_neu_p=p[.2, -.4, .8, 1.6, -.0, .0]
            global h21_neu_q=[1.6, -1.9, 1.5, 0.4, 1.6, 0.0]
            global above_washr_p=p[-.2, .1, .3, 1.2, -1.2, -1.2]
            global above_washr_q=[-1.6, -2.2, 2.5, -0.3, -0.0, 0.0]
            $ 3 "Gripper Move30% (1)"
            # ...omitted gripper code...
            # end: URCap Program Node
            $ 4 "h21_neu"
            movel(h21_neu_p, a=1.2, v=0.2)
            $ 9 "MoveJ"
            $ 10 "above_washr"
            movej(get_inverse_kin(above_washr_p, qnear=above_washr_q), a=1.3, v=1.0)
        end
    '''.strip())

    lines = example_script.split('\n')

    script = parse_lines(lines)

    assert test(script.cmds) == [
        gripper('Gripper Move30% (1)'),
        movel('h21_neu'),
        movej('above_washr'),
    ]

    assert test(script.defs) == {
        'h21_neu_p': [0.2, -0.4, 0.8, 1.6, -0.0, 0.0],
        'h21_neu_q': [1.6, -1.9, 1.5, 0.4, 1.6, 0.0],
        'above_washr_p': [-0.2, 0.1, 0.3, 1.2, -1.2, -1.2],
        'above_washr_q': [-1.6, -2.2, 2.5, -0.3, -0.0, 0.0],
    }

    assert test(script.subs) == {
        'Gripper Move30% (1)': [
            '# Gripper Move30% (1)',
            '# ...omitted gripper code...',
            '# end: URCap Program Node',
        ],
        'header': ['set_gravity([0.0, 0.0, 9.8])'],
    }

    cmds: list[Command] = [
        gripper('Gripper Move30% (1)'),
        movel('h21_neu'),
        movel('h21_neu', dy=-0.3),
        movej('above_washr'),
    ]

    resolved = resolve_with(script, cmds)
    resolved_str = '\n'.join(resolved)

    assert test(resolved_str) == dedent('''
        # Gripper Move30% (1)
        # ...omitted gripper code...
        # end: URCap Program Node
        h21_neu_p = p[0.2, -0.4, 0.8, 1.6, -0.0, 0.0]
        movel(h21_neu_p, a=1.2, v=0.25)
        h21_neu_p = p[0.2, -0.4, 0.8, 1.6, -0.0, 0.0]
        h21_neu_p[1] = h21_neu_p[1] + -0.3
        movel(h21_neu_p, a=1.2, v=0.25)
        above_washr_p = p[-0.2, 0.1, 0.3, 1.2, -1.2, -1.2]
        above_washr_q = [-1.6, -2.2, 2.5, -0.3, -0.0, 0.0]
        movej(get_inverse_kin(above_washr_p, qnear=above_washr_q), a=1.4, v=1.05)
    ''').strip()

    if '-v' in sys.argv:
        print(__file__, 'passed tests')

test_parse_and_resolve()

