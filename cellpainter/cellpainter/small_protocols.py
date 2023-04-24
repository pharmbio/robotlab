from __future__ import annotations
from typing import *
from dataclasses import *
from .commands import *
from .commandlib import Interleaving

from .moves import World
from . import moves
from . import estimates

import re
import pbutils
from .log import Metadata

from .protocol import (
    Locations,
    ProtocolArgs,
    make_protocol_config,
    Plate,
    define_plates,
    RobotarmCmds,
    cell_paint_program,
    Early,
)

from . import protocol
from . import protocol_paths

from labrobots.liconic import FridgeSlots

@dataclass(frozen=True)
class SmallProtocolArgs:
    num_plates: int = 1
    params: list[str] = field(default_factory=list)
    protocol_dir: str = 'automation_v5.0'
    fridge_contents: FridgeSlots | None = None

SmallProtocol: TypeAlias = Callable[[SmallProtocolArgs], Program]

ur_protocols: list[SmallProtocol] = []
pf_protocols: list[SmallProtocol] = []

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
    return out - {'fridge_contents'}

# @ur_protocols.append
def trigger_biotek_comm_issue(args: SmallProtocolArgs):
    '''

        This should trigger Error code: 6058 Unable to open the COM port

        2023-04-12 10:16:42.521  disp  1504  RunValidated('automation_v4.0_colo52', '4.0_D_SA_PRIME_PFA.LHC')
        2023-04-12 10:16:42.527  disp  1504  0.0 disp message protocol begin
        2023-04-12 10:16:43.540  disp  1504  1.016 disp message protocol done
        2023-04-12 10:16:43.548  disp  1504  1.031 disp status 4
        2023-04-12 10:16:43.557  disp  1504  1.031 disp message ErrorCode: 6, ErrorString: Error starting run. Error code: 6058
        2023-04-12 10:16:43.565  disp  1504  1.047 disp Unable to open the COM port

        Note: this seems to be fixed now: the COM ports are directly specified in labrobots/__init__.py:class WindowsNUC:
        "COM4" instead of "USB 405 TS/LS sn:191107F" and "COM3" instead of "USB MultiFloFX sn:19041612".

    '''
    cmds: list[Command] = [
        DispCmd('Validate', pfa := 'automation_v4.0_colo52/4.0_D_SA_PRIME_PFA.LHC').fork(),
        WaitForResource('disp'),
    ]
    for i in range(100):
        cmds += [
            WashCmd('Validate', 'automation_v4.0_colo52/7_W_3X_beforeStains_leaves10ul_PBS.LHC').fork(),
            Idle((i % 10 + 15) * 0.01),
            DispCmd('RunValidated', pfa).fork(),
            WaitForResource('disp'),
            WaitForResource('wash'),
        ]
    return Program(Seq(*cmds).add(Metadata(gui_force_show=True)))

@ur_protocols.append
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
                IncuCmd('put', p.incu_loc).fork(),
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

@ur_protocols.append
def test_comm(_: SmallProtocolArgs):
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    return Program(protocol.program_test_comm().add(Metadata(gui_force_show=True)))

@ur_protocols.append
def test_circuit(args: SmallProtocolArgs):
    '''
    Move one plate around to all its positions using the robotarm, without running incubator, bluewasher or bioteks.

    Required lab prerequisites:
        1. hotel one:               empty!
        2. hotel two:               empty!
        3. hotel three:             empty!
        4. biotek washer:           empty!
        5. biotek dispenser:        empty!
        5. bluewasher:              empty!
        6. incubator transfer door: one plate with lid
        7. robotarm:                in neutral position by lid hotel
    '''
    [[plate]] = define_plates([1])
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    protocol_config = make_protocol_config(paths, ProtocolArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=True))
    program = cell_paint_program([1], protocol_config=protocol_config)
    cmds = program.command
    cmds = Seq(
        *[
            cmd.add(metadata)
            for cmd, metadata in cmds.collect()
            if isinstance(cmd, RobotarmCmd)
            # if metadata.step not in {'Triton', 'Stains'}
        ],
        *RobotarmCmds(plate.out_get),
        *RobotarmCmds('B21-to-incu'),
    )
    return Program(cmds, World({'incu': plate.id}))

