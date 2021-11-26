from __future__ import annotations
from typing import Any, TypeVar, Iterable, Iterator
from dataclasses import *

from collections import defaultdict, Counter

import contextlib
import graphlib
import os
import pickle
import platform
import re
import textwrap

from commands import (
    Command,
    Fork,
    Info,
    Meta,
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
from runtime import RuntimeConfig, Runtime, dry_run
from symbolic import Symbolic
import commands
import constraints
import moves

import utils

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

A_locs:    list[str] = [f'A{i}' for i in H]
B_locs:    list[str] = [f'B{i}' for i in H]
C_locs:    list[str] = [f'C{i}' for i in H]

Incu_locs: list[str] = [f'L{i}' for i in I] + [f'R{i}' for i in I]
RT_locs_few:  list[str] = C_locs[:4] + A_locs[:4]    # up to 8 plates
RT_locs_many: list[str] = C_locs[:5] + A_locs[:5] + [B_locs[4]]
Out_locs:  list[str] = A_locs[5:][::-1] + B_locs[5:][::-1] + C_locs[5:][::-1]
Lid_locs:  list[str] = [b for b in B_locs if '19' in b or '17' in b]

A = TypeVar('A')

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

washlin = Interleaving.init('''
    incu -> B21 -> wash -> B21 -> incu
    incu -> B21 -> wash -> B21 -> incu
''')

washjune = Interleaving.init('''
    incu -> B21 -> wash
    incu -> B21
                   wash -> B15
            B21 -> wash
                           B15 -> B21 -> incu
    incu -> B21
                   wash -> B15
            B21 -> wash
                           B15 -> B21 -> incu
                   wash -> B15
                           B15 -> B21 -> incu
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
                           B15 -> B21 -> out
    incu -> B21
                   wash -> B15
            B21 -> wash
                           B15 -> B21 -> out
                   wash -> B15
                           B15 -> B21 -> out
''')

Interleavings = {k: v for k, v in globals().items() if isinstance(v, Interleaving)}


@dataclass(frozen=True)
class ProtocolConfig:
    step_names:    list[str]
    wash:          list[str]
    prime:         list[str]
    pre_disp:      list[str]
    disp:          list[str]
    incu:          list[Symbolic]
    interleavings: list[str]
    interleave:    bool
    lockstep:      bool
    prep_wash:     str | None = None
    prep_disp:     str | None = None
    def __post_init__(self):
        d: dict[str, list[Any]] = {}
        for field in fields(self):
            k = field.name
            v = getattr(self, k)
            if isinstance(v, list):
                d[k] = v
        for ka, kb in utils.iterate_with_next(list(d.items())):
            if kb:
                _, a = ka
                _, b = kb
                assert len(a) == len(b), f'{ka} and {kb} do not have same lengths'
        for ilv in self.interleavings:
            assert ilv in Interleavings

def make_v3(*, incu_csv: str, interleave: bool, six: bool = False, lockstep: bool = False):
    N = 6 if six else 5

    incu = [
        Symbolic.wrap(
            float(m.group(1)) * 60 + float(m.group(2))
            if (m := re.match(r'(\d+):(\d\d)$', s)) else
            float(s)
            if re.match(r'\d', s)
            else s
        )
        for s in utils.read_commasep(incu_csv)
    ]
    incu = incu + [incu[-1]] * N
    incu = incu[:N-1] + [Symbolic.wrap(0)]

    interleavings: list[str]
    if six:
        if interleave:
            interleavings = 'june june june june washjune finjune'.split()
        else:
            interleavings = 'lin  lin  lin  lin  washlin  finlin'.split()
    else:
        if interleave:
            interleavings = 'june june june june finjune'.split()
        else:
            interleavings = 'lin  lin  lin  lin  finlin'.split()

    return ProtocolConfig(
        prep_wash='automation_v3.1/0_W_D_PRIME.LHC',
        prep_disp=None,
        step_names=
            ['Mito', 'PFA', 'Triton', 'Stains', 'Wash 1', 'Final']
            if six else
            ['Mito', 'PFA', 'Triton', 'Stains', 'Final'],
        wash = [
            'automation_v3.1/1_W-2X_beforeMito_leaves20ul.LHC',
            'automation_v3.1/3_W-3X_beforeFixation_leaves20ul.LHC',
            'automation_v3.1/5_W-3X_beforeTriton.LHC',
            'automation_v3.1/7_W-3X_beforeStains.LHC',
        ] + (
            ['automation_v3.1/9_10_W-3X_NoFinalAspirate.LHC'] * 2
            if six else
            ['automation_v3.1/9_W-5X_NoFinalAspirate.LHC']
        ),
        prime = [
            'automation_v3.1/1_D_P1_MIX_PRIME.LHC',
            'automation_v3.1/3_D_SA_PRIME.LHC',
            'automation_v3.1/5_D_SB_PRIME.LHC',
            'automation_v3.1/7_D_P2_MIX_PRIME.LHC',
            '',
            '',
        ][:N],
        pre_disp = [
            'automation_v3.1/2_D_P1_purge_then_prime.LHC',
            '',
            '',
            'automation_v3.1/8_D_P2_purge_then_prime.LHC',
            '',
            '',
        ][:N],
        disp = [
            'automation_v3.1/2_D_P1_40ul_mito.LHC',
            'automation_v3.1/4_D_SA_384_80ul_PFA.LHC',
            'automation_v3.1/6_D_SB_384_80ul_TRITON.LHC',
            'automation_v3.1/8_D_P2_20ul_stains.LHC',
            '',
            '',
        ][:N],
        lockstep = lockstep,
        incu = incu,
        interleave = interleave,
        interleavings = interleavings,
    )

def test_make_v3():
    for incu_csv in ['i1, i2, i3', '21:00,20:00', '1200']:
        for six in [True, False]:
            for interleave in [True, False]:
                make_v3(incu_csv=incu_csv, six=six, interleave=interleave)

test_make_v3()

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
        incu=[
            Symbolic.var(f'incu {i}')
            for i, _ in enumerate(protocol_config.incu)
        ]
    )
    program = cell_paint_program([1], protocol_config=protocol_config, sleek=True)
    program = Sequence(
        *(
            cmd.with_metadata(metadata)
            for cmd, metadata in program.collect()
            if not isinstance(cmd, IncuCmd)
            if not isinstance(cmd, Fork) or cmd.resource != 'incu'
            if not isinstance(cmd, WaitForResource) or cmd.resource != 'incu'
            if not isinstance(cmd, Duration) or '37C' not in cmd.name
            if not isinstance(cmd, RobotarmCmd) or any(
                needle in cmd.program_name
                for needle in ['wash', 'disp']
            )
        )
    )
    ATTENTION(time_bioteks.__doc__ or '')
    execute_program(config, program, metadata={'program': 'time_bioteks'})

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
    for loc in Incu_locs[:IncuLocs]:
        incu += [
            commands.IncuCmd('put', loc),
            commands.IncuCmd('get', loc),
        ]
    arm: list[Command] = []
    plate = Plate('', '', '', '', '', 1)
    for lid_loc in Lid_locs[:N]:
        plate = replace(plate, lid_loc=lid_loc)
        arm += [
            *RobotarmCmds(plate.lid_put),
            *RobotarmCmds(plate.lid_get),
        ]
    for rt_loc in RT_locs_many[:N]:
        plate = replace(plate, rt_loc=rt_loc)
        arm += [
            *RobotarmCmds(plate.rt_put),
            *RobotarmCmds(plate.rt_get),
        ]
    for out_loc in Out_locs[:N]:
        plate = replace(plate, out_loc=out_loc)
        arm += [
            *RobotarmCmds(plate.out_put),
            *RobotarmCmds(plate.out_get),
        ]
    plate = replace(plate, lid_loc=Lid_locs[0], rt_loc=RT_locs_many[0])
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
        sleek_program(Sequence(*arm2)),
        *arm2,
    ]
    program = Sequence(*cmds)
    execute_program(config, program, metadata={'program': 'time_arm_incu'})

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
    cmds: list[Command] = []
    for i, (lid, A, C) in enumerate(zip(Lid_locs, A_locs, C_locs)):
        p = Plate('p', incu_loc='', rt_loc=C, lid_loc=lid, out_loc=A, batch_index=1)
        cmds += [
            *RobotarmCmds(p.lid_put),
            *RobotarmCmds(p.lid_get),
            *RobotarmCmds(p.rt_put),
            *RobotarmCmds(p.rt_get),
            *RobotarmCmds(p.lid_put),
            *RobotarmCmds(p.lid_get),
            *RobotarmCmds(p.out_put),
            *RobotarmCmds(p.out_get),
        ]
    program = sleek_program(Sequence(*cmds))
    ATTENTION(lid_stress_test.__doc__ or '')
    execute_program(config, program, {'program': 'lid_stress_test'})

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
    cmds: list[Command] = []
    for i, (incu_loc, a_loc) in enumerate(zip(Incu_locs, A_locs[::-1]), start=1):
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
        cmds += [
            Sequence(*[
                RobotarmCmd(f'incu_A{pos} put prep'),
                RobotarmCmd(f'incu_A{pos} put transfer to drop neu'),
                WaitForResource('incu'),
                RobotarmCmd(f'incu_A{pos} put transfer from drop neu'),
                IncuFork('put', p.incu_loc),
                RobotarmCmd(f'incu_A{pos} put return'),
            ]).with_metadata(plate_id=p.id)
        ]
    program = Sequence(*[
        RobotarmCmd('incu_A21 put-prep'),
        *cmds,
        RobotarmCmd('incu_A21 put-return'),
        WaitForResource('incu'),
    ])
    ATTENTION(load_incu.__doc__ or '')
    execute_program(config, program, {'program': 'load_incu'})

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
    cmds: list[Command] = []
    for p in plates:
        assert p.out_loc.startswith('out')
        pos = p.out_loc.removeprefix('out')
        cmds += [
            IncuFork('put', p.incu_loc),
            RobotarmCmd(f'incu_A{pos} get prep'),
            WaitForResource('incu'),
            RobotarmCmd(f'incu_A{pos} get transfer'),
            RobotarmCmd(f'incu_A{pos} get return'),
        ]
    program = Sequence(*cmds)
    ATTENTION(unload_incu.__doc__ or '')
    execute_program(config, program, {'program': 'unload_incu'})

