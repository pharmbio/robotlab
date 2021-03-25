from __future__ import annotations

from dataclasses import dataclass, field, replace
from utils import dotdict
from typing import Dict, Any, Tuple, Literal, NewType
import datetime

JobId = NewType('JobId', str)

@dataclass(frozen=True)
class UnresolvedTime:
    time: str
    id: JobId | None = None # first wait for this machine

@dataclass(frozen=True)
class Plate:
    id: str
    loc: str
    lid_loc: str = 'self'
    target_loc: None | str = None
    queue: list[ProtocolStep] = field(default_factory=list)
    waiting_for: None | JobId | datetime.datetime | UnresolvedTime = None
    meta: Any = None

p = Plate('p1', 'i42')
print(p)
q = replace(p, loc='incu')
print(q)

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [ i+1 for i in range(42) ]
Out = [18] # [ i+1 for i in range(18) ] # todo: measure out_hotel_dist

if 1:
    # small test version
    H = [21, 19, 17, 15, 13]
    I = [1, 2, 3]
    Out = [18]

h21 = 'h21'

incu_locs: list[str] = [ f'i{i}' for i in I ]
h_locs:    list[str] = [ f'h{i}' for i in H ]
r_locs:    list[str] = [ f'r{i}' for i in H ]
out_locs:  list[str] = [ f'out{i}' for i in Out ]
lid_locs:  list[str] = [ h for h in h_locs if h != h21 ]

locs: list[str] = 'wash disp incu'.split()
locs += incu_locs
locs += h_locs
locs += r_locs
locs += out_locs

@dataclass(frozen=True)
class World:
    plates: dict[str, Plate]


    def __getattr__(self, loc: str) -> str:
        for p in self.plates.values():
            if loc == p.loc:
                return p.id
            if loc == p.lid_loc:
                return f'lid({p.id})'
            if loc == p.target_loc:
                return f'target({p.id})'
        return 'free'

    # def __getitem__(self, loc: str) -> str:
    __getitem__ = __getattr__

    def success(self, p: Plate, cmds: list[run]=[]) -> Success:
        w = replace(self, plates={**self.plates, p.id: p})
        return Success(w=w, cmds=cmds)

@dataclass(frozen=True)
class run:
    device: str
    arg: Any | None = None
    id: JobId | None = None

@dataclass(frozen=True)
class Success:
    w: World
    cmds: list[run]

def world_locations(w: World) -> dict[str, str]:
    return {loc: w[loc] for loc in locs}

@dataclass
class UniqueSupply:
    count: int = 0
    def __call__(self, prefix: str='') -> str:
        self.count += 1
        return f'{prefix}({self.count})'

    def reset(self) -> None:
        self.count = 0

unique = UniqueSupply()

from abc import ABC, abstractmethod

class Step(ABC):
    @abstractmethod
    def step(self, p: Plate, w: World) -> Success | None:
        pass

class ProtocolStep(Step):
    pass

class RobotStep(Step):
    pass

@dataclass(frozen=True)
class incu_pop(ProtocolStep):
    target: str
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc in incu_locs and w[self.target] == 'free':
            id = JobId(unique('incu'))
            return w.success(
                replace(p, loc='incu', target_loc=self.target, waiting_for=id),
                [run('incu_get', p.loc, id=id)]
            )
        return None

@dataclass(frozen=True)
class incu_put(ProtocolStep):
    time: str
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == h21 and p.lid_loc == 'self':
            for incu_loc in incu_locs:
                if w[incu_loc] == 'free':
                    id = JobId(unique('incu'))
                    return w.success(
                        replace(p, loc=incu_loc, waiting_for=UnresolvedTime(time=self.time, id=id)),
                        [
                            run('robot', 'generated/incu_put'),
                            run('incu_put', incu_loc, id=id),
                        ]
                    )
        return None

@dataclass(frozen=True)
class wash(ProtocolStep):
    arg1: str | None = None
    arg2: str | None = None
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == h21 and p.lid_loc != 'self':
            id = JobId(unique('wash'))
            return w.success(
                replace(p, loc='wash', waiting_for=id),
                [
                    run('robot', 'generated/wash_put'),
                    run('wash', [self.arg1, self.arg2], id=id),
                ],
            )
        return None

@dataclass(frozen=True)
class disp(ProtocolStep):
    arg1: str | None = None
    arg2: str | None = None
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == h21 and p.lid_loc != 'self':
            id = JobId(unique('disp'))
            return w.success(
                replace(p, loc='disp', waiting_for=id),
                [
                    run('robot', 'wash_get'),
                    run('disp', [self.arg1, self.arg2], id=id)
                ],
            )
        return None

