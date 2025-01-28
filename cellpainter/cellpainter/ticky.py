'''

The tick-based scheduler

Plates are treated at a fixed tick (for simplicity) and robot moves are
scheduled freely around the liquid handler machines.

'''

from __future__ import annotations
from typing import *
from dataclasses import *

from pprint import pp

from .constraints import import_z3

import_z3()

import z3
import abc
import contextlib
import time

import itertools

@dataclass
class Color:
    enabled: bool = True

    def do(self, code: str, s: str) -> str:
        if self.enabled:
            reset: str = '\033[0m'
            return code + s + reset
        else:
            return s

    def none       (self, s: str) -> str: return self.do('', '') + s
    def black      (self, s: str) -> str: return self.do('\033[30m', s)
    def red        (self, s: str) -> str: return self.do('\033[31m', s)
    def green      (self, s: str) -> str: return self.do('\033[32m', s)
    def orange     (self, s: str) -> str: return self.do('\033[33m', s)
    def blue       (self, s: str) -> str: return self.do('\033[34m', s)
    def purple     (self, s: str) -> str: return self.do('\033[35m', s)
    def cyan       (self, s: str) -> str: return self.do('\033[36m', s)
    def lightgrey  (self, s: str) -> str: return self.do('\033[37m', s)
    def darkgrey   (self, s: str) -> str: return self.do('\033[90m', s)
    def lightred   (self, s: str) -> str: return self.do('\033[91m', s)
    def lightgreen (self, s: str) -> str: return self.do('\033[92m', s)
    def yellow     (self, s: str) -> str: return self.do('\033[93m', s)
    def lightblue  (self, s: str) -> str: return self.do('\033[94m', s)
    def pink       (self, s: str) -> str: return self.do('\033[95m', s)
    def lightcyan  (self, s: str) -> str: return self.do('\033[96m', s)

A = TypeVar('A')
B = TypeVar('B')

def groupby(xs: list[A], key: Callable[[A], Any]) -> itertools.groupby[Any, A]:
    return itertools.groupby(sorted(xs, key=key), key=key)

@dataclass(frozen=True)
class Timeit:
    times: dict[str, list[float]] = field(default_factory=lambda: DefaultDict(list))

    def __call__(self, desc: str = ''):
        @contextlib.contextmanager
        def worker():
            print(f'{desc}: starting...')
            t0 = time.monotonic()
            yield
            T = time.monotonic() - t0
            print(f'{desc}: done, {round(T, 3)}s')
            self.times[desc] += [T]

        return worker()

    def describe(self, ndigits: int=3):
        for desc, ts in self.times.items():
            print(f'{desc}:', *[f'{round(t, ndigits)}s' for t in ts])

    def flatten(self):
        out: dict[str, float] = {}
        for desc, ts in self.times.items():
            if len(ts) == 1:
                out[desc] = ts[0]
            else:
                for i, t in enumerate(ts):
                    out[f'{desc}[{i}]'] = t
        return out

@dataclass(frozen=True)
class Cmd(abc.ABC):
    def synthetic(self) -> bool:
        return False

@dataclass(frozen=True)
class Tick(Cmd):
    offset: str | None = None
    def synthetic(self):
        return True

@dataclass(frozen=True)
class Glue(Cmd):
    def synthetic(self):
        return True

@dataclass(frozen=True)
class Idle(Cmd):
    def synthetic(self):
        return True

@dataclass(frozen=True)
class Checkpoint(Cmd):
    name: str
    def synthetic(self):
        return True

@dataclass(frozen=True)
class WaitForCheckpoint(Cmd):
    name: str
    def synthetic(self):
        return True

@dataclass(frozen=True)
class Noop(Cmd):
    def synthetic(self):
        return True

@dataclass(frozen=True)
class Disp(Cmd):
    protocol: str

@dataclass(frozen=True)
class Wash(Cmd):
    protocol: str

@dataclass(frozen=True)
class Incu(Cmd):
    direction: Literal['put', 'get']

@dataclass(frozen=True)
class Shake(Cmd):
    protocol: str

Part: TypeAlias = Literal[
    'prep',
    'xfer',
    'post',
    'pick',
    'xfer-without-pick',
    'xfer-without-drop',
    'drop',
    'full-xfer',
]

Parts: TypeAlias = Part | Literal['prep-xfer-post', 'prep-pick-xfer-post', 'prep-xfer-drop-post']

def expand_parts(parts: Parts) -> list[Part]:
    match parts:
        case 'prep-xfer-post':
            return ['prep', 'xfer', 'post']
        case 'prep-pick-xfer-post':
            return ['prep', 'pick', 'xfer-without-pick', 'post']
        case 'prep-xfer-drop-post':
            return ['prep', 'xfer-without-drop', 'drop', 'post']
        case _:
            return [parts]

@dataclass(frozen=True)
class Arm(Cmd):
    src: str
    dest: str
    part: Part
    def __str__(self):
        return f'Arm({self.src} → {self.dest} [{self.part}])'
        # return f'Arm({self.src}_{self.dest}_{self.part})'
        # return f'Arm({self.part})'

def Arms(src: str, dest: str, parts: Parts='prep-xfer-post') -> list[Arm]:
    return [Arm(src=src, dest=dest, part=part) for part in expand_parts(parts)]

@dataclass(frozen=True)
class Lid(Cmd):
    delid_pos: int
    direction: Literal['remove', 'take']

@dataclass(frozen=False)
class MakeArm:
    pos: str

    def __call__(self, dest: str, parts: Parts='prep-xfer-post') -> list[Arm]:
        src = self.pos
        self.pos = dest
        return Arms(src=src, dest=dest, parts=parts)

@dataclass(frozen=True)
class MinimizeStart(Cmd):
    name: str
    def synthetic(self):
        return True

