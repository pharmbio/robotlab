'''
robotarm moves
'''
from __future__ import annotations
from dataclasses import *
from typing import *

from pathlib import Path
from utils import show, pr
import abc
import ast
import json
import re
import sys
import textwrap
import utils

class Move(abc.ABC):
    def to_dict(self) -> dict[str, Any]:
        data = {
            k: v
            for field in fields(self)
            for k in [field.name]
            for v in [getattr(self, k)]
            if v != field.default
        }
        return {'type': self.__class__.__name__, **data}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Move:
        subs = { c.__name__: c for c in cls.__subclasses__() }
        d = d.copy()
        return subs[d.pop('type')](**d) # type: ignore

    @abc.abstractmethod
    def to_script(self) -> str:
        raise NotImplementedError

    def try_name(self) -> str:
        if hasattr(self, 'name'):
            return getattr(self, 'name')
        else:
            return ""

    def is_close(self) -> bool:
        if isinstance(self, GripperMove):
            return self.pos == 255
        else:
            return False

    def is_open(self) -> bool:
        if isinstance(self, GripperMove):
            return self.pos != 255
        else:
            return False


def call(name: str, *args: Any, **kwargs: Any) -> str:
    strs = [str(arg) for arg in args]
    strs += [k + '=' + str(v) for k, v in kwargs.items()]
    return name + '(' + ', '.join(strs) + ')'

def keep_true(**kvs: Any) -> dict[str, Any]:
    return {k: v for k, v in kvs.items() if v}

@dataclass(frozen=True)
class MoveLin(Move):
    '''
    Move linearly to an absolute position in the room reference frame.

    xyz in mm
    rpy is roll-pitch-yaw in degrees, with:

    roll:  gripper twist. 0°: horizontal
    pitch: gripper incline. 0°: horizontal, -90° pointing straight down
    yaw:   gripper rotation in room XY, CCW. 0°: to x+, 90°: to y+
    '''
    xyz: list[float]
    rpy: list[float]
    tag: str | None = None
    name: str = ""
    slow: bool = False

    def to_script(self) -> str:
        return call('MoveLin', *self.xyz, *self.rpy, **keep_true(slow=self.slow))

@dataclass(frozen=True)
class MoveRel(Move):
    '''
    Move linearly to a position relative to the current position.

    xyz in mm
    rpy in degrees

    xyz applied in rotation of room reference frame, unaffected by any rpy, so:

    xyz' = xyz + Δxyz
    rpy' = rpy + Δrpy
    '''
    xyz: list[float]
    rpy: list[float]
    tag: str | None = None
    name: str = ""
    slow: bool = False

    def to_script(self) -> str:
        return call('MoveRel', *self.xyz, *self.rpy, **keep_true(slow=self.slow))

@dataclass(frozen=True)
class MoveJoint(Move):
    '''
    Joint rotations in degrees
    '''
    joints: list[float]
    name: str = ""
    slow: bool = False

    def to_script(self) -> str:
        return call('MoveJoint', *self.joints, **keep_true(slow=self.slow))


@dataclass(frozen=True)
class GripperMove(Move):
    pos: int
    soft: bool = False
    def to_script(self) -> str:
        return call('GripperMove', self.pos, **keep_true(soft=self.soft))

@dataclass(frozen=True)
class Section(Move):
    sections: list[str]
    def to_script(self) -> str:
        return textwrap.indent(', '.join(self.sections), '# ')

@dataclass(frozen=True)
class RawCode(Move):
    code: str
    def to_script(self) -> str:
        return self.code

