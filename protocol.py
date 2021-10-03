from __future__ import annotations
from typing import *
from dataclasses import *

from datetime import datetime, timedelta
from collections import defaultdict

import graphlib
import json
import os
import platform
import protocol
import re
import textwrap
import sys
import traceback

from moves import movelists
from robots import RuntimeConfig, Command, Runtime
from robots import wait_for_ready_cmd
from utils import pr, show, Mutable
import robots
import utils
import moves
import threading

if 0:
    'wash -> disp'
    'disp -> A21'
    'wash -> B21'
    'lid B21 -> B21'

    'B21 -> incu, prep'
    'B21 -> incu, transfer'
    'B21 -> incu, return'

def ATTENTION(s: str):
    color = utils.Color()
    print(color.red('*' * 80))
    print()
    print(textwrap.indent(textwrap.dedent(s.strip('\n')), '    ').rstrip('\n'))
    print()
    print(color.red('*' * 80))
    v = input('Continue? [y/n] ')
    if v.strip() != 'y':
        raise ValueError('Program aborted by user')
    else:
        print('continuing...')

@dataclass(frozen=True)
class Plate:
    id: str
    incu_loc: str
    rt_loc: str
    lid_loc: str
    out_loc: str
    batch_index: int

    @property
    def lid_put(self):
        return f'lid_{self.lid_loc} put'

    @property
    def lid_get(self):
        return f'lid_{self.lid_loc} get'

    @property
    def rt_put(self):
        return f'{self.rt_loc} put'

    @property
    def rt_get(self):
        return f'{self.rt_loc} get'

    @property
    def out_put(self):
        return f'{self.out_loc} put'

    @property
    def out_get(self):
        return f'{self.out_loc} get'

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(22)]

h21 = 'h21'
r21 = 'r21'