@dataclass(frozen=True)
class MinimizeEnd(Cmd):
    name: str
    def synthetic(self):
        return True

def simple_est(cmd: Cmd) -> float:
    match cmd:
        case Disp():
            return 12
        case Incu():
            return 6
        case Arm():
            return 2 if 'xfer' in cmd.part else 1
        case Wash():
            return 15
        case Shake():
            return 12
        case Idle():
            return 0
        case _:
            if cmd.synthetic():
                return 0
            else:
                raise ValueError(f'No simple estimate for {cmd}')

@dataclass(frozen=False)
class CmdCtx:
    plate: int
    seq: int
    cmd: Cmd
    pos: str | None
    duration_override: float | z3.ExprRef | None = None

    @property
    def p0(self):
        match self.pos, self.cmd:
            case None | 'incu', Incu():
                return 'incu'
            case None, Arm():
                return self.cmd.src
            case _, Arm() | Incu():
                raise ValueError(f'Cannot have arm {self.cmd} and {self.pos=}')
            case _:
                return self.pos

    @property
    def p1(self):
        match self.pos, self.cmd:
            case None | 'incu', Incu():
                return 'incu'
            case None, Arm() if self.cmd.part != 'prep':
                return self.cmd.dest
            case _, Arm(part='prep'):
                return self.pos
            case _, Arm() | Incu():
                raise ValueError(f'Cannot have arm {self.cmd} and {self.pos=}')
            case _:
                return self.pos

    @property
    def name(self):
        # return f'`plate {self.plate} seq {self.seq} {self.cmd}`'
        return f'{self.plate}.{self.seq}.{self.cmd}'

    @property
    def order(self):
        return self.seq, self.plate

    @property
    def t0(self):
        return z3.Real(self.name)

    @property
    def t1(self):
        return z3.Real(self.name) + self.duration()

    def duration(self):
        if self.duration_override is None:
            return simple_est(self.cmd)
        else:
            return self.duration_override

    @staticmethod
    def from_list(plate: int, cmds: list[Cmd]) -> list[CmdCtx]:
        out: list[CmdCtx] = []
        for i, cmd in enumerate(cmds):
            if i == 0 or isinstance(cmd, Arm):
                out += [CmdCtx(plate, i, cmd, None)]
            else:
                out += [CmdCtx(plate, i, cmd, out[-1].p1)]
        return out

def pairs(xs: list[A]):
    return zip(xs, xs[1:])

