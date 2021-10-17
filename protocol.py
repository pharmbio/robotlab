from __future__ import annotations
from typing import Any, Generic, TypeVar, Iterable, Iterator
from dataclasses import *

from datetime import datetime, timedelta
from collections import defaultdict, Counter

import graphlib
import json
import os
import platform
import protocol
import re
import sys
import textwrap
import threading
import traceback

from commands import (
    Command,
    Fork,
    Checkpoint,
    Duration,
    Idle,
    Sequence,
    WashCmd,
    DispCmd,
    IncuCmd,
    WashFork,
    DispFork,
    IncuFork,
    RobotarmCmd,
    WaitForCheckpoint,
    WaitForResource,
)
from moves import movelists
from runtime import RuntimeConfig, Runtime, configs
import commands
import moves

from utils import pr, show, Mutable
import utils

from symbolic import Symbolic

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
    wash:          Steps[str]
    prime:         Steps[str]
    pre_disp:      Steps[str]
    disp:          Steps[str]
    post_disp:     Steps[str]
    incu:          Steps[float | Symbolic]
    interleavings: Steps[str]
    prep_wash:     str | None = None
    prep_disp:     str | None = None

linear_interleavings = Steps(
    Mito   = 'lin',
    PFA    = 'lin',
    Triton = 'lin',
    Stains = 'lin',
    Final  = 'finlin',
)

june_interleavings = Steps(
    Mito   = 'june',
    PFA    = 'june',
    Triton = 'june',
    Stains = 'june',
    Final  = 'finjune',
)

proto_v3 = ProtocolConfig(
    prep_wash='automation_v3.1/0_W_D_PRIME.LHC',
    prep_disp=None,
    wash = Steps(
        'automation_v3.1/1_W-2X_beforeMito_leaves20ul.LHC',
        'automation_v3.1/3_W-3X_beforeFixation_leaves20ul.LHC',
        'automation_v3.1/5_W-3X_beforeTriton.LHC',
        'automation_v3.1/7_W-3X_beforeStains.LHC',
        'automation_v3.1/9_W-5X_NoFinalAspirate.LHC',
    ),
    prime = Steps(
        'automation_v3.1/1_D_P1_MIX_PRIME.LHC',
        'automation_v3.1/3_D_SA_PRIME.LHC',
        'automation_v3.1/5_D_SB_PRIME.LHC',
        'automation_v3.1/7_D_P2_MIX_PRIME.LHC',
        '',
    ),
    pre_disp = Steps(
        'automation_v3.1/2_D_P1_purge_then_prime.LHC',
        '',
        '',
        'automation_v3.1/8_D_P2_purge_then_prime.LHC',
        '',
    ),
    disp = Steps(
        'automation_v3.1/2_D_P1_40ul_mito.LHC',
        'automation_v3.1/4_D_SA_384_80ul_PFA.LHC',
        'automation_v3.1/6_D_SB_384_80ul_TRITON.LHC',
        'automation_v3.1/8_D_P2_20ul_stains.LHC',
        '',
    ),
    post_disp = Steps(
        '',
        '',
        '',
        '',
        '',
    ),
    incu = Steps(1200, 1200, 1200, 1200, 0),
    # incu = Steps(Symbolic.var('seconds incu 1'), Symbolic.var('seconds incu 2'), Symbolic.var('seconds incu 3'), Symbolic.var('seconds incu 4'), 0),
    interleavings = linear_interleavings,
    # interleavings = june_interleavings,
)

