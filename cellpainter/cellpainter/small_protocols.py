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
    CellPaintingArgs,
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

from pbutils.args import arg

def assert_valid_project_name(s: str):
    import string
    ok = string.ascii_letters + string.digits + '_-'
    for c in s:
        if c not in ok:
            raise ValueError(f'Invalid character {c!r} in {s!r}')
    if not s:
        raise ValueError(f'Input {s!r} is empty')
    if not s[0].isalpha():
        raise ValueError(f'Input {s!r} does not start with alpha')

@dataclass(frozen=True)
class SmallProtocolArgs:
    num_plates: int = arg(1)
    params: list[str] = arg()
    protocol_dir: str = arg('automation_v5.0')
    initial_fridge_contents_json: str = arg('null')

    @property
    def initial_fridge_contents(self) -> FridgeSlots | None:
        import json
        return json.loads(self.initial_fridge_contents_json)

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
    try:
        _ = small_protocol(intercepted_args)
    except:
        pass
    return out - {'fridge_contents'}

@ur_protocols.append
def incu_load(args: SmallProtocolArgs):
    '''
    Load incubator from A hotel, starting at the bottom, to incubator positions L1, L2, ... or starting as specified in params

    Required lab prerequisites:
        1. incubator transfer door: empty!
        2. incubator L1, ...:       empty!
        3. hotel A1, A2, ...:       plates with lid
        4. robotarm:                in neutral position by B hotel
    '''
    num_plates = args.num_plates
    starting_loc = ' '.join(args.params) or 'L1'
    incu_locs = []
    for _, focus, next in pbutils.iterate_with_full_context(Locations.Incu):
        if focus == starting_loc:
            incu_locs = [focus, *next]
            break
    if not incu_locs:
        raise ValueError(f'Cannot start from {starting_loc}, try for example L1 or R1')
    cmds: list[Command] = []
    world0: dict[str, str] = {}
    assert 1 <= num_plates <= 21, 'Number of plates should be in 1..21'
    assert num_plates <= len(Locations.A), 'Too many plates'
    assert num_plates <= len(incu_locs), 'Too few incubator locations left'
    for i, (incu_loc, a_loc) in enumerate(zip(incu_locs, Locations.A[::-1]), start=1):
        if i > num_plates:
            break
        p = Plate(
            id=str(i),
            incu_loc=incu_loc,
            out_loc=a_loc,
            rt_loc='',
            dlid_loc='',
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
        RobotarmCmd('ur gripper init and check'),
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
    return Program(protocol.program_test_comm(with_blue=False).add(Metadata(gui_force_show=True)))

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
    if 'spheroid' in args.protocol_dir.lower():
        '''
        Check if the path contains the string spheroid (regardless of case).
        For spheroid protocols we run the protocol linear, not with interleaving.
        '''
        interleave = False
    else:
        interleave = True
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    protocol_config = make_protocol_config(paths, CellPaintingArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=interleave))
    program = cell_paint_program([1], protocol_config=protocol_config)
    cmds = program.command
    cmds = Seq(
        BlueCmd(action='get_working_plate', protocol_path=None).fork() if protocol_config.use_blue else Idle(),
        RobotarmCmd('ur gripper init and check'),
        WaitForResource('blue') if protocol_config.use_blue else Idle(),
        *[
            cmd.add(metadata)
            for cmd, metadata in cmds.collect(flatten_sections=True)
            if isinstance(cmd, RobotarmCmd | DLidCheckStatusCmd)
        ],
        *RobotarmCmds(plate.out_get),
        *RobotarmCmds(f'{plate.dlid_loc}-to-incu'),
    )
    if protocol_config.steps and protocol_config.steps[0].name in ['Mito', 'PFA']:
        w0 = World({'incu': plate.id})
    else:
        w0 = World({plate.rt_loc: plate.id})
    return Program(cmds, w0)

