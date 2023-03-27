'''
robotarm moves
'''
from __future__ import annotations
from dataclasses import *
from typing import *

from pathlib import Path
import abc
import re
import pbutils
from pbutils.mixins import DBMixin

from .ur_script import URScript

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

    def try_name(self) -> str:
        if hasattr(self, 'name'):
            return getattr(self, 'name')
        else:
            return ""

    def is_gripper(self) -> bool:
        return isinstance(self, (GripperMove, GripperInitAndCheck))

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
class GripperInitAndCheck(Move):
    def to_script(self) -> str:
        return call('GripperInitAndCheck')

@dataclass(frozen=True)
class Section(Move):
    section: str
    def to_script(self) -> str:
        return f'# {self.section}'

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

HotelLocs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
HotelLocs_B_C = [x for x in HotelLocs if x % 2 == 1]

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
        "lid_B19_put" becomes "lid_B1_put" and so on.
        '''
        hotel_dist: float = 70.94
        out: dict[str, MoveList] = {}
        hotel_locs = HotelLocs if 'A' in name else HotelLocs_B_C
        for tag in set(self.tags()):
            if m := re.match(r'(\d+)/21$', tag):
                ref_h = int(m.group(1))
                assert str(ref_h) in name
                assert ref_h in hotel_locs
                for h in hotel_locs:
                    dz = (h - ref_h) / 2 * hotel_dist
                    name_h = name.replace(str(ref_h), str(h), 1)
                    out[name_h] = self.adjust_tagged(tag, dname=str(h), dz=dz)
        return out

    def with_sections(self, include_Section: bool=False) -> list[tuple[str, Move]]:
        out: list[tuple[str, Move]] = []
        active: str = ''
        for _i, move in enumerate(self):
            if isinstance(move, Section):
                active = move.section
                if include_Section:
                    out += [(active, move)]
            else:
                out += [(active, move)]
        return out

    def expand_sections(self) -> dict[str, MoveList]:
        with_section = self.with_sections()
        sections: set[str] = {
            section
            for section, _move in with_section
            if section
        }

        for section, move in with_section:
            if not section:
                raise ValueError(f'Move {move} not in a section {self}')


        out: dict[str, MoveList] = {}
        for section in sections:
            pos = {i for i, (active, _) in enumerate(with_section) if section == active[:len(section)]}
            maxi = max(pos)
            assert all(i == maxi or i + 1 in pos for i in pos), f'section {section} not contiguous'

            name = section
            out[name] = MoveList(m for active, m in with_section if section == active[:len(section)])

        return out

    def describe(self) -> str:
        return '\n'.join([
            m.__class__.__name__ + ' ' +
            (m.try_name() or pbutils.catch(lambda: str(getattr(m, 'pos')), ''))
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

    def split(self, name: str) -> MoveListParts:
        before_pick, close, after_pick = self.split_on(Move.is_close)
        mid, open, after_drop = after_pick.split_on(Move.is_open)
        return MoveListParts.init(
            name=name,
            before_pick=before_pick,
            close=close,
            transfer_inner=mid,
            open=open,
            after_drop=after_drop,
        )

    def make_script(self, with_gripper: bool, name: str='script') -> URScript:
        body = '\n'.join(
            ("# " + getattr(m, 'name') + '\n' if hasattr(m, 'name') else '')
            + m.to_script()
            for m in self
        )
        code = f'''
            def {name}():
                {URScript.prelude}
                {URScript.gripper_code(with_gripper)}
                {body}
                textmsg("log {name} done")
            end
        '''
        return URScript.make(name=name, code=code)

@dataclass(frozen=True)
class MoveListParts:
    prep: MoveList
    transfer: MoveList
    transferless: MoveList
    ret: MoveList

    @staticmethod
    def init(
        name: str,
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

        # neu
        # pick
        # [gripper close]
        # ... anything ...
        # [gripper open]
        # neu

        if 1:
            assert pick_neu.try_name().endswith("neu"),  f'{name!r}: {pick_neu.try_name()!r} needs a neu before pick'
            assert pick_pos.try_name().endswith("pick"), f'{name!r}: {pick_pos.try_name()!r} needs a pick move before gripper pick close'
            assert drop_neu.try_name().endswith("neu"),  f'{name!r}: {drop_neu.try_name()!r} needs a neu after drop'

        return MoveListParts(
            prep         = MoveList([*to_pick_neu, pick_neu]),
            transfer     = MoveList([              pick_neu, pick_pos, close, *transfer_inner, open, drop_neu]),
            transferless = MoveList([              pick_neu,                  *transfer_inner                ]),
            ret          = MoveList([                                                                drop_neu, *from_drop_neu]),
        )

HasMoveList = TypeVar('HasMoveList')

def sleek_movements(
    xs: list[HasMoveList],
    get_movelist: Callable[[HasMoveList], MoveList | None],
    pair_ok: Callable[[HasMoveList, HasMoveList], bool],
) -> list[HasMoveList]:
    '''
    if program A ends by B21 neu and program B by B21 neu then run:
        program A to B21 neu
        program B from B21 neu
    '''
    ms: list[tuple[int, MoveList]] = []
    for i, x in enumerate(xs):
        if m := get_movelist(x):
            ms += [(i, m)]

    rm: set[int] = set()

    for (i, a), (j, b) in zip(ms, ms[1:]):
        a_first = a[0].try_name().replace('drop', 'pick')
        b_last = b[-1].try_name().replace('drop', 'pick')
        if a.has_gripper() or b.has_gripper():
            continue
        if a_first and a_first == b_last and pair_ok(xs[i], xs[j]):
            rm |= {i, j}

    return [
        x
        for i, x in enumerate(xs)
        if i not in rm
    ]

@dataclass(frozen=True)
class NamedMoveList:
    base: str
    kind: Literal[
        'full',
        'prep',
        'transfer',
        'transferless',
        'return',
    ] | str
    movelist: MoveList

    @property
    def name(self):
        if self.kind == 'full':
            return self.base
        else:
            return self.base + ' ' + self.kind

def read_and_expand(filename: Path) -> dict[str, MoveList]:
    ml = MoveList.read_jsonl(filename)
    expanded = ml.expand_sections()
    for k, v in list(expanded.items()):
        expanded |= v.expand_hotels(k)
    return expanded

def read_movelists() -> dict[str, MoveList]:
    expanded: dict[str, MoveList] = {}
    for filename in Path('./movelists').glob('*.jsonl'):
        expanded |= read_and_expand(filename)

    if not expanded:
        import sys
        print(f'''
            No movelists found. You need to start this program in the
            repo root directory so that ./movelists/ is a direct child.

            If you installed with pip install --editable, you probably
            want to be in {Path(__file__).parent.parent}
            but you're in {Path.cwd()}
        ''', file=sys.stderr)
        sys.exit(-1)

    out: list[NamedMoveList] = []
    for base, v in expanded.items():
        if base in 'B-neu-to-A-neu A-neu-to-B-neu'.split():
            out += [NamedMoveList(base, 'full', v)]
            continue
        if 'calib' in base:
            continue
        if 'wave' in base:
            out += [NamedMoveList(base, 'full', v)]
            continue
        out += [NamedMoveList(base, 'full', v)]
        parts = v.split(base)
        prep = NamedMoveList(base, 'prep', parts.prep)
        ret = NamedMoveList(base, 'return', parts.ret)
        transfer = NamedMoveList(base, 'transfer', parts.transfer)
        transferless = NamedMoveList(base, 'transferless', parts.transferless)
        out += [
            prep,
            ret,
            transfer,
            transferless,
        ]
        if re.match(r'A\d+-to-incu', base):
            # special handling for quick incubator load which has a neutral somewhere around A5
            to_neu, neu, after_neu = parts.transfer.split_on(lambda m: m.try_name().endswith('drop neu'))
            assert to_neu.has_close() and not to_neu.has_open()
            assert not after_neu.has_close() and after_neu.has_open()
            to_drop = NamedMoveList(base, 'transfer to drop neu', MoveList(to_neu + [neu]))
            from_drop = NamedMoveList(base, 'transfer from drop neu', after_neu)
            out += [
                to_drop,
                from_drop,
            ]

    out += [
        NamedMoveList('noop', 'full', MoveList()),
        NamedMoveList('gripper init and check', 'full', MoveList([GripperInitAndCheck()])),
    ]

    to_neu = {v.name: v for v in out}['lid-B19 put prep'].movelist[0]
    assert isinstance(to_neu, MoveJoint)
    assert to_neu.name == 'B neu'
    to_neu_slow = replace(to_neu, slow=True)

    out += [
        NamedMoveList('to neu', 'full', MoveList([to_neu_slow])),
    ]
    return {v.name: v.movelist for v in out}

@dataclass(frozen=True)
class World(DBMixin):
    data: dict[str, str] = field(default_factory=dict)
    t: float = 0  # filled in when executing
    id: int = -1

    def __getitem__(self, key: str) -> str:
        return self.data[key]

class Effect(abc.ABC):
    def apply(self, world: World) -> World:
        next = {**world.data}
        for k, v in self.effect(world).items():
            if v is None:
                assert k in world.data
                next.pop(k)
            else:
                assert k not in world.data
                next[k] = v
        return World(next)

    @abc.abstractmethod
    def effect(self, world: World) -> dict[str, str | None]:
        pass

@dataclass(frozen=True)
class InitialWorld(Effect):
    world0: World
    def effect(self, world: World) -> dict[str, str | None]:
        assert not world.data
        return {**self.world0.data}

@dataclass(frozen=True)
class MovePlate(Effect):
    source: str
    target: str
    def effect(self, world: World) -> dict[str, str | None]:
        return {self.source: None, self.target: world[self.source]}

@dataclass(frozen=True)
class TakeLidOff(Effect):
    source: str
    target: str
    def effect(self, world: World) -> dict[str, str | None]:
        return {self.target: 'lid ' + world[self.source]}

@dataclass(frozen=True)
class PutLidOn(Effect):
    source: str
    target: str
    def effect(self, world: World) -> dict[str, str | None]:
        assert world[self.source] == 'lid ' + world[self.target]
        return {self.source: None}

pbutils.serializer.register(globals())

movelists: dict[str, MoveList]
movelists = read_movelists()

B21 = 'B21'
effects: dict[str, Effect] = {}

for k, v in movelists.items():
    m = re.match(r'(\w+)-to-(\w+)$', k)
    if m:
        source, target = m.groups()
        effects[k] = MovePlate(source=source, target=target)

for i in HotelLocs:
    Ai = f'A{i}'
    Bi = f'B{i}'
    Ci = f'C{i}'
    effects[Ai + ' get'] = MovePlate(source=Ai, target=B21)
    effects[Bi + ' get'] = MovePlate(source=Bi, target=B21)
    effects[Ci + ' get'] = MovePlate(source=Ci, target=B21)

    effects[Ai + ' put'] = MovePlate(source=B21, target=Ai)
    effects[Bi + ' put'] = MovePlate(source=B21, target=Bi)
    effects[Ci + ' put'] = MovePlate(source=B21, target=Ci)

    lid_Bi = f'lid-B{i}'
    effects[lid_Bi + ' get'] = PutLidOn(source=Bi, target=B21)
    effects[lid_Bi + ' put'] = TakeLidOff(source=B21, target=Bi)

for k in list(effects.keys()):
    effects[k + ' transfer'] = effects[k]

for i in HotelLocs:
    Ai = f'A{i}'
    effects[f'{Ai}-to-incu transfer from drop neu'] = MovePlate(source=Ai, target='incu')

