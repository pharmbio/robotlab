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
import textwrap
from pbutils.mixins import DBMixin

from .ur_script import URScript

# UR room:
HotelLocs_A = [h+1 for h in range(21)]
HotelLocs_B = [21, 19, 17, 16, 14, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
HotelLocs_Base = [14, 12]

# PF room:
HotelLocs_H = [h+1 for h in range(19) if h+1 != 12]

HotelDict = {
    'A': HotelLocs_A,
    'B': HotelLocs_B,
    'Base': HotelLocs_Base,
    'H': HotelLocs_H,
}

class Move(abc.ABC):
    @abc.abstractmethod
    def to_ur_script(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def to_pf_script(self) -> str:
        raise NotImplementedError

    def try_name(self) -> str:
        if hasattr(self, 'name'):
            return getattr(self, 'name')
        else:
            return ""

    def is_gripper(self) -> bool:
        return isinstance(self, GripperMove)

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

def ur_call(name: str, *args: Any, **kwargs: Any) -> str:
    strs = [str(arg) for arg in args]
    strs += [k + '=' + str(v) for k, v in kwargs.items()]
    return name + '(' + ', '.join(strs) + ')'

def pf_call(name: str, *args: Any) -> str:
    strs = [
        str(
            round(arg, 6) if isinstance(arg, float) else arg
        )
        for arg in args
    ]
    return ' '.join([name, *strs])

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

    For PF: only yaw of rpy is used.
    '''
    xyz: list[float]
    rpy: list[float]
    tag: str | None = None
    name: str = ""
    slow: bool = False
    sleep_secs: float | None = None
    in_joint_space: bool = False

    def to_ur_script(self) -> str:
        res = ur_call('MoveLin', *self.xyz, *self.rpy, **keep_true(slow=self.slow, in_joint_space=self.in_joint_space))
        if self.sleep_secs:
            res += f'\nsleep({self.sleep_secs})'
        return res

    def to_pf_script(self) -> str:
        return pf_call('MoveC', '1', *self.xyz, self.rpy[-1], 90, 180)

@dataclass(frozen=True)
class MoveRel(Move):
    '''
    Move linearly to a position relative to the current position.

    xyz in mm
    rpy in degrees

    xyz applied in rotation of room reference frame, unaffected by any rpy, so:

    xyz' = xyz + Δxyz
    rpy' = rpy + Δrpy

    For PF: only yaw of rpy is used.
    '''
    xyz: list[float]
    rpy: list[float]
    tag: str | None = None
    name: str = ""
    slow: bool = False

    def to_ur_script(self) -> str:
        return ur_call('MoveRel', *self.xyz, *self.rpy, **keep_true(slow=self.slow))

    def to_pf_script(self) -> str:
        return pf_call('MoveC_Rel', '1', *self.xyz, self.rpy[-1], 0, 0)

@dataclass(frozen=True)
class MoveJoint(Move):
    '''
    Joint rotations in degrees

    For UR: All 6 are used
    For PF: Only the 4 first are used
    '''
    joints: list[float]
    name: str = ""
    slow: bool = False

    def to_ur_script(self) -> str:
        return ur_call('MoveJoint', *self.joints, **keep_true(slow=self.slow))

    def to_pf_script(self) -> str:
        joints = self.joints[:4]
        assert len(joints) == 4
        return pf_call('MoveJ_NoGripper', '1', *joints)

@dataclass(frozen=True)
class GripperMove(Move):
    pos: int
    soft: bool = False
    def to_ur_script(self) -> str:
        return ur_call('GripperMove', self.pos, **keep_true(soft=self.soft))

    def to_pf_script(self) -> str:
        return pf_call('MoveGripper', '1', self.pos)

@dataclass(frozen=True)
class Section(Move):
    section: str
    def to_ur_script(self) -> str:
        return f'# {self.section}'

    def to_pf_script(self) -> str:
        return ''

@dataclass(frozen=True)
class RawCode(Move):
    '''
    Send a raw piece of code, used only in the gui and available at the cli.
    '''
    code: str
    def to_ur_script(self) -> str:
        return self.code

    def to_pf_script(self) -> str:
        return textwrap.dedent(self.code).strip()

    def is_gripper(self) -> bool: raise ValueError
    def is_open(self) -> bool: raise ValueError
    def is_close(self) -> bool: raise ValueError

class MoveList(list[Move]):
    '''
    Utility class for dealing with moves in a list
    '''

    @staticmethod
    def read_jsonl(filename: str | Path) -> MoveList:
        return MoveList(pbutils.serializer.read_jsonl(filename))

    def write_jsonl(self, filename: str | Path) -> None:
        pbutils.serializer.write_jsonl(self, filename)

    def adjust_tagged(self, tag: str, *, dname: dict[str, str], dz: float) -> MoveList:
        '''
        Adjusts the z in room reference frame for all MoveLin with the given tag.
        '''
        out = MoveList()
        for m in self:
            if isinstance(m, MoveLin) and m.tag == tag:
                x, y, z = list(m.xyz)
                name = m.name
                for k, v in dname.items():
                    name = name.replace(k, v)
                out += [
                    replace(m, name=name,
                        tag=None,
                        xyz=[x, y, round(z + dz, 1)]
                    )
                ]
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
        Expands tags like B14 to all positions in the B hotel.
        There are also "Base" tags like Base14 which is expanded to the two base positions in B (14 and 12)
        '''

        hotel_dist: float = 70.94 / 2

        out: Dict[str, MoveList] = {name: self}

        for tag in sorted(set(self.tags()), key=lambda s: 'Base' in s):
            if not (m := re.match(r'^(\D+)(\d+)$', tag)):
                raise ValueError(f'Invalid tag name {tag=}')
            tag_hotel, tag_h = m.groups()
            tag_h = int(tag_h)
            for out_name, out_list in list(out.items()):
                del out[out_name]
                for h in HotelDict[tag_hotel]:
                    target_hotel = tag_hotel.replace('Base', 'B')
                    target_loc = f'{target_hotel}{h}'
                    name_h = out_name.replace(tag, target_loc)
                    dz = (h - tag_h) * hotel_dist
                    out[name_h] = out_list.adjust_tagged(tag, dname={tag: target_loc}, dz=dz)

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

    def has_raw(self) -> bool:
        return any(isinstance(m, RawCode) for m in self)

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

    def make_ur_script(self, with_gripper: bool, name: str='script') -> URScript:
        name = URScript.normalize_name(name)
        body = '\n'.join(
            ("# " + getattr(m, 'name') + '\n' if hasattr(m, 'name') else '')
            + m.to_ur_script()
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
        if a.has_raw() or b.has_raw():
            continue
        if a.has_gripper() or b.has_gripper():
            continue
        if a_first and a_first == b_last and pair_ok(xs[i], xs[j]):
            rm |= {i, j}
        else:
            continue
            # print(f'cannot sleek {xs[i][0].program_name!r} {xs[j][0].program_name!r} {a_first=} {b_last=}')

    return [
        x
        for i, x in enumerate(xs)
        if i not in rm
    ]

def raw(s: str) -> MoveList:
    return MoveList([RawCode(s)])

static: dict[str, MoveList] = {
    'noop': MoveList(),
    'pf test comm': raw('version'),
    'pf freedrive': raw('Freedrive'),
    'pf stop freedrive': raw('StopFreedrive'),
    'pf init': raw('''
        hp 1 60
        attach 1
        home
    '''),
    'pf open gripper': raw('MoveGripper 1 100'),
    'ur open gripper': raw('GripperMove(88)'),
    'ur freedrive': raw('freedrive_mode() sleep(3600)'),
    'ur gripper init and check': raw('GripperInitAndCheck()'),
}

sleeking_not_allowed = set(static.keys())

def guess_robot(name: str) -> Literal['ur', 'pf', 'ur or pf']:
    if name == 'noop':
        return 'ur or pf'
    for x in 'pf squid fridge nikon H'.split():
        if x in name:
            return 'pf'
    for x in 'updown ur A B C wash disp blue incu lid wave calib'.split():
        if x in name:
            return 'ur'

    raise ValueError(f'Cannot guess robot for: {name}')

@dataclass(frozen=True)
class NamedMoveList:
    base: str
    kind: Literal[
        'full',
        'prep',
        'transfer',
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
    expanded = {
        k: v
        for k, v in expanded.items()
        if 'Base' not in k
    }
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
        if guess_robot(base) == 'pf':
            out += [NamedMoveList(base, 'full', v)]
            continue
        out += [NamedMoveList(base, 'full', v)]
        parts = v.split(base)
        prep = NamedMoveList(base, 'prep', parts.prep)
        ret = NamedMoveList(base, 'return', parts.ret)
        transfer = NamedMoveList(base, 'transfer', parts.transfer)
        out += [
            prep,
            ret,
            transfer,
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

    for k, v in static.items():
        out += [
            NamedMoveList(k, 'full', v),
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
                assert k in world.data, f'{k=} is not in {world.data=} already when applying {self}'
                next.pop(k)
            else:
                assert k not in world.data, f'{k=} is in {world.data=} already when applying {self}'
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

@dataclass(frozen=True)
class DLid(Effect):
    plate_loc: str
    dlid_loc: str
    def effect(self, world: World) -> dict[str, str | None]:
        if self.dlid_loc in world.data:
            assert world[self.dlid_loc] == 'lid ' + world[self.plate_loc]
            return {self.dlid_loc: None}
        else:
            return {self.dlid_loc: 'lid ' + world[self.plate_loc]}

pbutils.serializer.register(globals())

movelists: dict[str, MoveList]
movelists = read_movelists()

B21 = 'B21'
B16 = 'B16'
effects: dict[str, Effect] = {}

for k, v in movelists.items():
    m = re.match(r'(\w+)-to-(\w+)$', k)
    if m:
        source, target = m.groups()
        effects[k] = MovePlate(source=source, target=target)

effects['dlid B14'] = DLid(plate_loc='B14', dlid_loc='D2')
effects['dlid B12'] = DLid(plate_loc='B12', dlid_loc='D1')

for i in HotelLocs_A:
    for b in HotelLocs_Base:
        lid_Bi = f'lid-B{i}'
        effects[f'lid-B{i} off [base B{b}]'] = TakeLidOff(source=f'B{b}', target=f'B{i}')
        effects[f'lid-B{i} on [base B{b}]'] = PutLidOn(source=f'B{i}', target=f'B{b}')

for k in list(effects.keys()):
    effects[k + ' transfer'] = effects[k]

for i in HotelLocs_A:
    Ai = f'A{i}'
    effects[f'{Ai}-to-incu transfer from drop neu'] = MovePlate(source=Ai, target='incu')

