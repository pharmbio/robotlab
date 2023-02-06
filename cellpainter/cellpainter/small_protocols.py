from __future__ import annotations
from typing import *
from dataclasses import *

from .commands import (
    BlueFork,
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

from .moves import World

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

@small_protocols.append
def incu_load(args: SmallProtocolArgs):
    '''
    Load incubator from A hotel, starting at the bottom, to incubator positions L1, ...

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L1, ...:       empty!
        3. hotel A1, A2, ...:       plates with lid
        4. robotarm:                in neutral position by B hotel
    '''
    num_plates = args.num_plates
    cmds: list[Command] = []
    world0: dict[str, str] = {}
    assert num_plates <= len(Locations.A)
    assert num_plates <= len(Locations.Incu)
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
                RobotarmCmd(f'A{pos}-to-incu prep'),
                RobotarmCmd(f'A{pos}-to-incu transfer to drop neu'),
                WaitForResource('incu'),
                RobotarmCmd(f'A{pos}-to-incu transfer from drop neu'),
                IncuFork('put', p.incu_loc),
                RobotarmCmd(f'A{pos}-to-incu return'),
            ).add(Metadata(plate_id=p.id, stage=f'plate from A{pos} to {p.incu_loc}'))
        ]
    program = Seq(*[
        RobotarmCmd(f'B-neu-to-A-neu'),
        *cmds,
        RobotarmCmd(f'A-neu-to-B-neu'),
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
            # if metadata.step not in {'Triton', 'Stains'}
        ],
        *RobotarmCmds(plate.out_get),
        *RobotarmCmds('B21-to-incu'),
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

    section: list[Command]
    section = []
    for plate in plates:
        section += [*RobotarmCmds(plate.out_get)]
        section += [*RobotarmCmds(plate.lid_put)]
        section += [*RobotarmCmds('B21-to-wash')]

        section += [Fork(WashCmd('Run', 'wash-plates-clean/WD_3X_leaves80ul.LHC'))]
        section += [WaitForResource('wash')]

        section += [*RobotarmCmds('wash-to-B21')]
        section += [*RobotarmCmds(plate.lid_get)]
        section += [*RobotarmCmds(plate.rt_put)]
    cmds += [Seq(*section).add_to_physical_commands(Metadata(section='H₂O'))]

    section = []
    section += [Fork(WashCmd('Run', 'wash-plates-clean/WC_PRIME.LHC'))]
    section += [WaitForResource('wash')]
    for i, plate in enumerate(plates):
        section += [*RobotarmCmds(plate.rt_get)]
        section += [*RobotarmCmds(plate.lid_put)]
        section += [*RobotarmCmds('B21-to-wash')]

        section += [Fork(WashCmd('Run', 'wash-plates-clean/WC_1X_leaves80ul.LHC'))]
        section += [WaitForResource('wash')]

        if i == 0:
            section += [Checkpoint('first wash')]

        section += [*RobotarmCmds('wash-to-B21')]
        section += [*RobotarmCmds(plate.lid_get)]
        section += [*RobotarmCmds(plate.rt_put)]
    cmds += [Seq(*section).add_to_physical_commands(Metadata(section='EtOH'))]

    cmds += [WaitForCheckpoint('first wash', plus_secs=60 * 15, assume='nothing')]

    section = []
    for plate in plates:
        section += [*RobotarmCmds(plate.rt_get)]
        section += [*RobotarmCmds(plate.lid_put)]
        section += [*RobotarmCmds('B21-to-wash')]

        section += [Fork(WashCmd('Run', 'wash-plates-clean/WD_3X_leaves10ul.LHC'))]
        section += [WaitForResource('wash')]

        section += [*RobotarmCmds('wash-to-B21')]
        section += [*RobotarmCmds(plate.lid_get)]
        section += [*RobotarmCmds(plate.out_put)]
    cmds += [Seq(*section).add_to_physical_commands(Metadata(section='H₂O 2'))]

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
        WashCmd('Validate', p)
        for p in paths.all_wash_paths()
    ]
    disp = [
        DispCmd('Validate', p)
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

    Example arguments: wash-put-prep, 'B21-to-wash prep'
    '''
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            RobotarmCmd(x.replace('-', ' ')),
        ]
    return Program(Seq(*cmds))

@small_protocols.append
def robotarm_small_cycle(args: SmallProtocolArgs):
    '''
    Small stress test on robotarm on B21 and B19. Set number of cycles with num_plates.

    Required lab prerequisites:
        B21: plate with lid
        B19: empty
    '''
    N = args.num_plates or 4
    cmds = [
        RobotarmCmd('gripper init and check'),
    ]
    for _i in range(N):
        cmds += [
            *RobotarmCmds('B19 put'),
            *RobotarmCmds('B19 get'),
            *RobotarmCmds('lid-B19 put'),
            *RobotarmCmds('lid-B19 get'),
        ]
    program = Seq(*cmds)
    program = sleek_program(program)
    return Program(program)

@small_protocols.append
def time_robotarm(_: SmallProtocolArgs):
    '''
    Timing for robotarm.

    Required lab prerequisites:
        1. incubator transfer door: one plate with lid
        3. hotel B:                 empty!
        4. hotel A:                 empty!
        5. hotel C:                 empty!
        6. biotek washer:           empty!
        7. biotek dispenser:        empty!
        8. robotarm:                in neutral position by B hotel
    '''
    arm: list[Command] = [
        *RobotarmCmds('incu-to-B21'),
    ]
    plate = Plate('', '', '', '', '', 1)
    for lid_loc in Locations.Lid[:2]:
        plate = replace(plate, lid_loc=lid_loc)
        arm += [
            *RobotarmCmds(plate.lid_put),
            *RobotarmCmds(plate.lid_get),
        ]
    for out_loc in Locations.Out:
        plate = replace(plate, out_loc=out_loc)
        arm += [
            *RobotarmCmds(plate.out_put),
            *RobotarmCmds(plate.out_get),
        ]
    for rt_loc in reversed(Locations.RT):
        plate = replace(plate, rt_loc=rt_loc)
        arm += [
            *RobotarmCmds(plate.rt_put),
            *RobotarmCmds(plate.rt_get),
        ]
    plate = replace(plate, lid_loc=Locations.Lid[0], rt_loc=Locations.RT[0])
    arm += [
        *RobotarmCmds(plate.lid_put),
        *RobotarmCmds('B21-to-wash'),
        *RobotarmCmds('wash-to-disp'),
        *RobotarmCmds('disp-to-B21'),
        *RobotarmCmds('B21-to-wash'),
        *RobotarmCmds('wash-to-B21'),
        *RobotarmCmds('B15 put'),
        *RobotarmCmds('B15-to-wash'),
        *RobotarmCmds('wash-to-B15'),
        *RobotarmCmds('B15 get'),
        *RobotarmCmds(plate.lid_get),
        *RobotarmCmds('B21-to-incu'),
    ]
    program = Seq(*arm)
    return Program(program, world0=World({'incu': '1'}))

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
            RobotarmCmd(f'incu-to-A{pos} prep'),
            WaitForResource('incu'),
            RobotarmCmd(f'incu-to-A{pos} transfer'),
            RobotarmCmd(f'incu-to-A{pos} return'),
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

@small_protocols.append
def bluewash_init_all(args: SmallProtocolArgs):
    '''
    Required to run before using BlueWasher:
    Initializes linear drive, rotor, inputs, outputs, motors, valves.
    Presents working carrier (= top side of rotor) to RACKOUT.
    '''
    return Program(BlueFork('init_all'))

@small_protocols.append
def wave(args: SmallProtocolArgs):
    '''
    Makes the robot wave, twice!
    '''
    waves = [RobotarmCmd('wave')] * 2
    return Program(Seq(*waves))

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