@ur_protocols.append
def test_circuit_with_incubator(args: SmallProtocolArgs):
    '''
    Move plates around to all its positions using the robotarm and incubator, without running bluewasher or bioteks.
    Plates start in incubator L1, L2, .. as normal cell painting
    '''
    num_plates = args.num_plates
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    protocol_config = make_protocol_config(paths, ProtocolArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=True))
    program = cell_paint_program([num_plates], protocol_config=protocol_config)
    cmds = program.command
    cmds = Seq(
        *[
            cmd.add(metadata)
            for cmd, metadata in cmds.collect()
            if any([
                isinstance(cmd, RobotarmCmd),
                isinstance(cmd, Fork) and cmd.resource == 'incu',
                isinstance(cmd, WaitForResource) and cmd.resource == 'incu' ,
                isinstance(cmd, WaitForCheckpoint) and re.search(r'\bincu\b', cmd.name),
                isinstance(cmd, Checkpoint) and re.search(r'\bincu\b', cmd.name),
            ])
        ],
    )
    return Program(cmds, world0=program.world0)

@ur_protocols.append
def measure_liquids(args: SmallProtocolArgs):
    '''
    Measure liquids from dispenser and washers by moving one plate several times around running all the protocols.
    No incubation. No lids are used.

    Use num plates for the number of times each step will be run.

    B21: plate without lid
    washer, dispenser, bluewasher: no plate  and connected as desired
    '''
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    p = make_protocol_config(paths, ProtocolArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=True))
    cmds: list[Command] = []

    def Predisp(cmd: Command):
        return cmd.add_to_physical_commands(Metadata(plate_id=None))

    for prime in p.wash_prime:
        if prime:
            cmds += [
                Predisp(
                    Fork(ValidateThenRun('wash', prime)),
                )
            ]

    blue_primed: bool = False
    loc: str = 'B21'
    prev: str

    # pbutils.p(p)

    for step in p.steps:
        step_cmds: list[Command] = []
        if step.blue and not blue_primed:
            blue_primed = True
            for prime in p.blue_prime:
                if prime:
                    assert loc != 'blue', f'Cannot prime blue washer with the plate there ({loc=})'
                    step_cmds += [
                        Predisp(
                            Fork(ValidateThenRun('blue', prime)),
                            # cannot align='end' here without checkpoint making sure plate has left blue washer
                        ),
                        WaitForResource('blue'),
                    ]
        if step.disp_prime:
            step_cmds += [
                Predisp(
                    Fork(ValidateThenRun('disp', step.disp_prime), align='end'),
                ),
            ]
        for i in range(args.num_plates):
            stage_cmds: list[Command] = []
            if not step.blue and not step.wash:
                step = replace(step, blue='evacuate/HardDecant.prog')
            if step.blue and step.wash:
                raise ValueError(f'Cannot have both {step.blue=} and {step.wash=}')
            if step.blue:
                prev, loc = loc, 'blue'
                stage_cmds += [
                    Fork(BlueCmd('Validate', step.blue) >> Early(5), align='end') if i == 0 else Idle(),
                    *(RobotarmCmds(f'{prev}-to-{loc}') if prev != loc else []),
                    Fork(BlueCmd('RunValidated', step.blue)),
                    WaitForResource('blue'),
                ]
            if step.wash:
                prev, loc = loc, 'wash'
                stage_cmds += [
                    Fork(WashCmd('Validate', step.wash) >> Early(5), align='end') if i == 0 else Idle(),
                    *(RobotarmCmds(f'{prev}-to-{loc}') if prev != loc else []),
                    Fork(WashCmd('RunValidated', step.wash)),
                    WaitForResource('wash'),
                ]
            if step.disp_prep:
                stage_cmds += [
                    Predisp(
                        Fork(ValidateThenRun('disp', step.disp_prep), align='end'),
                    )
                ]
            if step.disp:
                prev, loc = loc, 'disp'
                stage_cmds += [
                    Fork(DispCmd('Validate', step.disp) >> Early(5), align='end') if i == 0 else Idle(),
                    *(RobotarmCmds(f'{prev}-to-{loc}') if prev != loc else []),
                    Fork(DispCmd('RunValidated', step.disp)),
                    WaitForResource('disp'),
                ]
            step_cmds += [
                Seq(*stage_cmds).add(Metadata(stage=f'{step.name}, iteration {i+1}'))
            ]
        cmds += [
            Seq(*step_cmds).add(Metadata(plate_id='1', section=step.name))
        ]

    from itertools import count
    unique = count(0).__next__

    def W(cmd: Command):
        i = unique()
        if isinstance(cmd, Fork):
            return Seq(Early(0) + f'idle {i}', cmd)
        else:
            return cmd

    cmds = [
        Checkpoint('start'),
        protocol.program_test_comm(with_incu=False, with_blue=True),
        *cmds,
        Duration('start', Min(1)),
    ]

    cmd = Seq(*cmds).transform(W)
    prog = Program(cmd, world0=World({'B21': '1'}))
    return prog