def make_v3(incu_csv: str, linear: bool) -> ProtocolConfig:
    incu = [
        Symbolic.wrap(
            float(s) if re.match(r'\d', s) else s
        )
        for s in incu_csv.split(',')
    ]
    incu = incu + [incu[-1]] * 4
    incu = incu[:4] + [Symbolic.wrap(0)]
    return replace(
        proto_v3,
        incu = Steps(*incu),
        interleavings = linear_interleavings if linear else june_interleavings
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
    protocol_config = replace(
        protocol_config,
        incu=Steps(
            Symbolic.var('incu 1'),
            Symbolic.var('incu 2'),
            Symbolic.var('incu 3'),
            Symbolic.var('incu 4'),
            Symbolic.var('incu 5'),
        )
    )
    events = eventlist([1], protocol_config=protocol_config, sleek=True)
    events = [
        e
        for e in events
        for c in [e.command]
        if not isinstance(c, IncuCmd)
        if not isinstance(c, Fork) or c.resource != 'incu'
        if not isinstance(c, WaitForResource) or c.resource != 'incu'
        if not isinstance(c, Duration) or '37C' not in c.name
        if not isinstance(c, RobotarmCmd) or any(
            needle in c.program_name
            for needle in ['wash', 'disp']
        )
    ]
    ATTENTION(time_bioteks.__doc__ or '')
    execute_events(config, events, metadata={'program': 'time_bioteks'})

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
    IncuLocs = 16
    N = 8
    incu: list[Command] = []
    for loc in incu_locs[:IncuLocs]:
        incu += [
            commands.IncuCmd('put', loc),
            commands.IncuCmd('get', loc),
        ]
    arm: list[Command] = []
    plate = Plate('', '', '', '', '', 1)
    for lid_loc in lid_locs[:N]:
        plate = replace(plate, lid_loc=lid_loc)
        arm += [
            *RobotarmCmds(plate.lid_put),
            *RobotarmCmds(plate.lid_get),
        ]
    for rt_loc in rt_locs[:N]:
        plate = replace(plate, rt_loc=rt_loc)
        arm += [
            *RobotarmCmds(plate.rt_put),
            *RobotarmCmds(plate.rt_get),
        ]
    for out_loc in out_locs[:N]:
        plate = replace(plate, out_loc=out_loc)
        arm += [
            *RobotarmCmds(plate.out_put),
            *RobotarmCmds(plate.out_get),
        ]
    plate = replace(plate, lid_loc=lid_locs[0], rt_loc=rt_locs[0])
    arm2: list[Command] = [
        *RobotarmCmds(plate.rt_put),
        *RobotarmCmds('incu get'),
        *RobotarmCmds(plate.lid_put),
        *RobotarmCmds('wash put'),
        *RobotarmCmds('wash_to_disp'),
        *RobotarmCmds('disp get'),
        *RobotarmCmds('wash put'),
        *RobotarmCmds('wash get'),
        *RobotarmCmds('B15 put'),
        *RobotarmCmds('wash15 put'),
        *RobotarmCmds('wash15 get'),
        *RobotarmCmds('B15 get'),
        *RobotarmCmds(plate.lid_get),
        *RobotarmCmds('incu put'),
        *RobotarmCmds(plate.rt_get),
    ]
    ATTENTION(time_arm_incu.__doc__ or '')
    cmds: list[Command] = [
        Fork(Sequence(*incu), resource='incu'),
        *arm,
        WaitForResource('incu'),
        *sleek_commands(arm2),
        *arm2,
    ]
    execute_commands(config, cmds, metadata={'program': 'time_arm_incu'})

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
            *RobotarmCmds(p.lid_put),
            *RobotarmCmds(p.lid_get),
            *RobotarmCmds(p.rt_put),
            *RobotarmCmds(p.rt_get),
            *RobotarmCmds(p.lid_put),
            *RobotarmCmds(p.lid_get),
            *RobotarmCmds(p.out_put),
            *RobotarmCmds(p.out_get),
        ]
        events += [
            Event(p.id, str(i), '', cmd)
            for cmd in commands
        ]
    events = sleek_events(events)
    ATTENTION(lid_stress_test.__doc__ or '')
    execute_events(config, events, {'program': 'lid_stress_test'})

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
        cmds = [
            RobotarmCmd(f'incu_A{pos} put prep'),
            RobotarmCmd(f'incu_A{pos} put transfer to drop neu'),
            WaitForResource('incu'),
            RobotarmCmd(f'incu_A{pos} put transfer from drop neu'),
            IncuFork('put', p.incu_loc),
            RobotarmCmd(f'incu_A{pos} put return'),
        ]
        events += [
            Event(p.id, 'incu load', '', cmd)
            for cmd in cmds
        ]
    events = [
        Event('', 'load incu', 'prep', RobotarmCmd('incu_A21 put-prep')),
        *events,
        Event('', 'load incu', 'return', RobotarmCmd('incu_A21 put-return'))
    ]
    ATTENTION(load_incu.__doc__ or '')
    execute_events(config, events, {'program': 'load_incu'})

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
        cmds = [
            IncuFork('put', p.incu_loc),
            RobotarmCmd(f'incu_A{pos} get prep'),
            WaitForResource('incu'),
            RobotarmCmd(f'incu_A{pos} get transfer'),
            RobotarmCmd(f'incu_A{pos} get return'),
        ]
        events += [
            Event(p.id, 'unload', '', cmd)
            for cmd in cmds
        ]
    events = [
        *events,
    ]
    ATTENTION(unload_incu.__doc__ or '')
    execute_events(config, events, {'program': 'unload_incu'})

