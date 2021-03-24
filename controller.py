from __future__ import annotations

from dataclasses import dataclass, field, replace
from utils import dotdict
from typing import Dict, Any, Tuple, Literal, NewType
import datetime

Id = NewType('Id', str)

@dataclass(frozen=True)
class Plate:
    id: Id
    loc: str
    lid_loc: str = 'self'
    target_loc: None | str = None
    queue: list = field(default_factory=list)
    waiting_for: None | Id | str | datetime.datetime | Tuple[Id, datetime.datetime] = None
                           # ^ time to be resolved into a datetime
    meta: Any = None

@dataclass(frozen=True)
class World:
    plates: dict[Id, Plate]
    # incu: Id | Literal['ready']
    # disp: Id | Literal['ready']
    # wash: Id | Literal['ready']
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
    __getattr__ = lookup

    def success(self, p, cmds=[], accept=False):
        w = replace(self, plates={**self.plates, p.id: p})
        return dotdict(w=w, cmds=cmds, accept=accept)

    def accept(self, p, cmds=[]):
        return self.success(p, cmds, accept=True)


def world_locations(w: World) -> dotdict:
    return dotdict({loc: lookup(w, loc) for loc in locs})


p = Plate('p1', 'i42')
print(p)
q = replace(p, loc='incu')
print(q)

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [ i+1 for i in range(42) ]
Out = [ i+1 for i in range(18) ]

if 1:
    # small test version
    H = [21, 19, 17, 15, 13]
    I = [1, 2, 3]
    Out = [18]

incu_locs = [ f'i{i}' for i in I ]
h_locs = [ f'h{i}' for i in H ]
r_locs = [ f'r{i}' for i in H ]
out_locs = [ f'out{i}' for i in Out ]

lid_locs = [ h for h in h_locs if h != 'h21' ]

locs = 'wash disp incu'.split()
locs += incu_locs
locs += h_locs
locs += r_locs
locs += out_locs

# this could be cached in various ways
def lookup(w, loc):
    for p in w.plates.values():
        if loc == p.loc:
            return p.id
        if loc == p.lid_loc:
            return f'lid({p.id})'
        if loc == p.target_loc:
            return f'target({p.id})'
    return 'free'

def world_locations(w):
    return dotdict({loc: lookup(w, loc) for loc in locs})

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
            if not p.queue:
                continue
            if res := accepting(p.queue[0], p, w):
                return (res.w, cmds + res.cmds)
            for m in moves:
                if res := m(p, w):
                    q.append((res.w, cmds + res.cmds))

def is_accepting(w):
    for p in w.plates.values():
        if p.queue[0].accepts(w):
            return True
    return False

# These have an implicit pre & post
moves = [
    h19_put, ...,
    h19_get, ...,
]

def target_wash(p, w):
    assert p.target_loc is None

    if w.wash != 'free':
        return fail('wash not free')
    else:
        return success(
            p=replace(p, target_loc='wash')
        )

def incu_pop(p, w):
    assert p.target_loc, 'set target before popping from incubator'
    assert p.loc in incu_locs
    assert p.lid == 'self'

    if w.incu != 'free':
        return fail('incu not free')
    else:
        id = w.timestamp
        return success(
            run=incu.get(p.loc, id),
            p=replace(p, loc='incu', waiting_for=Incu(id)),
        )

def incu_get(p, w):
    assert p.loc == 'incu'
    assert p.lid == 'self'
    assert p.waiting_for in ('incu', None)

    if w.h21 != 'free':
        return fail('h21 not free')
    elif p.waiting_for == 'incu':
        return fail('waiting')
    else:
        return success(
            run=robot('generated/incu_get'),
            p=replace(p, loc='h21'),
        )

def prep_h21(p, w):
    if w.h21 != 'free' and w.h21 != p.id:
        # cannot be done without returning the other plate
        fail('h21 not free')

    if p.loc == 'h21':
        prep = []
    else:
        # is this ever going to happen? noone will move this plate
        prep = [robot('generated/{p.loc}_get')]

    return prep


def delid(p, w):
    assert p.loc in h_locs
    assert p.lid == 'self'

    prep = prep_h21(p, w)

    for loc in lid_locs:
        if w[loc] == 'free':
            return success(
                run=prep + [robot('generated/lid_{loc}_put')],
                p=replace(p, loc='h21', lid_loc=loc),
            )
    return fail('no free lid locations!!!')

def lid(p, w):
    assert p.loc in h_locs
    assert p.lid != 'self'

    prep = prep_h21(p, w)

    return success(
        run=prep + [robot('generated/lid_{p.lid_loc}_get')],
        p=replace(p, loc='h21', lid_loc='self'),
    )

def wash_put(p, w):
    assert p.loc in h_locs
    assert p.lid != 'self'

    if w.wash != 'free' and p.target_loc != 'wash':
        fail('wash not free and not targeted')

    prep = prep_h21(p, w)

    id = w.timestamp
    return success(
        run=prep + [robot('generated/wash_put'), wash.start(id)],
        p=replace(p, loc='wash', waiting_for=Wash(id)),
    )

# Could both say accept + what effect it does

def success(p, cmds=[], accept=False):
    w = replace(w, plates={**w.plates, p.id: p})
    return dotdict(w=w, cmds=cmds, accept=accept)

def accept(p, w, cmds=[], accept=False):
    w = replace(w, plates={**w.plates, p.id: p})
    return dotdict(w=w, cmds=cmds, accept=accept)


@dataclass
class UniqueSupply():
    count = 0
    def __call__(self, prefix=''):
        self.count += 1
        return f'{prefix}({self.count})'

    def reset(self):
        self.count = 0

unique = UniqueSupply()

class Accepting:
    def incu_pop(p, w, target):
        if p.loc in incu_locs and w[target] == 'free':
            id = unique('incu')
            return w.accept(
                replace(p, loc='incu', target_loc=target, waiting_for=id),
                [run('incu_get', p.loc, id=id)]
            )

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





for method in dir(Accepting):
    globals()[method] = lambda *args, **kwargs: dotdict(method=method, args=args, kwargs=kwargs)

def accepting(d, p, w):
    if p.waiting_for is not None:
        return None
    elif res := getattr(Accepting, d.method)(p, w, *d.args, **d.kwargs):
        p, w = res
        ... something with:
        w.plates[p.id] = p
        + start programs on machines. make a cmd? put cmd queue in w?  eehh
    else:
        return None

# Cell Painting Workflow
protocol = [
    '# 2 Compound treatment: Remove (80%) media of all wells',
    incu_pop(target='wash'),
    wash(),

    '# 3 Mitotracker staining',
    disp('peripump 1', 'mitotracker solution'),
    incu_put('30 min'),
    incu_pop(target='wash'),
    wash('pump D', 'PBS'),

    '# 4 Fixation',
    disp('Syringe A', '4% PFA'),
    RT_incu('20 min'),
    wash('pump D', 'PBS'),

    '# 5 Permeabilization',
    disp('Syringe B', '0.1% Triton X-100 in PBS'),
    RT_incu('20 min'),
    wash('pump D', 'PBS'),

    '# 6 Post-fixation staining',
    disp('peripump 2', 'staining mixture in PBS'),
    RT_incu('20 min'),
    wash('pump D', 'PBS'),

    '# 7 Imaging',
    to_output_hotel(),
]