def solve(steps: list[CmdCtx], given_tick_length: float | None = None, interleave_threshold: int = 1000):
    timeit = Timeit()
    offsets: dict[str, z3.ExprRef] = {}
    num_plates = len(list(groupby(steps, key=lambda s: s.plate)))

    by_plate = [
        [b for b in sorted(list(bs), key=lambda s: s.seq)]
        for _, bs in groupby(steps, key=lambda s: s.plate)
    ]

    deps: dict[str, set[str]] = {}

    for bs in by_plate:
        my_active: set[str] = set()
        my_deps: set[str] = set()
        for b in bs:
            cmd = b.cmd
            if isinstance(cmd, Checkpoint):
                deps[cmd.name] = set(my_deps) # | set(my_active)
                my_active.add(cmd.name)
            if isinstance(cmd, WaitForCheckpoint):
                my_deps.add(cmd.name)

    pp(deps)
    done = False
    while not done:
        done = True
        for name, ds in list(deps.items()):
            len0 = len(ds)
            for dep in list(ds):
                deps[name] |= deps[dep]
            if len0 != len(ds):
                done = False
    pp(deps)

    def sep(xs):
        return ','.join(x.replace(' ', '_') for x in xs)

    for bs in by_plate:
        my_active: set[str] = set()
        my_deps: set[str] = set()
        for b in bs:
            cmd = b.cmd
            if isinstance(cmd, Checkpoint):
                my_active.add(cmd.name)
            if isinstance(cmd, WaitForCheckpoint):
                my_deps.add(cmd.name)
            # for act in list(my_active):
            #     my_active |= deps.get(act, set())
            for dep in list(my_deps):
                my_deps |= deps.get(dep, set())
            print(b.plate, 'active=' +  sep(my_active), 'deps=' +  sep(my_deps), b.cmd)



    with timeit('cs'):
        cs: list[z3.BoolRef | bool] = []

        tick_length = z3.Real('tick_length')

        for bs in by_plate:
            '''
            Sleek movements: back and forth to neutral position is removed when the same position is involved.
            '''
            for b in bs:
                if isinstance(b.cmd, Idle):
                    idle = b.duration_override = z3.Real(b.name + '.idle')
                    cs += [idle >= 0]

            bs = [b for b in bs if isinstance(b.cmd, Arm)]

            for b, next in zip(bs, bs[1:]):
                b_arm = cast(Arm, b.cmd)
                next_arm = cast(Arm, next.cmd)

                if b_arm.dest == next_arm.src and b_arm.part == 'post' and next_arm.part == 'prep':
                    '''
                    This has to come early in the function since it mutates the CmdCtx
                    '''
                    post = b.duration_override = z3.Real(b.name + '.post')
                    prep = next.duration_override = z3.Real(b.name + '.prep')
                    cs += [
                        post >= 0,
                        prep >= 0,
                    ]

                    post_time = simple_est(b.cmd)
                    prep_time = simple_est(next.cmd)

                    cs += [
                        z3.Or(
                            (next.t0 == b.t1) & (prep == 0) & (post == 0),
                            (next.t0 >= b.t1) & (prep == prep_time) & (post == post_time),
                        )
                    ]

            for b, next in zip(bs, bs[1:]):
                b_arm = cast(Arm, b.cmd)
                next_arm = cast(Arm, next.cmd)
                if b_arm.src == next_arm.src and b_arm.dest == next_arm.dest:
                    cs += [b.t1 == next.t0]
                else:
                    cs += [b.t1 <= next.t0]

        for bs in by_plate:
            '''
            Synthetic instructions

            Glue them to the next, or if last, the previous
            '''
            bs = [
                b for b in bs
                if not isinstance(b.cmd, Arm) or b.cmd.part not in ['prep', 'post']
            ]

            for i, b in enumerate(bs):
                if b.cmd.synthetic():
                    if i+1 < len(bs):
                        cs += [b.t1 == bs[i+1].t0]
                    elif i > 0:
                        cs += [b.t0 == bs[i-1].t1]
                if isinstance(b.cmd, Glue):
                    if i > 0:
                        cs += [b.t0 == bs[i-1].t1]

        for a in steps:
            '''
            Ticks are at a multiple time a constant.
            But if two different kinds of ticks are happening, one of them may have an offset.
            '''
            match a.cmd:
                case Tick():
                    if isinstance(name := a.cmd.offset, str):
                        offset: z3.ExprRef = z3.Real(name)
                        cs += [offset >= -tick_length]
                        cs += [offset <= tick_length]
                        offsets[name] = offset
                    else:
                        offset: float = 0
                    cs += [a.t0 == tick_length * (a.plate - 1) + offset]
                    if a.plate == 0:
                        cs += [a.t0 == offset]
                case _:
                    pass

        checkpoints: dict[str, CmdCtx] = {}
        for s in steps:
            if isinstance(s.cmd, Checkpoint):
                if s.cmd.name in checkpoints:
                    raise ValueError(f'Duplicate checkpoint {s.cmd.name}: {checkpoints[s.name]} and {s}')
                checkpoints[s.cmd.name] = s

        for s in steps:
            if isinstance(s.cmd, WaitForCheckpoint):
                if s.cmd.name not in checkpoints:
                    raise ValueError(f'Missing checkpoint {s.cmd.name}: {s}')
                cs += [
                    s.t1 >= checkpoints[s.cmd.name].t0
                ]

        runs: list[tuple[int, str, z3.ArithRef | float, z3.ArithRef | float]] = []

        for bs in by_plate:
            '''
            Arm xfer + Machine instructions
            * actual position of plate
            '''
            bs = [
                b for b in bs
                if not b.cmd.synthetic()
                if not isinstance(b.cmd, Arm) or b.cmd.part not in ['prep', 'post']
            ]

            if not bs:
                continue

            for b, next in zip(bs, bs[1:]):
                '''
                * chronological per plate
                '''
                cs += [b.t1 <= next.t0]

            b0 = bs[0]
            if isinstance(b0.cmd, Arm):
                pos = b0.cmd.src
            elif isinstance(b0.cmd, Incu):
                pos = 'incu'
            else:
                raise ValueError(f'Cannot start with {b0.cmd}')

            locs: list[tuple[str, z3.ArithRef | float]] = []

            for b in bs:
                if isinstance(b.cmd, Arm):
                    match b.cmd.part:
                        case 'xfer':
                            ps = [b.cmd.src, b.cmd.dest]
                        case 'full-xfer':
                            ps = [b.cmd.src, b.cmd.dest]
                        case 'pick':
                            ps = [b.cmd.src]
                        case 'xfer-without-pick':
                            ps = [b.cmd.dest]
                        case 'drop':
                            ps = [b.cmd.dest]
                        case 'xfer-without-drop':
                            ps = [b.cmd.src]
                        case 'prep' | 'post':
                            raise ValueError('unreachable')
                elif isinstance(b.cmd, Incu):
                    if b.cmd.direction == 'put':
                        ps = ['incu']
                    elif b.cmd.direction == 'get':
                        ps = ['incu']
                    else:
                        raise ValueError('unreachable')
                else:
                    ps = [pos]

                pos = ps[-1]

                for p in ps:
                    locs += [(p, b.t0)]
                    locs += [(p, b.t1)]

            # print(' ', *locs, sep='\n  ')

            for g, g_locs in itertools.groupby(locs, key=lambda pt: pt[0]):
                g_locs = list(g_locs)
                # print(g, g_locs)
                u = [(b0.plate, g, g_locs[0][1], g_locs[-1][1])]
                runs += u

        # print(' ', *runs, sep='\n  ')

        runs_by_plate = [
            (plate, list(ptt))
            for plate, ptt in groupby(runs, key=lambda pltt: pltt[0])
        ]

        for plate_a, pltts_a in runs_by_plate:
            for plate_b, pltts_b in runs_by_plate:
                if plate_b <= plate_a:
                    continue
                if plate_b - plate_a >= interleave_threshold:
                    # print('too far away', plate_b, plate_a)
                    # print(pltts_b[0])
                    # print(pltts_a[-1])
                    # print()
                    cs += [pltts_b[0][2] > pltts_a[-1][3]]
                    continue
                for plate_a, loc_a, t0_a, t1_a in pltts_a:
                    for plate_b, loc_b, t0_b, t1_b in pltts_b:
                        if loc_a == loc_b:
                            cs += [
                                z3.Or(
                                    t1_a <= t0_b,
                                    t1_b <= t0_a,
                                )
                            ]

        full_arms: list[tuple[CmdCtx, z3.ArithRef, z3.ArithRef]] = []

        for _, g in itertools.groupby(
            [s for s in steps if isinstance(s.cmd, Arm)],
            key=lambda s: (s.plate, s.cmd.src, s.cmd.dest)
        ):
            head, *_ = *_, last = list(g)
            full_arms += [(head, head.t0, last.t1)]

        full_arms_by_plate = [
            (plate, list(ptt))
            for plate, ptt in groupby(full_arms, key=lambda ptt: ptt[0].plate)
        ]

        for plate_a, ptts_a in full_arms_by_plate:
            for plate_b, ptts_b in full_arms_by_plate:
                if plate_b <= plate_a:
                    continue
                if plate_b - plate_a >= interleave_threshold:
                    # print('too far away', plate_b, plate_a)
                    # print(ptts_b[0])
                    # print(ptts_a[-1])
                    # print()
                    cs += [ptts_b[0][1] >= ptts_a[-1][2]]
                    continue
                for a, t0_a, t1_a in ptts_a:
                    for b, t0_b, t1_b in ptts_b:
                        '''
                        Arm can only do one thing at a time
                        '''
                        cs += [
                            z3.Or(
                                t1_a <= t0_b,
                                t1_b <= t0_a,
                            )
                        ]


        to_minimize = DefaultDict[str, list[z3.ExprRef | float]](list)

        for plate, bs in groupby(steps, key=lambda s: s.plate):
            bs = [b for b in bs if not isinstance(b.cmd, Tick)]
            bs = sorted(bs, key=lambda s: s.seq)
            t0s: dict[str, z3.Real] = {}
            for b in bs:
                if isinstance(b.cmd, MinimizeStart):
                    t0s[b.cmd.name] = b.t0
                if isinstance(b.cmd, MinimizeEnd):
                    to_minimize[b.cmd.name] += [b.t1 - t0s.pop(b.cmd.name)]

        if 0:
            begin = z3.Real('begin')
            end = z3.Real('end')

            for s in steps:
                cs += [begin <= s.t0]
                cs += [end >= s.t1]
            to_minimize['~ptp'] = [end - begin]

        # print(*cs, sep='\n')

        cs += [(tick_length >= 0)]
        if given_tick_length is not None:
            cs += [(tick_length == given_tick_length)]

        def make_s():
            s = z3.Optimize()
            s.set(priority='lex')
            for c in cs:
                s.add(c)

            minis: list[z3.ArithRef] = []
            minis += [tick_length]

            for k, v in sorted(to_minimize.items()):
                max_v = z3.Real(f'max({k})')
                for vv in v:
                    s.add(max_v >= vv)
                minis += [max_v]
            for k, v in sorted(to_minimize.items()):
                avg_v = z3.Real(f'avg({k})')
                s.add(avg_v == z3.Sum(v) / num_plates)
                minis += [avg_v]
                # minis += [(max_v + avg_v) / 2]

            # s.minimize(end - begin)
            return minis, s

    def m_eval(m, t) -> float:
        if isinstance(t, float | int):
            return float(t)
        else:
            x = m.eval(t)
            if isinstance(x, z3.IntNumRef):
                return x.as_long()
            else:
                return float(m.eval(t).as_decimal(1).strip('?'))

    minis, s = make_s()

    with timeit('check'):
        s.check()

    with timeit(f'opt'):
        minis, s = make_s()
        for m_other in minis:
            s.minimize(m_other)
        check = s.check()

        if str(check) == 'sat':
            for m in minis:
                print(m, m_eval(s.model(), m))
        else:
            suc = z3.Solver()
            suc.set('smt.core.minimize', 'true')
            added = set()
            for c in cs:
                if str(c) not in added:
                    added.add(str(c))
                    suc.assert_and_track(c, str(c))
            print('=== unsat core ===', suc.check())
            print(suc.unsat_core())
            raise ValueError('unsat')

    m = s.model()

    # with timeit('eval'):
    if 1:

        times: list[tuple[float, float, CmdCtx]] = []

        for s in steps:
            # if not isinstance(s.cmd, Arm):
                t0 = m_eval(m, s.t0)
                t1 = m_eval(m, s.t1)
                times += [(t0, t1, s)]

        if 0:
            for s, t0, t1 in full_arms:
                t0 = m_eval(m, t0)
                t1 = m_eval(m, t1)
                s.cmd = replace(s.cmd, part='full-xfer')
                times += [(t0, t1, s)]

        times = sorted(times, key=lambda abc: abc[0])

        ends = {
            (s.plate, s.cmd.name): t1
            for _, t1, s in times
            if isinstance(s.cmd, MinimizeEnd)
        }
        # print(ends)
        times = [
            (
                t0,
                ends[s.plate, s.cmd.name]
                if isinstance(s.cmd, MinimizeStart)
                else t1,
                s,
            )
            for t0, t1, s in times
            if not isinstance(s.cmd, MinimizeEnd)
        ]

        if times:
          for show_arm in [True, False]:
            last_t1 = times[0][1]

            all_t0 = min([t0 for t0, _, _ in times])
            all_t1 = max([t1 for _, t1, _ in times])
            width = all_t1 - all_t0

            times = [(t0 - all_t0, t1 - all_t0, s) for t0, t1, s in times]

            def sub(s: int | str) -> str:
                tr = {
                    '0': '₀',
                    '1': '₁',
                    '2': '₂',
                    '3': '₃',
                    '4': '₄',
                    '5': '₅',
                    '6': '₆',
                    '7': '₇',
                    '8': '₈',
                    '9': '₉',
                }
                return str(s).translate(str.maketrans(tr))

            def trunc(t: float):
                import math
                return math.ceil(t / 1)

            color = Color()

            for t0, t1, s in times:
                if isinstance(s.cmd, Noop):
                    continue
                if isinstance(s.cmd, (Arm, Glue, Tick)) and not show_arm:
                    continue
                    pass
                c: Callable[[str], str] = lambda x: x
                if isinstance(s.cmd, Disp):
                    c = color.purple
                if isinstance(s.cmd, Incu):
                    c = color.green
                if isinstance(s.cmd, Wash):
                    c = color.blue
                if trunc(t1 - t0) > 0:
                    # pre  = trunc(m_eval(m, s.pre_duration))
                    # post = trunc(m_eval(m, s.post_duration))
                    pre = 0
                    post = 0
                    mid = '═'
                    if isinstance(s.cmd, MinimizeStart):
                        mid = '─'
                    txt = ' ' * trunc(t0) + sub(s.plate) + c('─' * trunc(pre) + mid * trunc(t1 - t0 - pre - post) + '─' * trunc(post))
                else:
                    if isinstance(s.cmd, Arm):
                        continue
                    txt = ' ' * trunc(t0) + sub(s.plate) + c('⎸')
                print(' ', txt, str(s.cmd).replace('MinimizeStart', 'Minimize'))

            for t0, t1, s in times:
                break

                if isinstance(s.cmd, Arm):

                    if last_t1 != t0:
                        print(f'{last_t1:> 8.1f}  {"  " * s.plate}  Idle(secs={t0 - last_t1})')
                    last_t1 = t1

                # print(f'{t0:> 6.0f} {t1:> 6.0f}  {s.name}')
                pre  = m_eval(m, s.pre_duration)
                post = m_eval(m, s.post_duration)
                if pre > 0: print(f'{t0:> 8.1f}  {"  " * s.plate}  Prep{s.cmd}')
                print(f'{t0 + pre:> 8.1f}  {"  " * s.plate}  {s.cmd}')
                if post > 0: print(f'{t1 - post:> 8.1f}  {"  " * s.plate}  Post{s.cmd}')

    # with timeit(f'eval'):
    if 1:
        d: dict[str, float] = {
            'tick_length': m_eval(m, tick_length)
        }
        for k, v in offsets.items():
            d[k] = m_eval(m, v)
        for mini in minis:
            d[str(mini)] = m_eval(m, mini)
        for k, v in sorted(to_minimize.items()):
            # d[k] = m_eval(m, z3.Sum(v)) / len(v)
            d[k] = [m_eval(m, vv) for vv in v]

        if 0:
            cps: dict[str, float] = {
                name: m_eval(m, s.t0)
                for name, s in checkpoints.items()
            }
            pp(cps)

    return timeit, d

