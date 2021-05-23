'''
robotarm moves
'''
from __future__ import annotations
from dataclasses import *
from typing import *

from textwrap import dedent, shorten
from utils import *
import abc
import ast
import json
import re
import sys
import textwrap

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
class GripperClose(Move):
    def to_script(self) -> str:
        return call('GripperClose')

@dataclass(frozen=True)
class GripperOpen(Move):
    def to_script(self) -> str:
        return call('GripperOpen')

@dataclass(frozen=True)
class Section(Move):
    sections: str
    def to_script(self) -> str:
        return ''

A = TypeVar('A')
def context(xs: list[A]) -> list[tuple[A | None, A, A | None]]:
    return list(zip(
        [None, None] + xs,        # type: ignore
        [None] + xs + [None],     # type: ignore
        xs + [None, None]))[1:-1] # type: ignore

class MoveList(list[Move]):
    def to_json(self, filename: None | str = None) -> str:
        ms = [m.to_dict() for m in self]
        jsons = []
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
        # json_str = json.dumps(M, indent=2)
        # mini_ws = lambda s: re.sub(r'[\s\n]+', ' ', s, flags=re.MULTILINE)
        # json_str = re.sub(r'\[[-\d\.\s,\n]*\]', lambda m: mini_ws(m.group(0)), json_str, flags=re.MULTILINE)
        if filename:
            with open(filename, 'w') as f: f.write(json_str)
        return json_str

    def normalize(self) -> MoveList:
        out = []
        for prev, m, next in context(self):
            if isinstance(m, Section) and (isinstance(next, Section) or next is None):
                pass
            else:
                out += [m]
        return MoveList(out)

    def to_rel(self) -> MoveList:
        out: list[Move] = []
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
            else:
                out += [m]
        return MoveList(out)

    def to_abs(self) -> MoveList:
        out: list[Move] = []
        last: MoveLin | None = None
        for m in self:
            if isinstance(m, MoveLin):
                last = m
                out += [last]
            elif isinstance(m, MoveRel):
                if last is None:
                    raise ValueError('MoveRel without MoveLin reference')
                last = MoveLin(
                    xyz=[round(a + b, 1) for a, b in zip(m.xyz, last.xyz)],
                    rpy=[round(a + b, 1) for a, b in zip(m.rpy, last.rpy)],
                    name=m.name,
                    slow=m.slow,
                    tag=m.tag,
                )
                out += [last]
            elif isinstance(m, MoveJoint):
                last = None
            else:
                out += [m]
        return MoveList(out)

    def adjust_tagged(self, tag: str, dz: float) -> MoveList:
        out: list[Move] = []
        for m in self:
            if isinstance(m, MoveLin) and m.tag == tag:
                x, y, z = list(m.xyz)
                out += [replace(m, tag=None, xyz=[x, y, round(z + dz, 1)])]
            elif isinstance(m, MoveRel) and m.tag == tag:
                raise ValueError('Tagged move must be MoveLin')
            else:
                out += [m]
        return MoveList(out)

    def tags(self) -> list[str]:
        out = []
        for m in self:
            if hasattr(m, 'tag'):
                tag = getattr(m, 'tag')
                if tag is not None:
                    out += [tag]
        return out

    def apply_dz_tags(self) -> MoveList:
        dzs: dict[str, float] = {}
        for tag in self.tags():
            if tag.startswith('dz='):
                dzs[tag] = float(tag[len('dz='):])
        res: MoveList = self
        for tag, dz in dzs.items():
            res = res.adjust_tagged(tag, dz)
        return res

movelists: dict[str, list[Move]]
movelists = {}

hotel_dist: float = 70.94

from pathlib import Path

for filename in Path('./movelists').glob('*.json'):
    name = filename.with_suffix('').name
    ml = MoveList([Move.from_dict(m) for m in json.load(open(filename))])
    ml = ml.apply_dz_tags()
    for tag in set(ml.tags()):
        if m := re.match('(\d+)/21$', tag):
            ref_h = int(m.group(1))
            assert str(ref_h) in name
            for h in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
                dz = (h - ref_h) / 2 * hotel_dist
                name_h = name.replace(str(ref_h), str(h), 1)
                movelists[name_h] = ml.adjust_tagged(tag, dz)
    movelists[name] = ml

pr(movelists['lid_h21_put'])
pr(movelists.keys())

# TODO: expand sections
