from __future__ import annotations
from typing import *
from dataclasses import *

from .commands import (
    Program,               # type: ignore
    Command,               # type: ignore
    Fork,                  # type: ignore
    Info,                  # type: ignore
    Meta,                  # type: ignore
    Checkpoint,            # type: ignore
    Duration,              # type: ignore
    Idle,                  # type: ignore
    Seq,                   # type: ignore
    WashCmd,               # type: ignore
    DispCmd,               # type: ignore
    IncuCmd,               # type: ignore
    WashFork,              # type: ignore
    DispFork,              # type: ignore
    IncuFork,              # type: ignore
    BiotekCmd,             # type: ignore
    BiotekValidateThenRun, # type: ignore
    RobotarmCmd,           # type: ignore
    WaitForCheckpoint,     # type: ignore
    WaitForResource,       # type: ignore
)
from . import commands

from .moves import InitialWorld, World

import pbutils
from .log import Metadata

from .protocol import (
    Locations,
    ProtocolArgs,
    make_protocol_config,
    Plate,
    define_plates,
    RobotarmCmds,
    sleek_program,
    cell_paint_program,
)

from . import protocol
from .protocol_paths import paths_v5
from . import protocol_paths

@dataclass(frozen=True)
class SmallProtocolArgs:
    num_plates: int = 1
    params: list[str] = field(default_factory=list)
    protocol_dir: str = 'automation_v5.0'

SmallProtocol: TypeAlias = Callable[[SmallProtocolArgs], Program]

small_protocols: list[SmallProtocol] = []

def protocol_args(small_protocol: SmallProtocol) -> set[str]:
    out: set[str] = set()
    args = SmallProtocolArgs()
    missing = object()
    class Intercept:
        def __getattr__(self, key: str):
            v = getattr(args, key, missing)
            if v is not missing:
                out.add(key)
                return v
            else:
                raise AttributeError
    intercepted_args: Any = Intercept()
    _ = small_protocol(intercepted_args)
    return out

def Section(section: str) -> Command:
    return Info(section).add(Metadata(section=section))

