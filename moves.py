
from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta
from robots import *

from collections import deque
import random

import abc

from utils import show
import snoop # type: ignore
snoop.install(pformat=show)

Waitable = Union[Literal['ready', 'wash', 'disp'], datetime, timedelta]

def minutes(m: int) -> timedelta:
    return timedelta(minutes=m)

@dataclass(frozen=True)
class Plate:
    id: str
    loc: str
    lid_loc: str = 'self'
    waiting_for: Waitable = 'ready'
    queue: list[ProtocolStep] = field(default_factory=list, repr=True)

    def top(self) -> ProtocolStep:
        return self.queue[0]

    def pop(self) -> Plate:
        return replace(self, queue=self.queue[1:])

    def replace(self, loc: str | None = None, lid_loc: str | None = None, waiting_for: Waitable | None = None) -> Plate:
        '''
        Returns a new plate with some parts replaced.

        The type of dataclasses.replace is broken.  https://github.com/python/mypy/issues/5152
        This is a correctly typed replacement for plates.
        '''
        kws = dict(loc=loc, lid_loc=lid_loc, waiting_for=waiting_for)
        kws = {k: v for k, v in kws.items() if v is not None}
        return replace(self, **kws)


H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(42)]
Out = [18] # [ i+1 for i in range(18) ] # todo: measure out_hotel_dist
# Out = [ i+1 for i in range(18) ] # todo: measure out_hotel_dist

if 0:
    # small test version
    H = [21, 19, 17, 15, 13]
    I = [1, 2, 3, 4, 5]
    Out = [18]

h21 = 'h21'