@ur_protocols.append
def test_circuit_with_incubator(args: SmallProtocolArgs):
    '''
    Move plates around to all its positions using the robotarm and incubator, without running bluewasher or bioteks.
    Plates start in incubator L1, L2, .. as normal cell painting
    '''
    num_plates = args.num_plates
    assert 1 <= num_plates <= 21, 'Number of plates should be in 1..21'
    if 'spheroid' in args.protocol_dir.lower():
        '''
        Check if the path contains the string spheroid (regardless of case).
        For spheroid protocols we run the protocol linear, not with interleaving.
        '''
        interleave = False
    else:
        interleave = True
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    protocol_config = make_protocol_config(paths, CellPaintingArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=interleave))
    program = cell_paint_program([num_plates], protocol_config=protocol_config)
    cmds = program.command
    cmds = Seq(
        BlueCmd(action='get_working_plate', protocol_path=None).fork() if protocol_config.use_blue else Idle(),
        RobotarmCmd('ur gripper init and check'),
        WaitForResource('blue') if protocol_config.use_blue else Idle(),
        *[
            cmd.add(metadata)
            for cmd, metadata in cmds.collect(flatten_sections=True)
            if any([
                isinstance(cmd, RobotarmCmd),
                isinstance(cmd, DLidCheckStatusCmd),
                isinstance(cmd, Fork) and cmd.resource == 'incu',
                isinstance(cmd, WaitForResource) and cmd.resource == 'incu' ,
                isinstance(cmd, WaitForCheckpoint) and re.search(r'\bincu\b', cmd.name),
                isinstance(cmd, Checkpoint) and re.search(r'\bincu\b', cmd.name),
            ])
        ],
    )
    return Program(cmds, world0=program.world0)

# @ur_protocols.append
def measure_liquids(args: SmallProtocolArgs):
    '''
    Measure liquids from dispenser and washers by moving one plate several times around running all the protocols.
    No incubation. No lids are used.

    Use num plates for the number of times each step will be run.

    B21: plate without lid
    washer, dispenser, bluewasher: no plate  and connected as desired
    '''
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    p = make_protocol_config(paths, CellPaintingArgs(incu='s1,s2,s3,s4,s5', two_final_washes=True, interleave=True))
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
                    *(RobotarmCmds(f'{prev}-to-{loc}') if prev != loc else []),
                    Fork(BlueCmd('Run', step.blue)),
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

# @ur_protocols.append
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
def run_bluewasher(args: SmallProtocolArgs):
    '''
    Run protocols on the bioteks or bluewasher from the protocol directory.

    For each parameter $X runs all protocols that matches ${PROTOCOL_DIR}/$X.
    For example with automation_v4.0, "2" will run
    automation_v4.0/2.0_D_SB_PRIME_Mito and then
    automation_v4.0/2.1_D_SB_30ul_Mito.
    '''
    cmds: list[Command] = []
    for path in args.params:
        cmds += [BlueCmd(action='Run', protocol_path=path).fork_and_wait()]
    return Program(Seq(*cmds))

@ur_protocols.append
def run_biotek_bluewasher(args: SmallProtocolArgs):
    '''
    Run protocols on the bioteks or bluewasher from the protocol directory.

    For each parameter $X runs all protocols that matches ${PROTOCOL_DIR}/$X.
    For example with automation_v4.0, "2" will run
    automation_v4.0/2.0_D_SB_PRIME_Mito and then
    automation_v4.0/2.1_D_SB_30ul_Mito.
    '''
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]
    wash = paths.all_wash_paths()
    disp = paths.all_disp_paths()
    blue = paths.all_blue_paths()
    protocols = [
        *[(p, 'wash') for p in wash],
        *[(p, 'disp') for p in disp],
        *[(p, 'blue') for p in blue],
    ]
    # print('Available:', end=' ')
    # pbutils.pr([p for p, _ in protocols])
    cmds: list[Command] = []
    for x in args.params:
        ok = False
        for p, machine in protocols:
            if f'/{x.lower()}' in p.lower():
                cmds += [
                    Fork(ValidateThenRun(cast(Any, machine), p)),
                    WaitForResource(cast(Any, machine))
                ]
                ok = True
        if not ok:
            raise ValueError(f'No protocol starting with {x}')
    return Program(Seq(*cmds))

