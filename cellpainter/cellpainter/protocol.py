from __future__ import annotations
from typing import *
from dataclasses import *

import graphlib
import re

import itertools as it

from .commands import (
    Program,
    Command,
    Fork,
    Metadata,
    Checkpoint,
    Duration,
    Idle,
    Seq,
    WashCmd,
    BlueCmd,
    DispCmd,
    IncuCmd,
    ValidateThenRun,
    RobotarmCmd,
    WaitForCheckpoint,
    WaitForResource,
    ProgramMetadata,
    Max,
    Min,
    WaitAssumption,
    OptimizeSection,
)
from .commandlib import Interleaving
from .moves import World
from .symbolic import Symbolic
from . import commands

import pbutils

class OptPrio:
    wash_to_disp  = Min(priority=8, weight=1)
    incubation    = Min(priority=7, weight=1)
    total_time    = Min(priority=6, weight=1)
    without_lid   = Min(priority=5, weight=1)
    inside_incu   = Max(priority=4, weight=1)
    squeeze_steps = Min(priority=3, weight=1)

    # incu_slack    = Min(priority=6, weight=1)

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
        return f'lid-{self.lid_loc} put'

    @property
    def lid_get(self):
        return f'lid-{self.lid_loc} get'

    @property
    def lid_get_base_B15(self):
        return f'lid-{self.lid_loc} get [base B15]'

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

