from __future__ import annotations
from typing import Callable, Any, TypeAlias
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

from .moves import InitialWorld, NoEffect

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

from .symbolic import Symbolic

from . import protocol

@dataclass(frozen=True)
class SmallProtocolArgs:
    num_plates: int = 1
    params: list[str] = field(default_factory=list)

SmallProtocol: TypeAlias = Callable[[SmallProtocolArgs], Command]

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
            Sequence(
                RobotarmCmd(f'incu_A{pos} put prep'),
                RobotarmCmd(f'incu_A{pos} put transfer to drop neu'),
                WaitForResource('incu'),
                RobotarmCmd(f'incu_A{pos} put transfer from drop neu'),
                IncuFork('put', p.incu_loc),
                RobotarmCmd(f'incu_A{pos} put return'),
            ).add(Metadata(plate_id=p.id))
        ]
    program = Sequence(*[
        RobotarmCmd('incu_A21 put-prep'),
        *cmds,
        RobotarmCmd('incu_A21 put-return'),
        WaitForResource('incu'),
    ])
    program = add_world_metadata(program, world0)
    return program

@small_protocols.append
def test_comm(_: SmallProtocolArgs):
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    return protocol.test_comm_program()

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
    program = Sequence(
        Info('initial world').add(Metadata(effect=InitialWorld({'incu': plate.id}))),
        program,
    )
    return program

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
    cmds: list[Command] = []
    [plates] = define_plates([N])
    cmds += [Section('H₂O')]
    for plate in plates:
        cmds += [*RobotarmCmds(plate.out_get)]
        cmds += [*RobotarmCmds(plate.lid_put)]
        cmds += [*RobotarmCmds('wash put')]

        cmds += [Fork(WashCmd('automation_v4.0/wash-plates-clean/WD_3X_leaves80ul.LHC'))]
        cmds += [WaitForResource('wash')]

        cmds += [*RobotarmCmds('wash get')]
        cmds += [*RobotarmCmds(plate.lid_get)]
        cmds += [*RobotarmCmds(plate.rt_put)]

    cmds += [Section('EtOH')]
    cmds += [
        Fork(WashCmd('automation_v4.0/wash-plates-clean/WC_PRIME.LHC')),
        WaitForResource('wash')
    ]

    for i, plate in enumerate(plates):
        cmds += [*RobotarmCmds(plate.rt_get)]
        cmds += [*RobotarmCmds(plate.lid_put)]
        cmds += [*RobotarmCmds('wash put')]

        cmds += [Fork(WashCmd('automation_v4.0/wash-plates-clean/WC_1X_leaves80ul.LHC'))]
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

        cmds += [Fork(WashCmd('automation_v4.0/wash-plates-clean/WD_3X_leaves10ul.LHC'))]
        cmds += [WaitForResource('wash')]

        cmds += [*RobotarmCmds('wash get')]
        cmds += [*RobotarmCmds(plate.lid_get)]
        cmds += [*RobotarmCmds(plate.out_put)]

    world0 = {plate.out_loc: plate.id for plate in plates}
    program = Sequence(*cmds)
    program = sleek_program(program)
    program = add_world_metadata(program, world0)
    return program

@small_protocols.append
def validate_all_protocols(_: SmallProtocolArgs):
    '''
    Validate all biotek protocols.
    '''
    w: list[str | None] = []
    d: list[str | None] = []
    for six in [True, False]:
        v3 = make_v3(ProtocolArgs(incu='s1,s2,s3,s4,s5', two_final_washes=six, interleave=True))
        w += [*v3.wash, v3.prep_wash]
        d += [*v3.disp, *v3.pre_disp, *v3.prime, v3.prep_disp]
    wash = [
        WashCmd(p, cmd='Validate')
        for p in set(w)
        if p
    ]
    disp = [
        DispCmd(p, cmd='Validate')
        for p in set(d)
        if p
    ]
    program = Sequence(
        Fork(Sequence(*wash)),
        Fork(Sequence(*disp)).delay(1.5),
        WaitForResource('wash'),
        WaitForResource('disp'),
    )
    return program

@small_protocols.append
def run_biotek(args: SmallProtocolArgs):
    '''
    Run protocols on the bioteks from automation_v4.0/.

    For each parameter <X> runs all protocols that matches automation_v4.0/<X>.
    For example, 2 will run 2.0_D_SB_PRIME_Mito and then 2.1_D_SB_30ul_Mito.

    Note: the two final washes protocol 9_10_W is not included.
    '''
    wash: list[str] = []
    disp: list[str] = []
    v3 = make_v3()
    wash += [*v3.wash, v3.prep_wash or '']
    disp += [*v3.disp, *v3.pre_disp, *v3.prime, v3.prep_disp or '']
    protocols = [
        *[(p, 'wash') for p in wash if p],
        *[(p, 'disp') for p in disp if p],
    ]
    protocols = sorted(set(protocols))
    # print('Available:', end=' ')
    # utils.pr([p for p, _ in protocols])
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
    return Sequence(*cmds)

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
    return Sequence(*cmds)

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
    return Sequence(*cmds)

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
        Fork(Sequence(*incu)),
        *arm,
        WaitForResource('incu'),
        sleek_program(Sequence(*arm2)),
        *arm2,
    ]
    program = Sequence(*cmds)
    return program

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
    program = sleek_program(Sequence(*cmds))
    return program

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
    return Sequence(*cmds)

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
    program = Sequence(*cmds)
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
    program = Sequence(*cmds)
    return program

@small_protocols.append
def time_bioteks(_: SmallProtocolArgs):
    '''
    Timing for biotek protocols and robotarm moves to and from bioteks.

    This is preferably done with the bioteks connected to water.

    Required lab prerequisites:
        1. hotel B21:        one plate *without* lid
        2. biotek washer:    empty
        3. biotek washer:    connected to water
        4. biotek dispenser: empty
        5. biotek dispenser: all pumps and syringes connected to water
        6. robotarm:         in neutral position by B hotel

        7. incubator transfer door: not used
        8. hotel B1-19:             not used
        9. hotel A:                 not used
       10. hotel C:                 not used
    '''
    protocol_config = make_v3()
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
            cmd.add(metadata.merge(Metadata(effect=NoEffect())))
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
    [[plate]] = define_plates([1])
    program = add_world_metadata(program, {'B21': plate.id})
    return program

@dataclass(frozen=True)
class SmallProtocolData:
    name: str
    make: SmallProtocol
    args: set[str]
    doc: str

small_protocols_dict = {
    p.__name__: SmallProtocolData(p.__name__, p, protocol_args(p), utils.doc_header(p))
    for p in small_protocols
}
