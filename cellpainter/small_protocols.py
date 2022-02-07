from __future__ import annotations
from typing import Callable, Protocol, cast
from dataclasses import *

from .commands import (
    Command,            # type: ignore
    Fork,               # type: ignore
    Info,               # type: ignore
    Meta,               # type: ignore
    Checkpoint,         # type: ignore
    Duration,           # type: ignore
    Idle,               # type: ignore
    Sequence,           # type: ignore
    WashCmd,            # type: ignore
    DispCmd,            # type: ignore
    IncuCmd,            # type: ignore
    WashFork,           # type: ignore
    DispFork,           # type: ignore
    IncuFork,           # type: ignore
    BiotekCmd,          # type: ignore
    RobotarmCmd,        # type: ignore
    WaitForCheckpoint,  # type: ignore
    WaitForResource,    # type: ignore
)
from . import commands

from . import utils
from .log import Metadata

from .protocol import (
    Locations,
    ProtocolArgs,
    make_v3,
    Plate,
    define_plates,
    RobotarmCmds,
    sleek_program,
    add_world_metadata,
    cell_paint_program,
)

class ArgsLike(Protocol):
    num_plates: int
    params: list[str]

small_protocols: list[Callable[[ArgsLike], Command]] = []

@small_protocols.append
def plate_shuffle(_: ArgsLike):
    '''
    Shuffle plates around in the incubator. L7-L12 goes to L1-L6
    '''
    cmds: list[Command] = []
    for dest, src in zip(Locations.Incu[:6], Locations.Incu[6:]):
        cmds += [
            IncuFork('get', src),
            WaitForResource('incu'),
            IncuFork('put', dest),
            WaitForResource('incu'),
        ]
    program = Sequence(*cmds)
    return program

@small_protocols.append
def add_missing_timings(_: ArgsLike):
    '''
    Do some timings that were missing.
    '''
    cmds: list[Command] = []
    for out_loc in 'b5 b7 b9 b11 c3'.upper().split():
        plate = Plate('1', '', '', '', out_loc=out_loc, batch_index=1)
        cmds += [
            *RobotarmCmds(plate.out_put),
            *RobotarmCmds(plate.out_get),
        ]
    program = Sequence(*cmds)
    return program

@small_protocols.append
def time_arm_incu(_: ArgsLike):
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
    for loc in Locations.Incu[:IncuLocs]:
        incu += [
            commands.IncuCmd('put', loc),
            commands.IncuCmd('get', loc),
        ]
    arm: list[Command] = []
    plate = Plate('', '', '', '', '', 1)
    for lid_loc in Locations.Lid[:N]:
        plate = replace(plate, lid_loc=lid_loc)
        arm += [
            *RobotarmCmds(plate.lid_put),
            *RobotarmCmds(plate.lid_get),
        ]
    for rt_loc in Locations.RT_many[:N]:
        plate = replace(plate, rt_loc=rt_loc)
        arm += [
            *RobotarmCmds(plate.rt_put),
            *RobotarmCmds(plate.rt_get),
        ]
    for out_loc in Locations.Out[:N]:
        plate = replace(plate, out_loc=out_loc)
        arm += [
            *RobotarmCmds(plate.out_put),
            *RobotarmCmds(plate.out_get),
        ]
    plate = replace(plate, lid_loc=Locations.Lid[0], rt_loc=Locations.RT_many[0])
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
    cmds: list[Command] = [
        Fork(Sequence(*incu)),
        *arm,
        WaitForResource('incu'),
        sleek_program(Sequence(*arm2)),
        *arm2,
    ]
    program = Sequence(*cmds)
    return program

@small_protocols.append
def lid_stress_test(_: ArgsLike):
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
    for _i, (lid, A, C) in enumerate(zip(Locations.Lid, Locations.A, Locations.C)):
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
    return program