def mito(rt_pos: int, delid_pos: int) -> list[Cmd]:
    rt = f'rt_{rt_pos}'
    delid = f'delid_{delid_pos}'
    arm = MakeArm('incu')
    return [
        MinimizeStart('2.RT'),
        Incu('get'),
        # *arm(rt),
        *arm(delid),
        MinimizeStart('3.lid off'),
        *arm(delid + '_no_lid'),
        # Lid(delid_pos, 'remove'),
        # arm(f'wash'),
        # MinimizeStart('1.wash squeeze'),
        # Wash('1X'),
        *arm('disp'),
        Tick(),
        Disp('mito'),
        # MinimizeEnd('1.wash squeeze'),
        *arm(delid + '_no_lid'),
        MinimizeEnd('3.lid off'),
        *arm(delid),
        # Lid(delid_pos, 'take'),
        # arm(rt),
        *arm('incu'),
        Incu('put'),
        MinimizeEnd('2.RT'),
    ]

def stains(rt_pos: int, delid_pos: int) -> list[Cmd]:
    rt = f'rt_{rt_pos}'
    delid = f'delid_{delid_pos}'
    arm = MakeArm(rt)
    return [
        *arm(delid),
        MinimizeStart('3.lid off'),
        *arm(delid + '_no_lid'),
        # Lid(delid_pos, 'remove'),
        *arm(f'wash'),
        MinimizeStart('1.wash squeeze'),
        Tick('stains'),
        Wash('1X'),
        # arm('jet'),
        *arm('disp'),
        Disp('stains'),
        MinimizeEnd('1.wash squeeze'),
        *arm(delid + '_no_lid'),
        *arm(delid),
        MinimizeEnd('3.lid off'),
        # Lid(delid_pos, 'take'),
        *arm(rt),
    ]