@small_protocols.append
def incu_load(args: SmallProtocolArgs):
    '''
    Load incubator from A hotel, starting at the bottom, to incubator positions L1, ...

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L1, ...:       empty!
        3. hotel A1, A3, ...:       plates with lid
        4. robotarm:                in neutral position by B hotel
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
            Seq(
                RobotarmCmd(f'incu_A{pos} put prep'),
                RobotarmCmd(f'incu_A{pos} put transfer to drop neu'),
                WaitForResource('incu'),
                RobotarmCmd(f'incu_A{pos} put transfer from drop neu'),
                IncuFork('put', p.incu_loc),
                RobotarmCmd(f'incu_A{pos} put return'),
            ).add(Metadata(plate_id=p.id, stage=f'plate from A{pos} to {p.incu_loc}'))
        ]
    program = Seq(*[
        RobotarmCmd('incu_A21 put-prep'),
        *cmds,
        RobotarmCmd('incu_A21 put-return'),
        WaitForResource('incu'),
    ])
    return Program(program, World(world0))

@small_protocols.append
def test_comm(_: SmallProtocolArgs):
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    return Program(protocol.test_comm_program().add(Metadata(gui_force_show=True)))

@small_protocols.append
def test_circuit(_: SmallProtocolArgs):
    '''
    Move one plate around to all its positions using the robotarm, without running incubator or bioteks.

    Required lab prerequisites:
        1. hotel one:               empty!
        2. hotel two:               empty!
        3. hotel three:             empty!
        4. biotek washer:           empty!
        5. biotek dispenser:        empty!
        6. incubator transfer door: one plate with lid
        7. robotarm:                in neutral position by lid hotel
    '''
    [[plate]] = define_plates([1])
    v5 = make_protocol_config(paths_v5(), ProtocolArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=True))
    program = cell_paint_program([1], protocol_config=v5).command
    program = Seq(
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
    return Program(program, World({'incu': plate.id}))

@small_protocols.append
def test_circuit_with_incubator(args: SmallProtocolArgs):
    '''
    Move plates around to all its positions using the robotarm and incubator, without running bioteks.
    Plates start in incubator L1, L2, .. as normal cell painting
    '''
    num_plates = args.num_plates
    v5 = make_protocol_config(paths_v5(), ProtocolArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=True))
    program = cell_paint_program([num_plates], protocol_config=v5).command
    program = Seq(
        *[
            cmd.add(metadata)
            for cmd, metadata in program.collect()
            if (
                isinstance(cmd, Info) or
                isinstance(cmd, RobotarmCmd) or
                isinstance(cmd, Fork) and cmd.resource == 'incu' or
                isinstance(cmd, WaitForResource) and cmd.resource == 'incu'
            )
        ],
    )
    program = sleek_program(program)
    return Program(program)

@small_protocols.append
def incu_reset_and_activate(_: SmallProtocolArgs):
    '''
    Reset and activate the incubator.
    '''
    program = Seq(
        IncuFork('reset_and_activate'),
        WaitForResource('incu'),
        IncuFork('get_status'),
        WaitForResource('incu'),
    )
    return Program(program.add(Metadata(gui_force_show=True)))

@small_protocols.append
def wash_plates_clean(args: SmallProtocolArgs):
    '''
    Wash test plates clean using ethanol.

    Required lab prerequisites:
        1. incubator transfer door: not used
        2. hotel B21:               empty
        3. hotel A1, A3, ...:       plates with lid
        4. hotel B:                 empty!
        5. hotel C:                 empty!
        6. biotek washer:           empty!
        7. biotek dispenser:        not used
        8. robotarm:                in neutral position by B hotel
    '''
    N = args.num_plates
    if not N:
        return Program()
    cmds: list[Command] = []
    [plates] = define_plates([N])
    cmds += [Section('H₂O')]
    for plate in plates:
        cmds += [*RobotarmCmds(plate.out_get)]
        cmds += [*RobotarmCmds(plate.lid_put)]
        cmds += [*RobotarmCmds('wash put')]

        cmds += [Fork(WashCmd('wash-plates-clean/WD_3X_leaves80ul.LHC', 'Run'))]
        cmds += [WaitForResource('wash')]

        cmds += [*RobotarmCmds('wash get')]
        cmds += [*RobotarmCmds(plate.lid_get)]
        cmds += [*RobotarmCmds(plate.rt_put)]

    cmds += [Section('EtOH')]
    cmds += [Fork(WashCmd('wash-plates-clean/WC_PRIME.LHC', 'Run'))]
    cmds += [WaitForResource('wash')]

    for i, plate in enumerate(plates):
        cmds += [*RobotarmCmds(plate.rt_get)]
        cmds += [*RobotarmCmds(plate.lid_put)]
        cmds += [*RobotarmCmds('wash put')]

        cmds += [Fork(WashCmd('wash-plates-clean/WC_1X_leaves80ul.LHC', 'Run'))]
        cmds += [WaitForResource('wash')]

        if i == 0:
            cmds += [Checkpoint('first wash')]

        cmds += [*RobotarmCmds('wash get')]
        cmds += [*RobotarmCmds(plate.lid_get)]
        cmds += [*RobotarmCmds(plate.rt_put)]

    cmds += [WaitForCheckpoint('first wash', plus_secs=60 * 15, assume='nothing')]
    cmds += [Section('H₂O 2')]

    for plate in plates:
        cmds += [*RobotarmCmds(plate.rt_get)]
        cmds += [*RobotarmCmds(plate.lid_put)]
        cmds += [*RobotarmCmds('wash put')]

        cmds += [Fork(WashCmd('wash-plates-clean/WD_3X_leaves10ul.LHC', 'Run'))]
        cmds += [WaitForResource('wash')]

        cmds += [*RobotarmCmds('wash get')]
        cmds += [*RobotarmCmds(plate.lid_get)]
        cmds += [*RobotarmCmds(plate.out_put)]

    world0 = World({plate.out_loc: plate.id for plate in plates})
    program = Seq(*cmds)
    program = sleek_program(program)
    return Program(program, world0)

@small_protocols.append
def validate_all_protocols(args: SmallProtocolArgs):
    '''
    Validate all biotek protocols.
    '''
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    wash = [
        WashCmd(p, cmd='Validate')
        for p in paths.all_wash_paths()
    ]
    disp = [
        DispCmd(p, cmd='Validate')
        for p in paths.all_disp_paths()
    ]
    program = Seq(
        Fork(Seq(*wash)).delay(2),
        Fork(Seq(*disp)),
        WaitForResource('wash'),
        WaitForResource('disp'),
    )
    return Program(program.add(Metadata(gui_force_show=True)))

@small_protocols.append
def run_biotek(args: SmallProtocolArgs):
    '''
    Run protocols on the bioteks from the protocol dir.

    For each parameter $X runs all protocols that matches ${PROTOCOL_DIR}/$X.
    For example with automation_v4.0, "2" will run
    automation_v4.0/2.0_D_SB_PRIME_Mito and then
    automation_v4.0/2.1_D_SB_30ul_Mito.
    '''
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    wash = paths.all_wash_paths()
    disp = paths.all_disp_paths()
    protocols = [
        *[(p, 'wash') for p in wash],
        *[(p, 'disp') for p in disp],
    ]
    # print('Available:', end=' ')
    # pbutils.pr([p for p, _ in protocols])
    cmds: list[Command] = []
    for x in args.params:
        for p, machine in protocols:
            if f'/{x.lower()}' in p.lower():
                cmds += [
                    Fork(BiotekValidateThenRun(machine, p)),
                    WaitForResource(machine)
                ]
    return Program(Seq(*cmds))

@small_protocols.append
def incu_put(args: SmallProtocolArgs):
    '''
    Insert a plate into the incubator.

    Use incubator locations such as L1.
    '''
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            IncuFork('put', x),
            WaitForResource('incu'),
        ]
    return Program(Seq(*cmds))

@small_protocols.append
def incu_get(args: SmallProtocolArgs):
    '''
    Eject a plate from the incubator.

    Use incubator locations such as L1.
    '''
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            IncuFork('get', x),
            WaitForResource('incu'),
        ]
    return Program(Seq(*cmds))

@small_protocols.append
def robotarm(args: SmallProtocolArgs):
    '''
    Run robotarm programs.

    Example arguments: wash-put-prep, 'wash put prep'
    '''
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            RobotarmCmd(x.replace('-', ' ')),
        ]
    return Program(Seq(*cmds))

# @small_protocols.append
def time_arm_incu(_: SmallProtocolArgs):
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
        Fork(Seq(*incu)),
        *arm,
        WaitForResource('incu'),
        sleek_program(Seq(*arm2)),
        *arm2,
    ]
    program = Seq(*cmds)
    return Program(program)

# @small_protocols.append
def lid_stress_test(_: SmallProtocolArgs):
    '''
    Do a lid stress test

    Required lab prerequisites:
        1. hotel B21:   plate with lid
        2. hotel B1-19: empty
        2. hotel A:     empty
        2. hotel B:     empty
        4. robotarm:    in neutral position by B hotel
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
    program = sleek_program(Seq(*cmds))
    return Program(program)

