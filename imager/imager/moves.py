'''
robotarm moves
'''
from __future__ import annotations
from dataclasses import *
from typing import *

from pathlib import Path
import abc
import json
import re
import textwrap
import pbutils

HotelHeights = [h+1 for h in range(12)]
HotelLocs = [f'H{h}' for h in HotelHeights]

class Move(abc.ABC):
    def to_dict(self) -> dict[str, Any]:
        res = pbutils.to_json(self)
        assert isinstance(res, dict)
        return res

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Move:
        return pbutils.from_json(d)

    @abc.abstractmethod
    def to_script(self) -> str:
        raise NotImplementedError

    def desc(self) -> str:
        return self.to_script()

    def try_name(self) -> str:
        if hasattr(self, 'name'):
            return getattr(self, 'name')
        else:
            return ""

def call(name: str, *args: Any) -> str:
    strs = [str(arg) for arg in args]
    return ' '.join([name, *strs])

@dataclass(frozen=True)
class MoveC(Move):
    '''
    Move linearly to an absolute position in the room reference frame.

    xyz in mm
    yaw in in degrees
    '''
    xyz: list[float]
    yaw: float
    name: str = ""
    tag: str | None = None

    def __post_init__(self):
        assert len(self.xyz) == 3

    def to_script(self) -> str:
        return call('MoveC', '1', *self.xyz, self.yaw, 90, 180)

    def desc(self) -> str:
        return call('MoveC', *self.xyz, self.yaw)

@dataclass(frozen=True)
class MoveC_Rel(Move):
    '''
    Move linearly to a position relative to the current position.

    xyz in mm
    rpy in degrees

    xyz applied in rotation of room reference frame, unaffected by any rpy, so:

    xyz' = xyz + Δxyz
    rpy' = rpy + Δrpy
    '''
    xyz: list[float]
    yaw: float
    name: str = ""

    def __post_init__(self):
        assert len(self.xyz) == 3

    def to_script(self) -> str:
        return call('MoveC_Rel', '1', *self.xyz, self.yaw, 0, 0)

@dataclass(frozen=True)
class MoveJ(Move):
    '''
    Joint rotations in degrees
    '''
    joints: list[float]
    name: str = ""

    def __post_init__(self):
        assert len(self.joints) == 4

    def to_script(self) -> str:
        return call('MoveJ_NoGripper', '1', *self.joints)

    def desc(self) -> str:
        return call('MoveJ', *self.joints)

@dataclass(frozen=True)
class MoveGripper(Move):
    pos: int | float
    def to_script(self) -> str:
        return call('MoveGripper', '1', self.pos)

    def desc(self) -> str:
        return call('Gripper', self.pos)

@dataclass(frozen=True)
class Section(Move):
    sections: list[str]
    def to_script(self) -> str:
        return textwrap.indent(', '.join(self.sections), '# ')

@dataclass(frozen=True)
class RawCode(Move):
    '''
    Send a raw piece of code, used only in the gui and available at the cli.
    '''
    code: str
    def to_script(self) -> str:
        return self.code

class MoveList(list[Move]):
    '''
    Utility class for dealing with moves in a list
    '''

    @staticmethod
    def read_jsonl(filename: str | Path) -> MoveList:
        return MoveList(pbutils.serializer.read_jsonl(filename))

    def write_jsonl(self, filename: str | Path) -> None:
        pbutils.serializer.write_jsonl(self, filename)

    def adjust_tagged(self, tag: str, *, dname: str, dz: float) -> MoveList:
        '''
        Adjusts the z in room reference frame for all MoveC with the given tag.
        '''
        out = MoveList()
        for m in self:
            if isinstance(m, MoveC) and m.tag == tag:
                x, y, z = list(m.xyz)
                out += [replace(m, name=dname + ' ' + m.name, tag=None, xyz=[x, y, round(z + dz, 1)])]
            elif hasattr(m, 'tag') and getattr(m, 'tag') == tag:
                raise ValueError('Tagged move must be MoveC for adjust_tagged')
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

    def with_sections(self, include_Section: bool=False) -> list[tuple[tuple[str, ...], Move]]:
        out: list[tuple[tuple[str, ...], Move]] = []
        active: tuple[str, ...] = tuple()
        for move in self:
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
            for sect, _move in with_section
            if sect
        }

        out: dict[str, MoveList] = {}
        if include_self:
            out[base_name] = self
        for section in sections:
            pos = {i for i, (active, _) in enumerate(with_section) if section == active[:len(section)]}
            maxi = max(pos)
            assert all(i == maxi or i + 1 in pos for i in pos), f'section {section} not contiguous'

            name = ' '.join(section)
            out[name] = MoveList(m for active, m in with_section if section == active[:len(section)])

        return out

    def expand_hotels(self, name: str) -> dict[str, MoveList]:
        '''
        If there is a tag like 19/21 then expand to all heights 1/21, 3/21, .., 21/21
        The first occurence of 19 in the name is replaced with 1, 3, .., 21, so
        "lid_B19_put" becomes "lid_B1_put" and so on.
        '''
        hotel_dist: float = 70.94 / 2.0 - 3 / 11.0
        out: dict[str, MoveList] = {}
        for tag in set(self.tags()):
            if m := re.match(r'(\d+)/12$', tag):
                ref_h = int(m.group(1))
                assert str(ref_h) in name
                assert ref_h in HotelHeights
                for h in HotelHeights:
                    if h == ref_h:
                        continue
                    dz = (h - ref_h) * hotel_dist
                    name_h = name.replace(f'H{ref_h}', f'H{h}', 1)
                    out[name_h] = self.adjust_tagged(tag, dname=str(h), dz=dz)
        return out

    def describe(self) -> str:
        return '\n'.join([
            m.__class__.__name__ + ' ' +
            (m.try_name() or pbutils.catch(lambda: str(getattr(m, 'pos')), ''))
            for m in self
        ])

def read_and_expand(filename: Path) -> dict[str, MoveList]:
    ml = MoveList.read_jsonl(filename)
    name = filename.stem
    expanded = ml.expand_sections(name, include_self=False)
    for k, v in list(expanded.items()):
        expanded |= v.expand_hotels(k)
    return expanded

def read_movelists() -> dict[str, MoveList]:
    expanded: dict[str, MoveList] = {}
    for filename in Path('./movelists').glob('*.jsonl'):
        expanded |= read_and_expand(filename)

    return expanded

pbutils.serializer.register(globals())

movelists: dict[str, MoveList]
movelists = read_movelists()

movelists['home'] = MoveList([
    RawCode('hp 1'),
    RawCode('attach 1'),
    RawCode('home 1'),
])

movelists['test-comm'] = MoveList([
    RawCode('version'),
])

movelists['freedrive'] = MoveList([
    RawCode('Freedrive'),
])

movelists['stop-freedrive'] = MoveList([
    RawCode('StopFreedrive'),
])