def fix_pygments():
    import pygments.console as C

    copy = {**C.codes}

    # switch around some colors
    C.codes["yellow"]  = copy["green"]
    C.codes["blue"]    = copy["magenta"]
    C.codes["green"]   = copy["blue"]
    C.codes["magenta"] = copy["yellow"]

    # make dark color scheme and light color scheme be the same
    for d, l in zip(C.dark_colors, C.light_colors):
        C.codes[l] = C.codes[d]

@dataclass
class ResolvedCheckpoints:
    before: list[list[set[str]]]
    after: list[list[set[str]]]
    deadlocks: set[str]

    def raise_if_deadlocks(self):
        if self.deadlocks:
            raise ValueError(f'Deadlock in checkpoints {self.deadlocks}')

def resolve_checkpoints(program: list[list[Cmd]]) -> ResolvedCheckpoints:
    before: list[list[set[str]]] = []
    after: list[list[set[str]]] = []

    cp_pos: dict[str, tuple[int, int]] = {}
    wf_pos: list[tuple[str, int, int]] = []

    for p, plate in enumerate(program):
        for c, cmd in enumerate(plate):
            if isinstance(cmd, Checkpoint):
                if cmd.name in cp_pos:
                    raise ValueError(f'Duplicate checkpoint {cmd.name}')
                cp_pos[cmd.name] = (p, c)
            if isinstance(cmd, WaitForCheckpoint):
                wf_pos += [(cmd.name, p, c)]

    for name, p, c in wf_pos:
        if name not in cp_pos:
            raise ValueError(f'Missing checkpoint {name} ({(p, c) = })')

    for plate in program:
        a: list[set[str]] = []
        active = set[str]()
        for cmd in plate:
            if isinstance(cmd, Checkpoint):
                active.add(cmd.name)
            a += [set(active)]
        after += [a]

    done = False
    while not done:
        done = True
        for name, p_wf, c_wf in wf_pos:
            p_cp, c_cp = cp_pos[name]
            active_cp = after[p_cp][c_cp]
            active_wf = after[p_wf][c_wf]
            if any(a not in active_wf for a in active_cp):
                done = False
                for c in range(c_wf, len(after[p_wf])):
                    after[p_wf][c] |= active_cp

    deadlocks = {
        name
        for name, (p, c) in cp_pos.items()
        if c-1 >= 0
        if name in after[p][c-1]
    }

    for plate in program:
        b: list[set[str]] = []
        inactive = set[str]()
        for cmd in plate[::-1]:
            b += [set(inactive)]
            if isinstance(cmd, Checkpoint):
                inactive.add(cmd.name)
        b = b[::-1]
        before += [b]

    ilvs = enumerate_checkpoint_interleavings(program)
    times = [ilv.expand_times() for ilv in ilvs]
    print()
    for ilv in ilvs:
        print(ilv.order, *ilv.expand_times(), *ilv.pendings[-1], sep='\n    ')

    # A cmd i can not be after j
    # if for some u,
    #   u in before(i) and
    #   u in after(j)
    if not deadlocks:
        for pi, plate_i in enumerate(program):
            for pj, plate_j in enumerate(program):
                if pi == pj:
                    continue
                for ci, cmd_i in enumerate(plate_i):
                    for cj, cmd_j in enumerate(plate_j):
                        if isinstance(cmd_i, Checkpoint):
                            continue
                        if isinstance(cmd_j, Checkpoint):
                            continue
                        # can i be after j in the timestamps?
                        time_pairs = [
                            (time[pi][ci], time[pj][cj])
                            for time in times
                        ]
                        i_after_j_times = any(
                            time[pi][ci] > time[pj][cj]
                            for time in times
                        )
                        i_after_j_possible = all(
                            a not in after[pj][cj]
                            for a in before[pi][ci]
                        )
                        if 1: print(f'''
                            {(pi, ci, cmd_i)    = }
                            {(pj, cj, cmd_j)    = }
                            {after[pj][cj]      = }
                            {before[pi][ci]     = }
                            {i_after_j_times    = }
                            {i_after_j_possible = }
                        ''')
                        '''
                            {time_pairs         = }
                        '''
                        assert i_after_j_times == i_after_j_possible


    return ResolvedCheckpoints(
        before=before,
        after=after,
        deadlocks=deadlocks,
    )