# @small_protocols.append
def incu_unload(args: SmallProtocolArgs):
    '''
    Unload plates from incubator positions L1, ..., to A hotel, starting at the bottom.

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L1, ...:       plates with lid
        3. hotel A1-A#:             empty!
        4. robotarm:                in neutral position by B hotel
    '''
    num_plates = args.num_plates

    world0: dict[str, str] = {}
    cmds: list[Command] = []
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
        world0[p.incu_loc] = p.id
        assert p.out_loc.startswith('A')
        pos = p.out_loc.removeprefix('A')
        cmds += [
            IncuFork('put', p.incu_loc),
            RobotarmCmd(f'incu_A{pos} get prep'),
            WaitForResource('incu'),
            RobotarmCmd(f'incu_A{pos} get transfer'),
            RobotarmCmd(f'incu_A{pos} get return'),
        ]
    return Program(Seq(*cmds))

# @small_protocols.append
def plate_shuffle(_: SmallProtocolArgs):
    '''
    Shuffle plates around in the incubator. L7-L12 goes to L1-L6

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L7-L12: plates
        3. incubator L1-L6:  empty
    '''
    cmds: list[Command] = []
    for dest, src in zip(Locations.Incu[:6], Locations.Incu[6:]):
        cmds += [
            IncuFork('get', src),
            WaitForResource('incu'),
            IncuFork('put', dest),
            WaitForResource('incu'),
        ]
    program = Seq(*cmds)
    return program

# @small_protocols.append
def add_missing_timings(_: SmallProtocolArgs):
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
    program = Seq(*cmds)
    return Program(program)

@small_protocols.append
def time_bioteks(args: SmallProtocolArgs):
    '''
    Timing for biotek protocols, with dispenser running on air.

    Required lab prerequisites:
        1. biotek washer:    one plate *without* lid
        2. biotek washer:    connected to water
        3. biotek dispenser: all pumps and syringes disconnected (just use air) (plate optional)
        4. robotarm:         not used
    '''
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    wash = [
        BiotekValidateThenRun('wash', p)
        for p in paths.all_wash_paths()
    ]
    disp = [
        BiotekValidateThenRun('disp', p)
        for p in paths.all_disp_paths()
    ]
    program = Seq(
        Fork(Seq(*wash)),
        Fork(Seq(*disp)).delay(2),
        WaitForResource('wash'),
        WaitForResource('disp'),
    )
    return Program(program)

@dataclass(frozen=True)
class SmallProtocolData:
    name: str
    make: SmallProtocol
    args: set[str]
    doc: str

small_protocols_dict = {
    p.__name__: SmallProtocolData(
        p.__name__,
        p,
        protocol_args(p),
        pbutils.doc_header(p)
    )
    for p in small_protocols
}
