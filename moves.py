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

def call(name: str, *args: Any, **kwargs: Any) -> str:
    strs = [str(arg) for arg in args]
    strs += [k + '=' + str(v) for k, v in kwargs.items()]
    return name + '(' + ', '.join(strs) + ')'

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
        return call('MoveLin', *self.xyz, *self.rpy, **(dict(slow=True) if self.slow else {}))

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
        return call('MoveRel', *self.xyz, *self.rpy, **(dict(slow=True) if self.slow else {}))

@dataclass(frozen=True)
class MoveJoint(Move):
    '''
    Joint rotations in degrees
    '''
    joints: list[float]
    name: str = ""
    slow: bool = False

    def to_script(self) -> str:
        return call('MoveJoint', *self.joints, **(dict(slow=True) if self.slow else {}))


@dataclass(frozen=True)
class GripperMove(Move):
    pos: int
    def to_script(self) -> str:
        return call('GripperMove', self.pos)

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

    def expand_sections(self, base_name: str) -> dict[str, MoveList]:
        with_section = self.with_sections()
        sections: set[tuple[str, ...]] = {
            sect
            for sect, move in with_section
        }

        out: dict[str, MoveList] = {base_name: self}
        for section in sections:
            pos = {i for i, (active, _) in enumerate(with_section) if section == active[:len(section)]}
            maxi = max(pos)
            assert all(i == maxi or i + 1 in pos for i in pos), f'section {section} not contiguous'

            name = '_'.join([base_name, *section])
            out[name] = MoveList(m for active, m in with_section if section == active[:len(section)])

        return out



def read_movelists() -> dict[str, MoveList]:
    out: dict[str, MoveList] = {}

    for filename in Path('./movelists').glob('*.json'):
        ml = MoveList.from_json_file(filename)
        name = filename.with_suffix('').name

        for name, ml in ml.expand_sections(name).items():
            out |= ml.expand_hotels(name)
            out[name] = ml.to_rel()

    return out

movelists: dict[str, MoveList]
movelists = read_movelists()
