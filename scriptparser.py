from __future__ import annotations
from dataclasses import dataclass, field, replace, astuple
from typing import *

import textwrap

from abc import ABC
from functools import lru_cache
from utils import show

import ast
import re
import sys

class ScriptStep(ABC):
    pass

@dataclass(frozen=True)
class movel(ScriptStep):
    name: str
    slow: bool = False
    tag: str | None = None

@dataclass(frozen=True)
class movej(ScriptStep):
    name: str

@dataclass(frozen=True)
class gripper(ScriptStep):
    name: str
    pos: int | None = None

@dataclass(frozen=True)
class section(ScriptStep):
    name: str
    steps: list[ScriptStep]

@dataclass
class ParsedScript:
    '''
    The parser extracts and returns a tuple of:
    - steps: moves and gripper commands,
    - defs: coordinates and gripper open in percent to raw gripper pos,

    The moves are used to generate program stubs which
    are manually rewritten to cut up the program loops to atomic programs.

    The coordinates in these programs are then resolved using the
    parsed coordinates. The gripper commands and the header are
    also resolved using the result from the parser.
    '''
    steps: list[ScriptStep] = field(default_factory=list)
    defs: dict[str, list[float]] = field(default_factory=dict)

@lru_cache
def parse(filename: str) -> ParsedScript:
    return parse_lines(list(open(filename, 'r')))

def parse_lines(lines: list[str]) -> ParsedScript:
    res = ParsedScript()
    last_gripper_name = ""
    for i, line in enumerate(lines):
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
        elif m := re.match(' *\$ \d* "(Gripper.*)"', line):
            name, = m.groups()
            last_gripper_name = name
        elif m := re.match(' *rq_set_pos_spd_for\((\d+)', line):
            pos, = m.groups()
            res.steps += [gripper(pos=int(pos), name=last_gripper_name)]
            res.defs[last_gripper_name] = [int(pos)]

    return res

def resolve(filename: str, steps: list[ScriptStep]) -> list[Move]:
    return list(resolve_parsed(parse(filename), steps))

from scipy.spatial.transform import Rotation, Rotation as R # type: ignore
from moves import *

nice_trf : Rotation
nice_trf = R.from_euler("xyz", [-90, 90, 0], degrees=True)

nice_trf_pose : list[float]
nice_trf_pose = [0, 0, 0, nice_trf.as_rotvec()]

def round_nnz(x: float, ndigits: int=1) -> float:
    '''
    Round and normalize negative zero
    '''
    v = round(x, ndigits)
    if v == -0.0:
        return 0.0
    else:
        return v

def make_nice(in_zero_trf: list[float]) -> tuple[list[float], list[float]]:
    '''
    Converts a UR pose given in the zero TRF (as in set_tcp(0,0,0,0,0,0))
    and makes it nice as described in MoveLin.

    >>> make_nice([0.605825, -0.720087, 0.233797, 1.640554, -0.010878, 0.011601])
    ([605.8, -720.1, 233.8], [-0.8, -4.0, 90.1])
    '''
    xyz_m = in_zero_trf[:3]
    xyz = [round_nnz(c * 1000, 1) for c in xyz_m]
    rv = in_zero_trf[3:]
    rv_R = R.from_rotvec(rv)
    in_nice_R = rv_R * nice_trf
    rpy = in_nice_R.as_euler('xyz', degrees=True)
    rpy = [round_nnz(c, 1) for c in rpy]
    return xyz, rpy

import math

def resolve_parsed(script: ParsedScript, steps: list[ScriptStep], active_sections: list[str]=[]) -> Iterator[Move]:
    for step in steps:
        if isinstance(step, movel):
            p = script.defs[step.name + '_p']
            xyz, rpy = make_nice(p)
            yield MoveLin(xyz=xyz, rpy=rpy, slow=step.slow, name=step.name, tag=step.tag)
        elif isinstance(step, movej):
            q = script.defs[step.name + '_q']
            yield MoveJoint(joints=[round(math.degrees(v)) for v in q], name=step.name)
        elif isinstance(step, gripper):
            pos = script.defs[step.name][0] if step.pos is None else step.pos
            yield GripperMove(pos=int(pos))
        elif isinstance(step, section):
            inner_sections = [*active_sections, step.name]
            yield Section(sections=' '.join(inner_sections))
            yield from resolve_parsed(script, step.steps, active_sections=inner_sections)
            yield Section(sections=' '.join(active_sections))
        else:
            raise ValueError

@dataclass(frozen=True)
class test:
    lhs: object
    def __eq__(self, rhs: object) -> bool:
        lhs = self.lhs
        true = lhs == rhs
        if not true:
            print(f'lhs = {show(lhs)}\nrhs = {show(rhs)}')
        elif '-v' in sys.argv:
            print(f'passed test(...) == {textwrap.shorten(repr(rhs), 60, placeholder=" ...")}')
        return true

def test_parse_and_resolve() -> None:
    example_script = textwrap.dedent('''
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
        gripper('Gripper Move30% (1)', 77),
        movel('h21_neu'),
        movej('above_washr'),
    ]

    assert test(script.defs) == {
        'h21_neu_p': [0.2, -0.4, 0.8, 1.6, -0.0, 0.0],
        'h21_neu_q': [1.6, -1.9, 1.5, 0.4, 1.6, 0.0],
        'above_washr_p': [-0.2, 0.1, 0.3, 1.2, -1.2, -1.2],
        'above_washr_q': [-1.6, -2.2, 2.5, -0.3, -0.0, 0.987654],
        'Gripper Move30% (1)': [77],
    }

    steps: list[ScriptStep] = [
        gripper('Gripper Move30% (1)'),
        movel('h21_neu'),
        section('final_part', [
            movel('h21_neu', tag='h19', slow=True),
            movej('above_washr'),
        ])
    ]

    resolved = list(resolve_parsed(script, steps))

    assert test(resolved) == [
      GripperMove(77),
      MoveLin(
        xyz=[200.0, -400.0, 800.0],
        rpy=[0.0, -1.7, 90.0],
        name='h21_neu',
      ),
      Section('final_part'),
      MoveLin(
        xyz=[200.0, -400.0, 800.0],
        rpy=[0.0, -1.7, 90.0],
        name='h21_neu',
        slow=True,
        tag='h19',
      ),
      MoveJoint(
        joints=[-92, -126, 143, -17, 0, 57],
        name='above_washr',
      ),
      Section(''),
    ]

    if '-v' in sys.argv:
        print(__file__, 'passed tests')

test_parse_and_resolve()
import doctest
doctest.testmod()