Times: TypeAlias = dict[tuple[int, int], int]

@dataclass(frozen=True)
class InterleaveResult:
    order: list[str]
    pendings: list[set[str]]
    times: Times

    def expand_times(self):
        out: list[list[int]] = []
        for (p, c), t in self.times.items():
            while len(out) <= p:
                out += [[]]
            while len(out[p]) <= c:
                out[p] += [-1]
            out[p][c] = t
        return out

def enumerate_checkpoint_interleavings(program: list[list[Cmd]]) -> list[InterleaveResult]:
    def go(pcs: list[int]=[-1] * len(program), active: set[str]=set(), times: Times={}, t: int=0) -> list[InterleaveResult]:
        res: list[InterleaveResult] = []
        for P, _ in enumerate(program):
            my_pcs = list(pcs)
            candidates: set[str] = set()
            pending: set[str] = set()
            my_times = dict(times)
            my_active = set(active)
            for p, plate in enumerate(program):
                if p != P:
                    continue
                for c, cmd in list(enumerate(plate))[max(my_pcs[p], 0):][:2]:
                    stuck = False
                    if isinstance(cmd, WaitForCheckpoint):
                        if cmd.name in my_active:
                            pass
                        else:
                            pending.add(cmd.name)
                            stuck = True
                    elif isinstance(cmd, Checkpoint):
                        my_active.add(cmd.name)
                    if stuck:
                        my_pcs[p] = c - 1
                        break
                    else:
                        my_pcs[p] = c
                        if (p, c) not in my_times:
                            my_times[p, c] = t
            # print(t, P, my_pcs[P], pcs[P], active, candidates, my_times)
            if my_active > active or my_pcs[P] > pcs[P]:
                for cont in go(my_pcs, my_active, my_times, t+1):
                    # print(cont.times, my_times)
                    res += [
                        InterleaveResult(
                            order=list(my_active - active) + cont.order,
                            pendings=[pending] + cont.pendings,
                            times=cont.times,
                        )
                    ]
        if not res:
            return [InterleaveResult(order=[], pendings=[set()], times=times)]
        else:
            return res
    return go()