@ur_protocols.append
def incu_reset_and_activate(_: SmallProtocolArgs):
    '''
    Reset and activate the incubator.
    '''
    program = Seq(
        IncuCmd('reset_and_activate').fork(),
        WaitForResource('incu'),
        IncuCmd('get_status').fork(),
        WaitForResource('incu'),
    )
    return Program(program.add(Metadata(gui_force_show=True)))

@ur_protocols.append
def wash_plates_clean(args: SmallProtocolArgs):
    '''
    Wash test plates clean using ethanol.

    Required lab prerequisites:
        1. incubator transfer door: not used
        2. hotel B21:               empty
        3. hotel A1, A2, ...:       plates with lid
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
    return Program(program, world0)

@ur_protocols.append
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

@ur_protocols.append
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
                    Fork(ValidateThenRun(machine, p)),
                    WaitForResource(machine)
                ]
    return Program(Seq(*cmds))

@ur_protocols.append
def incu_put(args: SmallProtocolArgs):
    '''
    Insert a plate into the incubator.

    Use incubator locations such as L1.
    '''
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            IncuCmd('put', x).fork(),
            WaitForResource('incu'),
        ]
    return Program(Seq(*cmds))

@ur_protocols.append
def incu_get(args: SmallProtocolArgs):
    '''
    Eject a plate from the incubator.

    Use incubator locations such as L1.
    '''
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            IncuCmd('get', x).fork(),
            WaitForResource('incu'),
        ]
    return Program(Seq(*cmds))

@ur_protocols.append
def run_robotarm(args: SmallProtocolArgs):
    '''
    Run robotarm programs.

    Example arguments: wash-put-prep, 'B21-to-wash prep'
    '''
    cmds: list[Command] = []
    for x in args.params:
        cmds += [
            RobotarmCmd(x)
            if moves.guess_robot(x) == 'ur' else
            WithLock('PF and Fridge', [PFCmd(x)]),
        ]
    return Program(Seq(*cmds))

@ur_protocols.append
def robotarm_ur_cycle(args: SmallProtocolArgs):
    '''
    Small stress test on robotarm on B21 and B19. Set number of cycles with num_plates.

    Required lab prerequisites:
        B21: plate with lid
        B19: empty
    '''
    N = args.num_plates or 4
    cmds = [
        RobotarmCmd('ur gripper init and check'),
    ]
    for _i in range(N):
        cmds += [
            *RobotarmCmds('B19 put'),
            *RobotarmCmds('B19 get'),
            *RobotarmCmds('lid-B19 put'),
            *RobotarmCmds('lid-B19 get'),
        ]
    program = Seq(*cmds)
    return Program(program)

@ur_protocols.append
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

# @ur_protocols.append
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
    program = Seq(*cmds)
    return Program(program)

# @ur_protocols.append
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
            RobotarmCmd(f'incu-to-A{pos} prep'),
            Fork(IncuCmd('get', p.incu_loc), align='end'),
            RobotarmCmd(f'incu-to-A{pos} transfer'),
            IncuCmd('get_status', None).fork(), # signal to incu that it's now empty
            RobotarmCmd(f'incu-to-A{pos} return'),
        ]
    return Program(Seq(*cmds))

# @ur_protocols.append
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
            IncuCmd('get', src).fork(),
            WaitForResource('incu'),
            IncuCmd('put', dest).fork(),
            WaitForResource('incu'),
        ]
    program = Seq(*cmds)
    return program

# @ur_protocols.append
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

@ur_protocols.append
def time_protocols(args: SmallProtocolArgs):
    '''
    Timing for biotek and bluewasher protocols.

    Required lab prerequisites:
        1. biotek washer:    one plate *without* lid
        2. biotek washer:    connected to water
        3. biotek dispenser: all pumps and syringes disconnected (air or water with plate)
        4. bluewasher:       correct balance plate inserted, one plate *without* lid presented as working plate
        5. robotarm:         not used
    '''
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    wash = [
        ValidateThenRun('wash', p)
        for p in paths.all_wash_paths()
    ]
    disp = [
        ValidateThenRun('disp', p)
        for p in paths.all_disp_paths()
    ]
    blue = [
        ValidateThenRun('blue', p)
        for p in paths.all_blue_paths()
    ]
    program = Seq(
        Fork(Seq(*wash)),
        Fork(Seq(*disp)).delay(2),
        Fork(Seq(*blue)),
        WaitForResource('wash'),
        WaitForResource('disp'),
        WaitForResource('blue'),
    )
    return Program(program)

@ur_protocols.append
def bluewash_reset_and_activate(args: SmallProtocolArgs):
    '''
    Required to run before using BlueWasher:
    Initializes linear drive, rotor, inputs, outputs, motors, valves.
    Presents working carrier (= top side of rotor) to RACKOUT.
    '''
    return Program(
        Seq(
            BlueCmd('reset_and_activate').fork(),
            WaitForResource('blue'),
        )
    )

@ur_protocols.append
def wave(args: SmallProtocolArgs):
    '''
    Makes the robot wave.
    '''
    waves = [RobotarmCmd('wave')] * 2
    return Program(Seq(*waves))

def fill_estimates(cmd: Command):
    for c in cmd.universe():
        if isinstance(c, RobotarmCmd):
            moves.movelists[c.program_name] = moves.MoveList()
        if isinstance(c, Meta) and (est := c.metadata.est) is not None:
            i = c.peel_meta()
            if isinstance(i, estimates.PhysicalCommand):
                estimates.estimates[i] = est
                # print(i, est)


# @ur_protocols.append
def example(args: SmallProtocolArgs):
    '''
    Example prepared for presentation for BRICs
    '''
    args.params
    params = [int(p) for p in args.params if p.isdigit()]
    time_pfa, *_ = [*params, 15]
    time_mito = 20
    if 0: pbutils.pr(dict(
        time_pfa=time_pfa,
        time_mito=time_mito,
    ))
    class X:
        wait_disp = WaitForResource('disp')

        disp_init = Fork(DispCmd('TestCommunications', None))
        arm_hotel_to_disp = RobotarmCmd('hotel-to-disp') @ Metadata(est=15, plate_id='to disp')
        arm_disp_to_hotel = Seq(
            RobotarmCmd('disp-to-hotel') @ Metadata(est=17, plate_id='to hotel'),
        )

        disp_mito = Fork(DispCmd('Run', 'mito') @ Metadata(est=time_mito, plate_id='mito'))
        disp_mix_mito = Fork(
            Seq(DispCmd('Run', 'mix') @ Metadata(est=25, plate_id='mix mito')),
            align='end'
        )

        disp_pfa = Fork(DispCmd('Run', 'pfa') @ Metadata(est=time_pfa, plate_id='PFA'))
        disp_prime_pfa_fork = Fork(
            Seq(DispCmd('Run', 'prime_pfa') @ Metadata(est=25, plate_id='prime PFA')),
        )
        disp_prime_pfa_prefork = Fork(
            Seq(DispCmd('Run', 'prime_pfa') @ Metadata(est=25, plate_id='prime PFA')),
            align='end'
        )

        disp_prime_mito_prefork = Fork(
            Seq(DispCmd('Run', 'prime_mito') @ Metadata(est=25, plate_id='prime mito')),
            align='end'
        )

    incu_time = 120

    cmds = [
        Checkpoint('batch'),
        # X.disp_init,

        Idle(0) + 'idle',
        X.arm_hotel_to_disp,
        # X.disp_prime_mito_prefork,
        X.disp_mito,
        X.wait_disp,
        Checkpoint('incu 1'),
        X.arm_disp_to_hotel,

        WaitForCheckpoint('batch') + 'sep',

        X.arm_hotel_to_disp,
        X.disp_mito,
        X.wait_disp,
        Checkpoint('incu 2'),
        X.arm_disp_to_hotel,

        # X.disp_prime_pfa_fork.delay(17),

        WaitForCheckpoint('incu 1') + 'wait 1',
        Duration('batch', Max(1)),

        X.arm_hotel_to_disp,

        WaitForCheckpoint('incu 1') + incu_time,
        Duration('incu 1', Max(1)),

        # X.disp_prime_pfa_prefork,

        X.disp_pfa,
        X.wait_disp,
        X.arm_disp_to_hotel,

        WaitForCheckpoint('incu 2') + 'wait 2',
        Duration('batch', Max(1)),

        X.arm_hotel_to_disp,
        WaitForCheckpoint('incu 2') + incu_time,
        Duration('incu 2', Max(1)),
        X.disp_pfa,
        X.wait_disp,
        X.arm_disp_to_hotel,

        Duration('batch', Min(2))
    ]
    cmd = Seq(*cmds)
    fill_estimates(cmd)
    return Program(cmd)

def pf_fridge_program(cmds: list[Command]) -> Program:
    cmds = [
        WithLock('PF and Fridge', cmds),
    ]
    return Program(Seq(*cmds))

@pf_protocols.append
def fridge_reset_and_activate(args: SmallProtocolArgs) -> Program:
    return pf_fridge_program([FridgeCmd('reset_and_activate').fork_and_wait()])

@pf_protocols.append
def pf_init(args: SmallProtocolArgs) -> Program:
    return pf_fridge_program([PFCmd('pf init')])

@pf_protocols.append
def pf_freedrive(args: SmallProtocolArgs) -> Program:
    return pf_fridge_program([PFCmd('pf freedrive')])

@pf_protocols.append
def pf_stop_freedrive(args: SmallProtocolArgs) -> Program:
    return pf_fridge_program([PFCmd('pf stop freedrive')])

@pf_protocols.append
def fridge_load(args: SmallProtocolArgs) -> Program:
    '''

        Loads --num-plates from hotel to fridge. Specify the project of the plates in params[0].

    '''
    cmds: list[Command] = []
    args.num_plates
    if len(args.params) != 1:
        return Program(Seq())
    project, *_ = args.params
    for i, _ in reversed(list(enumerate(range(args.num_plates), start=1))):
        assert i <= 12
        cmds += [
            BarcodeClear(),
            PFCmd(f'H{i}-to-H12') if i != 12 else Seq(),
            PFCmd(f'H12-to-fridge'),
            FridgeInsert(project).fork_and_wait(),
        ]
    cmds = [
        WithLock('PF and Fridge', cmds),
    ]
    return Program(Seq(*cmds))

@pf_protocols.append
def fridge_unload(args: SmallProtocolArgs) -> Program:
    '''

        Unloads --num-plates from fridge to hotel in dictionary order. Specify the project of the plates in params[0].

    '''
    cmds: list[Command] = []
    args.num_plates
    if len(args.params) != 1:
        return Program(Seq())
    import labrobots
    try:
        contents = labrobots.WindowsGBG().remote().fridge.contents()
    except:
        contents = {}
    project, *_ = args.params
    plates = sorted(
        [
            slot['plate']
            for slot in contents.values()
            if slot['project'] == project
        ]
    )
    for i, plate in enumerate(plates[:args.num_plates], start=1):
        assert i <= 12
        cmds += [
            FridgeEject(plate=plate, project=project).fork_and_wait(),
            PFCmd(f'fridge-to-H12'),
            PFCmd(f'H12-to-H{i}'),
        ]
    cmds = [
        WithLock('PF and Fridge', cmds),
    ]
    return Program(Seq(*cmds))


@pf_protocols.append
def squid_from_hotel(args: SmallProtocolArgs) -> Program:
    '''

        Images the plate at H12. Params are: protocol, project, plate

    '''
    cmds: list[Command] = []
    if len(args.params) != 3:
        return Program(Seq())
    config_path, project, plate = args.params
    cmds += [
        WithLock('Squid', [
            WithLock('PF and Fridge', [
                SquidStageCmd('goto_loading').fork_and_wait(),
                PFCmd('H12-to-squid'),
            ]),
            Seq(
                SquidStageCmd('leave_loading'),
                SquidAcquire(config_path, project=project, plate=plate),
            ).fork_and_wait(),
            WithLock('PF and Fridge', [
                SquidStageCmd('goto_loading').fork_and_wait(),
                PFCmd('squid-to-H12'),
            ]),
            SquidStageCmd('leave_loading').fork_and_wait(),
        ])
    ]
    return Program(Seq(*cmds))


@pf_protocols.append
def nikon_from_hotel(args: SmallProtocolArgs) -> Program:
    '''

        Images the plate at H12. Params are: job name, project, plate_name_1, ..., plate_name_N

    '''
    cmds: list[Command] = []
    if len(args.params) < 3:
        return Program(Seq())
    job_name, project, *plate_names = args.params
    for plate_name in plate_names:
        cmds += [
            WithLock('Nikon', [
                WithLock('PF and Fridge', [
                    NikonStageCmd('goto_loading').fork_and_wait(),
                    PFCmd('H12-to-nikon'),
                ]),
                Seq(
                    NikonStageCmd('leave_loading'),
                    NikonAcquire(job_name=job_name, project=project, plate=plate_name),
                ).fork_and_wait(),
                WithLock('PF and Fridge', [
                    NikonStageCmd('goto_loading').fork_and_wait(),
                    PFCmd('nikon-to-H12'),
                ]),
            ])
        ]
    return Program(Seq(*cmds))


@pf_protocols.append
def squid_from_fridge(args: SmallProtocolArgs) -> Program:
    '''

        Images plates in the fridge. Params are: protocol, project, RT_time_secs, plate1_barcode, plate1_name, plate2_barcode, plate2_name,..., plateN_barcode, plateN_name

    '''
    cmds: list[Command] = []
    if len(args.params) < 5:
        return Program(Seq())
    config_path, project, RT_time_secs_str, *barcode_and_plates = args.params
    barcodes = barcode_and_plates[0::2]
    plates = barcode_and_plates[1::2]
    import labrobots
    try:
        contents = labrobots.WindowsGBG().remote().fridge.contents()
    except:
        contents = None
    if contents is not None:
        for barcode in barcodes:
            if sum(
                1
                for _loc, slot in contents.items()
                if slot['project'] == project
                if slot['plate'] == barcode
            ) != 1:
                raise ValueError(f'Could not find {barcode=} from {project=} in fridge!')
    RT_time_secs = float(RT_time_secs_str)
    for i, (barcode, plate) in enumerate(zip(barcodes, plates, strict=True), start=1):
        cmds += [
            FridgeEject(plate=barcode, project=project).fork_and_wait(),
            Checkpoint(f'RT {i}'),
            PFCmd(f'fridge-to-H12'),
            SquidStageCmd('goto_loading').fork_and_wait(),
            PFCmd(f'H12-to-squid'),

            Seq(
                SquidStageCmd('leave_loading'),
                WaitForCheckpoint(f'RT {i}', plus_secs=RT_time_secs, assume='nothing'),
                SquidAcquire(config_path, project=project, plate=plate),
            ).fork_and_wait(),

            SquidStageCmd('goto_loading').fork_and_wait(),
            PFCmd(f'squid-to-H12'),
            SquidStageCmd('leave_loading').fork_and_wait(),
            BarcodeClear(),
            PFCmd(f'H12-to-fridge'),
            FridgeInsert(project, expected_barcode=barcode).fork_and_wait(),
        ]
    cmd = Seq(*cmds)
    cmd = cmd.with_lock('PF and Fridge')
    cmd = cmd.with_lock('Squid')
    return Program(cmd)

@pf_protocols.append
def nikon_open_stage(_: SmallProtocolArgs) -> Program:
    return Program(
        Seq(
            NikonStageCmd('goto_loading').fork_and_wait(),
        ).with_lock('Nikon')
    )

@pf_protocols.append
def H12_to_nikon(_: SmallProtocolArgs) -> Program:
    return Program(
        Seq(
            NikonStageCmd('goto_loading').fork_and_wait(),
            PFCmd('H12-to-nikon'),
            NikonStageCmd('leave_loading').fork_and_wait(),
        ).with_lock('PF and Fridge').with_lock('Nikon')
    )

@pf_protocols.append
def nikon_to_H12(_: SmallProtocolArgs) -> Program:
    return Program(
        Seq(
            NikonStageCmd('goto_loading').fork_and_wait(),
            PFCmd('nikon-to-H12'),
        ).with_lock('PF and Fridge').with_lock('Nikon')
    )

@pf_protocols.append
def nikon_from_fridge(args: SmallProtocolArgs) -> Program:
    '''

        Images plates in the fridge. Params are: job names (comma-separated), project, RT_time_secs, plate1_barcode, plate1_name, plate2_barcode, plate2_name,..., plateN_barcode, plateN_name

    '''
    cmds: list[Command] = []
    if len(args.params) < 5:
        return Program(Seq())
    job_names_csv, project, RT_time_secs_str, *barcode_and_plates = args.params
    job_names = job_names_csv.split(',')
    barcodes = barcode_and_plates[0::2]
    plates = barcode_and_plates[1::2]
    contents = args.fridge_contents
    if contents is not None:
        for barcode in barcodes:
            if sum(
                1
                for _loc, slot in contents.items()
                if slot['project'] == project
                if slot['plate'] == barcode
            ) != 1:
                raise ValueError(f'Could not find {barcode=} from {project=} in fridge!')
    RT_time_secs = float(RT_time_secs_str)
    chunks: dict[tuple[str, int], list[Command]] = {}
    for i, (barcode, plate) in enumerate(zip(barcodes, plates, strict=True), start=1):
        chunks['fridge -> H11', i] = [
            # get from fridge
            Checkpoint(f'Delay eject {i}'),
            WaitForCheckpoint(f'Delay eject {i}', assume='nothing') + f'slack {i}',
            # Duration(f'Delay eject {i}', Min(2)),
            FridgeEject(plate=barcode, project=project, check_barcode=False).fork_and_wait(),
            Checkpoint(f'RT {i}'),
            PFCmd(f'fridge-to-H12'),
            PFCmd(f'H12-to-H11'),
        ]
        chunks['H11 -> nikon', i] = [
            WaitForCheckpoint(f'RT {i}', plus_secs=RT_time_secs, assume='nothing'),
            Duration(f'RT {i}', Min(3)),
            PFCmd(f'H11-to-H12'),
            NikonStageCmd('goto_loading').fork_and_wait(),
            NikonStageCmd('init_laser').fork_and_wait(),
            PFCmd(f'H12-to-nikon'),
            Seq(
                NikonStageCmd('leave_loading'),
                *[
                    NikonAcquire(job_name=job_name, project=project, plate=plate).add(Metadata(plate_id=str(i)))
                    for job_name in job_names
                ],
            ).fork(),
        ]
        chunks['nikon -> fridge', i] = [
            WaitForResource('nikon'),
            NikonStageCmd('goto_loading').fork_and_wait(),
            PFCmd(f'nikon-to-H12'),
            NikonStageCmd('leave_loading').fork(),
            BarcodeClear(),
            PFCmd(f'H12-to-fridge'),
            FridgeInsert(
                project,
                # expected_barcode=barcode
                assume_barcode=barcode, # for RMS-SPECS
            ).fork_and_wait(),
            WaitForResource('nikon'),
        ]
    ilv = Interleaving.init('''
        fridge -> H11
                  H11 -> nikon
        fridge -> H11
                         nikon -> fridge
                  H11 -> nikon
        fridge -> H11
                         nikon -> fridge
                  H11 -> nikon
                         nikon -> fridge
    ''')
    for i, substep in ilv.inst(list([i for i, _ in enumerate(plates, start=1)])):
        cmds += [Seq(*chunks[substep, i]).add(Metadata(section=f'{1 + (i-1)//10} {0}'))]
    cmds = [
        Checkpoint('start'),
        *cmds,
        Duration('start', Min(2)),
    ]
    cmd = Seq(*cmds)
    cmd = cmd.with_lock('PF and Fridge')
    cmd = cmd.with_lock('Nikon')
    return Program(cmd)


@dataclass(frozen=True)
class SmallProtocolData:
    name: str
    make: SmallProtocol
    args: set[str]
    doc: str

small_protocols: list[SmallProtocol] = ur_protocols + pf_protocols

def small_protocols_dict(imager: bool=True, painter: bool=True):
    return {
        p.__name__: SmallProtocolData(
            p.__name__,
            p,
            protocol_args(p),
            pbutils.doc_header(p)
        )
        for p in [
            *(ur_protocols if painter else []),
            *(pf_protocols if imager else []),
        ]
    }