@dataclass(frozen=True)
class Event:
    plate_id: str
    part: str
    subpart: str
    command: commands.Command

    def desc(self):
        return {
            'event_plate_id': self.plate_id,
            'event_part': self.part,
            'event_subpart': self.subpart,
        }

    @staticmethod
    def wrap(commands: Command | list[Command], plate_id: str='', part: str='', subpart: str=''):
        if isinstance(commands, Command):
            commands = [commands]
        return [Event(plate_id, part, subpart, command) for command in commands]

def execute_events_in_runtime(runtime: Runtime, events: list[Event]) -> None:
    for i, event in enumerate(events):
        metadata: dict[str, str | int] = {
            'event_index': i,
            **event.desc(),
        }
        event.command.execute(runtime, metadata)

Desc = tuple[Plate, str, str]

def RobotarmCmds(s: str, before_pick: list[Command] = [], after_drop: list[Command] = []) -> list[Command]:
    return [
        commands.RobotarmCmd(s + ' prep'),
        *before_pick,
        commands.RobotarmCmd(s + ' transfer'),
        *after_drop,
        commands.RobotarmCmd(s + ' return'),
    ]

def Early(secs: float):
    return Idle(secs=secs, only_for_scheduling=True)

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
    incu -> B21
            B21 -> wash
    incu -> B21
                   wash -> B15
            B21 -> wash
                           B15 -> out
    incu -> B21
                   wash -> B15
            B21 -> wash
                           B15 -> out
                   wash -> B15
                           B15 -> out