@small_protocols.append
def load_incu(args: ArgsLike):
    '''
    Load incubator with --num-plates plates from A hotel, starting at the bottom, to incubator positions L1, ...

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L1, ...:       empty!
        3. hotel A1-A#:             plates with lid
        4. robotarm:                in neutral position by B hotel
        5. gripper:                 sufficiently open to grab a plate
    '''
    num_plates = args.num_plates
    cmds: list[Command] = []
    world0: dict[str, str] = {}
    for i, (incu_loc, a_loc) in enumerate(zip(Locations.Incu, Locations.A[::-1]), start=1):
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
        world0[p.out_loc] = p.id
        assert p.out_loc.startswith('A')
        pos = p.out_loc.removeprefix('A')
        cmds += [
            Sequence(*[
                RobotarmCmd(f'incu_A{pos} put prep'),
                RobotarmCmd(f'incu_A{pos} put transfer to drop neu'),
                WaitForResource('incu'),
                RobotarmCmd(f'incu_A{pos} put transfer from drop neu'),
                IncuFork('put', p.incu_loc),
                RobotarmCmd(f'incu_A{pos} put return'),
            ]).add(Metadata(plate_id=p.id))
        ]
    program = Sequence(*[
        RobotarmCmd('incu_A21 put-prep'),
        *cmds,
        RobotarmCmd('incu_A21 put-return'),
        WaitForResource('incu'),
    ])
    # ATTENTION(load_incu.__doc__ or '')
    program = add_world_metadata(program, world0)
    return program

@small_protocols.append
def unload_incu(args: ArgsLike):
    '''
    Unload --num-plates plates from incubator positions L1, ..., to A hotel, starting at the bottom.

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L1, ...:       plates with lid
        3. hotel A1-A#:             empty!
        4. robotarm:                in neutral position by B hotel
        5. gripper:                 sufficiently open to grab a plate
    '''

    num_plates = args.num_plates

    [plates] = define_plates([num_plates])
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
    return Sequence(*cmds)
    ATTENTION(unload_incu.__doc__ or '')
    execute_program(config, program, {'program': 'unload_incu'})

@small_protocols.append
def test_circuit(_: ArgsLike):
    '''
    Test circuit: Short test paint on one plate, only robotarm, no incubator or bioteks

    Required lab prerequisites:
        1. hotel one:               empty!
        2. hotel two:               empty!
        3. hotel three:             empty!
        4. biotek washer:           empty!
        5. biotek dispenser:        empty!
        6. incubator transfer door: one plate with lid
        7. robotarm:                in neutral position by lid hotel
        8. gripper:                 sufficiently open to grab a plate
    '''
    [[plate]] = define_plates([1])
    v3 = make_v3(ProtocolArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=True))
    program = cell_paint_program([1], protocol_config=v3)
    program = Sequence(
        *[
            cmd.add(metadata)
            for cmd, metadata in program.collect()
            if isinstance(cmd, RobotarmCmd)
            if metadata.step not in {'Triton', 'Stains'}
        ],
        *RobotarmCmds(plate.out_get),
        *RobotarmCmds('incu put'),
    )
    program = sleek_program(program)
    return program

@small_protocols.append
def validate_all_protocols(_: ArgsLike):
    '''
    Validate all biotek protocols.
    '''
    v3 = make_v3(ProtocolArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=True))
    wash = [
        WashCmd(p, cmd='Validate')
        for p in set([*v3.wash, v3.prep_wash])
        if p
    ]
    disp = [
        DispCmd(p, cmd='Validate')
        for p in set([*v3.disp, *v3.pre_disp, *v3.prime, v3.prep_disp])
        if p
    ]
    program = Sequence(
        Fork(Sequence(*wash)),
        Fork(Sequence(*disp)),
        WaitForResource('wash'),
        WaitForResource('disp'),
    )
    return program

@small_protocols.append
def run_biotek(args: ArgsLike):
    v3 = make_v3(cast(ProtocolArgs, args))
    wash = [*v3.wash, v3.prep_wash or '']
    disp = [*v3.disp, *v3.pre_disp, *v3.prime, v3.prep_disp or '']
    protocols = [
        *[(p, 'wash') for p in wash if p],
        *[(p, 'disp') for p in disp if p],
    ]
    protocols = sorted(set(protocols))
    print('Available:', end=' ')
    utils.pr([p for p, _ in protocols])
    cmds: list[Command] = []
    for x in args.params:
        for p, machine in protocols:
            if f'/{x.lower()}' in p.lower():
                cmds += [
                    Fork(BiotekCmd(machine, p, action='Run')),
                    WaitForResource(machine)
                ]
    return Sequence(*cmds)

@small_protocols.append
def incu_put(args: ArgsLike):
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            IncuFork('put', x),
            WaitForResource('incu'),
        ]
    return Sequence(*cmds)

@small_protocols.append
def incu_get(args: ArgsLike):
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            IncuFork('get', x),
            WaitForResource('incu'),
        ]
    return Sequence(*cmds)

@small_protocols.append
def robotarm(args: ArgsLike):
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            RobotarmCmd(x.replace('-', ' ')),
        ]
    return Sequence(*cmds)