@ur_protocols.append
def incu_put(args: SmallProtocolArgs):
    '''
    Insert a plate into the incubator from its transfer door.

    Use incubator locations such as L1.
    '''
    cmds: list[Command] = []
    for x in args.params:
        assert x in Locations.Incu, f'Not a valid location: {x!r}. Locations are named L1, L2, ..'
        cmds += [
            IncuCmd('put', x).fork(),
            WaitForResource('incu'),
        ]
    return Program(Seq(*cmds))

@ur_protocols.append
def incu_get(args: SmallProtocolArgs):
    '''
    Eject a plate from the incubator to its transfer door.

    Use incubator locations such as L1.
    '''
    cmds: list[Command] = []
    for x in args.params:
        assert x in Locations.Incu, f'Not a valid location: {x!r}. Locations are named L1, L2, ..'
        cmds += [
            IncuCmd('get', x).fork(),
            WaitForResource('incu'),
        ]
    return Program(Seq(*cmds))

# @ur_protocols.append
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
    plate = Plate(
        id='',
        incu_loc='',
        out_loc='',
        rt_loc='',
        lid_loc='',
        dlid_loc='',
        batch_index=1
    )
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
        *RobotarmCmds('B16 put'),
        *RobotarmCmds('B16-to-wash'),
        *RobotarmCmds('wash-to-B16'),
        *RobotarmCmds('B16 get'),
        *RobotarmCmds(plate.lid_get),
        *RobotarmCmds('B21-to-incu'),
    ]
    program = Seq(*arm)
    return Program(program, world0=World({'incu': '1'}))

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
            dlid_loc='',
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
    waves = [RobotarmCmd('wave')]
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

LoadLocs   = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 13]
UnloadLocs = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 13]

@pf_protocols.append
def fridge_load_from_hotel(args: SmallProtocolArgs) -> Program:
    '''

        Loads --num-plates from hotel to fridge, from H11 and down and then H13.

        Specify the project of the plates in params[0].

    '''
    cmds: list[Command] = []
    N = len(LoadLocs)
    assert 1 <= args.num_plates <= N, f'Number of plates should be in 1..{N} (not {args.num_plates})'
    assert len(args.params) == 1, 'Specify one project'
    project, *_ = args.params
    assert_valid_project_name(project)
    top, *rest = LoadLocs[:args.num_plates]
    locs = [top, *rest[::-1]] # first take H11 then go from bottom to top
    for i in locs:
        assert 1 <= i <= 19, f'Internal error: trying to use shelf {i}'
        assert i != 12, f'Internal error: trying to use shelf {i}'
        cmds += [
            XArmCmd(f'H{i}-to-H11') if i != 11 else Seq(),
            WaitForResource('fridge'),
            BarcodeClear(),
            XArmCmd(f'H11-to-fridge'),
            XArmCmd('fridge-barcode-wave', only_if_no_barcode=True),
            FridgeInsert(project).fork(),
        ]
    cmds += [
        WaitForResource('fridge'),
    ]
    return Program(Seq(*cmds))


def fridge_unload_helper(plates: list[str]) -> Program:
    N = len(UnloadLocs)
    assert 1 <= len(plates) <= N, f'Number of plates should be in 1..{N} (not {len(plates)})'
    cmds: list[Command] = []
    for i, plate in reversed(list(zip(UnloadLocs, plates))):
        assert 1 <= i <= 19, f'Internal error: trying to use shelf {i}'
        assert i != 12, f'Internal error: trying to use shelf {i}'
        project, sep, barcode = plate.partition(':')
        assert sep, 'Separate project and barcode with :'
        cmds += [
            FridgeEject(plate=barcode, project=project, check_barcode=False).fork_and_wait(align='end'),
            XArmCmd(f'fridge-to-H11'),
            FridgeCmd('get_status').fork_and_wait(), # after this the fridge can eject the next
            XArmCmd(f'H11-to-H{i}') if i != 11 else Idle(),
        ]
    return Program(Seq(*cmds))