@dataclass(frozen=True)
class RT_incu(ProtocolStep):
    time: str
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == 'h21' and p.lid_loc == 'self':
            for r_loc in r_locs:
                if w[r_loc] == 'free':
                    return w.success(
                        replace(p, loc=r_loc, waiting_for=UnresolvedTime(self.time)),
                        [run('robot', 'generated/{r_loc}_put')]
                    )
        return None

@dataclass(frozen=True)
class to_output_hotel(ProtocolStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == 'h21' and p.lid_loc == 'self':
            for out_loc in out_locs:
                if w[out_loc] == 'free':
                    return w.success(
                        replace(p, loc=out_loc),
                        [run('robot', 'generated/{out_loc}_put')]
                    )
        return None

@dataclass
class disp_get(RobotStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == 'disp' and w.h21 == 'free':
            assert p.waiting_for is None
            return w.success(
                replace(p, loc=h21),
                [run('robot', 'generated/disp_get')]
            )
        return None

@dataclass
class wash_get(RobotStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == 'wash' and w.h21 == 'free':
            assert p.waiting_for is None
            return w.success(
                replace(p, loc=h21),
                [run('robot', 'generated/disp_get')]
            )
        return None

@dataclass
class incu_get(RobotStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == 'incu' and w.h21 == 'free':
            assert p.waiting_for is None
            return w.success(
                replace(p, loc=h21),
                [run('robot', 'generated/incu_get')]
            )
        return None

@dataclass
class RT_get(ProtocolStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc in r_locs and w.h21 == 'free':
            assert p.waiting_for is None
            return w.success(
                replace(p, loc=h21),
                [run('robot', 'generated/{r_loc}_get')]
            )
        return None


@dataclass
class h21_take(RobotStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc in h_locs and w[h21] == 'free':
            return w.success(
                replace(p, loc=h21),
                [run('robot', 'generated/{h_loc}_get')]
            )
        return None

@dataclass
class h21_release(RobotStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == h21:
            for h_loc in h_locs:
                if w[h_loc] == 'free':
                    return w.success(
                        replace(p, loc=h_loc),
                        [run('robot', 'generated/{h_loc}_put')]
                    )
        return None

@dataclass
class delid(RobotStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == h21 and p.lid_loc == 'self':
            for lid_loc in lid_locs:
                if w[lid_loc] == 'free':
                    return w.success(
                        replace(p, lid_loc=lid_loc),
                        [run('robot', 'generated/lid_{lid_loc}_put')],
                    )
        return None

@dataclass
class lid(RobotStep):
    def step(self, p: Plate, w: World) -> Success | None:
        if p.loc == h21 and p.lid_loc in lid_locs:
            return w.success(
                replace(p, lid_loc='self'),
                [run('robot', 'generated/lid_{p.lid_loc}_get')],
            )
        return None

# Cell Painting Workflow
protocol: list[ProtocolStep] = [
    # 2 Compound treatment: Remove (80%) media of all wells
    incu_pop(target='wash'),
    wash(),

    # 3 Mitotracker staining
    disp('peripump 1', 'mitotracker solution'),
    incu_put('30 min'),
    incu_pop(target='wash'),
    wash('pump D', 'PBS'),

    # 4 Fixation
    disp('Syringe A', '4% PFA'),
    RT_incu('20 min'),
    wash('pump D', 'PBS'),

    # 5 Permeabilization
    disp('Syringe B', '0.1% Triton X-100 in PBS'),
    RT_incu('20 min'),
    wash('pump D', 'PBS'),

    # 6 Post-fixation staining
    disp('peripump 2', 'staining mixture in PBS'),
    RT_incu('20 min'),
    wash('pump D', 'PBS'),

    # 7 Imaging
    to_output_hotel(),
]

from collections import deque

def bfs(w0, moves, max_fuel = 10**5):
    q = deque([(w0, [])])
    visited = set()
    fuel = max_fuel
    while q and fuel > 0:
        fuel -= 1
        w, cmds = q.popleft()
        if w in visited:
            continue
        visited.add(w)
        for p in w.plates.values():
            if p.waiting_for is not None:
                continue
            if not p.queue:
                continue
            if res := p.queue[0].step(p, w):
                return (res.w, cmds + res.cmds)
            for m in moves:
                if res := m(p, w):
                    q.append((res.w, cmds + res.cmds))