def test_checkpoints():
    fix_pygments()
    CP = Checkpoint
    WF = WaitForCheckpoint
    noop = Noop()
    a, b, c, d  = 'abcd'

    def e(*xss: list[set[str] | dict[Any, Any]]) -> list[list[set[str]]]:
        return [
            [set() if isinstance(x, dict) else x for x in xs]
            for xs in xss
        ]

    program: list[list[Cmd]] = [
        [noop, CP(a), noop, WF(b), noop],
        [noop, CP(b), noop, WF(a), noop],
    ]
    r = resolve_checkpoints(program)
    assert r.before == e(
        [{a}, {}, {}, {}, {}],
        [{b}, {}, {}, {}, {}],
    )
    assert r.after == e(
        [{}, {a}, {a}, {a, b}, {a, b}],
        [{}, {b}, {b}, {a, b}, {a, b}],
    )
    assert r.deadlocks == set()

    program: list[list[Cmd]] = [
        [noop, CP(a), noop, CP(b), noop],
        [noop, WF(b), noop],
    ]
    r = resolve_checkpoints(program)
    assert r.before == e(
        [{a, b}, {b}, {b}, {}, {}],
        [{}, {}, {}],
    )
    assert r.after == e(
        [{}, {a}, {a}, {a, b}, {a, b}],
        [{}, {a, b}, {a, b}],
    )
    assert r.deadlocks == set()

    program: list[list[Cmd]] = [
        [noop, CP(a), noop, CP(b), noop],
        [noop, WF(a), noop],
    ]
    r = resolve_checkpoints(program)
    assert r.before == e(
        [{a, b}, {b}, {b}, {}, {}],
        [{}, {}, {}],
    )
    assert r.after == e(
        [{}, {a}, {a}, {a, b}, {a, b}],
        [{}, {a}, {a}],
    )
    assert r.deadlocks == set()

    program: list[list[Cmd]] = [
        [noop, noop,  noop, CP(a), noop],
        [noop, WF(a), noop, CP(b), noop],
        [noop, WF(b), noop, noop,  noop],
    ]
    r = resolve_checkpoints(program)
    assert r.before == e(
        [{a}, {a}, {a}, {}, {}],
        [{b}, {b}, {b}, {}, {}],
        [{},  {},  {},  {}, {}],
    )
    assert r.after == e(
        [{}, {},     {},     {a},    {a}],
        [{}, {a},    {a},    {a, b}, {a, b}],
        [{}, {a, b}, {a, b}, {a, b}, {a, b}],
    )
    assert r.deadlocks == set()

    u, v, w = 'uvw'

    if 0:
        program: list[list[Cmd]] = [
            [noop, noop,  noop, CP(a), noop, CP(u), WF(u), WF(v), WF(w), noop],
            [noop, WF(a), noop, CP(b), noop, CP(v), WF(u), WF(v), WF(w), noop],
            [noop, WF(b), noop, noop,  noop, CP(w), WF(u), WF(v), WF(w), noop],
        ]
        r = resolve_checkpoints(program)
        assert r.before == e(
            [{a, u}, {a, u}, {a, u}, {u}, {u}, {}, {}, {}, {}, {}],
            [{b, v}, {b, v}, {b, v}, {v}, {v}, {}, {}, {}, {}, {}],
            [{w},    {w},    {w},    {w}, {w}, {}, {}, {}, {}, {}],
        )
        assert r.after == e(
            [{}, {},     {},     {a},    {a},    {a, u},    {a, u},       {a, b, u, v},    {a, b, u, v, w}, {a, b, u, v, w}],
            [{}, {a},    {a},    {a, b}, {a, b}, {a, b, v}, {a, b, u, v}, {a, b, u, v},    {a, b, u, v, w}, {a, b, u, v, w}],
            [{}, {a, b}, {a, b}, {a, b}, {a, b}, {a, b, w}, {a, b, u, w}, {a, b, u, v, w}, {a, b, u, v, w}, {a, b, u, v, w}],
        )
        assert r.deadlocks == set()

    r = resolve_checkpoints([[noop, CP(a), noop, WF(a), noop]])
    assert r.before ==     e([{a}, {},  {},  {},  {}])
    assert r.after ==      e([{},  {a}, {a}, {a}, {a}])
    assert r.deadlocks == set()

    r = resolve_checkpoints([[noop, WF(a), noop, CP(a), noop]])
    assert r.before ==     e([{a}, {a}, {a}, {}, {}])
    assert r.after ==      e([{},  {a}, {a}, {a}, {a}])
    assert r.deadlocks == {a}

    r = resolve_checkpoints([[WF(a), CP(a)]])
    assert r.before ==     e([{a}, {}])
    assert r.after ==      e([{a}, {a}])
    assert r.deadlocks == {a}

    program: list[list[Cmd]] = [
        [noop, WF(a), noop, CP(b), noop],
        [noop, WF(b), noop, CP(a), noop],
    ]
    r = resolve_checkpoints(program)
    assert r.before == e(
        [{b}, {b}, {b}, {}, {}],
        [{a}, {a}, {a}, {}, {}],
    )
    assert r.after == e(
        [{}, {a, b}, {a, b}, {a, b}, {a, b}],
        [{}, {a, b}, {a, b}, {a, b}, {a, b}],
    )
    assert r.deadlocks == {a, b}
    import pytest
    with pytest.raises(ValueError):
        r.raise_if_deadlocks()

    program: list[list[Cmd]] = [
        [WF(a), CP(b)],
        [WF(b), CP(a)],
    ]
    r = resolve_checkpoints(program)
    assert r.before == e(
        [{b}, {}],
        [{a}, {}],
    )
    assert r.after == e(
        [{a, b}, {a, b}],
        [{a, b}, {a, b}],
    )
    assert r.deadlocks == {a, b}