@pf_protocols.append
def fridge_unload(args: SmallProtocolArgs) -> Program:
    '''

        Specify project1:barcode1 .. projectN:barcodeN in params

    '''
    fridge_contents = args.initial_fridge_contents
    if fridge_contents:
        slots = {
            f'{slot["project"]}:{slot["plate"]}'
            for _, slot in fridge_contents.items()
        }
        for plate in args.params:
            if plate not in slots:
                raise ValueError(f'Cannot find {plate} in fridge')
    return fridge_unload_helper(args.params)

@pf_protocols.append
def fridge_put(args: SmallProtocolArgs):
    '''
    Insert a plate into the fridge from its transfer door. Put barcode in params
    '''
    barcode, project = args.params
    cmd = FridgeInsert(project=project, assume_barcode=barcode).fork_and_wait()
    return Program(cmd)


@pf_protocols.append
def squid_acquire_H11(args: SmallProtocolArgs) -> Program:
    '''

        Images the plate at H11 and puts it back. Params are: protocol, project, plate_name_1, ..., plate_name_N

    '''
    cmds: list[Command] = []
    protocol_path, project, *plate_names = args.params
    assert_valid_project_name(project)
    cmds += [SquidStageCmd('check_protocol_exists', protocol_path).fork_and_wait()]
    for plate_name in plate_names:
        cmds += [
            SquidStageCmd('goto_loading').fork_and_wait(),
            XArmCmd('H11-to-squid'),
            Seq(
                SquidStageCmd('leave_loading'),
                SquidAcquire(protocol_path, project=project, plate=plate_name),
            ).fork_and_wait(),
            SquidStageCmd('goto_loading').fork_and_wait(),
            XArmCmd('squid-to-H11'),
            SquidStageCmd('leave_loading').fork_and_wait(),
        ]
    return Program(Seq(*cmds))

@pf_protocols.append
def nikon_acquire_H11(args: SmallProtocolArgs) -> Program:
    '''

        Images the plate at H11 and puts it back. Params are: job_project job_name, project, plate_name_1, ..., plate_name_N

    '''
    cmds: list[Command] = []
    job_project, job_name, project, *plate_names = args.params
    assert_valid_project_name(project)
    cmds += [NikonStageCmd('check_protocol_exists', job_project=job_project, job_name=job_name).fork_and_wait()]

    for plate_name in plate_names:
        cmds += [
            NikonStageCmd('goto_loading').fork_and_wait(),
            XArmCmd(f'H11-to-nikon'),
            Seq(
                NikonStageCmd('leave_loading'),
                NikonAcquire(job_project=job_project, job_name=job_name, project=project, plate=plate_name),
            ).fork_and_wait(),

            NikonStageCmd('goto_loading').fork_and_wait(),
            XArmCmd(f'nikon-to-H11'),
            NikonStageCmd('leave_loading').fork_and_wait(),
        ]
    return Program(Seq(*cmds))

@pf_protocols.append
def test_circuit_to_squid(args: SmallProtocolArgs) -> Program:
    '''

        Puts a plate from H11 to squid and back. Squid software needs to be running and squid should be empty.

    '''
    cmds: list[Command] = []
    cmds += [
        SquidStageCmd('goto_loading').fork_and_wait(),
        XArmCmd('H11-to-squid'),
        SquidStageCmd('leave_loading').fork_and_wait(),
        SquidStageCmd('goto_loading').fork_and_wait(),
        XArmCmd('squid-to-H11'),
        SquidStageCmd('leave_loading').fork_and_wait(),
    ]
    N = int((args.params or ['1'])[0])
    cmds = cmds * N
    return Program(Seq(*cmds))

