from __future__ import annotations
from typing import *
import typing
from dataclasses import *

from collections import defaultdict, Counter

import graphlib
import re

from .commands import (
    Program,
    Command,
    Fork,
    Info,
    Metadata,
    Checkpoint,
    Duration,
    Idle,
    Seq,
    WashCmd,
    DispCmd,
    IncuCmd,
    WashFork,
    DispFork,
    IncuFork,
    BiotekValidateThenRun,
    RobotarmCmd,
    WaitForCheckpoint,
    WaitForResource,
    Meta,
    ProgramMetadata,
)
from .moves import movelists, effects, InitialWorld, World, MovePlate
from .symbolic import Symbolic
from .estimates import estimate
from . import commands
from . import moves

import pbutils

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

class Locations:
    H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
    I = [i+1 for i in range(22)]

    A: list[str] = [f'A{i}' for i in H]
    B: list[str] = [f'B{i}' for i in H]
    C: list[str] = [f'C{i}' for i in H]

    Incu:    list[str] = [f'L{i}' for i in I] + [f'R{i}' for i in I]
    RT_few:  list[str] = C[:4] + A[:4]    # up to 8 plates
    RT_many: list[str] = C[:5] + A[:5] + [B[4]]
    Out:     list[str] = A[5:][::-1] + B[5:][::-1] + C[5:][::-1]
    Lid:     list[str] = [b for b in B if '19' in b or '17' in b]

def sleek_program(program: Command) -> Command:
    def get_movelist(cmd_and_metadata: tuple[Command, Metadata]) -> moves.MoveList | None:
        cmd, _ = cmd_and_metadata
        if isinstance(cmd, RobotarmCmd):
            return movelists[cmd.program_name]
        else:
            return None
    def pair_ok(cmd_and_metadata1: tuple[Command, Metadata], cmd_and_metadata2: tuple[Command, Metadata]) -> bool:
        _, m1 = cmd_and_metadata1
        _, m2 = cmd_and_metadata2
        p1 = m1.plate_id
        p2 = m2.plate_id
        return p1 == p2
    return Seq(
        *[
            cmd.add(metadata)
            for cmd, metadata
            in moves.sleek_movements(program.collect(), get_movelist, pair_ok)
        ]
    )

def initial_world(plates: list[Plate], p: ProtocolConfig) -> World:
    return World({p.incu_loc: p.id for p in plates})

def define_plates(batch_sizes: list[int]) -> list[list[Plate]]:
    plates: list[list[Plate]] = []

    index = 0
    for batch_index, batch_size in enumerate(batch_sizes):
        batch: list[Plate] = []
        rt = Locations.RT_many if batch_size > len(Locations.RT_few) else Locations.RT_few
        for index_in_batch in range(batch_size):
            batch += [Plate(
                id=f'{index+1}',
                incu_loc=Locations.Incu[index],
                rt_loc=rt[index_in_batch],
                # lid_loc=Locations.Lid[index_in_batch],
                lid_loc=Locations.Lid[index_in_batch % 2],
                # lid_loc=Locations.Lid[0],
                out_loc=Locations.Out[index],
                batch_index=batch_index,
            )]
            index += 1
        plates += [batch]

    for i, p in enumerate(pbutils.flatten(plates)):
        for j, q in enumerate(pbutils.flatten(plates)):
            if i != j:
                assert p.id != q.id, (p, q)
                assert p.incu_loc != q.incu_loc, (p, q)
                assert p.out_loc not in [q.out_loc, q.rt_loc, q.lid_loc, q.incu_loc], (p, q)
                if p.batch_index == q.batch_index:
                    assert p.rt_loc != q.rt_loc, (p, q)
                    # assert p.lid_loc != q.lid_loc, (p, q)

    return plates

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