incu_locs: list[str] = [f'i{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H]
out_locs:  list[str] = [f'out{i}' for i in Out]
lid_locs:  list[str] = [h for h in h_locs if h != h21]

out_locs += r_locs

@dataclass(frozen=True)
class World:
    plates: dict[str, Plate]

    def __getattr__(self, loc: str) -> str:
        assert loc != 'incu'
        if loc in ('shape', 'dtype'):
            raise AttributeError
        for p in self.plates.values():
            if loc == p.loc:
                return p.id
            if loc == p.lid_loc:
                return f'lid({p.id})'
        return 'free'

    # def __getitem__(self, loc: str) -> str:
    __getitem__ = __getattr__

    def update(self, p: Plate) -> World:
        return replace(self, plates={**self.plates, p.id: p})

    def transition(self, p: Plate, cmds: list[Command]=[]) -> Transition:
        return Transition(w=self.update(p), cmds=cmds)

@dataclass(frozen=True)
class Transition:
    w: World
    cmds: list[Command] = field(default_factory=list)
    prio: int = 0
    def __rshift__(self, other: Transition) -> Transition:
        return Transition(other.w, self.cmds + other.cmds, max(self.prio, other.prio))

def world_locations(w: World) -> dict[str, str]:
    locs: list[str] = 'wash disp'.split()
    locs += incu_locs
    locs += h_locs
    locs += r_locs
    locs += out_locs
    return {loc: w[loc] for loc in locs}

def active_count(w: World) -> int:
    locs: list[str] = 'wash disp'.split()
    locs += h_locs
    # locs += r_locs
    return sum(
        1 for p in w.plates.values()
        if p.loc in locs
        if p.queue
        # ie not inside incubator and not in output
    )

class ProtocolStep(abc.ABC):
    @abc.abstractmethod
    def step(self, p: Plate, w: World) -> Transition | None:
        pass

    def prio(self) -> int:
        return 0

@dataclass(frozen=True)
class incu(ProtocolStep):
    timedelta: timedelta
    def step(self, p: Plate, w: World) -> Transition | None:
        if p.loc == h21 and p.lid_loc == 'self':
            for incu_loc in incu_locs:
                if w[incu_loc] == 'free':
                    return w.transition(
                        p.replace(loc=incu_loc, waiting_for=self.timedelta),
                        [
                            robotarm_cmd('generated/incu_put'),
                            incu_cmd('put', incu_loc),
                        ]
                    )
        return None

    def prio(self) -> int:
        return 2

@dataclass(frozen=True)
class wash(ProtocolStep):
    protocol_path: str
    # test-protocols/washer_prime_buffers_A_B_C_D_25ml.LHC
    def step(self, p: Plate, w: World) -> Transition | None:
        if p.loc == h21 and p.lid_loc != 'self' and w.wash == 'free':
            return w.transition(
                p.replace(loc='wash', waiting_for='wash'),
                [
                    robotarm_cmd('generated/wash_put'),
                    wash_cmd(self.protocol_path),
                ],
            )
        return None

    def prio(self) -> int:
        return 3

@dataclass(frozen=True)
class disp(ProtocolStep):
    protocol_path: str
    # test-protocols/dispenser_prime_all_buffers.LHC
    def step(self, p: Plate, w: World) -> Transition | None:
        if p.loc == h21 and p.lid_loc != 'self' and w.disp == 'free':
            return w.transition(
                p.replace(loc='disp', waiting_for='disp'),
                [
                    robotarm_cmd('generated/disp_put'),
                    disp_cmd(self.protocol_path)
                ],
            )
        return None

    def prio(self) -> int:
        return 3

@dataclass(frozen=True)
class RT_incu(ProtocolStep):
    timedelta: timedelta
    def step(self, p: Plate, w: World) -> Transition | None:
        if p.loc == 'h21' and p.lid_loc == 'self':
            for r_loc in r_locs:
                if w[r_loc] == 'free':
                    return w.transition(
                        p.replace(loc=r_loc, waiting_for=self.timedelta),
                        [robotarm_cmd(f'generated/{r_loc}_put')]
                    )
        return None

    def prio(self) -> int:
        return 1

@dataclass(frozen=True)
class to_output_hotel(ProtocolStep):
    def step(self, p: Plate, w: World) -> Transition | None:
        if p.loc == 'h21' and p.lid_loc == 'self':
            for out_loc in out_locs:
                if w[out_loc] == 'free':
                    return w.transition(
                        p.replace(loc=out_loc),
                        [robotarm_cmd(f'generated/{out_loc}_put')]
                    )
        return None

def moves(p: Plate, w: World) -> Iterator[Transition]:
    if p.waiting_for != 'ready':
        return

    # disp to h21
    if p.loc == 'disp' and w.h21 == 'free':
        assert p.waiting_for == 'ready'
        yield w.transition(
            p.replace(loc=h21),
            [robotarm_cmd('generated/disp_get')]
        )

    # wash to h21
    if p.loc == 'wash' and w.h21 == 'free':
        assert p.waiting_for == 'ready'
        yield w.transition(
            p.replace(loc=h21),
            [robotarm_cmd('generated/wash_get')]
        )

    # incu## to h21
    if p.loc in incu_locs and w.h21 == 'free':
        assert p.waiting_for == 'ready'
        yield w.transition(
            p.replace(loc=h21),
            [
                incu_cmd('get', p.loc),
                robotarm_cmd('generated/incu_get'),
            ]
        )

    # RT to h21
    if p.loc in r_locs and w.h21 == 'free':
        assert p.waiting_for == 'ready'
        yield w.transition(
            p.replace(loc=h21),
            [robotarm_cmd(f'generated/{p.loc}_get')]
        )

    # h## to h21
    if p.loc in h_locs and w.h21 == 'free':
        yield w.transition(
            p.replace(loc=h21),
            [robotarm_cmd(f'generated/{p.loc}_get')]
        )

    # h21 to h##
    if p.loc == h21:
        for h_loc in h_locs:
            if w[h_loc] == 'free':
                yield w.transition(
                    p.replace(loc=h_loc),
                    [robotarm_cmd(f'generated/{h_loc}_put')]
                )
                break

    # lid: move lid on h## to self
    if p.loc == h21 and p.lid_loc in lid_locs:
        yield w.transition(
            p.replace(lid_loc='self'),
            [robotarm_cmd(f'generated/lid_{p.lid_loc}_get')],
        )

    # delid: move lid on self to h##
    if p.loc == h21 and p.lid_loc == 'self':
        for lid_loc in lid_locs:
            if w[lid_loc] == 'free':
                yield w.transition(
                    p.replace(lid_loc=lid_loc),
                    [robotarm_cmd(f'generated/lid_{lid_loc}_put')],
                )
                break