# @pf_protocols.append
def test_circuit_to_nikon(args: SmallProtocolArgs) -> Program:
    '''

        Puts a plate from H11 to squid and back. Nikon should be empty.

    '''
    cmds: list[Command] = []
    cmds += [
        XArmCmd('H11-to-nikon'),
        XArmCmd('nikon-to-H11'),
    ]
    N = int((args.params or ['1'])[0])
    cmds = cmds * N
    cmds = [
        NikonStageCmd('goto_loading').fork_and_wait(),
        *cmds,
        NikonStageCmd('leave_loading').fork_and_wait(),
    ]
    return Program(Seq(*cmds))

@pf_protocols.append
def test_circuit_to_fridge(args: SmallProtocolArgs) -> Program:
    '''

        Puts a plate from H11 to the white fridge transfer station and back, then to go to H10 and back to H11. Fridge transfer station should be empty.

    '''
    cmds: list[Command] = []
    cmds += [
        XArmCmd('H11-to-fridge'),
        XArmCmd('fridge-barcode-wave'),
        XArmCmd('fridge-to-H11'),
        XArmCmd('H11-to-H10'),
        XArmCmd('H10-to-H11'),
    ]
    return Program(Seq(*cmds))

@pf_protocols.append
def test_circuit_to_squid_and_fridge(args: SmallProtocolArgs) -> Program:
    '''

        Start with a plate in H11. Will move between H13, fridge and squid. Squid software needs to be running.

    '''
    cmds: list[Command] = []
    cmds = [
        SquidStageCmd('goto_loading').fork_and_wait(),
        XArmCmd('H11-to-squid'),
        SquidStageCmd('leave_loading').fork_and_wait(),
        SquidStageCmd('goto_loading').fork_and_wait(),
        XArmCmd('squid-to-H11'),
        SquidStageCmd('leave_loading').fork_and_wait(),
    ]
    cmds = [
        *cmds,

        XArmCmd('H11-to-fridge'),
        XArmCmd('fridge-to-H11'),
        *cmds,

        XArmCmd('H11-to-H13'),
        XArmCmd('H13-to-H11'),
        *cmds,

        XArmCmd('H11-to-fridge'),
        XArmCmd('fridge-to-H11'),
        XArmCmd('H11-to-H13'),
        XArmCmd('H13-to-H11'),
        *cmds,

        XArmCmd('H11-to-H13'),
        XArmCmd('H13-to-H11'),
        XArmCmd('H11-to-fridge'),
        XArmCmd('fridge-to-H11'),
        *cmds,
    ]
    N = int((args.params or ['1'])[0])
    cmds = cmds * N
    return Program(Seq(*cmds))



@pf_protocols.append
def H11_to_squid(args: SmallProtocolArgs) -> Program:
    '''
    Moves the plate at H11 to the squid.
    '''
    cmds: list[Command] = [
        SquidStageCmd('goto_loading').fork_and_wait(),
        XArmCmd('H11-to-squid'),
        SquidStageCmd('leave_loading').fork_and_wait(),
    ]
    cmd = Seq(*cmds)
    return Program(cmd)

@pf_protocols.append
def squid_to_H11(args: SmallProtocolArgs) -> Program:
    '''
    Moves the plate on the squid to H11.
    '''
    cmds: list[Command] = [
        SquidStageCmd('goto_loading').fork_and_wait(),
        XArmCmd('squid-to-H11'),
        SquidStageCmd('leave_loading').fork_and_wait(),
    ]
    cmd = Seq(*cmds)
    return Program(cmd)

@pf_protocols.append
def H11_to_nikon(args: SmallProtocolArgs) -> Program:
    '''
    Moves the plate at H11 to the nikon.
    '''
    cmds: list[Command] = [
        NikonStageCmd('goto_loading').fork_and_wait(),
        XArmCmd('H11-to-nikon'),
        NikonStageCmd('leave_loading').fork_and_wait(),
    ]
    cmd = Seq(*cmds)
    return Program(cmd)