if __name__ == '__main__':
    import tabulate

    times: list[dict[str, float]] = []

    programs = [
        [
            [
                Tick(),
                *Arms('hotel', 'disp'),
                Disp('stains'),
                *Arms('disp', 'hotel'),
            ],
        ],
        [
            [
                Tick(),
                Incu('get'),
                # *Arms('incu', 'hotel', parts='prep-pick-xfer-post'),
                # *Arms('hotel', 'incu', parts='prep-xfer-drop-post'),
                *Arms('incu', 'hotel'),
                *Arms('hotel', 'incu'),
                Incu('put'),
            ],
        ],
    ]
    programs = [
        [
            [
                # MinimizeStart('RT'),
                WaitForCheckpoint(f'done {plate_num-2}') if plate_num-2 > 0 else Noop(),
                WaitForCheckpoint(f'in RT {plate_num-1}') if plate_num-1 > 0 else Noop(),
                Incu('get'),
                *Arms('incu', f'hotel{i}', parts='prep-pick-xfer-post'),
                Checkpoint(f'in RT {plate_num}'),
                # *Arms('incu', f'hotel{i}'),
                *Arms(f'hotel{i}', 'wash'),
                Tick(),
                MinimizeStart('squeeze'),
                Wash('1X'),
                # Glue(),
                *Arms(f'wash', 'disp'),
                # Glue(),
                Disp('pfa'),
                MinimizeEnd('squeeze'),
                *Arms('disp', f'hotel{i}'),
                Checkpoint(f'done {plate_num}'),
                # *Arms(f'hotel{i}', 'incu', parts='prep-xfer-drop-post'),
                # *Arms(f'hotel{i}', 'incu'),
                # Incu('put'),
                # MinimizeEnd('RT'),
            ]
            for plate_num, i in enumerate([1, 2] * k, start=1)
        ]
        for k in range(1, 9)
    ]
    programs = []
    programs += [
        [
            [
                WaitForCheckpoint(f'done {plate_num-2}') if plate_num-2 > 0 else Noop(),
                WaitForCheckpoint(f'in RT {plate_num-1}') if plate_num-1 > 0 else Noop(),
                MinimizeStart('3.RT'),
                Incu('get'),
                *Arms('incu', f'hotel{i}', parts='prep-pick-xfer-post'),
                Checkpoint(f'in RT {plate_num}'),
                MinimizeStart('2.without lid'),
                Glue(),
                *Arms(f'hotel{i}', f'hotel{i}_no_lid'),
                *Arms(f'hotel{i}', 'wash'),
                Tick(),
                MinimizeStart('1.wash'),
                Wash('1X'),
                Glue(),
                *Arms(f'wash', 'disp'),
                Glue(),
                Disp('mito'),
                MinimizeEnd('1.wash'),
                *Arms('disp', f'hotel{i}_no_lid'),
                Glue(),
                *Arms(f'hotel{i}_no_lid', f'hotel{i}'),
                MinimizeEnd('2.without lid'),
                *Arms(f'hotel{i}', f'incu{plate_num}', parts='prep-xfer-drop-post'),
                MinimizeEnd('3.RT'),
                # Incu('put'),
                Checkpoint(f'done {plate_num}'),


                Checkpoint(f'mito {plate_num}'),
                Idle(),
                *[WaitForCheckpoint(f'mito {x}') for x, _ in enumerate([1, 2] * k, start=1)],

                # WaitForCheckpoint(f'mito {2 * k}'),
                # Incu('get'),
                *Arms(f'incu{plate_num}', f'hotel{i}', parts='prep-pick-xfer-post'),
                *Arms(f'hotel{i}', f'RT{plate_num}'),
            ]
            for plate_num, i in enumerate([1, 2] * k, start=1)
        ]
        # for k in range(1, 10)
        for k in range(1, 10)
    ]
    skip = [
        [
            [
                MinimizeStart('RT'),
                Incu('get'),
                *Arms('incu', f'hotel{i}'),
                *Arms(f'hotel{i}', 'disp'),
                Tick(),
                Disp('stains'),
                *Arms('disp', f'hotel{i}'),
                *Arms(f'hotel{i}', 'incu'),
                Incu('put'),
                MinimizeEnd('RT'),
            ]
            for i in [1, 2, 3, 1, 2, 3]
        ],
        [
            [
                *Arms(f'hotel{i}', 'incu', parts='prep-xfer-drop-post'),
                Tick(f'plate{i}' if i > 1 else None),
                Incu('put'),
            ]
            for i in [1, 2, 3]
        ],
        [
            [
                Incu('get'),
                Tick(f'plate{i}' if i > 1 else None),
                *Arms('incu', f'hotel{i}', parts='prep-pick-xfer-post'),
            ]
            for i in [1, 2, 3]
        ],
        [
            [
                MinimizeStart('RT'),
                Incu('get'),
                *Arms('incu', f'hotel{i}'),
                *Arms(f'hotel{i}', 'disp'),
                Tick(),
                Disp('stains'),
                *Arms('disp', f'hotel{i}'),
                *Arms(f'hotel{i}', 'incu'),
                Incu('put'),
                MinimizeEnd('RT'),
            ]
            for i in [1, 2]
        ],
    ]# [2:][:1]

    for plates in programs:
        # for g in [29.9, 30, 31]:
        for g in [None]:
        # for g in [30]:
          # for interleave_threshold in [1, 2, 3, 1000]:
          # for interleave_threshold in [1, 2, 3, 100]:
          for interleave_threshold in [100]:
          # for interleave_threshold in [3, 4]:
            timeit, d = solve(
                [
                    cmd
                    for i, plate in enumerate(plates)
                    for cmd in CmdCtx.from_list(i + 1, plate)
                ],
                # given_tick_length=24,
                given_tick_length=g if interleave_threshold > 1 else None,
                interleave_threshold=interleave_threshold,
            )
            times += [{'N': len(plates), 'thr': interleave_threshold, **timeit.flatten(), **d}]
            tbl = tabulate.tabulate(times, headers='keys', tablefmt='simple_outline', floatfmt='.1f')
            tbl = '\n'.join([s[:180] for s in tbl.splitlines()])
            print(tbl)
            # quit()

    quit()

    for N in [4]:
        steps: list[CmdCtx] = []
        for i in range(N):
            steps += CmdCtx.from_list(i + 1, mito(21 - i, i % 2 + 1))
            # if i % 2 == 0:
            # else:
            #     steps += CmdCtx.from_list(i + 1, stains(21 - i, i % 2 + 3))

        timeit, d = solve(steps, given_tick_length=None)
        d = {k: ' '.join(map(str, xs)) if isinstance(xs, list) else xs for k, xs in d.items()}
        times += [{"N": N, **timeit.flatten(), **d}]

        print(
            tabulate.tabulate(times, headers='keys', tablefmt='simple_outline', floatfmt='.1f')
        )