''')

Interleavings = {k: v for k, v in globals().items() if isinstance(v, Interleaving)}

def paint_batch(batch: list[Plate], protocol_config: ProtocolConfig):

    p = protocol_config

    prep_wash = WashFork(p.prep_wash) if p.prep_wash else Idle()
    prep_disp = DispFork(p.prep_disp) + 2 if p.prep_disp else Idle()
    prep_cmds: list[Command] = [
        prep_wash,
        prep_disp,
        # WaitForResource('wash'),
        # WaitForResource('disp'),
    ]

    first_plate = batch[0]
    last_plate = batch[-1]
    batch_index = first_plate.batch_index
    first_batch = batch_index == 0

    if not first_batch:
        prep_cmds += [
            WaitForCheckpoint(f'batch {batch_index-1}') + Symbolic.var('batch sep'),
        ]

    prep_cmds += [
        Checkpoint(f'batch {batch_index}'),
    ]

    post_cmds = [
        Duration(f'batch {batch_index}', opt_weight=-10),
    ]

    parts: list[str] = ['Mito', 'PFA', 'Triton', 'Stains', 'Final']
    chunks: dict[Desc, Iterable[Command]] = {}
    for plate in batch:
        for i, part in enumerate(parts, start=1):
            plate_desc = f'plate {plate.id}'
            incu_delay: list[Command]
            if part == 'Mito':
                incu_delay = [
                    WaitForCheckpoint(f'batch {batch_index}') + f'{plate_desc} incu delay {i}'
                ]
            else:
                incu_delay = [
                    WaitForCheckpoint(f'{plate_desc} incubation {i-1}') + f'{plate_desc} incu delay {i}'
                ]

            wash_delay: list[Command]
            if part == 'Mito':
                wash_delay = [
                    WaitForCheckpoint(f'batch {batch_index}') + f'{plate_desc} first wash delay'
                ]
            else:
                wash_delay = [
                    Early(2),
                    WaitForCheckpoint(f'{plate_desc} incubation {i-1}') + p.incu[i-1]
                ]

            lid_off = [
                *RobotarmCmds(plate.lid_put, before_pick=[Checkpoint(f'{plate_desc} lid off {i}')]),
            ]

            lid_on = [
                *RobotarmCmds(plate.lid_get, after_drop=[Duration(f'{plate_desc} lid off {i}', opt_weight=-1)]),
            ]

            if part == 'Mito':
                incu_get = [
                    IncuFork('get', plate.incu_loc),
                    *RobotarmCmds('incu get', before_pick = [
                        WaitForResource('incu', assume='will wait'),
                    ]),
                    *lid_off,
                ]
            elif part == 'PFA':
                incu_get = [
                    IncuFork('get', plate.incu_loc),
                    *RobotarmCmds('incu get', before_pick = [
                        WaitForResource('incu', assume='will wait'),
                        Duration(f'{plate_desc} 37C', opt_weight=1),
                    ]),
                    *lid_off,
                ]
            else:
                incu_get = [
                    *RobotarmCmds(plate.rt_get),
                    *lid_off,
                ]

            if part == 'Mito':
                B21_to_incu = [
                    *RobotarmCmds('incu put',
                        before_pick = [
                            WaitForResource('incu', assume='nothing'),
                        ],
                        after_drop = [
                            Fork(
                                Sequence(
                                    IncuCmd('put', plate.incu_loc),
                                    Checkpoint(f'{plate_desc} 37C'),
                                ),
                                resource='incu',
                            )
                        ]
                    ),
                    # WaitForResource('incu'),
                ]
            else:
                B21_to_incu = [
                    *RobotarmCmds(plate.rt_put),
                ]

            if p.disp[i]:
                pre_disp = Fork(
                    Sequence(
                        WaitForCheckpoint(f'{plate_desc} pre disp {i}', assume='nothing'),
                        Idle() + f'{plate_desc} pre disp {i} delay',
                        DispCmd(p.pre_disp[i]) if p.pre_disp[i] else Idle(),
                        DispCmd(p.disp[i], cmd='Validate'),
                        Early(3),
                        Checkpoint(f'{plate_desc} pre disp done {i}'),
                    ),
                    resource='disp',
                    assume='nothing',
                )
                pre_disp_wait = Duration(f'{plate_desc} pre disp done {i}', opt_weight=-1)
            else:
                pre_disp = Idle()
                pre_disp_wait = Idle()

            if plate is first_plate:
                wash_prime = WashFork(p.wash[i], cmd='Validate', assume='nothing') + 2
            else:
                wash_prime = Idle()

            wash = [
                RobotarmCmd('wash put prep'),
                RobotarmCmd('wash put transfer'),
                # WaitForResource('wash'),
                Fork(
                    Sequence(
                        *wash_delay,
                        Duration(f'{plate_desc} incubation {i-1}', exactly=p.incu[i-1]) if 2 <= i <= 5 else Idle(),
                        Checkpoint(f'{plate_desc} pre disp {i}'),
                        WashCmd(p.wash[i], cmd='RunValidated'),
                        Checkpoint(f'{plate_desc} transfer {i}'),
                    ),
                    resource='wash',
                    assume='nothing',
                ),
                pre_disp,
                RobotarmCmd('wash put return'),
            ]

            if p.prime[i] and plate is first_plate:
                disp_prime = DispFork(
                    p.prime[i],
                    assume='nothing',
                )
            else:
                disp_prime = Idle()

            disp = [
                RobotarmCmd('wash_to_disp prep'),
                Early(1),
                WaitForResource('wash', assume='will wait'),
                RobotarmCmd('wash_to_disp transfer'),
                Duration(f'{plate_desc} transfer {i}', opt_weight=-1000),
                pre_disp_wait,
                Fork(
                    Sequence(
                        DispCmd(p.disp[i], cmd='RunValidated'),
                        Checkpoint(f'{plate_desc} disp {i} done'),
                        Checkpoint(f'{plate_desc} incubation {i}'),
                    ),
                    resource='disp',
                ),
                DispFork(p.post_disp[i]) if p.post_disp[i] else Idle(),
                RobotarmCmd('wash_to_disp return'),
            ]

            disp_to_B21 = [
                RobotarmCmd('disp get prep'),
                WaitForCheckpoint(f'{plate_desc} disp {i} done', report_behind_time=False, assume='nothing'),
                # WaitForResource('disp'),
                # Duration(f'{plate_desc} disp {i} done', opt_weight=0.0),
                # DispFork(p.disp.Stains),
                RobotarmCmd('disp get transfer'),
                RobotarmCmd('disp get return'),
                *lid_on,
            ]

            if part != 'Final':
                chunks[plate, part, 'incu -> B21' ] = [*incu_delay, disp_prime, wash_prime, *incu_get]
                chunks[plate, part,  'B21 -> wash'] = wash
                chunks[plate, part, 'wash -> disp'] = disp
                chunks[plate, part, 'disp -> B21' ] = disp_to_B21
                chunks[plate, part,  'B21 -> incu'] = B21_to_incu
            else:
                chunks[plate, 'Final', 'incu -> B21' ] = [*incu_delay, wash_prime, *incu_get]
                chunks[plate, 'Final',  'B21 -> wash'] = wash
                chunks[plate, 'Final', 'wash -> B21' ] = RobotarmCmds('wash get', before_pick=[WaitForResource('wash')])
                chunks[plate, 'Final',  'B21 -> out' ] = [*lid_on, *RobotarmCmds(plate.out_put)]
                chunks[plate, 'Final', 'wash -> B15' ] = RobotarmCmds('wash15 get', before_pick=[WaitForResource('wash')])
                chunks[plate, 'Final',  'B15 -> out' ] = [*RobotarmCmds('B15 get'), *lid_on, *RobotarmCmds(plate.out_put)]

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

    for part, next_part in utils.iterate_with_next(parts):
        if next_part:
            seq([
                desc(last_plate, part, 'B21 -> incu'),
                desc(first_plate, next_part, 'incu -> B21'),
            ])

    if 0:
        ilvs = {
            'Mito':   'lin',
            'PFA':    'lin',
            'Triton': 'lin',
            'Stains': 'lin',
            'Final':  'finlin',
        }

    ilvs = p.interleavings.asdict()

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

    if 0:
        for d, ds in deps.items():
            for x in ds:
                print(
                    ', '.join((x[1], x[0].id, x[2])),
                    '<',
                    ', '.join((d[1], d[0].id, d[2]))
                )

    linear = list(graphlib.TopologicalSorter(deps).static_order())

    if 0:
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

    # for e in plate_events:
    #     print(e)

    prep_events: list[Event] = [ Event('', 'prep', '', cmd) for cmd in prep_cmds ]
    post_events: list[Event] = [ Event('', '', '', cmd) for cmd in post_cmds ]

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
        if isinstance(event.command, commands.RobotarmCmd):
            return movelists[event.command.program_name]
        else:
            return None
    return moves.sleek_movements(events, get_movelist)

def sleek_commands(cmds: list[Command]) -> list[Command]:
    def get_movelist(cmd: Command) -> moves.MoveList | None:
        if isinstance(cmd, commands.RobotarmCmd):
            return movelists[cmd.program_name]
        else:
            return None
    return moves.sleek_movements(cmds, get_movelist)

def eventlist(batch_sizes: list[int], protocol_config: ProtocolConfig, sleek: bool = True) -> list[Event]:
    all_events: list[Event] = [
        Event('', 'prep', '', Checkpoint('run')),
    ]
    all_events += test_comm_events
    for batch in group_by_batch(define_plates(batch_sizes)):
        events = paint_batch(
            batch,
            protocol_config=protocol_config,
        )
        if sleek:
            events = sleek_events(events)
        all_events += events
    all_events += [
        Event('', '', '', Duration('run')),
    ]
    return all_events

def test_circuit(config: RuntimeConfig) -> None:
    '''
    Test circuit: Short test paint on one plate, without incubator
    '''
    plate, = define_plates([1])
    events = eventlist([1], protocol_config=make_v3('secs', linear=False))
    events = [
        event
        for event in events
        if isinstance(event.command, commands.RobotarmCmd)
        if event.part not in {'Triton', 'Stains'}
    ] + Event.wrap([
            *RobotarmCmds(plate.out_get),
            *RobotarmCmds('incu put')
        ],
        plate_id=plate.id,
        part='return'
    )
    events = sleek_events(events)
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
    execute_events(config, events, metadata={'program': 'test_circuit'})

test_comm_cmds: list[Command] = [
    DispFork(cmd='TestCommunications', protocol_path=None),
    IncuFork(action='get_climate', incu_loc=None),
    RobotarmCmd('gripper check'),
    WaitForResource('disp'),
    WashFork(cmd='TestCommunications', protocol_path=None),
    WaitForResource('incu'),
    WaitForResource('wash'),
]

test_comm_events = Event.wrap(test_comm_cmds, part='test comm')

def test_comm(config: RuntimeConfig):
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    print('Testing communication with robotarm, washer, dispenser and incubator.')
    execute_events(config, test_comm_events, {'program': 'test_comm'})
    print('Communication tests ok.')

def cell_paint(config: RuntimeConfig, protocol_config: ProtocolConfig, *, batch_sizes: list[int]) -> None:
    events = eventlist(batch_sizes, protocol_config=protocol_config)
    # pr(events)
    metadata: dict[str, str] = {
        'program': 'cell_paint',
        'batch_sizes': ','.join(str(bs) for bs in batch_sizes),
    }

    runtime = execute_events(config, events, metadata)
    for k, vs in group_times(runtime.times).items():
        print(k, '[' + ', '.join(vs) + ']')

def group_times(times: dict[str, list[float]]):
    groups = utils.group_by(list(times.items()), key=lambda s: s[0].rstrip(' 0123456789'))
    out: dict[str, list[str]] = {}
    def key(kv: tuple[str, Any]):
        s, _ = kv
        if s.startswith('plate'):
            plate, i, *what = s.split(' ')
            return f' plate {" ".join(what)} {int(i):03}'
        else:
            return s
    for k, vs in sorted(groups.items(), key=key):
        out[k] = [utils.pp_secs(v) for _, [v] in vs]
    return out

import contextlib

@contextlib.contextmanager
def make_runtime(config: RuntimeConfig, metadata: dict[str, str], *, log_to_file: bool=True, execute_scheduling_idles: bool=False) -> Iterator[Runtime]:
    metadata = {
        'start_time': str(datetime.now()).split('.')[0],
        **metadata,
        'config_name': config.name(),
    }
    if log_to_file:
        log_filename = ' '.join(['event log', *metadata.values()])
        log_filename = 'logs/' + log_filename.replace(' ', '_') + '.jsonl'
        os.makedirs('logs/', exist_ok=True)

        print(f'{log_filename=}')
    else:
        log_filename = None

    runtime = Runtime(config=config, log_filename=log_filename, execute_scheduling_idles=execute_scheduling_idles)
    # pr(commands.Estimates)

    metadata['git_HEAD'] = utils.git_HEAD() or ''
    metadata['host']     = platform.node()
    with runtime.excepthook():
        with runtime.timeit('run', metadata=metadata):
            yield runtime

import constraints

def execute_events(config: RuntimeConfig, events: list[Event], metadata: dict[str, str], log_to_file: bool = True) -> Runtime:
    with utils.timeit('constraints'):
        cmd = constraints.optimize(Sequence(*[e.command for e in events]))

    with make_runtime(config, metadata, log_to_file=log_to_file) as runtime:
        cmd.execute(runtime, {})
        # execute_command_in_runtime(runtime, cmd)
        ret = runtime

    if 0 and config.name() != 'live':
        with make_runtime(configs['dry-run'], {}, log_to_file=False, execute_scheduling_idles=True) as runtime:
            runtime.var_values.update(d)
            execute_events_in_runtime(runtime, events)
            entries = runtime.log_entries
            matches = 0
            mismatches = 0
            for e in entries:
                i = e.get('event_index')
                if 'idle_cmd' in str(e.get('arg',  '')):
                    continue
                if e.get('origin'):
                    continue
                if e['kind'] == 'end' and i:
                    if abs(e['t'] - ends[i]) > 0.1:
                        utils.pr(('no match!', i, e, ends[i]))
                        mismatches += 1
                    else:
                        matches += 1
                    # utils.pr((f'{matches=}', i, e, ends[i]))
            if mismatches or not matches:
                print(f'{matches=} {mismatches=} {len(ends)=}')

    # utils.pr(d)

    return ret

def execute_commands(config: RuntimeConfig, cmds: list[Command], metadata: dict[str, Any]={}) -> None:
    execute_events(config, [Event('', '', '', cmd) for cmd in cmds], metadata=metadata)