@pf_protocols.append
def nikon_to_H11(args: SmallProtocolArgs) -> Program:
    '''
    Moves the plate on the nikon to H11.
    '''
    cmds: list[Command] = [
        NikonStageCmd('goto_loading').fork_and_wait(),
        XArmCmd('nikon-to-H11'),
        NikonStageCmd('leave_loading').fork_and_wait(),
    ]
    cmd = Seq(*cmds)
    return Program(cmd)

def group_consecutive_by(xs: list[A], key: Callable[[A], Any]) -> list[list[A]]:
    g = DefaultDict[int, list[A]](list)
    i = 0
    for prev, x in pbutils.iterate_with_prev(xs):
        if prev is not None and key(prev) != key(x):
            i += 1
        g[i] += [x]
    return list(g.values())

@dataclass(frozen=True)
class ParsedPlate:
    protocol_path: str
    project: str
    barcode: str
    name: str

    @staticmethod
    def parse(plate: str):
        protocol_path, project, barcode, name = plate.split(':')
        return ParsedPlate(
            protocol_path=protocol_path,
            project=project,
            barcode=barcode,
            name=name,
         )


@pf_protocols.append
def squid_acquire_from_fridge(args: SmallProtocolArgs) -> Program:
    '''

        Images plates in the fridge.  Params are: RT_time_secs_csv protocol_path_1:project:barcode:name .. protocol_path_N:project:barcode:name

    '''
    cmds: list[Command] = []
    RT_time_secs_csv, *raw_plates = args.params
    plates: list[ParsedPlate] = [ParsedPlate.parse(raw_plate) for raw_plate in raw_plates]
    contents = args.initial_fridge_contents
    if contents is not None:
        for plate in plates:
            if sum(
                1
                for _loc, slot in contents.items()
                if slot['project'] == plate.project
                if slot['plate'] == plate.barcode
            ) != 1:
                raise ValueError(f'Could not find {plate.barcode} from {plate.project} in fridge!')
    RT_time_secs: list[float] = [float(rt) for rt in RT_time_secs_csv.split(',')]
    if not RT_time_secs:
        raise ValueError('Specify some RT time. Example: "1800" for 30 minutes')
    if not plates:
        raise ValueError('Select some plates.')
    ilv = Interleaving.init('''
        fridge -> H13
                  H13 -> squid
        fridge -> H13
                         squid -> fridge
                  H13 -> squid
        fridge -> H13
                         squid -> fridge
                  H13 -> squid
                         squid -> fridge
    ''')
    checks: list[Command] = []
    chunks: dict[tuple[str, int], list[Command]] = {}
    plate_groups = group_consecutive_by(plates, key=lambda plate: (plate.barcode, plate.project))
    for i, plate_group in enumerate(plate_groups, start=1):
        assert_valid_project_name(plate_group[0].project)
        for plate in plate_group:
            checks += [SquidStageCmd('check_protocol_exists', plate.protocol_path).fork_and_wait()]
        plus_secs = dict(enumerate(RT_time_secs, start=1)).get(i, RT_time_secs[-1])
        chunks['fridge -> H13', i] = [
            FridgeEject(plate=plate_group[0].barcode, project=plate_group[0].project, check_barcode=False).fork_and_wait(),
            Checkpoint(f'RT {i}'),
            XArmCmd(f'fridge-to-H11'),
            XArmCmd(f'H11-to-H13') if i > 1 else Noop(),
        ]
        chunks['H13 -> squid', i] = [
            SquidStageCmd('goto_loading').fork(),
            XArmCmd(f'H13-to-H11') if i > 1 else Noop(),
            WaitForResource('squid'),
            XArmCmd(f'H11-to-squid'),
            Seq(
                SquidStageCmd('leave_loading'),
                SquidStageCmd('goto_loading'),   # go back and forth a few times
                SquidStageCmd('leave_loading'),  # go back and forth a few times
                WaitForCheckpoint(f'RT {i}', plus_secs=plus_secs, assume='nothing'),
                WaitForCheckpoint(f'Ok to start {i}', assume='nothing'),
                *[
                    SquidAcquire(plate.protocol_path, project=plate.project, plate=plate.name)
                    for plate in plate_group
                ],
                Checkpoint(f'Done {i}'),
            ).fork(),
        ]
        chunks['squid -> fridge', i] = [
            Checkpoint(f'Ok to start {i}'),
            WaitForCheckpoint(f'Done {i}', assume='nothing'),
            SquidStageCmd('goto_loading').fork_and_wait(),
            XArmCmd(f'squid-to-H11'),
            SquidStageCmd('leave_loading').fork(),
            BarcodeClear(),
            XArmCmd(f'H11-to-fridge'),
            FridgeInsert(
                plate_group[0].project,
                assume_barcode=plate_group[0].barcode,
            ).fork(),
        ]
    for i, substep in ilv.inst(list([i for i, _ in enumerate(plate_groups, start=1)])):
        chunk = Seq(*chunks[substep, i])
        chunk = chunk.transform(lambda cmd: cmd.add(Metadata(plate_id=str(i))) if isinstance(cmd, SquidAcquire) else cmd)
        if substep == 'squid -> fridge' and i < len(plate_groups):
            t = (i // 10)
            name = f'({1 + t})'
            chunk = chunk.add(Metadata(section=name))
        cmds += [chunk]
    cmds += [WaitForResource('fridge')]
    cmd = Seq(*checks, *cmds)
    return Program(cmd)

@pf_protocols.append
def nikon_acquire_from_fridge(args: SmallProtocolArgs) -> Program:
    '''

        Images plates in the fridge.  Params are: RT_time_secs_csv job_name_1:project:barcode:name .. job_name_N:project:barcode:name

    '''
    cmds: list[Command] = []
    RT_time_secs_csv, *plates = args.params
    contents = args.initial_fridge_contents
    if contents is not None:
        for plate in plates:
            _job_full_name, project, barcode, name = plate.split(':')
            if sum(
                1
                for _loc, slot in contents.items()
                if slot['project'] == project
                if slot['plate'] == barcode
            ) != 1:
                raise ValueError(f'Could not find {barcode=} with {project=} in fridge!')
    RT_time_secs: list[float] = [float(rt) for rt in RT_time_secs_csv.split(',')]
    if not RT_time_secs:
        raise ValueError('Specify some RT time. Example: "1800" for 30 minutes')
    if not plates:
        raise ValueError('Select some plates.')
    checks: list[Command] = []
    for i, plate in enumerate(plates, start=1):
        job_full_name, project, barcode, name = plate.split(':')
        job_project, job_name = job_full_name.split('/', 1)
        checks += [NikonStageCmd('check_protocol_exists', job_project=job_project, job_name=job_name).fork_and_wait()]
        assert_valid_project_name(project)
        plus_secs = dict(enumerate(RT_time_secs, start=1)).get(i, RT_time_secs[-1])
        cmds += [
            FridgeEject(plate=barcode, project=project, check_barcode=False).fork_and_wait(),
            Checkpoint(f'RT {i}'),
            XArmCmd(f'fridge-to-H11'),
            NikonStageCmd('goto_loading').fork_and_wait(),
            XArmCmd(f'H11-to-nikon'),

            Seq(
                NikonStageCmd('leave_loading'),
                # could take plate back and init laser:
                # ..., NikonStageCmd('init_laser').fork_and_wait(), ...
                WaitForCheckpoint(f'RT {i}', plus_secs=plus_secs, assume='nothing'),
                NikonAcquire(job_project=job_project, job_name=job_name, project=project, plate=name),
            ).fork_and_wait(),

            NikonStageCmd('goto_loading').fork_and_wait(),
            XArmCmd(f'nikon-to-H11'),
            NikonStageCmd('leave_loading').fork_and_wait(),
            BarcodeClear(),
            XArmCmd(f'H11-to-fridge'),
            FridgeInsert(
                project,
                assume_barcode=barcode,
            ).fork_and_wait(),
        ]
    cmd = Seq(*checks, *cmds)
    return Program(cmd)


# # # @pf_protocols.append
# def nikon_open_stage(_: SmallProtocolArgs) -> Program:
#     return Program(
#         Seq(
#             NikonStageCmd('goto_loading').fork_and_wait(),
#         )
#     )

# # @pf_protocols.append
# def H12_to_nikon(_: SmallProtocolArgs) -> Program:
#     return Program(
#         Seq(
#             NikonStageCmd('goto_loading').fork_and_wait(),
#             XArmCmd('H11-to-nikon'),
#             NikonStageCmd('leave_loading').fork_and_wait(),
#         )
#     )

# # # @pf_protocols.append
# def nikon_to_H12(_: SmallProtocolArgs) -> Program:
#     return Program(
#         Seq(
#             NikonStageCmd('goto_loading').fork_and_wait(),
#             XArmCmd('nikon-to-H11'),
#         )
#     )

# # @pf_protocols.append
"""
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
            XArmCmd(f'fridge-to-H11'),
            XArmCmd(f'H11-to-H11'),
        ]
        chunks['H11 -> nikon', i] = [
            WaitForCheckpoint(f'RT {i}', plus_secs=RT_time_secs, assume='nothing'),
            Duration(f'RT {i}', Min(3)),
            XArmCmd(f'H11-to-H11'),
            NikonStageCmd('goto_loading').fork_and_wait(),
            NikonStageCmd('init_laser').fork_and_wait(),
            XArmCmd(f'H11-to-nikon'),
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
            XArmCmd(f'nikon-to-H11'),
            NikonStageCmd('leave_loading').fork(),
            BarcodeClear(),
            XArmCmd(f'H11-to-fridge'),
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
    return Program(cmd)
"""

def cmds_to_program(cmds: list[Command]) -> Program:
    return Program(Seq(*cmds))

@pf_protocols.append
def fridge_reset_and_activate(args: SmallProtocolArgs) -> Program:
    '''
    Reset and activate the fridge.
    '''
    return cmds_to_program([FridgeCmd('reset_and_activate').fork_and_wait()])

@pf_protocols.append
def pf_init(args: SmallProtocolArgs) -> Program:
    '''
    Initialize the PreciseFlex robotarm. Required after emergency stop.
    '''
    return cmds_to_program([XArmCmd('pf init')])

@pf_protocols.append
def pf_freedrive(args: SmallProtocolArgs) -> Program:
    '''
    Start freedrive on the PreciseFlex robotarm, making it easy to move around by hand.
    '''
    return cmds_to_program([XArmCmd('pf freedrive')])

@pf_protocols.append
def pf_stop_freedrive(args: SmallProtocolArgs) -> Program:
    '''
    Stops freedrive on the PreciseFlex robotarm.
    '''
    return cmds_to_program([XArmCmd('pf stop freedrive')])


A = TypeVar('A')

def on_each(*fs: Callable[[A], None]) -> Callable[[A], None]:
    def inner(a: A):
        for f in fs:
            f(a)
    return inner

@on_each(
    ur_protocols.append,
    pf_protocols.append,
)
def run_robotarm(args: SmallProtocolArgs):
    '''
    Run robotarm programs.

    Example arguments: wash-put-prep, 'B21-to-wash prep'
    '''
    cmds: list[Command] = []
    for x in args.params:
        if moves.guess_robot(x) == 'ur':
            cmds += [RobotarmCmd(x)]
        elif moves.guess_robot(x) == 'pf':
            cmds += [PFCmd(x)]
        elif moves.guess_robot(x) == 'xarm':
            cmds += [XArmCmd(x)]
        else:
            raise ValueError(f'Unknown cmd: {x}')
    return Program(Seq(*cmds))



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
