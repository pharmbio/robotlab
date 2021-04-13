from __future__ import annotations
from dataclasses import dataclass, field, replace, astuple
from typing import Any

from utils import show

import ast

import re
from textwrap import dedent, shorten

import sys

from abc import ABC

from functools import lru_cache

class ScriptStep(ABC):
    pass

@dataclass(frozen=True)
class movel(ScriptStep):
    name: str
    dx: None | float = None
    dy: None | float = None
    dz: None | float = None

@dataclass(frozen=True)
class movej(ScriptStep):
    name: str
    dx: None | float = None
    dy: None | float = None
    dz: None | float = None

@dataclass(frozen=True)
class gripper(ScriptStep):
    name: str

@dataclass(frozen=True)
class section(ScriptStep):
    name: str
    steps: list[ScriptStep]

@dataclass
class ParsedScript:
    '''
    The parser extracts and returns a tuple of:
    - steps: moves and gripper commands,
    - defs: coordinates,
    - subs: dict of extracted gripper subprograms and the header.
    The header sets up the env and gripper.

    The moves are used to generate program stubs which
    are manually rewritten to cut up the program loops to atomic programs.

    The coordinates in these programs are then resolved using the
    parsed coordinates. The gripper commands and the header are
    also resolved using the result from the parser.
    '''
    steps: list[ScriptStep] = field(default_factory=list)
    defs: dict[str, list[float]] = field(default_factory=dict)
    subs: dict[str, list[str]] = field(default_factory=dict)

@lru_cache
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
                val = ast.literal_eval(value)
                val = [round(v, 6) for v in val]
                res.defs[name] = val
            except:
                pass
        elif m := re.match(' *movel.*?(\w*)_[pq]', line):
            name, = m.groups()
            res.steps += [movel(name)]
        elif m := re.match(' *movej.*?(\w*)_[pq]', line):
            name, = m.groups()
            res.steps += [movej(name)]
        elif m := re.match('( *)\$ \d* "(Gripper.*)"', line):
            indent, name = m.groups()
            subprogram = ['# ' + name]
            gripper_init = ['# Gripper init']
            for line2 in lines[i+1:]:
                line2 = line2.strip()
                if '# end: URCap Program Node' in line2:
                    break
                elif line2.startswith('rq'):
                    subprogram += [line2]
                elif not re.match('gripper_\d_(selected|used)', line2):
                    gripper_init += [line2]
            res.subs[name] = subprogram
            # we only need one copy of gripper init
            res.subs['gripper_init'] = gripper_init
            res.steps += [gripper(name)]

    if last_header_line_index is not None:
        header = lines[1:last_header_line_index]
        if m := re.match(' *', header[0]):
            header_indent = m.end()
            res.subs['header'] = [line[header_indent:].rstrip() for line in header]

    return res

def resolve(name: str, filename: str, steps: list[ScriptStep]) -> dict[str, str]:
    return resolve_with(name, parse(filename), steps)

def resolve_with(name: str, script: ParsedScript, steps: list[ScriptStep]) -> dict[str, str]:
    out: list[str] = []
    sections: dict[str, str] = {}
    for step in steps:
        lines: list[str] = []
        if isinstance(step, (movel, movej)):
            q_name = step.name + '_q'
            p_name = step.name + '_p'
            lines += [
                f'{p_name} = p{script.defs[p_name]}',
            ]
            for i, d_name in enumerate('dx dy dz'.split()):
                if offset := getattr(step, d_name):
                    lines += [
                        f'{p_name}[{i}] = {p_name}[{i}] + {offset}'
                    ]
            if isinstance(step, movel):
                lines += [
                    f'movel({p_name}, a=1.2, v=0.25)'
                ]
            elif isinstance(step, movej):
                lines += [
                    f'{q_name} = {script.defs[q_name]}',
                    f'movej(get_inverse_kin({p_name}, qnear={q_name}), a=1.4, v=1.05)',
                ]
        elif isinstance(step, gripper):
            lines += script.subs[step.name]
        elif isinstance(step, section):
            subname = name + '_' + step.name
            sections |= resolve_with(subname, script, step.steps)
            lines = [sections[subname]]
        else:
            raise ValueError
        out += lines
    return {name: '\n'.join(out)} | sections