class MoveList(list[Move]):
    '''
    Utility class for dealing with moves in a list
    '''

    @staticmethod
    def from_json_file(filename: str | Path) -> MoveList:
        with open(filename) as f:
            return MoveList([Move.from_dict(m) for m in json.load(f)])

    def write_json(self, filename: str | Path) -> None:
        with open(filename, 'w') as f:
            f.write(self.to_json())

    def to_json(self) -> str:
        ms = [m.to_dict() for m in self]
        jsons: list[str] = []
        for m in ms:
            short = json.dumps(m)
            if len(short) < 120:
                jsons += [short]
            else:
                jsons += [
                    textwrap.indent(
                        json.dumps(m, indent=2),
                        '  ',
                        lambda x: not x.startswith('{'))]
        json_str = (
                '[\n  '
            +   ',\n  '.join(jsons)
            + '\n]'
        )
        return json_str

    def normalize(self) -> MoveList:
        out = MoveList()
        for prev, m, next in utils.context(self):
            if isinstance(m, Section) and (isinstance(next, Section) or next is None):
                pass
            else:
                out += [m]
        return out

    def to_rel(self) -> MoveList:
        out = MoveList()
        last: MoveLin | None = None
        for m in self.to_abs():
            if isinstance(m, MoveLin):
                if last is None:
                    out += [m]
                else:
                    out += [
                        MoveRel(
                            xyz=[round(a - b, 1) for a, b in zip(m.xyz, last.xyz)],
                            rpy=[round(a - b, 1) for a, b in zip(m.rpy, last.rpy)],
                            name=m.name,
                            slow=m.slow,
                            tag=m.tag,
                        )]
                last = m
            elif isinstance(m, MoveRel):
                assert False, 'to_abs returned a MoveRel'
            elif isinstance(m, MoveJoint):
                last = None
                out += [m]
            else:
                out += [m]
        return out

    def to_abs(self) -> MoveList:
        out = MoveList()
        last: MoveLin | None = None
        for m in self:
            if isinstance(m, MoveLin):
                last = m
                out += [last]
            elif isinstance(m, MoveRel):
                if last is None:
                    raise ValueError('MoveRel without MoveLin reference')
                xyz = [round(float(a + b), 1) for a, b in zip(m.xyz, last.xyz)]
                rpy = [round(float(a + b), 1) for a, b in zip(m.rpy, last.rpy)]
                last = MoveLin(xyz=xyz, rpy=rpy, name=m.name, slow=m.slow, tag=m.tag)
                out += [last]
            elif isinstance(m, MoveJoint):
                last = None
                out += [m]
            else:
                out += [m]
        return out

    def adjust_tagged(self, tag: str, *, dz: float) -> MoveList:
        '''
        Adjusts the z in room reference frame for all MoveLin with the given tag.
        '''
        out = MoveList()
        for m in self:
            if isinstance(m, MoveLin) and m.tag == tag:
                x, y, z = list(m.xyz)
                out += [replace(m, tag=None, xyz=[x, y, round(z + dz, 1)])]
            elif isinstance(m, MoveRel) and m.tag == tag:
                raise ValueError('Tagged move must be MoveLin')
            else:
                out += [m]
        return out

    def tags(self) -> list[str]:
        out: list[str] = []
        for m in self:
            if hasattr(m, 'tag'):
                tag = getattr(m, 'tag')
                if tag is not None:
                    out += [tag]
        return out

    def expand_hotels(self, name: str) -> dict[str, MoveList]:
        '''
        If there is a tag like 19/21 then expand to all heights 1/21, 3/21, .., 21/21
        The first occurence of 19 in the name is replaced with 1, 3, .., 21, so
        "lid_h19_put" becomes "lid_h1_put" and so on.
        '''
        hotel_dist: float = 70.94
        out: dict[str, MoveList] = {}
        for tag in set(self.tags()):
            if m := re.match(r'(\d+)/21$', tag):
                ref_h = int(m.group(1))
                assert str(ref_h) in name
                assert ref_h in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]
                for h in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
                    dz = (h - ref_h) / 2 * hotel_dist
                    name_h = name.replace(str(ref_h), str(h), 1)
                    out[name_h] = self.adjust_tagged(tag, dz=dz)
        return out

    def with_sections(self, include_Section: bool=False) -> list[tuple[tuple[str, ...], Move]]:
        out: list[tuple[tuple[str, ...], Move]] = []
        active: tuple[str, ...] = tuple()
        for i, move in enumerate(self):
            if isinstance(move, Section):
                active = tuple(move.sections)
                if include_Section:
                    out += [(active, move)]
            else:
                out += [(active, move)]
        return out

    def expand_sections(self, base_name: str, include_self: bool=True) -> dict[str, MoveList]:
        with_section = self.with_sections()
        sections: set[tuple[str, ...]] = {
            sect
            for sect, move in with_section
        }

        out: dict[str, MoveList] = {}
        if include_self:
            out[base_name] = self
        for section in sections:
            pos = {i for i, (active, _) in enumerate(with_section) if section == active[:len(section)]}
            maxi = max(pos)
            assert all(i == maxi or i + 1 in pos for i in pos), f'section {section} not contiguous'

            name = ' '.join([base_name, *section])
            out[name] = MoveList(m for active, m in with_section if section == active[:len(section)])

        return out