Interleavings = dict(
    lin = Interleaving.init('''
        incu -> B21 -> wash -> disp -> B21 -> incu
        incu -> B21 -> wash -> disp -> B21 -> incu
    '''),
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
    '''),
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
    '''),
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
    '''),
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
    '''),
    washlin = Interleaving.init('''
        incu -> B21 -> wash -> B21 -> incu
        incu -> B21 -> wash -> B21 -> incu
    '''),
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
    '''),
    finlin = Interleaving.init('''
        incu -> B21 -> wash -> B21 -> out
        incu -> B21 -> wash -> B21 -> out
    '''),
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
)

class ProtocolArgsInterface(typing.Protocol):
    incu:             str
    interleave:       bool
    two_final_washes: bool
    lockstep:         bool

@dataclass(frozen=True)
class ProtocolArgs:
    incu:             str  = '1200'
    interleave:       bool = False
    two_final_washes: bool = False
    lockstep:         bool = False

if typing.TYPE_CHECKING:
    _: ProtocolArgsInterface = ProtocolArgs()

@dataclass(frozen=True, kw_only=True)
class ProtocolConfig:
    step_names:    list[str]
    wash_prime:    list[str]
    wash:          list[str]
    disp_prime:    list[str]
    disp_prep:     list[str]
    disp:          list[str]
    incu:          list[Symbolic]
    interleavings: list[str]
    interleave:    bool
    lockstep:      bool
    def __post_init__(self):
        d: dict[str, list[Any]] = {}
        for field in fields(self):
            k = field.name
            v = getattr(self, k)
            if isinstance(v, list) and k != 'wash_prime':
                d[k] = v
        for ka, kb in pbutils.iterate_with_next(list(d.items())):
            if kb:
                _, a = ka
                _, b = kb
                assert len(a) == len(b), f'{ka} and {kb} do not have same lengths'
        for ilv in self.interleavings:
            assert ilv in Interleavings

from .protocol_paths import ProtocolPaths, paths_v5

def make_protocol_config(paths: ProtocolPaths, args: ProtocolArgsInterface = ProtocolArgs()) -> ProtocolConfig:
    incu_csv = args.incu
    six_cycles = args.two_final_washes
    N = 6 if six_cycles else 5
    # print(incu_csv, pbutils.read_commasep(incu_csv), file=sys.stderr)

    incu = [
        Symbolic.wrap(
            float(m.group(1)) * 60 + float(m.group(2))
            if (m := re.match(r'(\d+):(\d\d)$', s)) else
            float(s)
            if re.match(r'\d', s)
            else s
        )
        for s in pbutils.read_commasep(incu_csv)
    ]
    incu = incu + [incu[-1]] * N
    incu = incu[:N-1] + [Symbolic.wrap(0)]

    def resize(xs: list[str]) -> list[str]:
        while len(xs) < N:
            xs = [*xs, '']
        return xs[:N]

    interleavings: list[str]
    if six_cycles:
        if args.interleave:
            interleavings = 'june june june june washjune finjune'.split()
        else:
            interleavings = 'lin  lin  lin  lin  washlin  finlin'.split()
    else:
        if args.interleave:
            interleavings = 'june june june june finjune'.split()
        else:
            interleavings = 'lin  lin  lin  lin  finlin'.split()

    names_5 = ['Mito', 'PFA', 'Triton', 'Stains', 'Final']
    names_6 = ['Mito', 'PFA', 'Triton', 'Stains', 'Wash 1', 'Final']
    step_names = names_6 if six_cycles else names_5

    p = ProtocolConfig(
        wash_prime     = paths.wash_prime,
        step_names     = step_names,
        wash           = paths.wash_6 if six_cycles else paths.wash_5,
        disp_prime     = resize(paths.disp_prime),
        disp_prep      = resize(paths.disp_prep),
        disp           = resize(paths.disp_main),
        lockstep       = args.lockstep,
        incu           = incu,
        interleave     = args.interleave,
        interleavings  = interleavings,
    )
    return p

def test_make_protocol_config():
    argss: list[ProtocolArgs] = [
        ProtocolArgs(
            incu = incu,
            two_final_washes = two_final_washes,
            interleave = interleave,
            lockstep = lockstep,
        )
        for incu in ['i1, i2, i3', '21:00,20:00', '1200']
        for two_final_washes in [True, False]
        for interleave in [True, False]
        for lockstep in [False]
    ]
    for args in argss:
        make_protocol_config(paths_v5(), args)

test_make_protocol_config()

def test_comm_program(with_incu: bool=True) -> Command:
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    return Seq(
        DispFork(cmd='TestCommunications', protocol_path=None),
        IncuFork(action='get_status', incu_loc=None) if with_incu else Idle(),
        RobotarmCmd('gripper init and check'),
        WaitForResource('disp'),
        WashFork(cmd='TestCommunications', protocol_path=None),
        WaitForResource('incu') if with_incu else Idle(),
        WaitForResource('wash'),
    ).add(Metadata(step='test comm'))

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

    wash_prime: list[Command] = [
        BiotekValidateThenRun('wash', prime)
        for prime in p.wash_prime
    ]
    prep_cmds: list[Command] = [
        Fork(Seq(*wash_prime)),
    ]

    first_plate = batch[0]
    last_plate = batch[-1]
    batch_index = first_plate.batch_index
    first_batch = batch_index == 0

    # def Section(section: str) -> Command:
    #     section = f'{section} {batch_index}'
    #     return Info(section).add(Metadata(section=section, plate_id=''))

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
        lid_locs = Locations.Lid[:2]
    else:
        lid_locs = Locations.Lid[:1]
    lid_index = 0
    for i, step in enumerate(p.step_names):
        step_index = i
        for plate in batch:
            lid_loc = lid_locs[lid_index % len(lid_locs)]
            lid_index += 1
            plate_with_corrected_lid_pos = replace(plate, lid_loc=lid_loc)
            ix = i + 1
            plate_desc = f'plate {plate.id}'
            first_plate_desc = f'plate {batch[0].id}'

            incu_delay: list[Command]
            wash_delay: list[Command]
            if step_index == 0:
                incu_delay = [
                    WaitForCheckpoint(f'batch {batch_index}') + f'{plate_desc} incu delay {ix}'
                ]
                wash_delay = [
                    WaitForCheckpoint(f'batch {batch_index}') + f'{plate_desc} first wash delay'
                ]
            else:
                incu_delay = [
                    WaitForCheckpoint(f'{first_plate_desc} incubation {ix-1}') + f'{plate_desc} incu delay {ix}'
                ]
                wash_delay = [
                    Early(2),
                    WaitForCheckpoint(f'{plate_desc} incubation {ix-1}') + p.incu[i-1]
                ]

            lid_off = [
                *RobotarmCmds(plate_with_corrected_lid_pos.lid_put, before_pick=[Checkpoint(f'{plate_desc} lid off {ix}')]),
            ]

            lid_on = [
                *RobotarmCmds(plate_with_corrected_lid_pos.lid_get, after_drop=[Duration(f'{plate_desc} lid off {ix}', opt_weight=-1)]),
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
                                Seq(
                                    IncuCmd('put', plate.incu_loc),
                                    Checkpoint(f'{plate_desc} 37C'),
                                ),
                            )
                        ]
                    ),
                ]
            else:
                B21_to_incu = [
                    *RobotarmCmds(plate.rt_put),
                ]


            if p.disp_prime[i] and plate is first_plate:
                disp_prime = p.disp_prime[i]
            else:
                disp_prime = None

            if p.disp[i] or disp_prime:
                pre_disp_is_long = disp_prime or p.disp_prep[i]
                disp_prep = Seq(
                    Fork(
                        Seq(
                            WaitForCheckpoint(f'{plate_desc} incubation {ix-1}' if step_index > 0 else f'batch {batch_index}') + f'{plate_desc} pre disp {ix} delay',
                            BiotekValidateThenRun('disp', disp_prime).add(Metadata(plate_id='')) if disp_prime else Idle(),
                            BiotekValidateThenRun('disp', p.disp_prep[i]).add(Metadata(predispense=True)) if p.disp_prep[i] else Idle(),
                            DispCmd(p.disp[i], cmd='Validate') if p.disp[i] else Idle(),
                            Early(2),
                            Checkpoint(f'{plate_desc} pre disp done {ix}'),
                        ).add(Metadata(slot=3)),
                        assume='nothing',
                    ),
                )
                pre_disp_wait = WaitForCheckpoint(f'{plate_desc} pre disp done {ix}')
            else:
                pre_disp_is_long = False
                disp_prep = Idle()
                pre_disp_wait = Idle()

            wash = [
                RobotarmCmd('wash put prep'),
                WashFork(p.wash[i], cmd='Validate', assume='idle').delay(1) if plate is first_plate and p.wash[i] else Idle(),
                RobotarmCmd('wash put transfer'),
                disp_prep if pre_disp_is_long else Idle(),
                Fork(
                    Seq(
                        *wash_delay,
                        Duration(f'{plate_desc} incubation {ix-1}', exactly=p.incu[i-1]) if i > 0 else Idle(),
                        WashCmd(p.wash[i], cmd='RunValidated') if p.wash[i] else Idle(),
                        Checkpoint(f'{plate_desc} incubation {ix}')
                        if step == 'Wash 1' else
                        Checkpoint(f'{plate_desc} transfer {ix}'),
                    ),
                    assume='nothing',
                ),
                RobotarmCmd('wash put return'),
            ]

            disp = [
                RobotarmCmd('wash_to_disp prep'),
                Early(1),
                WaitForResource('wash', assume='nothing'),
                Idle() if pre_disp_is_long else disp_prep,
                RobotarmCmd('wash_to_disp transfer'),
                pre_disp_wait,
                Duration(f'{plate_desc} transfer {ix}', exactly=estimate(RobotarmCmd('wash_to_disp transfer'))) if p.disp[i] else Idle(),
                Fork(
                    Seq(
                        DispCmd(p.disp[i], cmd='RunValidated') if p.disp[i] else Idle(),
                        Checkpoint(f'{plate_desc} disp {ix} done'),
                        Checkpoint(f'{plate_desc} incubation {ix}'),
                    ),
                ),
                RobotarmCmd('wash_to_disp return'),
            ]

            disp_to_B21 = [
                RobotarmCmd('disp get prep'),
                WaitForCheckpoint(f'{plate_desc} disp {ix} done', assume='nothing'),
                RobotarmCmd('disp get transfer'),
                RobotarmCmd('disp get return'),
            ]

            # section_info_by_incu: Command = Idle()
            # section_info_by_wash: Command = Idle()
            # if plate is first_plate and step_index != 0:
            #     if p.lockstep:
            #         section_info_by_wash = Section(step)
            #     else:
            #         section_info_by_incu = Section(step)

            chunks[plate.id, step, 'incu -> B21' ] = [*incu_delay, *incu_get]
            chunks[plate.id, step,  'B21 -> wash'] = [*wash]
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
        for now, next in pbutils.iterate_with_next(filtered):
            if next:
                adjacent[now] |= {next}

    def desc(p: Plate | None, step: str, substep: str) -> Desc | None:
        if p is None:
            return None
        else:
            return p.id, step, substep

    if p.lockstep:
        for i, (step, next_step) in enumerate(pbutils.iterate_with_next(p.step_names)):
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
        for step, next_step in pbutils.iterate_with_next(p.step_names):
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
        pbutils.pr([
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
        command.add(Metadata(
            step=step,
            substep=substep,
            plate_id=plate_id,
            slot=slots[substep],
            stage=f'{step}, plate {plate_id}',
        )).add_to_physical_commands(Metadata(
            section=f'{step} {batch_index}',
        ))
        for desc in linear
        for plate_id, step, substep in [desc]
        for command in chunks[desc]
    ]

    for plate_id, step, _substep in linear:
        stage1 = f'{step}, plate {plate_id}'
        break
    else:
        stage1 = f'prep, batch {batch_index+1}'

    return Seq(
        # Section(p.step_names[0]),
        Seq(*prep_cmds).add(Metadata(step='prep', stage=stage1)),
        *plate_cmds,
        Seq(*post_cmds)
    ).add(Metadata(batch_index=batch_index + 1))

def cell_paint_program(batch_sizes: list[int], protocol_config: ProtocolConfig, sleek: bool = True) -> Program:
    cmds: list[Command] = []
    plates = define_plates(batch_sizes)
    for batch in plates:
        batch_cmds = paint_batch(
            batch,
            protocol_config=protocol_config,
        )
        cmds += [batch_cmds]

    world0 = initial_world(pbutils.flatten(plates), protocol_config)
    program = Seq(*cmds)
    if sleek:
        program = sleek_program(program)
    program = Seq(
        Checkpoint('run'),
        test_comm_program(),
        program,
        Duration('run', opt_weight=-0.1)
    )
    return Program(
        command=program,
        world0=world0,
        metadata=ProgramMetadata(
            protocol='cell-paint',
            num_plates=sum(batch_sizes),
            batch_sizes=','.join(map(str, batch_sizes)),
        )
    )
