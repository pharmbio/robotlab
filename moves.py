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

    def is_gripper(self) -> bool:
        return isinstance(self, (GripperMove, GripperCheck))

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
class GripperCheck(Move):
    def to_script(self) -> str:
        return call('GripperCheck')

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

    def is_gripper(self) -> bool: raise ValueError
    def is_open(self) -> bool: raise ValueError
    def is_close(self) -> bool: raise ValueError

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

    def adjust_tagged(self, tag: str, *, dname: str, dz: float) -> MoveList:
        '''
        Adjusts the z in room reference frame for all MoveLin with the given tag.
        '''
        out = MoveList()
        for m in self:
            if isinstance(m, MoveLin) and m.tag == tag:
                x, y, z = list(m.xyz)
                out += [replace(m, name=dname + ' ' + m.name, tag=None, xyz=[x, y, round(z + dz, 1)])]
            elif hasattr(m, 'tag') and getattr(m, 'tag') == tag:
                raise ValueError('Tagged move must be MoveLin for adjust_tagged')
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
                    out[name_h] = self.adjust_tagged(tag, dname=str(h), dz=dz)
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

    def has_open(self) -> bool:
        return any(m.is_open() for m in self)

    def has_close(self) -> bool:
        return any(m.is_close() for m in self)

    def has_gripper(self) -> bool:
        return any(m.is_gripper() for m in self)

    def split_on(self, pred: Callable[[Move], bool]) -> tuple[MoveList, Move, MoveList]:
        for i, move in enumerate(self):
            if pred(move):
                return MoveList(self[:i]), move, MoveList(self[i+1:])
        raise ValueError

    def split(self) -> MoveListParts:
        before_pick, close, after_pick = self.split_on(Move.is_close)
        mid, open, after_drop = after_pick.split_on(Move.is_open)
        return MoveListParts.init(
            before_pick=before_pick,
            close=close,
            transfer_inner=mid,
            open=open,
            after_drop=after_drop,
        )

@dataclass(frozen=True)
class MoveListParts:
    prep: MoveList
    transfer: MoveList
    ret: MoveList

    @staticmethod
    def init(
        before_pick: MoveList,
        close: Move,
        transfer_inner: MoveList,
        open: Move,
        after_drop: MoveList,
    ):
        assert not any(m.is_gripper() for m in before_pick)
        assert not any(m.is_gripper() for m in transfer_inner)
        assert not any(m.is_gripper() for m in after_drop)
        assert close.is_close()
        assert open.is_open()

        *to_pick_neu, pick_neu, pick_pos = before_pick
        drop_neu, *from_drop_neu = after_drop

        assert pick_neu.try_name().endswith("neu"),  f'{pick_neu.try_name()} needs a neu before pick'
        assert pick_pos.try_name().endswith("pick"), f'{pick_pos.try_name()} needs a pick move before gripper pick close'
        assert drop_neu.try_name().endswith("neu"),  f'{drop_neu.try_name()} needs a neu after drop'

        return MoveListParts(
            prep     = MoveList([*to_pick_neu, pick_neu]),
            transfer = MoveList([              pick_neu, pick_pos, close, *transfer_inner, open, drop_neu]),
            ret      = MoveList([                                                                drop_neu, *from_drop_neu]),
        )

HasMoveList = TypeVar('HasMoveList')

def sleek_movements(
    xs: list[HasMoveList],
    get_movelist: Callable[[HasMoveList], MoveList | None],
) -> list[HasMoveList]:
    '''
    if program A ends by h21 neu and program B by h21 neu then run:
        program A to h21 neu
        program B from h21 neu
    '''
    ms: list[tuple[int, MoveList]] = []
    for i, x in enumerate(xs):
        if m := get_movelist(x):
            ms += [(i, m)]

    rm: set[int] = set()

    for (i, a), (j, b) in zip(ms, ms[1:]):
        a_first = a[0].try_name()
        b_last = b[-1].try_name()
        if a.has_gripper() or b.has_gripper():
            continue
        if a_first and a_first == b_last:
            rm |= {i, j}

    return [
        x
        for i, x in enumerate(xs)
        if i not in rm
    ]

def read_movelists() -> dict[str, MoveList]:
    grand_out: dict[str, MoveList] = {}

    for filename in Path('./movelists').glob('*.json'):
        ml = MoveList.from_json_file(filename)
        name = filename.with_suffix('').name
        secs = ml.expand_sections(name, include_self=name in {'wash_to_disp'})
        for k, v in secs.items():
            expanded = v.expand_hotels(k)
            for kk, vv in {k: v, **expanded}.items() :
                out: dict[str, MoveList] = {}
                out[kk] = vv
                if 'put-prep' not in kk and not 'put-return' in kk:
                    parts = vv.split()
                    out[kk + ' prep']     = parts.prep
                    out[kk + ' transfer'] = parts.transfer
                    out[kk + ' return']   = parts.ret
                    if 'incu_A' in kk and 'put' in kk:
                        to_neu, neu, after_neu = parts.transfer.split_on(lambda m: m.try_name().endswith('drop neu'))
                        assert to_neu.has_close() and not to_neu.has_open()
                        assert not after_neu.has_close() and after_neu.has_open()
                        out[kk + ' transfer to drop neu'] = MoveList(to_neu + [neu])
                        out[kk + ' transfer from drop neu'] = after_neu
                grand_out = grand_out | out

    grand_out['noop'] = MoveList()
    grand_out['gripper check'] = MoveList([GripperCheck()])

    return grand_out

movelists: dict[str, MoveList]
movelists = read_movelists()

