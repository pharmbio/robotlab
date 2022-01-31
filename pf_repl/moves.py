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
        subs = {c.__name__: c for c in cls.__subclasses__()}
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
        return call('MoveC', '1', *self.xyz, self.yaw, 0, 0)

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
    slow: bool = False

    def __post_init__(self):
        assert len(self.xyz) == 3

    def to_script(self) -> str:
        return call('MoveLinRel', '1', *self.xyz, self.yaw, 0, 0)

@dataclass(frozen=True)
class MoveJ(Move):
    '''
    Joint rotations in degrees
    '''
    joints: list[float]
    name: str = ""
    slow: bool = False

    def __post_init__(self):
        assert len(self.joints) == 4

    def to_script(self) -> str:
        return call('MoveJ_NoGripper', '1', *self.joints)

@dataclass(frozen=True)
class MoveGripper(Move):
    pos: int
    def to_script(self) -> str:
        return call('MoveGripper', '1', self.pos)

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
    def from_jsonl_file(filename: str | Path) -> MoveList:
        return MoveList([
            Move.from_dict(m)
            for m in utils.read_json_lines(str(filename))
        ])

    def write_jsonl(self, filename: str | Path) -> None:
        with open(filename, 'w') as f:
            for m in self:
                print(json.dumps(m.to_dict()), file=f)

    def adjust_tagged(self, tag: str, *, dz: float) -> MoveList:
        '''
        Adjusts the z in room reference frame for all MoveC with the given tag.
        '''
        out = MoveList()
        for m in self:
            if isinstance(m, MoveC) and m.tag == tag:
                x, y, z = list(m.xyz)
                out += [replace(m, tag=None, xyz=[x, y, round(z + dz, 1)])]
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

            name = ' '.join([base_name, *section])
            out[name] = MoveList(m for active, m in with_section if section == active[:len(section)])

        return out

    def describe(self) -> str:
        return '\n'.join([
            m.__class__.__name__ + ' ' +
            (m.try_name() or utils.catch(lambda: str(getattr(m, 'pos')), ''))
            for m in self
        ])

def read_and_expand(filename: Path) -> dict[str, MoveList]:
    ml = MoveList.from_jsonl_file(filename)
    name = filename.stem
    expanded = ml.expand_sections(name, include_self=name == 'wash_to_disp')
    return expanded

def read_movelists() -> dict[str, MoveList]:
    expanded: dict[str, MoveList] = {}
    for filename in Path('./movelists').glob('*.jsonl'):
        expanded |= read_and_expand(filename)

    return expanded

movelists: dict[str, MoveList]
movelists = read_movelists()