class Locations:
    HA = [21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    HB = [21, 19, 17, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    I = [i+1 for i in range(22)]

    A: list[str] = [f'A{i}' for i in HA]
    B: list[str] = [f'B{i}' for i in HB]

    Lid:  list[str] = ['B19', 'B17']
    RT:   list[str] = A[:21] + B[4:]

    L: list[str] = [f'L{i}' for i in I]
    R: list[str] = [f'R{i}' for i in I]
    Incu: list[str] = [*L, *R]

    IncuPerBatch: dict[str, list[str]] = {
        '1 of 1': L,
        '1 of 2': L,
        '2 of 2': R,
    }

    Out: dict[str, list[str]] = {
        '1 of 1': A[:21] + B[4:],
        '1 of 2': B[4:] + A[18:], # 1st batch goes to B then starts to fill remaining locations in A (with one gap)
        '2 of 2': A[:17],         # 2nd batch goes to A (up to 17 plates)
    }

def initial_world(plates: list[Plate], p: ProtocolConfig) -> World:
    if p.steps and p.steps[0].name in ['Mito', 'PFA']:
        return World({p.incu_loc: p.id for p in plates})
    else:
        return World({p.rt_loc: p.id for p in plates})

def define_plates(batch_sizes: list[int]) -> list[list[Plate]]:

    plates: list[list[Plate]] = []

    index = 0
    for batch_index, batch_size in enumerate(batch_sizes):
        assert batch_size > 0

        batch_key = f'{batch_index + 1} of {len(batch_sizes)}'

        Out = Locations.Out.get(batch_key)
        if not Out:
            raise ValueError(f'The batch {batch_key} is not defined for output locations. Try one of {", ".join(Locations.Out.keys())}.')

        Incu = Locations.IncuPerBatch.get(batch_key)
        if not Incu:
            raise ValueError(f'The batch {batch_key} is not defined for incubator locations. Try one of {", ".join(Locations.IncuPerBatch.keys())}.')

        batch: list[Plate] = []
        rt = Locations.RT
        for index_in_batch in range(batch_size):
            batch += [Plate(
                id=f'{index+1}',
                incu_loc=Incu[index_in_batch],
                rt_loc=rt[index_in_batch],
                # lid_loc=Locations.Lid[index_in_batch],
                lid_loc=Locations.Lid[index_in_batch % 2],
                # lid_loc=Locations.Lid[0],
                out_loc=Out[index_in_batch],
                batch_index=batch_index,
            )]
            index += 1
        plates += [batch]

    for i, p in enumerate(pbutils.flatten(plates)):
        for j, q in enumerate(pbutils.flatten(plates)):
            if i != j:
                assert p.id != q.id, (p, q)
                assert p.incu_loc != q.incu_loc, (p, q)
                # assert p.out_loc not in [q.out_loc, q.rt_loc, q.lid_loc, q.incu_loc], (p, q)
                if p.batch_index == q.batch_index:
                    assert p.rt_loc != q.rt_loc, (p, q)
                    # assert p.lid_loc != q.lid_loc, (p, q)

    return plates

InterleavingName = Literal[
    'wash -> disp',
    'blue -> disp',
    'wash -> out',
    'blue -> out',
    'wash -> disp -> out',
    'blue -> disp -> out',
    'disp -> out',
    'disp',
    'wash',
    'blue',
]

def make_interleaving(name: InterleavingName, linear: bool) -> Interleaving:
    match name:
        case 'wash -> disp -> out' | 'blue -> disp -> out':
            lin = '''
                incu -> B21 -> wash -> disp -> B21 -> out
                incu -> B21 -> wash -> disp -> B21 -> out
            '''
            ilv = '''
                incu -> B21  -> wash
                incu -> B21
                                wash -> disp
                        B21  -> wash
                                        disp -> B21 -> out
                incu -> B21
                                wash -> disp
                        B21  -> wash
                                        disp -> B21 -> out
                                wash -> disp
                                        disp -> B21 -> out
            '''
        case 'wash -> disp' | 'blue -> disp':
            lin = '''
                incu -> B21 -> wash -> disp -> B21 -> incu
                incu -> B21 -> wash -> disp -> B21 -> incu
            '''
            ilv = '''
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
            '''
        case 'wash -> out' | 'blue -> out':
            lin = '''
                incu -> B21 -> wash -> B15 -> B21 -> out
                incu -> B21 -> wash -> B15 -> B21 -> out
            '''
            ilv = '''
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
            '''
        case 'wash' | 'blue':
            lin = '''
                incu -> B21 -> wash -> B21 -> incu
                incu -> B21 -> wash -> B21 -> incu
            '''
            ilv = '''
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
            '''
        case 'disp':
            lin = '''
                incu -> B21 -> disp -> B21 -> incu
                incu -> B21 -> disp -> B21 -> incu
            '''
            ilv = '''
                incu -> B21 -> disp
                               disp -> B15
                incu -> B21 -> disp
                                       B15 -> B21 -> incu
                               disp -> B15
                incu -> B21 -> disp
                                       B15 -> B21 -> incu
                               disp -> B15 -> B21 -> incu
            '''
        case 'disp -> out':
            lin = '''
                incu -> B21 -> disp -> B21 -> out
                incu -> B21 -> disp -> B21 -> out
            '''
            ilv = '''
                incu -> B21 -> disp
                               disp -> B15
                incu -> B21 -> disp
                                       B15 -> B21 -> out
                               disp -> B15
                incu -> B21 -> disp
                                       B15 -> B21 -> out
                               disp -> B15 -> B21 -> out
            '''
    if 'blue' in name:
        lin = lin.replace('wash', 'blue')
        ilv = ilv.replace('wash', 'blue')
    _mix = '''
        incu -> B21 -> wash
                       wash -> disp
        incu -> B21 -> wash
                               disp -> B21 -> incu
                       wash -> disp
        incu -> B21 -> wash
                               disp -> B21 -> incu
                       wash -> disp
                               disp -> B21 -> incu
    '''
    _quad = '''
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
    '''
    _three = '''
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
    '''
    return Interleaving.init(lin if linear else ilv, name=name)

from pbutils.args import arg

@dataclass(frozen=True)
class CellPaintingArgs:
    batch_sizes:         str  = arg('0', help='Cell paint with batch sizes separated by comma (such as 6,6 for 2x6). Plates start stored in incubator L1, L2, ..')
    incu:                str  = arg('1200,1200,1200,1200,1200', help='Incubation times in seconds, separated by comma')
    interleave:          bool = arg(False, help='Interleave plates, required for 7 plate batches')
    two_final_washes:    bool = arg(False, help='Use two shorter final washes in the end, required for big batch sizes, required for 8 plate batches')

@dataclass(frozen=True, kw_only=True)
class ProtocolConfig:
    steps: list[Step]
    wash_prime: list[str]
    blue_prime: list[str]
    use_blue: bool

    '''
    def any_disp(self):
        return any([
            *[step.disp for step in self.steps],
            *[step.disp_prime for step in self.steps],
            *[step.disp_prep for step in self.steps],
        ])

    def any_wash(self):
        return self.wash_prime or any([step.wash for step in self.steps])

    def any_blue(self):
        return self.use_blue or self.blue_prime or any([step.blue for step in self.steps])
    '''

from .protocol_paths import ProtocolPaths, paths_v5

@dataclass(frozen=True)
class Step:
    name: str
    incu: float | int | Symbolic
    blue: str | None
    wash: str | None
    disp: str | None
    disp_prime: str | None
    disp_prep: str | None
    interleaving: Interleaving

def make_protocol_config(paths: ProtocolPaths, args: CellPaintingArgs = CellPaintingArgs()) -> ProtocolConfig:
    incu_csv = args.incu
    six_cycles = args.two_final_washes

    incu_lengths = [
        Symbolic.wrap(
            float(m.group(1)) * 60 + float(m.group(2))
            if (m := re.match(r'(\d+):(\d\d)$', s)) else
            float(s)
            if re.match(r'\d', s)
            else s
        )
        for s in pbutils.read_commasep(incu_csv)
    ]

    def drop_trail(xs: list[str]) -> list[str]:
        for i, _ in enumerate(xs):
            if not any(xs[i:]):
                return xs[:i]
        return xs

    if paths.use_blue():
        names = ['Mito', 'PFA', 'Stains', 'Final']
    elif six_cycles:
        names = ['Mito', 'PFA', 'Triton', 'Stains', 'Wash 1', 'Final']
    else:
        names = ['Mito', 'PFA', 'Triton', 'Stains', 'Final']

    steps_proto = list(
        it.zip_longest(
            drop_trail(paths.wash_6 if six_cycles else paths.wash_5),
            drop_trail(paths.blue),
            drop_trail(paths.disp_main),
            fillvalue='',
        )
    )

    steps: list[Step] = []

    for i, (wash, blue, disp) in enumerate(steps_proto):
        incu = dict(enumerate(incu_lengths)).get(i, incu_lengths[-1])
        name = dict(enumerate(names)).get(i, f'Step {i+1}')
        last_step = i == len(steps_proto) - 1
        ilv_name: InterleavingName
        if wash and blue:
            raise ValueError(f'Cannot use both biotek washer and bluewasher in the same step [{i=} {wash=} {blue=}]')
        elif last_step:
            if wash and disp:
                ilv_name = 'wash -> disp -> out'
            elif blue and disp:
                ilv_name = 'blue -> disp -> out'
            elif wash:
                ilv_name = 'wash -> out'
            elif blue:
                ilv_name = 'blue -> out'
            elif disp:
                ilv_name = 'disp -> out'
            else:
                raise ValueError(f'Invalid last step [{i=} {wash=} {blue=} {disp=}]')
        elif wash and disp:
            ilv_name = 'wash -> disp'
        elif blue and disp:
            ilv_name = 'blue -> disp'
        elif wash:
            ilv_name = 'wash'
        elif blue:
            ilv_name = 'blue'
        elif disp:
            ilv_name = 'disp'
        else:
            continue
            # raise ValueError(f'Step must have some purpose [{i=} {wash=} {blue=} {disp=}]')
        ilv = make_interleaving(ilv_name, linear=not args.interleave)
        steps += [
            Step(
                name=name,
                incu=incu,
                wash=wash,
                blue=blue,
                disp=disp,
                disp_prime=dict(enumerate(paths.disp_prime)).get(i),
                disp_prep=dict(enumerate(paths.disp_prep)).get(i),
                interleaving=ilv,
            )
        ]

    # pbutils.pr(steps)

    return ProtocolConfig(
        wash_prime = paths.wash_prime,
        blue_prime = paths.blue_prime,
        steps      = steps,
        use_blue = paths.use_blue(),
    )

def test_make_protocol_config():
    argss: list[CellPaintingArgs] = [
        CellPaintingArgs(
            incu = incu,
            two_final_washes = two_final_washes,
            interleave = interleave,
        )
        for incu in ['i1, i2, i3', '21:00,20:00', '1200']
        for two_final_washes in [True, False]
        for interleave in [True, False]
    ]
    for args in argss:
        make_protocol_config(paths_v5(), args)

test_make_protocol_config()

def program_test_comm(with_incu: bool=True, with_blue: bool=True) -> Command:
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    return Seq(
        BlueCmd(action='TestCommunications', protocol_path=None).fork() if with_blue else Idle(),
        DispCmd(cmd='TestCommunications', protocol_path=None).fork(),
        IncuCmd(action='get_status', incu_loc=None).fork() if with_incu else Idle(),
        RobotarmCmd('ur gripper init and check'),
        WaitForResource('disp'),
        WashCmd(cmd='TestCommunications', protocol_path=None).fork(),
        WaitForResource('incu') if with_incu else Idle(),
        WaitForResource('wash'),
        WaitForResource('blue') if with_blue else Idle(),
    ).add(Metadata(step_desc='test comm'))

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

def CheckpointPair(name: str, assume: WaitAssumption = 'nothing'):
    return Checkpoint(name), WaitForCheckpoint(name, assume=assume)

def paint_batch(batch: list[Plate], protocol_config: ProtocolConfig) -> Command:
    p = protocol_config

    prep_cmds: list[Command] = []

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

    prep_cmds += [
        program_test_comm(with_blue=p.use_blue),
        BlueCmd('get_working_plate').fork() if p.use_blue else Idle(),
    ]

    post_cmds = [
        Duration(f'batch {batch_index}', OptPrio.total_time),
    ]

    chunks: dict[Desc, Iterable[Command]] = {}
    lid_locs = Locations.Lid[:2]
    lid_index = 0

    wash_prime = [
        ValidateThenRun('wash', prime)
        for prime in p.wash_prime
        if prime
    ]
    blue_prime = [
        ValidateThenRun('blue', prime)
        for prime in p.blue_prime
        if prime
    ]


    for i, (prev_step, step, next_step) in enumerate(pbutils.iterate_with_context(p.steps)):
        for plate in batch:

            lid_loc = lid_locs[lid_index % len(lid_locs)]
            lid_index += 1
            plate_with_corrected_lid_pos = replace(plate, lid_loc=lid_loc)
            ix = i + 1
            plate_desc = f'plate {plate.id}'
            first_plate_desc = f'plate {batch[0].id}'

            incu_delay: list[Command]
            wash_delay: list[Command]
            if not prev_step:
                # idle_ref = WaitForCheckpoint(f'batch {batch_index}')
                incu_delay = [
                    WaitForCheckpoint(f'batch {batch_index}') + f'{plate_desc} incu delay {ix}',
                ]
                wash_delay = [
                    WaitForCheckpoint(f'batch {batch_index}') + f'{plate_desc} first wash delay'
                ]
            else:
                # idle_ref = WaitForCheckpoint(f'{first_plate_desc} incubation {ix-1}')
                incu_delay = [
                    WaitForCheckpoint(f'{first_plate_desc} incubation {ix-1}') + f'{plate_desc} incu delay {ix}'
                ]
                _slack = (
                    Symbolic.var(f'{plate_desc} incubation {ix-1} slack')
                    + prev_step.incu
                )
                wash_delay = [
                    Early(2),
                    WaitForCheckpoint(f'{plate_desc} incubation {ix-1}', assume='will wait') + prev_step.incu,
                    Duration(f'{plate_desc} incubation {ix-1}', OptPrio.incubation),
                    # WaitForCheckpoint(f'{plate_desc} incubation {ix-1}', assume='will wait') + slack,
                    # Duration(f'{plate_desc} incubation {ix-1}', OptPrio.incu_slack),
                ]

            lid_off = [
                *RobotarmCmds(
                    plate_with_corrected_lid_pos.lid_put,
                    before_pick=[Checkpoint(f'{plate_desc} lid off {ix}')]
                ),
            ]

            lid_on = [
                *RobotarmCmds(
                    plate_with_corrected_lid_pos.lid_get,
                    after_drop=[Duration(f'{plate_desc} lid off {ix}', OptPrio.without_lid)]
                ),
            ]

            lid_on_base_B15 = [
                *RobotarmCmds(
                    plate_with_corrected_lid_pos.lid_get_base_B15,
                    after_drop=[Duration(f'{plate_desc} lid off {ix}', OptPrio.without_lid)]
                ),
            ]

            if step.name == 'Mito' or step.name == 'PFA':
                incu_get = [
                    # Idle() + 'sep {plate_desc} {step.name}',
                    RobotarmCmd('incu-to-B21 prep'),
                    Fork(
                        Seq(
                            IncuCmd('get', plate.incu_loc),
                            Duration(f'{plate_desc} 37C', OptPrio.inside_incu)
                            if step.name == 'PFA' and prev_step else
                            Idle(),
                        ),
                        align='end',
                    ),
                    Early(1),
                    RobotarmCmd('incu-to-B21 transfer'),
                    Fork(IncuCmd('get_status', incu_loc=None)), # use incu thread to signal that plate has left incu
                    WaitForResource('incu'),
                    RobotarmCmd('incu-to-B21 return'),
                ]
            else:
                incu_get = [
                    *RobotarmCmds(plate.rt_get),
                ]

            if step.name == 'Mito':
                B21_to_incu = [
                    RobotarmCmd('B21-to-incu prep'),
                    WaitForResource('incu', assume='nothing'),
                    RobotarmCmd('B21-to-incu transfer'),
                    Fork(
                        Seq(
                            IncuCmd('put', plate.incu_loc),
                            Checkpoint(f'{plate_desc} 37C'),
                        ),
                    ),
                    RobotarmCmd('B21-to-incu return'),
                ]
            else:
                B21_to_incu = [
                    *RobotarmCmds(plate.rt_put),
                ]

            if step.name == 'Mito':
                B15_to_incu = [
                    RobotarmCmd('B15-to-incu prep'),
                    WaitForResource('incu', assume='nothing'),
                    RobotarmCmd('B15-to-incu transfer'),
                    Fork(
                        Seq(
                            IncuCmd('put', plate.incu_loc),
                            Checkpoint(f'{plate_desc} 37C'),
                        ),
                    ),
                    RobotarmCmd('B15-to-incu return'),
                ]
            else:
                B15_to_incu = [
                    *RobotarmCmds('B15 get'),
                    *RobotarmCmds(plate.rt_put),
                ]

            B21_to_wash = [
                RobotarmCmd('B21-to-wash prep'),
                Fork(
                    Seq(
                        *[
                            cmd.add(Metadata(plate_id=''))
                            for cmd in wash_prime
                            if plate is first_plate
                            if not prev_step or not prev_step.wash
                        ],
                        WashCmd('Validate', step.wash),
                        # Early(5),
                    ),
                    align='end',
                ),
                RobotarmCmd('B21-to-wash transfer'),
                Fork(
                    Seq(
                        *wash_delay,
                        WashCmd('RunValidated', step.wash),
                        Checkpoint(f'{plate_desc} incubation {ix}')
                        if not step.disp else
                        Checkpoint(f'{plate_desc} transfer {ix}'),
                    )
                ),
                RobotarmCmd('B21-to-wash return'),
            ]
            B21_to_blue = [
                RobotarmCmd('B21-to-blue prep'),
                Fork(
                    Seq(
                        *[
                            cmd.add(Metadata(plate_id=''))
                            for cmd in blue_prime
                            if plate is first_plate
                            # if not prev_step or not prev_step.blue
                            if step.blue # let's just always prime blue for simplicity
                        ],
                    ),
                    align='end',
                ),
                WaitForResource('blue'),
                RobotarmCmd('B21-to-blue transfer'),
                Fork(
                    Seq(
                        *wash_delay,
                        BlueCmd('Run', step.blue),
                        Checkpoint(f'{plate_desc} incubation {ix}')
                        if not step.disp else
                        Checkpoint(f'{plate_desc} transfer {ix}'),
                    )
                ),
                RobotarmCmd('B21-to-blue return'),
            ]

            if step.disp_prime and plate is first_plate:
                disp_prime = [
                    ValidateThenRun('disp', step.disp_prime).add(Metadata(plate_id='')),
                ]
            else:
                disp_prime = []

            if step.disp_prep:
                disp_prep = [
                    ValidateThenRun('disp', step.disp_prep).add(Metadata(plate_id=None)),
                ]
            else:
                disp_prep = []

            run_disp = Seq(
                Fork(
                    Seq(
                        *disp_prime,
                        *disp_prep,
                        DispCmd('Validate', step.disp),
                        Early(2),
                    ),
                    align='end',
                ),
                Fork(
                    Seq(
                        *(wash_delay if not step.wash and not step.blue else []),
                        *(
                            [Duration(f'{plate_desc} transfer {ix}', OptPrio.wash_to_disp)]
                            if step.wash or step.blue else
                            []
                        ),
                        DispCmd('RunValidated', step.disp),
                        Checkpoint(f'{plate_desc} incubation {ix}'),
                    ),
                ),
            )

            wash_to_disp = [
                RobotarmCmd('wash-to-disp prep'),
                WaitForResource('wash', assume='will wait'),
                Early(1),
                RobotarmCmd('wash-to-disp transfer'),
                WashCmd('TestCommunications', protocol_path=None).fork(), # use it so it doesn't start while moving from it
                run_disp,
                RobotarmCmd('wash-to-disp return'),
            ]

            blue_to_disp = [
                RobotarmCmd('blue-to-disp prep'),
                WaitForResource('blue', assume='will wait'),
                Early(1),
                RobotarmCmd('blue-to-disp transfer'),
                BlueCmd('TestCommunications').fork(), # use it so it doesn't start while moving from it
                run_disp,
                RobotarmCmd('blue-to-disp return'),
            ]

            B21_to_disp = [
                RobotarmCmd('B21-to-disp prep'),
                Early(1),
                RobotarmCmd('B21-to-disp transfer'),
                run_disp,
                RobotarmCmd('B21-to-disp return'),
            ]

            def disp_to_B(z: int):
                return [
                    RobotarmCmd(f'disp-to-B{z} prep'),
                    Early(1),
                    WaitForResource('disp') if step.disp else Idle(),
                    RobotarmCmd(f'disp-to-B{z} transfer'),
                    DispCmd('TestCommunications', protocol_path=None).fork(), # use it so it doesn't start while moving from it
                    RobotarmCmd(f'disp-to-B{z} return'),
                ]

            def wash_to_B(z: int):
                return [
                    RobotarmCmd(f'wash-to-B{z} prep'),
                    Early(1),
                    WaitForResource('wash') if step.wash else Idle(),
                    RobotarmCmd(f'wash-to-B{z} transfer'),
                    WashCmd('TestCommunications', protocol_path=None).fork(), # use it so it doesn't start while moving from it
                    RobotarmCmd(f'wash-to-B{z} return'),
                ]

            def blue_to_B(z: int):
                return [
                    RobotarmCmd(f'blue-to-B{z} prep'),
                    Early(1),
                    WaitForResource('blue') if step.blue else Idle(),
                    RobotarmCmd(f'blue-to-B{z} transfer'),
                    BlueCmd('TestCommunications').fork(), # use it so it doesn't start while moving from it
                    RobotarmCmd(f'blue-to-B{z} return'),
                ]


            chunks[plate.id, step.name, 'incu -> B21' ] = [
                *incu_delay,
                *incu_get,
                *(
                    lid_off
                    if step.wash or step.blue else
                    [Checkpoint(f'{plate_desc} transfer {ix}')]
                ),
            ]

            # disp|blue|wash|B15 -> B21 should end up with a lid
            # disp|blue|wash     -> B15 should not have lid

            chunks[plate.id, step.name,  'B21 -> wash'] = [*B21_to_wash]
            chunks[plate.id, step.name,  'B21 -> blue'] = [*B21_to_blue]
            chunks[plate.id, step.name, 'wash -> disp'] = [*wash_to_disp]
            chunks[plate.id, step.name, 'blue -> disp'] = [*blue_to_disp]
            chunks[plate.id, step.name, 'disp -> B21' ] = [*disp_to_B(21), *lid_on]
            chunks[plate.id, step.name,  'B21 -> disp'] = [*lid_off, *B21_to_disp]

            chunks[plate.id, step.name, 'wash -> B21' ] = [*wash_to_B(21), *lid_on]
            chunks[plate.id, step.name, 'wash -> B15' ] = [*wash_to_B(15)]
            chunks[plate.id, step.name, 'blue -> B21' ] = [*blue_to_B(21), *lid_on]
            chunks[plate.id, step.name, 'blue -> B15' ] = [*blue_to_B(15)]

            if step.disp and not step.blue and not step.wash:
                # put on the lid now
                chunks[plate.id, step.name, 'disp -> B15' ] = [*disp_to_B(15), *lid_on_base_B15]
                chunks[plate.id, step.name,  'B15 -> B21' ] = []
                chunks[plate.id, step.name,  'B21 -> incu'] = [*RobotarmCmds('B15 get'), *B21_to_incu]
            else:
                chunks[plate.id, step.name, 'disp -> B15' ] = [*disp_to_B(15)]
                chunks[plate.id, step.name,  'B15 -> B21' ] = [*RobotarmCmds('B15 get'), *lid_on]
                chunks[plate.id, step.name,  'B21 -> incu'] = [*B21_to_incu]

            chunks[plate.id, step.name,  'B21 -> out' ] = [*RobotarmCmds(plate.out_put)]

    adjacent: dict[Desc, set[Desc]] = DefaultDict(set)

    def seq(descs: list[Desc | None]):
        filtered: list[Desc] = [ desc for desc in descs if desc ]
        for now, next in pbutils.iterate_with_next(filtered):
            if next:
                adjacent[now] |= {next}

    def desc(p: Plate | None, step: str, substep: str) -> Desc | None:
        if p is None:
            return None
        else:
            return p.id, step, substep

    for step, next_step in pbutils.iterate_with_next(p.steps):
        if next_step:
            ilv = step.interleaving
            next_ilv = next_step.interleaving
            seq([
                desc(last_plate, step.name, 'B21 -> incu'),
                desc(first_plate, next_step.name, 'incu -> B21'),
            ])

    for i, step in enumerate(p.steps):
        ilv = step.interleaving
        for offset, _ in enumerate(batch):
            seq([
                desc(batch[i+offset], step.name, substep)
                for i, substep in ilv.rows
                if i + offset < len(batch)
            ])

    deps: dict[Desc, set[Desc]] = DefaultDict(set)
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
        pbutils.pr([
            ', '.join((desc[1], desc[0], desc[2]))
            for desc in linear
        ])

    slots = DefaultDict[str, int](int) | {
        'incu -> B21':  1,
        'B21 -> wash':  2,
        'B21 -> disp':  3,
        'wash -> disp': 3,
        'disp -> B21':  4,
        'B21 -> incu':  4,
        'wash -> B21':  3,
        'B21 -> out':   4,
        'disp -> B15':  4,
        'wash -> B15':  3,
        'B15 -> B21':   4,
        'B15 -> incu':  4,
        'B15 -> out':   4,
    }
    for k, v in list(slots.items()):
        if 'wash' in k:
            slots[k.replace('wash', 'blue')] = v

    plate_cmds: list[Command] = []
    for prev_descrs, descr, next_descrs in pbutils.iterate_with_full_context(linear):
        plate_id, step_name, substep = descr
        commands: list[Command] = []
        for command in chunks[descr]:
            command = command.add(Metadata(
                plate_id=plate_id,
                slot=slots[substep],
                stage=f'{step_name}, plate {plate_id}',
                step_desc=f'{step_name} {substep}',
            ))
            command = command.add_to_physical_commands(Metadata(
                section=f'{step_name} {batch_index}',
            ))
            commands += [command]
        command = Seq(*commands)
        if 1:
            first_of_step = not any(prev_step == step_name for _, prev_step, _ in prev_descrs)
            last_of_step = not any(next_step == step_name for _, next_step, _ in next_descrs)
            checkpoint_name = f'squeeze {step_name} {batch_index}'
            if first_of_step:
                command, ok = command.transform_first_physical_command(lambda c: Seq(Checkpoint(checkpoint_name), c))
                assert ok
            if last_of_step:
                command = Seq(command, Duration(checkpoint_name, OptPrio.squeeze_steps))
        plate_cmds += [command]

    for plate_id, step_name, _substep in linear:
        stage1 = f'{step_name}, plate {plate_id}'
        break
    else:
        stage1 = f'prep, batch {batch_index+1}'

    return Seq(
        Seq(*prep_cmds).add(Metadata(step_desc='prep', stage=stage1)),
        Idle() + f'slack {batch_index+1}',
        *plate_cmds,
        Seq(*post_cmds)
    ).add(Metadata(batch_index=batch_index + 1))

def cell_paint_program(batch_sizes: list[int], protocol_config: ProtocolConfig) -> Program:
    cmds: list[Command] = []
    plates = define_plates(batch_sizes)
    program = Seq()
    for i, batch in enumerate(plates):
        batch_cmds = paint_batch(
            batch,
            protocol_config=protocol_config,
        )
        program = OptimizeSection(program >> batch_cmds, name=f'batch {i+1}/{len(plates)}' if len(plates) > 1 else None)
    world0 = initial_world(pbutils.flatten(plates), protocol_config)
    return Program(
        command=program,
        world0=world0,
        metadata=ProgramMetadata(
            protocol='cell-paint',
            num_plates=sum(batch_sizes),
            batch_sizes=','.join(map(str, batch_sizes)),
        )
    )