def expand_get(ml: MoveList, base_name: str):
    '''
    a get can be split into prep and main
    prep moves to the last neutral position before pick
    main continues from there and makes the pick
    '''
    out: dict[str, MoveList] = {}
    for i, _ in enumerate(ml):
        head = ml[:i]
        tail = ml[i:]

        if (
            len(tail) >= 3
            and tail[0].try_name().endswith('neu')
            and tail[1].try_name().endswith('pick')
            and tail[2].is_close()
        ):
            out[base_name + ' prep'] = MoveList([*head, tail[0]])
            out[base_name + ' main'] = MoveList(tail)
    return out

def expand_put(ml: MoveList, base_name: str):
    '''
    a put can be split into main and return
    main does the actual move and then pauses at the nearby neutral position
    return goes from the neutral position back to h
    '''
    out: dict[str, MoveList] = {}
    for i, _ in enumerate(ml):
        head = ml[:i]
        tail = ml[i:]

        if (
            len(head) >= 3
            and head[-3].try_name().endswith('drop')
            and head[-2].is_open()
            and head[-1].try_name().endswith('neu')
        ):
            out[base_name + ' main'] = MoveList(head)
            out[base_name + ' return'] = MoveList([head[-1], *tail])
    return out

neu: set[str] = {
    'h neu',
    'h21 neu',
    'wash neu',
    'disp neu',
    'incu pick neu',
}

def expand_from(ml: MoveList, base_name: str):
    out: dict[str, MoveList] = {}
    if 'return' in base_name:
        return out
    for i, m in enumerate(ml):
        if isinstance(m, GripperMove):
            break
        if m.try_name() in neu and i > 0:
            out[base_name + ' from ' + m.try_name()] = MoveList(ml[i:])
    return out

def expand_to(ml: MoveList, base_name: str):
    out: dict[str, MoveList] = {}
    if 'prep' in base_name:
        return out
    for i, m in reversed(list(enumerate(ml))):
        if isinstance(m, GripperMove):
            break
        if m.try_name() in neu and i < len(ml) - 1:
            out[base_name + ' to ' + m.try_name()] = MoveList(ml[:i+1])
    return out

def read_movelists() -> dict[str, MoveList]:
    grand_out: dict[str, MoveList] = {}

    for filename in Path('./movelists').glob('*.json'):
        ml = MoveList.from_json_file(filename)
        name = filename.with_suffix('').name
        special = {'wash_to_disp'}
        secs  = ml.expand_sections(name, include_self=name in special)
        for k, v in secs.items():
            out: dict[str, MoveList] = {k: v}
            if any(machine in k for machine in 'incu wash disp'.split()):
                if k.endswith('get'):
                    out |= expand_get(v, k)
                if k.endswith('put'):
                    out |= expand_put(v, k)
            out |= {
                kk: vv
                for k, v in out.items()
                for kk, vv in expand_from(v, k).items()
            }
            out |= {
                kk: vv
                for k, v in out.items()
                for kk, vv in expand_to(v, k).items()
            }
            out |= {
                kk: vv
                for k, v in out.items()
                for kk, vv in v.expand_hotels(k).items()
            }
            for kk, vv in out.items():
                # print(kk, ':', ' -> '.join([v.try_name() for v in vv]))
                pass
            grand_out |= out

    return grand_out

movelists: dict[str, MoveList]
movelists = read_movelists()