@dataclass(frozen=True)
class test:
    lhs: object
    def __eq__(self, rhs: object) -> bool:
        lhs = self.lhs
        true = lhs == rhs
        if not true:
            print(f'lhs = {show(lhs)}\nrhs = {show(rhs)}')
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
            global above_washr_q=[-1.6, -2.2, 2.5, -0.3, -0.0, 0.987654321]
            $ 3 "Gripper Move30% (1)"
            gripper_1_used = True
            if (connectivity_checked[0] != 1):
              gripper_id_ascii = rq_gripper_id_to_ascii("1")
              gripper_id_list = rq_get_sid("1")
              if not(rq_is_gripper_in_sid_list(gripper_id_ascii, gripper_id_list)):
                popup("Gripper 1 must be connected to run this program.", "No connection", False, True, True)
              end
              connectivity_checked[0] = 1
            end
            rq_set_pos_spd_for(77, 0, 0, "1")
            rq_go_to("1")
            rq_wait("1")
            gripper_1_selected = True
            gripper_2_selected = False
            gripper_1_used = False
            gripper_2_used = False
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

    assert test(script.steps) == [
        gripper('Gripper Move30% (1)'),
        movel('h21_neu'),
        movej('above_washr'),
    ]

    assert test(script.defs) == {
        'h21_neu_p': [0.2, -0.4, 0.8, 1.6, -0.0, 0.0],
        'h21_neu_q': [1.6, -1.9, 1.5, 0.4, 1.6, 0.0],
        'above_washr_p': [-0.2, 0.1, 0.3, 1.2, -1.2, -1.2],
        'above_washr_q': [-1.6, -2.2, 2.5, -0.3, -0.0, 0.987654],
    }

    assert test(script.subs) == {
        'Gripper Move30% (1)': [
            '# Gripper Move30% (1)',
            'rq_set_pos_spd_for(77, 0, 0, "1")',
            'rq_go_to("1")',
            'rq_wait("1")',
        ],
        'gripper_init': [
          '# Gripper init',
          'if (connectivity_checked[0] != 1):',
            'gripper_id_ascii = rq_gripper_id_to_ascii("1")',
            'gripper_id_list = rq_get_sid("1")',
            'if not(rq_is_gripper_in_sid_list(gripper_id_ascii, gripper_id_list)):',
              'popup("Gripper 1 must be connected to run this program.", "No connection", False, True, True)',
            'end',
            'connectivity_checked[0] = 1',
          'end',
        ],
        'header': ['set_gravity([0.0, 0.0, 9.8])'],
    }

    steps: list[ScriptStep] = [
        gripper('Gripper Move30% (1)'),
        movel('h21_neu'),
        movel('h21_neu', dy=-0.3),
        movej('above_washr'),
    ]

    resolved = resolve_with('root', script, steps)['root']

    assert test(resolved) == dedent('''
        # Gripper Move30% (1)
        rq_set_pos_spd_for(77, 0, 0, "1")
        rq_go_to("1")
        rq_wait("1")
        h21_neu_p = p[0.2, -0.4, 0.8, 1.6, -0.0, 0.0]
        movel(h21_neu_p, a=1.2, v=0.25)
        h21_neu_p = p[0.2, -0.4, 0.8, 1.6, -0.0, 0.0]
        h21_neu_p[1] = h21_neu_p[1] + -0.3
        movel(h21_neu_p, a=1.2, v=0.25)
        above_washr_p = p[-0.2, 0.1, 0.3, 1.2, -1.2, -1.2]
        above_washr_q = [-1.6, -2.2, 2.5, -0.3, -0.0, 0.987654]
        movej(get_inverse_kin(above_washr_p, qnear=above_washr_q), a=1.4, v=1.05)
    ''').strip()

    if '-v' in sys.argv:
        print(__file__, 'passed tests')

test_parse_and_resolve()

