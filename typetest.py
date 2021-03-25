
from __future__ import annotations
from dataclasses import dataclass, field, replace

# from utils import dotdict
import typing
from typing import Dict, Any, Tuple, Literal, NewType, TypedDict
from typing import *
import datetime

x: str = 1

def as_dataclass():
    ga = gripper('a')
    p: list[Move] = [
        ga,
        replace(ga, name='x'),
        movel('b', dx=1.0),
        movej('c', dy=-1.0),
    ]

    def resove_moves(moves: list[Move]) -> None:
        out: list[str] = []
        defs: dict[str, str] = {}
        for move in moves:
            if isinstance(move, (movel, movej)):
                q_name = move.name + '_q'
                p_name = move.name + '_p'
                out += [
                    f'{p_name} = p{defs[p_name]}',
                ]
                for i, d_name in enumerate('dx dy dz'.split()):
                    if offset := getattr(move, d_name):
                        out += [
                            f'{p_name}[{i}] = {p_name}[{i}] + {offset}'
                        ]
                if isinstance(move, movel):
                    out += [
                        f'movel({p_name}, a=1.2, v=0.25)'
                    ]
                elif isinstance(move, movej):
                    out += [
                        f'{q_name} = {defs[q_name]}',
                        f'movej(get_inverse_kin({p_name}, qnear={q_name}), a=1.4, v=1.05)',
                    ]
            elif isinstance(move, gripper):
                pass
                # out += subs[move.name]
        return out

    print(p)
    reveal_locals()

Id = NewType('Id', str)

@dataclass(frozen=True)
class Plate:
    id: Id
    loc: str
    lid_loc: str = 'self'
    target_loc: None | str = None
    queue: list = field(default_factory=list)
    waiting_for: (
        None | Id | Tuple[Id, str] | str | datetime.datetime
    ) = None
    meta: Any = None

@dataclass(frozen=True)
class World:
    plates: dict[Id, Plate]

    # this could be cached in various ways
    def lookup(self, loc: str) -> str:
        for p in self.plates.values():
            if loc == p.loc:
                return p.id
            if loc == p.lid_loc:
                return f'lid({p.id})'
            if loc == p.target_loc:
                return f'target({p.id})'
        return 'free'

    __getitem__ = lookup

    def __getattr__(self, loc: str) -> str:
        return self.lookup(loc)

# def world_locations(w: World):
#     return dotdict({loc: lookup(w, loc) for loc in locs})

w = World({})

reveal_type(w['a'])
reveal_type(w.a)
reveal_type(w.plates)
reveal_type(w.x)

@dataclass(frozen=True)
class Cmd:
    '''todo'''

@dataclass(frozen=True)
class run(Cmd):
    '''todo'''
    program: str
    argument: str
    id: Id

@dataclass(frozen=True)
class accept:
    p: Plate | None = None
    cmds: list[Cmd] = []
    w: World | None = None

@dataclass(frozen=True)
class Accepting:
    def accepts(self, p: Plate, w: World) -> accept | None:
        raise NotImplementedError

def unique(prefix: str) -> Id:
    return Id('todo')

incu_locs: list[str] = []

@dataclass(frozen=True)
class incu_pop(Accepting):
    target: None | str = None

    def accept(self, p: Plate, w: World) -> accept | None:
        if p.loc in incu_locs and (not self.target or w[self.target] == 'free'):
            id = unique('incu')
            return accept(
                replace(p, loc='incu', target_loc=self.target, waiting_for=id),
                [run('incu_get', p.loc, id=id)]
            )
        return None

    def incu_put(p, w, timeout):
        if p.loc == 'incu' and p.lid_loc == 'self':
            for incu_loc in incu_locs:
                if w[incu_loc] == 'free':
                    id = unique('incu')
                    return w.accept(
                        replace(p, loc=incu_loc, waiting_for=(id, timeout)),
                        [run('incu_put', incu_loc, id=id)]
                    )

        # what to do about waiting?
        # and p.waiting_for == 'time' and p.waiting_arg == timeout

    def wash(p, w, *program):
        if p.loc == 'wash' and p.lid_loc != 'self':
            id = unique('wash')
            return w.accept(
                replace(p, waiting_for=id),
                [run('wash', program=program, id=id)],
            )