incu_locs: list[str] = [f'L{i}' for i in I] + [f'R{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
rt_locs:   list[str] = [f'r{i}' for i in H][1:]
out_locs:  list[str] = [f'out{i}' for i in reversed(H)] + list(reversed(rt_locs))
lid_locs:  list[str] = [h for h in h_locs if h != h21]

A_locs:    list[str] = [f'out{i}' for i in H]
C_locs:    list[str] = [f'r{i}' for i in H]

A = TypeVar('A')

@dataclass(frozen=True)
class Steps(Generic[A]):
    Mito:   A
    PFA:    A
    Triton: A
    Stains: A
    Final:  A

    def asdict(self) -> dict[str, A]:
        return dict(
            Mito   = self.Mito,
            PFA    = self.PFA,
            Triton = self.Triton,
            Stains = self.Stains,
            Final  = self.Final,
        )

    def values(self) -> list[A]:
        '''
        Returns *truthy* values
        '''
        return [v for k, v in self.asdict().items() if v]

    def __getitem__(self, index: int) -> A:
        '''
        *One-indexed* get item, 1 = Mito, 2 = PFA, ...
        '''
        return list(self.asdict().values())[index - 1]

@dataclass(frozen=True)
class ProtocolConfig:
    wash:  Steps[str]
    prime: Steps[str]
    disp:  Steps[str]
    incu:  Steps[int]
    prep_wash: str | None = None
    prep_disp: str | None = None

v3 = ProtocolConfig(
    prep_wash='automation_v3/0_W_D_PRIME.LHC',
    prep_disp=None,
    wash = Steps(
        'automation_v3/1_W-1X_beforeMito_leaves20ul.LHC',
        'automation_v3/3_W-3X_beforeFixation_leaves20ul.LHC',
        'automation_v3/5_W-3X_beforeTriton.LHC',
        'automation_v3/7_W-3X_beforeStains.LHC',
        'automation_v3/9_W-5X_NoFinalAspirate.LHC',
    ),
    prime = Steps(
        'automation_v3/1_D_P1_MIX_PRIME.LHC',
        'automation_v3/3_D_SA_PRIME.LHC',
        'automation_v3/5_D_SB_PRIME.LHC',
        'automation_v3/7_D_P2_MIX_PRIME.LHC',
        '',
    ),
    disp = Steps(
        'automation_v3/2_D_P1_40ul_purge_mito.LHC',
        'automation_v3/4_D_SA_384_80ul_PFA.LHC',
        'automation_v3/6_D_SB_384_80ul_TRITON.LHC',
        'automation_v3/8_D_P2_20ul_purge_stains.LHC',
        '',
    ),
    incu = Steps(
        1230 / 60,
        1200 / 60,
        1200 / 60,
        1200 / 60,
        0
    ),
    # incu = Steps(1250 / 60, 1210 / 60, 1210 / 60, 1210 / 60, 0),
)

def time_bioteks(config: RuntimeConfig, protocol_config: ProtocolConfig):
    '''
    Timing for biotek protocols and robotarm moves from and to bioteks.

    This is preferably done with the bioteks connected to water.

    Required lab prerequisites:
        1. hotel B21:        one plate *without* lid
        2. biotek washer:    empty
        3. biotek washer:    connected to water
        4. biotek dispenser: empty
        5. biotek dispenser: all pumps and syringes connected to water
        6. robotarm:         in neutral position by B hotel
        7. gripper:          sufficiently open to grab a plate

        8. incubator transfer door: not used
        9. hotel B1-19:             not used
       10. hotel A:                 not used
       11. hotel C:                 not used
    '''
    protocol_config = replace(protocol_config, incu = Steps(0,0,0,0,0))
    events = eventlist([1], protocol_config=protocol_config, short_test_paint=False, sleek=True)
    events = [
        e
        for e in events
        for c in [e.command]
        if not isinstance(c, robots.incu_cmd)
        if not isinstance(c, robots.robotarm_cmd) or any(
            needle in c.program_name
            for needle in ['wash', 'disp']
        )
    ]
    ATTENTION(time_bioteks.__doc__ or '')
    execute_events(config, events, metadata={'options': 'time_bioteks'})

def time_arm_incu(config: RuntimeConfig):
    '''
    Timing for robotarm and incubator.

    Required lab prerequisites:
        1. incubator transfer door: one plate with lid
        2. hotel B21:               one plate with lid
        3. hotel B1-19:             empty!
        4. hotel A:                 empty!
        5. hotel C:                 empty!
        6. biotek washer:           empty!
        7. biotek dispenser:        empty!
        8. robotarm:                in neutral position by B hotel
        9. gripper:                 sufficiently open to grab a plate
    '''
    N = 4
    incu: list[Command] = []
    for loc in incu_locs[:N]:
        incu += [
            robots.incu_cmd('put', loc),
            robots.wait_for_ready_cmd('incu'),
            robots.incu_cmd('get', loc),
            robots.wait_for_ready_cmd('incu'),
        ]
    arm: list[Command] = []
    plate = Plate('', '', '', '', '', 1)
    for lid_loc in lid_locs[:N]:
        plate = replace(plate, lid_loc=lid_loc)
        arm += [
            *robotarm_cmds(plate.lid_put),
            *robotarm_cmds(plate.lid_get),
        ]
    for rt_loc in rt_locs[:N]:
        plate = replace(plate, rt_loc=rt_loc)
        arm += [
            *robotarm_cmds(plate.rt_put),
            *robotarm_cmds(plate.rt_get),
        ]
    for out_loc in out_locs[:N]:
        plate = replace(plate, out_loc=out_loc)
        arm += [
            *robotarm_cmds(plate.out_put),
            *robotarm_cmds(plate.out_get),
        ]
    plate = replace(plate, lid_loc=lid_locs[0], rt_loc=rt_locs[0])
    arm2: list[Command] = [
        *robotarm_cmds(plate.rt_put),
        *robotarm_cmds('incu get'),
        *robotarm_cmds(plate.lid_put),
        *robotarm_cmds('wash put'),
        *robotarm_cmds('wash_to_disp'),
        *robotarm_cmds('disp get'),
        *robotarm_cmds('wash put'),
        *robotarm_cmds('wash get'),
        *robotarm_cmds(plate.lid_get),
        *robotarm_cmds('incu put'),
        *robotarm_cmds(plate.rt_get),
    ]
    with make_runtime(config, {'options': 'time_arm_incu'}) as runtime:
        ATTENTION(time_arm_incu.__doc__ or '')
        def execute(name: str, cmds: list[Command]):
            runtime.register_thread(f'{name} last_main')
            execute_commands_in_runtime(runtime, cmds)
            runtime.thread_idle()

        threads = [
            threading.Thread(target=lambda: execute('incu', incu), daemon=True),
            threading.Thread(target=lambda: execute('arm', arm), daemon=True),
        ]

        runtime.thread_idle()

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        execute_commands_in_runtime(runtime, arm2)

def lid_stress_test(config: RuntimeConfig):
    '''
    Do a lid stress test

    Required lab prerequisites:
        1. hotel B21:   plate with lid
        2. hotel B1-19: empty
        2. hotel A:     empty
        2. hotel B:     empty
        4. robotarm:    in neutral position by B hotel
        5. gripper:     sufficiently open to grab a plate
    '''
    events: list[Event] = []
    for i, (lid, A, C) in enumerate(zip(lid_locs, A_locs, C_locs)):
        p = Plate('p', incu_loc='', rt_loc=C, lid_loc=lid, out_loc=A, batch_index=1)
        commands: list[Command] = [
            *robotarm_cmds(p.lid_put),
            *robotarm_cmds(p.lid_get),
            *robotarm_cmds(p.rt_put),
            *robotarm_cmds(p.rt_get),
            *robotarm_cmds(p.lid_put),
            *robotarm_cmds(p.lid_get),
            *robotarm_cmds(p.out_put),
            *robotarm_cmds(p.out_get),
        ]
        events += [
            Event(p.id, str(i), '', cmd)
            for cmd in commands
        ]
    events = sleek_events(events)
    ATTENTION(lid_stress_test.__doc__ or '')
    execute_events(config, events, {'options': 'lid_stress_test'})

def load_incu(config: RuntimeConfig, num_plates: int):
    '''
    Load the incubator with plates from A hotel, starting at the bottom, to incubator positions L1, ...

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L1, ...:       empty!
        3. hotel A1-A#:             plates with lid
        4. robotarm:                in neutral position by B hotel
        5. gripper:                 sufficiently open to grab a plate
    '''
    events: list[Event] = []
    for i, (incu_loc, a_loc) in enumerate(zip(incu_locs, reversed(A_locs)), start=1):
        if i > num_plates:
            break
        p = Plate(
            id=str(i),
            incu_loc=incu_loc,
            out_loc=a_loc,
            rt_loc='',
            lid_loc='',
            batch_index=0
        )
        assert p.out_loc.startswith('out')
        pos = p.out_loc.removeprefix('out')
        commands = [
            robots.robotarm_cmd(f'incu_A{pos} put prep'),
            robots.robotarm_cmd(f'incu_A{pos} put transfer to drop neu'),
            robots.wait_for_ready_cmd('incu'),
            robots.robotarm_cmd(f'incu_A{pos} put transfer from drop neu'),
            robots.incu_cmd('put', p.incu_loc),
            robots.robotarm_cmd(f'incu_A{pos} put return'),
        ]
        events += [
            Event(p.id, 'incu load', '', cmd)
            for cmd in commands
        ]
    events = [
        Event('', 'load incu', 'prep', robots.robotarm_cmd('incu_A21 put-prep')),
        *events,
        Event('', 'load incu', 'return', robots.robotarm_cmd('incu_A21 put-return'))
    ]
    ATTENTION(load_incu.__doc__ or '')
    execute_events(config, events, {'options': 'load_incu'})

def unload_incu(config: RuntimeConfig, num_plates: int):
    '''
    Unload the incubator with plates from incubator positions L1, ..., to A hotel, starting at the bottom.

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L1, ...:       plates with lid
        3. hotel A1-A#:             empty!
        4. robotarm:                in neutral position by B hotel
        5. gripper:                 sufficiently open to grab a plate
    '''
    plates = define_plates([num_plates])
    events: list[Event] = []
    for p in plates:
        assert p.out_loc.startswith('out')
        pos = p.out_loc.removeprefix('out')
        commands = [
            robots.wait_for_ready_cmd('incu'),
            robots.incu_cmd('get', p.incu_loc),
            robots.robotarm_cmd(f'incu_A{pos} get prep'),
            robots.wait_for_ready_cmd('incu'),
            robots.robotarm_cmd(f'incu_A{pos} get transfer'),
            robots.robotarm_cmd(f'incu_A{pos} get return'),
        ]
        events += [
            Event(p.id, 'unload', '', cmd)
            for cmd in commands
        ]
    events = [
        *events,
    ]
    ATTENTION(unload_incu.__doc__ or '')
    execute_events(config, events, {'options': 'unload_incu'})

@dataclass(frozen=True)
class Event:
    plate_id: str
    part: str
    subpart: str
    command: robots.Command

    def machine(self) -> str:
        return self.command.__class__.__name__.rstrip('cmd').strip('_')

    def desc(self):
        return {
            'event_plate_id': self.plate_id,
            'event_part': self.part,
            'event_subpart': self.subpart,
            'event_machine': self.machine(),
        }

def execute_commands_in_runtime(runtime: Runtime, cmds: list[Command]) -> None:
    execute_events_in_runtime(runtime, [Event('', '', '', cmd) for cmd in cmds])

def execute_events_in_runtime(runtime: Runtime, events: list[Event]) -> None:
    for i, event in enumerate(events, start=1):
        # print(f'=== event {i}/{len(events)} | {" | ".join(event.desc().values())} ===')
        metadata: dict[str, str | int] = {
            'event_id': i,
            **event.desc(),
        }
        event.command.execute(runtime, metadata)

Desc = tuple[Plate, str, str]

def robotarm_cmds(s: str, before_pick: list[robots.Command] = [], after_drop: list[robots.Command] = []) -> list[robots.Command]:
    return [
        robots.robotarm_cmd(s + ' prep'),
        *before_pick,
        robots.robotarm_cmd(s + ' transfer'),
        *after_drop,
        robots.robotarm_cmd(s + ' return'),
    ]

@dataclass(frozen=True)
class Interleaving:
    rows: list[tuple[int, str]]
    @staticmethod
    def init(s: str) -> Interleaving:
        rows: list[tuple[int, str]] = []
        seen: Counter[str] = Counter()
        for line in s.strip().split('\n'):
            sides = line.strip().split('->')
            for a, b in zip(sides, sides[1:]):
                arrow = f'{a.strip()} -> {b.strip()}'
                rows += [(seen[arrow], arrow)]
                seen[arrow] += 1
        target = list(seen.values())[0]
        assert target > 1, 'need at least two copies of all transitions'
        for k, v in seen.items():
            assert v == target, f'{k!r} occurred {v} times, should be {target} times'
        return Interleaving(rows)

lin = Interleaving.init('''
    incu -> B21 -> wash -> disp -> B21 -> incu
    incu -> B21 -> wash -> disp -> B21 -> incu
''')

june = Interleaving.init('''
    incu -> B21  -> wash
    incu -> B21
                    wash -> disp
            B21  -> wash
                            disp -> B21 -> incu
    incu -> B21
                    wash -> disp
            B21  -> wash
                            disp -> B21 -> incu
                    wash -> disp
                            disp -> B21 -> incu
''')

mix = Interleaving.init('''
    incu -> B21 -> wash
                   wash -> disp
    incu -> B21 -> wash
                           disp -> B21 -> incu
                   wash -> disp
    incu -> B21 -> wash
                           disp -> B21 -> incu
                   wash -> disp
                           disp -> B21 -> incu
''')


quad = Interleaving.init('''
    incu -> B21 -> wash
                   wash -> disp
    incu -> B21 -> wash
                           disp -> B21
                   wash -> disp
                                   B21  -> incu
    incu -> B21 -> wash
                           disp -> B21
                   wash -> disp
                                   B21  -> incu
                           disp -> B21
                                   B21  -> incu
''')


three = Interleaving.init('''
    incu -> B21 -> wash
                   wash -> disp
    incu -> B21 -> wash
                           disp -> B21
                   wash -> disp
    incu -> B21 -> wash
                                   B21 -> incu
                           disp -> B21
                   wash -> disp
    incu -> B21 -> wash
                                   B21 -> incu
                           disp -> B21
                   wash -> disp
                                   B21 -> incu
                           disp -> B21
                                   B21 -> incu
''')

finlin = Interleaving.init('''
    incu -> B21 -> wash -> B21 -> out
    incu -> B21 -> wash -> B21 -> out
''')

finjune = Interleaving.init('''
    incu -> B21 -> wash
                   wash -> B21
    incu -> B21 -> wash
                           B21 -> out
                   wash -> B21
    incu -> B21 -> wash
                           B21 -> out
                   wash -> B21
                           B21 -> out
''')

Interleavings = {k: v for k, v in globals().items() if isinstance(v, Interleaving)}

def paint_batch(batch: list[Plate], protocol_config: ProtocolConfig, short_test_paint: bool=False):

    p = protocol_config

    if p.prep_wash and p.prep_disp:
        prep_cmds: list[Command] = [
            robots.wash_cmd(p.prep_wash),
            robots.disp_cmd(p.prep_disp, before=[robots.idle_cmd() + 5]),
            robots.wait_for_ready_cmd('disp'),
            robots.wait_for_ready_cmd('wash'),
        ]
    elif p.prep_wash and not p.prep_disp:
        prep_cmds: list[Command] = [
            robots.wash_cmd(p.prep_wash),
            robots.wait_for_ready_cmd('wash'),
        ]
    elif not p.prep_wash and p.prep_disp:
        prep_cmds: list[Command] = [
            robots.disp_cmd(p.prep_disp),
            robots.wait_for_ready_cmd('disp'),
        ]
    elif not p.prep_wash and not p.prep_disp:
        prep_cmds: list[Command] = []
    else:
        assert False

    first_plate = batch[0]
    last_plate = batch[-1]
    first_batch = first_plate.batch_index == 0

    if not first_batch:
        prep_cmds += [
            robots.wait_for_checkpoint_cmd('batch start', or_now=True) + Symbolic.var('batch sep'),
        ]

    prep_cmds += [
        robots.checkpoint_cmd('info', 'batch start'),
        robots.checkpoint_cmd('begin', 'batch'),
    ]

    post_cmds = [
        robots.checkpoint_cmd('end', 'batch'),
    ]

    chunks: dict[Desc, Iterable[Command]] = {}
    for i, plate in enumerate(batch):
        lid_on = [
            *robotarm_cmds(plate.lid_get, after_drop=[robots.checkpoint_cmd('begin', f'plate {plate.id} lid on')]),
        ]

        lid_off = [
            *robotarm_cmds(plate.lid_put, before_pick=[robots.checkpoint_cmd('end', f'plate {plate.id} lid on', strict=False)]),
        ]

        incu_get = [
            robots.incu_cmd('get', plate.incu_loc,
                after=[robots.checkpoint_cmd('end', f'plate {plate.id} incubator', strict=False)]),
            *robotarm_cmds('incu get',
                before_pick = [robots.wait_for_ready_cmd('incu')]),
            *lid_off,
        ]

        B21_to_incu = [
            *robotarm_cmds('incu put',
                after_drop = [
                    robots.incu_cmd('put', plate.incu_loc,
                        after=[robots.checkpoint_cmd('begin', f'plate {plate.id} incubator')])]),
            robots.wait_for_ready_cmd('incu'),
                # todo: this is required by 'lin' ilv but makes 'mix' w->d transfer worse
        ]

        incu_put = [
            *lid_on,
            *B21_to_incu,
        ]

        RT_get = [
            *robotarm_cmds(plate.rt_get),
            *lid_off,
        ]

        RT_put = [
            *lid_on,
            *robotarm_cmds(plate.rt_put),
        ]

        B21_to_RT = [
            *robotarm_cmds(plate.rt_put),
        ]

        def wash(wash_wait: list[robots.wait_for_checkpoint_cmd], wash_path: str, disp_prime_path: str | None=None):
            if plate is first_plate and disp_prime_path is not None:
                disp_prime = [robots.disp_cmd(disp_prime_path, before=[robots.idle_cmd() + 5])]
            else:
                disp_prime = []
            return [
                robots.robotarm_cmd('wash put prep'),
                robots.robotarm_cmd('wash put transfer'),
                robots.wash_cmd(
                    wash_path,
                    before=[*wash_wait, robots.checkpoint_cmd('end', f'plate {plate.id} active', strict=False)],
                    after=[robots.checkpoint_cmd('begin', f'plate {plate.id} transfer')],
                ),
                *disp_prime,
                robots.robotarm_cmd('wash put return'),
            ]

        def disp(disp_path: str):
            return [
                robots.robotarm_cmd('wash_to_disp prep'),
                robots.wait_for_ready_cmd('wash'),
                robots.robotarm_cmd('wash_to_disp transfer'),
                robots.wait_for_ready_cmd('disp'),  # ensure dispenser priming is done
                robots.disp_cmd(
                    disp_path,
                    before=[robots.checkpoint_cmd('end', f'plate {plate.id} transfer')],
                    after=[
                        robots.checkpoint_cmd('begin', f'plate {plate.id} disp done'),
                        robots.checkpoint_cmd('begin', f'plate {plate.id} active')
                    ],
                ),
                robots.robotarm_cmd('wash_to_disp return'),
            ]

        disp_to_incu = [
            robots.robotarm_cmd('disp get prep'),
            robots.wait_for_ready_cmd('disp'),
            robots.checkpoint_cmd('end', f'plate {plate.id} disp done'),
            robots.robotarm_cmd('disp get transfer'),
            robots.robotarm_cmd('disp get return'),
            *incu_put,
        ]

        disp_to_B21 = [
            robots.robotarm_cmd('disp get prep'),
            robots.wait_for_ready_cmd('disp'),
            robots.checkpoint_cmd('end', f'plate {plate.id} disp done'),
            robots.robotarm_cmd('disp get transfer'),
            robots.robotarm_cmd('disp get return'),
            *lid_on,
        ]

        disp_to_RT = [
            robots.robotarm_cmd('disp get prep'),
            robots.wait_for_ready_cmd('disp'),
            robots.checkpoint_cmd('end', f'plate {plate.id} disp done'),
            robots.robotarm_cmd('disp get transfer'),
            robots.robotarm_cmd('disp get return'),
            *RT_put,
        ]

        var = robots.Symbolic.var

        wait_before_incu_get: dict[int, list[robots.wait_for_checkpoint_cmd]] = {
            1: [robots.wait_for_checkpoint_cmd(f'batch')                   + var(f'plate {plate.id} incu get delay 1')],
            2: [robots.wait_for_checkpoint_cmd(f'plate {plate.id} active') + var(f'plate {plate.id} incu get delay 2')],
            3: [robots.wait_for_checkpoint_cmd(f'plate {plate.id} active') + var(f'plate {plate.id} incu get delay 3')],
            4: [robots.wait_for_checkpoint_cmd(f'plate {plate.id} active') + var(f'plate {plate.id} incu get delay 4')],
            5: [robots.wait_for_checkpoint_cmd(f'plate {plate.id} active') + var(f'plate {plate.id} incu get delay 5')],
        }

        wait_before_wash_start: dict[int, list[robots.wait_for_checkpoint_cmd]] = {
            1: [robots.wait_for_checkpoint_cmd(f'batch')                                + var(f'plate {plate.id} first wash delay')],
            2: [robots.wait_for_checkpoint_cmd(f'plate {plate.id} active', strict=True) + (p.incu[1] * 60 - d) for d in [2,0]], # be there 2s early
            3: [robots.wait_for_checkpoint_cmd(f'plate {plate.id} active', strict=True) + (p.incu[2] * 60 - d) for d in [2,0]], # be there 2s early
            4: [robots.wait_for_checkpoint_cmd(f'plate {plate.id} active', strict=True) + (p.incu[3] * 60 - d) for d in [2,0]], # be there 2s early
            5: [robots.wait_for_checkpoint_cmd(f'plate {plate.id} active', strict=True) + (p.incu[4] * 60 - d) for d in [2,0]], # be there 2s early
        }

        parts = chunks

        parts[plate, 'Mito',   'incu -> B21' ] = [*wait_before_incu_get[1], *incu_get]
        parts[plate, 'Mito',    'B21 -> wash'] = wash(wait_before_wash_start[1], p.wash[1], p.prime[1])
        parts[plate, 'Mito',   'wash -> disp'] = disp(p.disp[1])
        parts[plate, 'Mito',   'disp -> B21' ] = disp_to_B21
        parts[plate, 'Mito',    'B21 -> incu'] = B21_to_incu

        parts[plate, 'PFA',    'incu -> B21' ] = [*wait_before_incu_get[2], *incu_get]
        parts[plate, 'PFA',     'B21 -> wash'] = wash(wait_before_wash_start[2], p.wash[2], p.prime[2])
        parts[plate, 'PFA',    'wash -> disp'] = disp(p.disp[2])
        parts[plate, 'PFA',    'disp -> B21' ] = disp_to_B21
        parts[plate, 'PFA',     'B21 -> incu'] = B21_to_RT

        parts[plate, 'Triton', 'incu -> B21' ] = [*wait_before_incu_get[3], *RT_get]
        parts[plate, 'Triton',  'B21 -> wash'] = wash(wait_before_wash_start[3], p.wash[3], p.prime[3])
        parts[plate, 'Triton', 'wash -> disp'] = disp(p.disp[3])
        parts[plate, 'Triton', 'disp -> B21' ] = disp_to_B21
        parts[plate, 'Triton',  'B21 -> incu'] = B21_to_RT

        parts[plate, 'Stains', 'incu -> B21' ] = [*wait_before_incu_get[4], *RT_get]
        parts[plate, 'Stains',  'B21 -> wash'] = wash(wait_before_wash_start[4], p.wash[4], p.prime[4])
        parts[plate, 'Stains', 'wash -> disp'] = disp(p.disp[4])
        parts[plate, 'Stains', 'disp -> B21' ] = disp_to_B21
        parts[plate, 'Stains',  'B21 -> incu'] = B21_to_RT

        parts[plate, 'Final', 'incu -> B21' ] = [*wait_before_incu_get[5], *RT_get]
        parts[plate, 'Final',  'B21 -> wash'] = wash(wait_before_wash_start[5], p.wash[5])
        parts[plate, 'Final', 'wash -> B21' ] = robotarm_cmds('wash get', before_pick=[robots.wait_for_ready_cmd('wash')])
        parts[plate, 'Final',  'B21 -> out' ] = [*lid_on, *robotarm_cmds(plate.out_put)]

    from collections import defaultdict
    adjacent: dict[Desc, set[Desc]] = defaultdict(set)

    def seq(descs: list[Desc | None]):
        filtered: list[Desc] = [ desc for desc in descs if desc ]
        for now, next in utils.iterate_with_next(filtered):
            if next:
                adjacent[now] |= {next}

    def desc(p: Plate | None, part: str, subpart: str) -> Desc | None:
        if p is None:
            return None
        else:
            return p, part, subpart

    parts = ['Mito', 'PFA', 'Triton', 'Stains', 'Final']
    # parts = ['Mito', 'PFA']

    if short_test_paint:
        skip = ['Triton', 'Stains']
        parts = [part for part in parts if part not in skip]
        chunks = {
            desc: cmd
            for desc, cmd in chunks.items()
            for _, part, _ in [desc]
            if part not in skip
        }

    for part, next_part in utils.iterate_with_next(parts):
        if next_part:
            seq([
                desc(last_plate, part, 'B21 -> incu'),
                desc(first_plate, next_part, 'incu -> B21'),
            ])

    ilvs = {
        'Mito':   'june',
        'PFA':    'june',
        'Triton': 'june',
        'Stains': 'june',
        'Final':  'finjune',
    }

    for part in parts:
        ilv = Interleavings[ilvs[part]]
        for offset, _ in enumerate(batch):
            seq([
                desc(batch[i+offset], part, subpart)
                for i, subpart in ilv.rows
                if i + offset < len(batch)
            ])

    deps: dict[Desc, set[Desc]] = defaultdict(set)
    for node, nexts in adjacent.items():
        for next in nexts:
            deps[next] |= {node}

    for d, ds in deps.items():
        for x in ds:
            print(
                ', '.join((x[1], x[0].id, x[2])),
                '<',
                ', '.join((d[1], d[0].id, d[2]))
            )

    linear = list(graphlib.TopologicalSorter(deps).static_order())

    if 1:
        pr([
            ', '.join((desc[1], desc[0].id, desc[2]))
            for desc in linear
        ])

    plate_events = [
        Event(
            plate_id=plate.id,
            part=part,
            subpart=subpart,
            command=command,
        )
        for desc in linear
        for plate, part, subpart in [desc]
        for command in chunks[desc]
    ]

    for e in plate_events:
        print(e)

    prep_events: list[Event] = [ Event('', 'prep', '', cmd) for cmd in prep_cmds ]
    post_events: list[Event] = [ Event('', 'post', '', cmd) for cmd in post_cmds ]

    return prep_events + plate_events + post_events

def define_plates(batch_sizes: list[int]) -> list[Plate]:
    plates: list[Plate] = []

    index = 0
    for batch_index, batch_size in enumerate(batch_sizes):
        for index_in_batch in range(batch_size):
            plates += [Plate(
                id=f'{index+1}',
                incu_loc=incu_locs[index],
                rt_loc=rt_locs[index_in_batch],
                # lid_loc=lid_locs[index_in_batch],
                lid_loc=lid_locs[index_in_batch % 2],
                # lid_loc=lid_locs[0],
                out_loc=out_locs[index],
                batch_index=batch_index,
            )]
            index += 1

    for i, p in enumerate(plates):
        for j, q in enumerate(plates):
            if i != j:
                assert p.id != q.id, (p, q)
                assert p.incu_loc != q.incu_loc, (p, q)
                assert p.out_loc not in [q.out_loc, q.rt_loc, q.lid_loc, q.incu_loc], (p, q)
                if p.batch_index == q.batch_index:
                    assert p.rt_loc != q.rt_loc, (p, q)
                    # assert p.lid_loc != q.lid_loc, (p, q)

    return plates

def group_by_batch(plates: list[Plate]) -> list[list[Plate]]:
    d: dict[int, list[Plate]] = defaultdict(list)
    for plate in plates:
        d[plate.batch_index] += [plate]
    return sorted(d.values(), key=lambda plates: plates[0].batch_index)

def sleek_events(events: list[Event]) -> list[Event]:
    def get_movelist(event: Event) -> moves.MoveList | None:
        if isinstance(event.command, robots.robotarm_cmd):
            return movelists[event.command.program_name]
        else:
            return None
    return moves.sleek_movements(events, get_movelist)

def eventlist(batch_sizes: list[int], protocol_config: ProtocolConfig, short_test_paint: bool = False, sleek: bool = True) -> list[Event]:
    all_events: list[Event] = []
    for batch in group_by_batch(define_plates(batch_sizes)):
        events = paint_batch(
            batch,
            protocol_config=protocol_config,
            short_test_paint=short_test_paint,
        )
        if sleek:
            events = sleek_events(events)
        all_events += events
    return all_events

def test_circuit(config: RuntimeConfig) -> None:
    '''
    Test circuit: Short test paint on one plate, without incubator
    '''
    plate, = define_plates([1])
    events = eventlist([1], protocol_config=v3, short_test_paint=True)
    events = [
        event
        for event in events
        if isinstance(event.command, robots.robotarm_cmd)
    ] + [
        Event(plate.id, 'return', name, robots.robotarm_cmd(name))
        for name in [
            plate.out_get,
            'incu put'
        ]

    ]
    ATTENTION('''
        Test circuit using one plate.

        Required lab prerequisites:
            1. hotel one:               empty!
            2. hotel two:               empty!
            3. hotel three:             empty!
            4. biotek washer:           empty!
            5. biotek dispenser:        empty!
            6. incubator transfer door: one plate with lid
            7. robotarm:                in neutral position by lid hotel
            8. gripper:                 sufficiently open to grab a plate
    ''')
    execute_events(config, events, metadata={'options': 'test_circuit'})


def cell_paint(config: RuntimeConfig, protocol_config: ProtocolConfig, *, batch_sizes: list[int], short_test_paint: bool = False) -> None:
    events = eventlist(batch_sizes, protocol_config=protocol_config, short_test_paint=short_test_paint)
    # pr(events)
    metadata: dict[str, str] = {
        'batch_sizes': ','.join(str(bs) for bs in batch_sizes),
    }

    if short_test_paint:
        metadata = {
            **metadata,
            'options': 'short_test_paint'
        }
        robots.test_comm(config)
        ATTENTION('''
            Short test paint mode, NOT real cell painting
        ''')

    runtime = execute_events(config, events, metadata)
    for k, v in sorted(runtime.times.items(), key=lambda s: ' '.join(s[0].split(' ')[2:] + s[0].split(' ')[:2])):
        print(k, v)

from collections import defaultdict

@dataclass(frozen=True)
class Ids:
    counts: dict[str, int] = field(default_factory=lambda: defaultdict[str, int](int))

    def next(self, prefix: str = ''):
        self.counts[prefix] += 1
        return prefix + str(self.counts[prefix])

from robots import Symbolic
from z3 import * # type: ignore

def constraints(events: list[Event]) -> dict[str, float]:
    variables: set[str] = {
        v
        for e in events
        for v in robots.vars_of(e.command)
    }
    if not variables:
        return {}
    ids = Ids()

    var = Symbolic.var
    const = Symbolic.const

    last_main: Symbolic = const(0)
    last_wash: Symbolic = const(0)
    last_disp: Symbolic = const(0)
    last_incu: Symbolic = const(0)
    checkpoints: dict[str, Symbolic] = {}

    C: list[
        tuple[Symbolic, Literal['>', '>=', '=='], Symbolic] |
        tuple[Symbolic, Literal['== max'], Symbolic, Symbolic]
    ] = []

    def tag(cmd: robots.checkpoint_cmd | robots.wait_for_checkpoint_cmd | robots.idle_cmd, base: Symbolic) -> Symbolic:
        if isinstance(cmd, robots.checkpoint_cmd):
            if cmd.kind == 'info':
                v = checkpoints[cmd.name] = var(ids.next(cmd.name + ' '))
                C.append((v, '==', base))
                return v
            elif cmd.kind == 'begin':
                if cmd.strict:
                    assert cmd.name not in checkpoints, utils.pr((cmd.name, checkpoints, cmd, base))
                v = checkpoints[cmd.name] = var(ids.next(cmd.name + ' '))
                C.append((v, '==', base))
                return v
            elif cmd.kind == 'end':
                try:
                    v = checkpoints.pop(cmd.name)
                    vd = var(ids.next(cmd.name + ' duration '))
                    C.append((v + vd, '==', base))
                except KeyError:
                    if cmd.strict:
                        raise
                return base
            else:
                raise ValueError(cmd.kind)
        elif isinstance(cmd, robots.wait_for_checkpoint_cmd):
            if cmd.name not in checkpoints:
                assert cmd.or_now
                return base
            else:
                C.append((checkpoints[cmd.name] + cmd.plus_seconds, '>=', base))
                if cmd.strict:
                    C.append((checkpoints[cmd.name] + cmd.plus_seconds, '==', base))
                return checkpoints[cmd.name] + cmd.plus_seconds
        else:
            assert isinstance(cmd, robots.idle_cmd)
            return base + cmd.seconds

    for e in events:
        cmd = e.command
        if isinstance(cmd, robots.robotarm_cmd):
            last_main = last_main + cmd.est()
        elif isinstance(cmd, robots.wait_for_ready_cmd):
            v: Symbolic
            if cmd.machine == 'incu':
                v = last_incu
            elif cmd.machine == 'disp':
                v = last_disp
            elif cmd.machine == 'wash':
                v = last_wash
            else:
                raise ValueError
            wait = var(ids.next(f'{cmd.machine} wait '))
            C.append((wait, '== max', last_main, v))
            last_main = wait
        elif isinstance(cmd, robots.wash_cmd):
            base = last_main
            for c in cmd.before:
                base = tag(c, base)
            C.append((base, '>=', last_wash))
            base = base + cmd.est()
            for c in cmd.after:
                base = tag(c, base)
            last_wash = base
        elif isinstance(cmd, robots.disp_cmd):
            base = last_main
            for c in cmd.before:
                base = tag(c, base)
            C.append((base, '>=', last_disp))
            base = base + cmd.est()
            for c in cmd.after:
                base = tag(c, base)
            last_disp = base
        elif isinstance(cmd, robots.incu_cmd):
            base = last_main
            C.append((base, '>=', last_incu))
            base = base + cmd.est()
            for c in cmd.after:
                base = tag(c, base)
            last_incu = base
        elif isinstance(cmd, (robots.checkpoint_cmd, robots.wait_for_checkpoint_cmd, robots.idle_cmd)):
            last_main = tag(cmd, last_main)
        else:
            raise ValueError

    s: Any = Optimize()

    vs: set[str] = set()

    R = 1

    def to_expr(x: Symbolic) -> Any:
        for v in x.var_names:
            vs.add(v)
            # s.add(Real(v) >= 0)
        return Sum(
            int(x.offset * R),
            *[Real(v) for v in x.var_names]
        )

    with utils.timeit('constrs'):
        for i, (lhs, op, *rhss) in enumerate(C):
            # print(i, lhs, op, *rhss)
            rhs, *_ = rhss
            if op == '==':
                s.add(to_expr(lhs) == to_expr(rhs))
            elif op == '>':
                s.add(to_expr(lhs) > to_expr(rhs))
            elif op == '>=':
                s.add(to_expr(lhs) >= to_expr(rhs))
            elif op == '== max':
                a, b = rhss
                s.add(to_expr(lhs) == If(to_expr(a) > to_expr(b), to_expr(a), to_expr(b)))
            else:
                raise ValueError(op)

    maxi: list[tuple[float, str]] = []
    maxi += [(1, a) for a in vs if 'duration' in a and 'lid on' in a]
    maxi += [(10, a) for a in vs if 'duration' in a and 'incubator' in a]
    maxi += [(-100, a) for a in vs if 'duration' in a and 'transfer' in a]
    maxi += [(-0.1, a) for a in vs if 'duration' in a and 'batch' in a]

    # maxi += [(-1, a) for a in vs if 'duration' in a and 'batch sep' in a]

    utils.pr(maxi)

    transfers = [
        a
        for a in vs
        if 'transfer' in a and 'duration' in a
    ]

    batch_sep = 120 # for v3 jump
    s.add(Real('batch sep') == batch_sep * 60 * R)

    s.maximize(Sum(*[m * Real(v) for m, v in maxi]))

    print(s.check())

    M = s.model()

    def get(a: str) -> float:
        return float(M.eval(Real(a)).as_decimal(3).strip('?')) / R

    us = [
        (a, get(a))
        for a in vs
        if 'delay' in a or 'batch' in a
    ]
    for a, v in sorted(us):
        print(a, v, sep='\t')
    print()
    us = [
        (a, get(a))
        for a in maxi
        if 'lid' in a
    ]
    for a, v in sorted(us):
        print(a, v, sep='\t')
    print()
    us = [
        (a, get(a))
        for a in maxi
        if 'incubator' in a
    ]
    for a, v in sorted(us):
        print(a, v, sep='\t')

    res = {
        **{
            a: get(a)
            for a in variables & vs
        },
        **{
            a: 0
            for a in variables - vs
        }
    }
    return res

import contextlib

@contextlib.contextmanager
def make_runtime(config: RuntimeConfig, metadata: dict[str, str]) -> Iterator[Runtime]:
    metadata = {
        'start_time': str(datetime.now()).split('.')[0],
        **metadata,
        'config_name': config.name(),
    }
    if config.log_to_file:
        log_filename = ' '.join(['event log', *metadata.values()])
        log_filename = 'logs/' + log_filename.replace(' ', '_') + '.jsonl'
        os.makedirs('logs/', exist_ok=True)

        print(f'{log_filename=}')
    else:
        log_filename = None

    runtime = robots.Runtime(config=config, log_filename=log_filename)
    # pr(robots.Estimates)

    metadata['git_HEAD'] = utils.git_HEAD() or ''
    metadata['host']     = platform.node()
    with runtime.excepthook():
        with runtime.timeit('experiment', metadata=metadata):
            yield runtime

def execute_events(config: RuntimeConfig, events: list[Event], metadata: dict[str, str]) -> Runtime:
    with utils.timeit('constraints'):
        d = constraints(events)
    pr(d)
    with make_runtime(config, metadata) as runtime:
        runtime.var_values.update(d)
        execute_events_in_runtime(runtime, events)
        return runtime