Desc = tuple[str, str, str]

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

def paint_batch(batch: list[Plate], protocol_config: ProtocolConfig) -> Command:

    p = protocol_config

    prep_wash = WashFork(p.prep_wash) if p.prep_wash else Idle()
    prep_disp = DispFork(p.prep_disp).delay(2) if p.prep_disp else Idle()
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

    def Section(section: str) -> Command:
        section = f'{section} {batch_index}'
        return Info(section).with_metadata(section=section, plate_id='')

    if not first_batch:
        prep_cmds += [
            WaitForCheckpoint(f'batch {batch_index-1}') + Symbolic.var('batch sep'),
        ]

    prep_cmds += [
        Checkpoint(f'batch {batch_index}'),
    ]

    post_cmds = [
        Duration(f'batch {batch_index}', opt_weight=-1),
    ]

    chunks: dict[Desc, Iterable[Command]] = {}
    if p.interleave:
        lid_locs = Lid_locs[:2]
    else:
        lid_locs = Lid_locs[:1]
    lid_index = 0
    for i, step in enumerate(p.step_names):
        for plate in batch:
            lid_loc = lid_locs[lid_index % len(lid_locs)]
            lid_index += 1
            plate_with_corrected_lid_pos= replace(plate, lid_loc=lid_loc)
            ix = i + 1
            plate_desc = f'plate {plate.id}'

            incu_delay: list[Command]
            wash_delay: list[Command]
            if step == 'Mito':
                incu_delay = [
                    WaitForCheckpoint(f'batch {batch_index}', report_behind_time=plate is not first_plate) + f'{plate_desc} incu delay {ix}'
                ]
                wash_delay = [
                    (WaitForCheckpoint(f'batch {batch_index}', report_behind_time=plate is not first_plate) + f'{plate_desc} first wash delay').with_metadata(log_sleep=True)
                ]
            else:
                incu_delay = [
                    WaitForCheckpoint(f'{plate_desc} incubation {ix-1}') + f'{plate_desc} incu delay {ix}'
                ]
                wash_delay = [
                    Early(2),
                    (WaitForCheckpoint(f'{plate_desc} incubation {ix-1}') + p.incu[i-1]).with_metadata(log_sleep=True)
                ]

            lid_off = [
                *RobotarmCmds(plate_with_corrected_lid_pos.lid_put, before_pick=[Checkpoint(f'{plate_desc} lid off {ix}')]),
            ]

            lid_on = [
                *RobotarmCmds(plate_with_corrected_lid_pos.lid_get, after_drop=[Duration(f'{plate_desc} lid off {ix}', opt_weight=-1).with_metadata(silent=True)]),
            ]

            if step == 'Mito':
                incu_get = [
                    WaitForResource('incu', assume='nothing'),
                    IncuFork('get', plate.incu_loc),
                    *RobotarmCmds('incu get', before_pick = [
                        WaitForResource('incu', assume='will wait'),
                    ]),
                    *lid_off,
                ]
            elif step == 'PFA':
                incu_get = [
                    WaitForResource('incu', assume='nothing'),
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

            if step == 'Mito':
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
                ]
            else:
                B21_to_incu = [
                    *RobotarmCmds(plate.rt_put),
                ]


            if p.prime[i] and plate is first_plate:
                disp_prime = p.prime[i]
            else:
                disp_prime = None

            if p.disp[i] or disp_prime:
                pre_disp = Fork(
                    Sequence(
                        WaitForCheckpoint(f'{plate_desc} pre disp {ix}', assume='nothing'),
                        Idle() + f'{plate_desc} pre disp {ix} delay',
                        DispCmd(disp_prime).with_metadata(plate_id='') if disp_prime else Idle(),
                        DispCmd(p.pre_disp[i]).with_metadata(predispense=True) if p.pre_disp[i] else Idle(),
                        DispCmd(p.disp[i], cmd='Validate'),
                        Early(2),
                        Checkpoint(f'{plate_desc} pre disp done {ix}'),
                    ).with_metadata(slot=3),
                    resource='disp',
                    assume='nothing',
                )
                pre_disp_wait = Duration(f'{plate_desc} pre disp done {ix}', opt_weight=-1).with_metadata(silent=True)
            else:
                pre_disp = Idle()
                pre_disp_wait = Idle()

            wash = [
                RobotarmCmd('wash put prep'),
                WashFork(p.wash[i], cmd='Validate', assume='idle').delay(1) if plate is first_plate else Idle(),
                RobotarmCmd('wash put transfer'),
                Fork(
                    Sequence(
                        *wash_delay,
                        Duration(f'{plate_desc} incubation {ix-1}', exactly=p.incu[i-1]) if i > 0 else Idle(),
                        Checkpoint(f'{plate_desc} pre disp {ix}').with_metadata(silent=True),
                        WashCmd(p.wash[i], cmd='RunValidated'),
                        Checkpoint(f'{plate_desc} transfer {ix}').with_metadata(silent=True)
                        if i < 4 else
                        Checkpoint(f'{plate_desc} incubation {ix}'),
                    ),
                    resource='wash',
                    assume='nothing',
                ),
                pre_disp,
                RobotarmCmd('wash put return'),
            ]

            disp = [
                RobotarmCmd('wash_to_disp prep'),
                Early(1),
                WaitForResource('wash', assume='will wait'),
                RobotarmCmd('wash_to_disp transfer'),
                Duration(f'{plate_desc} transfer {ix}', exactly=RobotarmCmd('wash_to_disp transfer').est()).with_metadata(silent=True),
                pre_disp_wait,
                Fork(
                    Sequence(
                        DispCmd(p.disp[i], cmd='RunValidated'),
                        Checkpoint(f'{plate_desc} disp {ix} done'),
                        Checkpoint(f'{plate_desc} incubation {ix}'),
                    ),
                    resource='disp',
                ),
                RobotarmCmd('wash_to_disp return'),
            ]

            disp_to_B21 = [
                RobotarmCmd('disp get prep'),
                WaitForCheckpoint(f'{plate_desc} disp {ix} done', report_behind_time=False, assume='nothing'),
                RobotarmCmd('disp get transfer'),
                RobotarmCmd('disp get return'),
            ]

            if plate is first_plate and step != 'Mito':
                section_info = Section(step)
            else:
                section_info = Idle()

            chunks[plate.id, step, 'incu -> B21' ] = [*incu_delay, section_info, *incu_get]
            chunks[plate.id, step,  'B21 -> wash'] = wash
            chunks[plate.id, step, 'wash -> disp'] = disp
            chunks[plate.id, step, 'disp -> B21' ] = [*disp_to_B21, *lid_on]

            chunks[plate.id, step, 'wash -> B21' ] = [*RobotarmCmds('wash get', before_pick=[WaitForResource('wash')]), *lid_on]
            chunks[plate.id, step, 'wash -> B15' ] = RobotarmCmds('wash15 get', before_pick=[WaitForResource('wash')])
            chunks[plate.id, step,  'B15 -> B21' ] = [*RobotarmCmds('B15 get'), *lid_on]

            chunks[plate.id, step,  'B21 -> incu'] = B21_to_incu
            chunks[plate.id, step,  'B21 -> out' ] = [*RobotarmCmds(plate.out_put)]

    adjacent: dict[Desc, set[Desc]] = defaultdict(set)

    def seq(descs: list[Desc | None]):
        filtered: list[Desc] = [ desc for desc in descs if desc ]
        for now, next in utils.iterate_with_next(filtered):
            if next:
                adjacent[now] |= {next}

    def desc(p: Plate | None, step: str, substep: str) -> Desc | None:
        if p is None:
            return None
        else:
            return p.id, step, substep

    if p.lockstep:
        for i, (step, next_step) in enumerate(utils.iterate_with_next(p.step_names)):
            if next_step:
                ilv = Interleavings[p.interleavings[i]]
                next_ilv = Interleavings[p.interleavings[i+1]]
                overlap = [
                    (batch[-2], step, {row_subpart for _, row_subpart in ilv.rows}),
                    (batch[-1], step, {row_subpart for _, row_subpart in ilv.rows}),
                    (batch[0], next_step, {row_subpart for _, row_subpart in next_ilv.rows}),
                    (batch[1], next_step, {row_subpart for _, row_subpart in next_ilv.rows}),
                ]
                for offset, _ in enumerate(overlap):
                    seq([
                        desc(p, step, substep=substep)
                        for i, substep in ilv.rows
                        if i + offset < len(overlap)
                        for p, step, subparts in [overlap[i + offset]]
                        if substep in subparts
                    ])
    else:
        for step, next_step in utils.iterate_with_next(p.step_names):
            if next_step:
                seq([
                    desc(last_plate, step, 'B21 -> incu'),
                    desc(first_plate, next_step, 'incu -> B21'),
                ])


    for i, step in enumerate(p.step_names):
        ilv = Interleavings[p.interleavings[i]]
        for offset, _ in enumerate(batch):
            seq([
                desc(batch[i+offset], step, substep)
                for i, substep in ilv.rows
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
                    ', '.join((x[1], x[0], x[2])),
                    '<',
                    ', '.join((d[1], d[0], d[2]))
                )

    linear = list(graphlib.TopologicalSorter(deps).static_order())

    if 0:
        utils.pr([
            ', '.join((desc[1], desc[0], desc[2]))
            for desc in linear
        ])

    slots = {
        'incu -> B21':  1,
        'B21 -> wash':  2,
        'wash -> disp': 3,
        'disp -> B21':  4,
        'B21 -> incu':  4,
        'wash -> B21':  3,
        'B21 -> out':   4,
        'wash -> B15':  3,
        'B15 -> B21':   4,
        'B15 -> out':   4,
    }

    plate_cmds = [
        command.with_metadata(
            step=step,
            substep=substep,
            plate_id=plate_id,
            slot=slots[substep],
        )
        for desc in linear
        for plate_id, step, substep in [desc]
        for command in chunks[desc]
    ]

    return Sequence(
        Section('Mito'),
        Sequence(*prep_cmds).with_metadata(step='prep'),
        *plate_cmds,
        Sequence(*post_cmds)
    ).with_metadata(batch_index=batch_index)

def define_plates(batch_sizes: list[int]) -> list[Plate]:
    plates: list[Plate] = []

    index = 0
    for batch_index, batch_size in enumerate(batch_sizes):
        rt_locs = RT_locs_many if batch_size > len(RT_locs_few) else RT_locs_few
        for index_in_batch in range(batch_size):
            plates += [Plate(
                id=f'{index+1}',
                incu_loc=Incu_locs[index],
                rt_loc=rt_locs[index_in_batch],
                # lid_loc=Lid_locs[index_in_batch],
                lid_loc=Lid_locs[index_in_batch % 2],
                # lid_loc=Lid_locs[0],
                out_loc=Out_locs[index],
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

def sleek_program(program: Command) -> Command:
    def get_movelist(cmd_and_metadata: tuple[Command, Any]) -> moves.MoveList | None:
        cmd, _ = cmd_and_metadata
        if isinstance(cmd, RobotarmCmd):
            return movelists[cmd.program_name]
        else:
            return None
    return Sequence(
        *[
            cmd.with_metadata(metadata)
            for cmd, metadata in moves.sleek_movements(
                program.collect(),
                get_movelist,
            )
        ]
    )

def cell_paint_program(batch_sizes: list[int], protocol_config: ProtocolConfig, sleek: bool = True) -> Command:
    cmds: list[Command] = []
    for batch in group_by_batch(define_plates(batch_sizes)):
        batch_cmds = paint_batch(
            batch,
            protocol_config=protocol_config,
        )
        if sleek:
            batch_cmds = sleek_program(batch_cmds)
        cmds += [batch_cmds]
    program = Sequence(
        Checkpoint('run'),
        test_comm_program,
        *cmds,
        Duration('run')
    )
    return program


def test_circuit(config: RuntimeConfig) -> None:
    '''
    Test circuit: Short test paint on one plate, without incubator
    '''
    plate, = define_plates([1])
    program = cell_paint_program([1], protocol_config=make_v3(incu_csv='s1,s2,s3,s4,s5', six=True, interleave=True))
    program = Sequence(
        *[
            cmd.with_metadata(metadata)
            for cmd, metadata in program.collect()
            if isinstance(cmd, RobotarmCmd)
            if metadata.get('step') not in {'Triton', 'Stains'}
        ],
        *RobotarmCmds(plate.out_get),
        *RobotarmCmds('incu put'),
    )
    program = sleek_program(program)
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
    execute_program(config, program, metadata={'program': 'test_circuit'})

test_comm_program: Command = Sequence(
    DispFork(cmd='TestCommunications', protocol_path=None),
    IncuFork(action='get_climate', incu_loc=None),
    RobotarmCmd('gripper check'),
    WaitForResource('disp'),
    WashFork(cmd='TestCommunications', protocol_path=None),
    WaitForResource('incu'),
    WaitForResource('wash'),
).with_metadata(step='test comm')

def test_comm(config: RuntimeConfig):
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    print('Testing communication with robotarm, washer, dispenser and incubator.')
    execute_program(config, test_comm_program, {'program': 'test_comm'})
    print('Communication tests ok.')

def cell_paint(config: RuntimeConfig, protocol_config: ProtocolConfig, *, batch_sizes: list[int]) -> None:
    program = cell_paint_program(batch_sizes, protocol_config=protocol_config)
    metadata: dict[str, str] = {
        'program': 'cell_paint',
        'batch_sizes': ','.join(str(bs) for bs in batch_sizes),
    }

    runtime = execute_program(config, program, metadata)

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
        if k.startswith('plate'):
            plate, i, *what = k.split(' ')
            k = f'plate {int(i):>2} {" ".join(what)}'
        out[k] = [utils.pp_secs(v) for _, [v] in vs]
    return out

@contextlib.contextmanager
def make_runtime(config: RuntimeConfig, metadata: dict[str, str]) -> Iterator[Runtime]:
    metadata = {
        'start_time': utils.now_str_for_filename(),
        **metadata,
        'config_name': config.name,
    }
    if config.log_to_file:
        log_filename = config.log_filename
        if not log_filename:
            log_filename = ' '.join(['event log', *metadata.values()])
            log_filename = 'logs/' + log_filename.replace(' ', '_') + '.jsonl'
        abspath = os.path.abspath(log_filename)
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        print(f'{log_filename=}')
    else:
        log_filename = None

    config = config.replace(log_filename=log_filename)

    runtime = config.make_runtime()

    with runtime.excepthook():
        yield runtime

def execute_program(config: RuntimeConfig, program: Command, metadata: dict[str, str]):
    program = program.remove_noops()
    resume_config = config.resume_config
    if not resume_config:
        program = program.assign_ids()

    if not resume_config:
        with utils.timeit('constraints'):
            program, expected_ends = constraints.optimize(program)
    else:
        expected_ends = {}

    with utils.timeit('estimates'):
        with make_runtime(dry_run.replace(log_to_file=False, resume_config=config.resume_config), {}) as runtime_est:
            program.execute(runtime_est, {})
        est_entries = runtime_est.log_entries

    if not resume_config:
        with utils.timeit('check correspondence'):
            matches = 0
            mismatches = 0
            seen: set[str] = set()
            for e in est_entries:
                i = e.get('id')
                if i and (e.get('kind') == 'end' or e.get('kind') == 'info' and e.get('source') == 'checkpoint'):
                    seen.add(i)
                    if abs(e['t'] - expected_ends[i]) > 0.1:
                        utils.pr(('no match!', i, e, expected_ends[i]))
                        mismatches += 1
                    else:
                        matches += 1
                    # utils.pr((f'{matches=}', i, e, ends[i]))
            by_id: dict[str, Command] = {
                i: c
                for c in program.universe()
                if isinstance(c, commands.Meta)
                if (i := c.metadata.get('id')) and isinstance(i, str)
            }

            for i, e in expected_ends.items():
                if i not in seen:
                    cmd = by_id.get(i)
                    match cmd:
                        case Meta(command=Info()):
                            continue
                    print('not seen:', i, e, cmd, sep='\t')

            if mismatches or not matches:
                print(f'{matches=} {mismatches=} {len(expected_ends)=}')

    if config.name == 'test-arm-incu':
        def Filter(cmd: Command) -> Command:
            match cmd:
                case commands.BiotekCmd() | commands.Idle():
                    return Sequence()
                case commands.WaitForCheckpoint() if 'incu #' not in cmd.name:
                    return Sequence()
                case _:
                    return cmd
        program = program.transform(Filter)
        program = program.remove_noops()

    with make_runtime(config, metadata) as runtime:
        try:
            print('Expected finish:', runtime.pp_time_offset(max(expected_ends.values())))
        except:
            pass

        program_opt = program.remove_scheduling_idles()

        runtime_metadata: dict[str, str | int | float | None] = {
            'pid': os.getpid(),
            'host': platform.node(),
            'speedup': runtime.speedup(),
            'git_HEAD': utils.git_HEAD() or '',
            'log_filename': config.log_filename,
        }

        os.makedirs('cache/', exist_ok=True)
        base = 'cache/' + utils.now_str_for_filename() + '_'
        save = {
            'estimates_pickle_file': est_entries,
            'program_pickle_file': program_opt,
        }
        for k, v in save.items():
            with open(base + k, 'wb') as fp:
                pickle.dump(v, fp)
            runtime_metadata[k] = base + k

        runtime.log('info', 'system', None, {'runtime_metadata': runtime_metadata, 'silent': True})
        program_opt.execute(runtime, {})
        runtime.log('info', 'system', None, {'completed': True, 'silent': True})

        for k, vs in group_times(runtime.times).items():
            print(k, '[' + ', '.join(vs) + ']')
