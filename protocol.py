from __future__ import annotations
from typing import *
from dataclasses import *

from datetime import datetime, timedelta
from collections import defaultdict

import graphlib
import json
import os
import platform
import protocol
import re
import textwrap
import sys
import traceback

from moves import movelists
from robots import RuntimeConfig, Command, Runtime
from robots import DispFinished, WashStarted, Now, Ready
from utils import pr, show, Mutable
import robots
import utils
import moves
import threading

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
    r_loc: str
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
    def r_put(self):
        return f'{self.r_loc} put'

    @property
    def r_get(self):
        return f'{self.r_loc} get'

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
r_locs:    list[str] = [f'r{i}' for i in H][1:]
out_locs:  list[str] = [f'out{i}' for i in reversed(H)] + list(reversed(r_locs))
lid_locs:  list[str] = [h for h in h_locs if h != h21]

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
    wash:  Steps[str]
    prime: Steps[str]
    disp:  Steps[str]
    incu:  Steps[int]
    guesstimate_time_wash_3X_minus_incu_pop: int
    guesstimate_time_wash_3X_minus_RT_pop:   int
    guesstimate_time_wash_4X_minus_wash_3X:  int
    prep_wash: str | None = None
    prep_disp: str | None = None
    delay_before_first_wash: int = 0
    separation_between_first_washes: int = 0
    wait_before_incu_get_1st: Steps[int] = Steps(0,60,60,60,60)
    wait_before_incu_get_2nd: Steps[int] = Steps(60,60,60,60,60)
    wait_before_incu_get_rest: Steps[int] = Steps(60,60,60,60,60)

v3 = ProtocolConfig(
    prep_wash='automation_v3/0_W_D_PRIME.LHC',
    prep_disp=None, # 'automation_v3/1_D_P1_MIX.LHC',
    wash = Steps(
        'automation_v3/1_W-1X_beforeMito_leaves20ul.LHC',
        'automation_v3/3_W-3X_beforeFixation_leaves20ul.LHC',
        'automation_v3/5_W-3X_beforeTriton.LHC',
        'automation_v3/7_W-3X_beforeStains.LHC',
        'automation_v3/9_W-5X_NoFinalAspirate.LHC',
    ),
    prime = Steps(
        'automation_v3/1_D_P1_MIX_PRIME.LHC',
        'automation_v3/3_D_SA_PRIME.LHC',
        'automation_v3/5_D_SB_PRIME.LHC',
        'automation_v3/7_D_P2_MIX_PRIME.LHC',
        '',
    ),
    disp = Steps(
        'automation_v3/2_D_P1_40ul_purge_mito.LHC',
        'automation_v3/4_D_SA_384_80ul_PFA.LHC',
        'automation_v3/6_D_SB_384_80ul_TRITON.LHC',
        'automation_v3/8_D_P2_20ul_purge_stains.LHC',
        '',
    ),
    incu = Steps(20, 20, 20, 20, 0),
    guesstimate_time_wash_3X_minus_incu_pop = 110, # TODO
    guesstimate_time_wash_3X_minus_RT_pop   = 60,  # TODO
    guesstimate_time_wash_4X_minus_wash_3X  = 200, # TODO
    delay_before_first_wash         = 0,
    separation_between_first_washes = 0,
    wait_before_incu_get_1st  = Steps(0,60,40,40,40),
    wait_before_incu_get_2nd  = Steps(0,174,0,0,0),
    wait_before_incu_get_rest = Steps(0,174,0,0,0),
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
    protocol_config = replace(protocol_config, incu = Steps(0,0,0,0,0))
    events = eventlist([1], protocol_config=protocol_config, short_test_paint=False, sleek=True)
    events = [
        e
        for e in events
        for c in [e.command]
        if not isinstance(c, robots.incu_cmd)
        if not isinstance(c, robots.robotarm_cmd) or any(
            needle in c.program_name
            for needle in ['wash', 'disp']
        )
    ]
    ATTENTION(time_bioteks.__doc__ or '')
    execute_events_with_logging(config, events, metadata={'options': 'time_bioteks'})

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
    N = 4
    incu: list[Command] = []
    for loc in incu_locs[:N]:
        incu += [
            robots.incu_cmd('put', loc),
            robots.wait_for(robots.Ready('incu')),
            robots.incu_cmd('get', loc),
            robots.wait_for(robots.Ready('incu')),
        ]
    arm: list[Command] = []
    plate = Plate('', '', '', '', '', 1)
    for lid_loc in lid_locs[:N]:
        plate = replace(plate, lid_loc=lid_loc)
        arm += [
            *robotarm_cmds(plate.lid_put),
            *robotarm_cmds(plate.lid_get),
        ]
    for r_loc in r_locs[:N]:
        plate = replace(plate, r_loc=r_loc)
        arm += [
            *robotarm_cmds(plate.r_put),
            *robotarm_cmds(plate.r_get),
        ]
    for out_loc in out_locs[:N]:
        plate = replace(plate, out_loc=out_loc)
        arm += [
            *robotarm_cmds(plate.out_put),
            *robotarm_cmds(plate.out_get),
        ]
    plate = replace(plate, lid_loc=lid_locs[0], r_loc=r_locs[0])
    arm2: list[Command] = [
        *robotarm_cmds(plate.r_put),
        *robotarm_cmds('incu get'),
        *robotarm_cmds(plate.lid_put),
        *robotarm_cmds('wash put'),
        *robotarm_cmds('wash_to_disp'),
        *robotarm_cmds('disp get'),
        *robotarm_cmds('wash put'),
        *robotarm_cmds('wash get'),
        *robotarm_cmds(plate.lid_get),
        *robotarm_cmds('incu put'),
        *robotarm_cmds(plate.r_get),
    ]
    with runtime_with_logging(config, {'options': 'time_protocols'}) as runtime:
        ATTENTION(time_arm_incu.__doc__ or '')
        def execute(name: str, cmds: list[Command]):
            runtime.register_thread(f'{name} main')
            execute_commands(runtime, cmds)
            runtime.thread_idle()

        threads = [
            threading.Thread(target=lambda: execute('incu', incu), daemon=True),
            threading.Thread(target=lambda: execute('arm', arm), daemon=True),
        ]

        runtime.thread_idle()

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        execute_commands(runtime, arm2)

@dataclass(frozen=True)
class Event:
    plate_id: str
    part: str
    subpart: str
    command: robots.Command

    def machine(self) -> str:
        return self.command.__class__.__name__.rstrip('cmd').strip('_')

    def desc(self):
        return {
            'event_plate_id': self.plate_id,
            'event_part': self.part,
            'event_subpart': self.subpart,
            'event_machine': self.machine(),
        }

def execute_commands(runtime: Runtime, cmds: list[Command]) -> None:
    execute_events(runtime, [Event('', '', '', cmd) for cmd in cmds])

def execute_events(runtime: Runtime, events: list[Event]) -> None:
    for i, event in enumerate(events, start=1):
        # print(f'=== event {i}/{len(events)} | {" | ".join(event.desc().values())} ===')
        metadata: dict[str, str | int] = {
            'event_id': i,
            **event.desc(),
        }
        event.command.execute(runtime, metadata)

Desc = tuple[Plate, str, str]

def robotarm_cmds(s: str, before_pick: list[robots.Command] = [], after_drop: list[robots.Command] = []) -> list[robots.Command]:
    return [
        robots.robotarm_cmd(s + ' prep'),
        *before_pick,
        robots.robotarm_cmd(s + ' transfer'),
        *after_drop,
        robots.robotarm_cmd(s + ' return'),
    ]

def paint_batch(batch: list[Plate], protocol_config: ProtocolConfig, short_test_paint: bool=False):

    p = protocol_config

    if p.prep_wash and p.prep_disp:
        prep_cmds: list[Command] = [
            robots.wash_cmd(p.prep_wash),
            robots.disp_cmd(p.prep_disp, delay=robots.wait_for(robots.WashStarted()) + 5),
            robots.wait_for(robots.Ready('disp')),
            robots.wait_for(robots.Ready('wash')),
        ]
    elif p.prep_wash and not p.prep_disp:
        prep_cmds: list[Command] = [
            robots.wash_cmd(p.prep_wash),
            robots.wait_for(robots.Ready('wash')),
        ]
    elif not p.prep_wash and p.prep_disp:
        prep_cmds: list[Command] = [
            robots.disp_cmd(p.prep_disp),
            robots.wait_for(robots.Ready('disp')),
        ]
    elif not p.prep_wash and not p.prep_disp:
        prep_cmds: list[Command] = []
    else:
        assert False

    prep_events: list[Event] = [
        Event('', 'prep', '', cmd) for cmd in prep_cmds
    ]

    first_plate = batch[0]
    second_plate = batch[1] if len(batch) >= 2 else None
    last_plate = batch[-1]

    chunks: dict[Desc, Iterable[Command]] = {}
    for plate in batch:
        lid_mount = [
            *robotarm_cmds(plate.lid_get),
        ]

        lid_unmount = [
            *robotarm_cmds(plate.lid_put),
        ]

        incu_get = [
            robots.incu_cmd('get', plate.incu_loc),
            *robotarm_cmds('incu get', before_pick = [robots.wait_for(Ready('incu'))]),
            *lid_unmount,
        ]

        incu_put = [
            *lid_mount,
            *robotarm_cmds('incu put', after_drop = [robots.incu_cmd('put', plate.incu_loc)]),
            robots.wait_for(Ready('incu')),
        ]

        RT_get = [
            *robotarm_cmds(plate.r_get),
            *lid_unmount,
        ]

        RT_put = [
            *lid_mount,
            *robotarm_cmds(plate.r_put),
        ]

        def wash(wash_wait: robots.wait_for | None, wash_path: str, disp_prime_path: str | None=None, add_time: bool = True):
            if plate is first_plate and disp_prime_path is not None:
                disp_prime = [robots.disp_cmd(disp_prime_path, delay=robots.wait_for(Now()) + 5)]
            else:
                disp_prime = []
            return [
                robots.robotarm_cmd('wash put prep'),
                robots.robotarm_cmd('wash put transfer'),
                robots.wash_cmd(wash_path, delay=wash_wait, plate_id=plate.id),
                *disp_prime,
                robots.robotarm_cmd('wash put return'),
            ]

        def disp(disp_path: str):
            return [
                robots.robotarm_cmd('wash_to_disp prep'),
                robots.wait_for(Ready('wash')),
                robots.robotarm_cmd('wash_to_disp transfer'),
                robots.wait_for(Ready('disp')),  # ensure dispenser priming is done
                robots.disp_cmd(disp_path, plate_id=plate.id),
                robots.robotarm_cmd('wash_to_disp return'),
            ]

        disp_to_incu = [
            robots.robotarm_cmd('disp get prep'),
            robots.wait_for(Ready('disp')),
            robots.robotarm_cmd('disp get transfer'),
            robots.robotarm_cmd('disp get return'),
            *incu_put,
        ]

        disp_to_RT = [
            robots.robotarm_cmd('disp get prep'),
            robots.wait_for(Ready('disp')),
            robots.robotarm_cmd('disp get transfer'),
            robots.robotarm_cmd('disp get return'),
            *RT_put,
        ]

        wait_before_wash_start: dict[int, robots.wait_for | None] = {
            # 1: robots.wait_for(Now()) + p.delay_before_first_wash,
            1: robots.wait_for(WashStarted()) + p.separation_between_first_washes,
            2: robots.wait_for(DispFinished(plate.id)) + p.incu[1] * 60,
            3: robots.wait_for(DispFinished(plate.id)) + p.incu[2] * 60,
            4: robots.wait_for(DispFinished(plate.id)) + p.incu[3] * 60,
            5: robots.wait_for(DispFinished(plate.id)) + p.incu[4] * 60,
        }

        if plate is first_plate:
            wait_before_wash_start[1] = robots.wait_for(Now()) + p.delay_before_first_wash
            wait_before_incu_get = {
                1: [],
                2: [robots.wait_for(DispFinished(plate.id)) + (p.incu[1] * 60 - p.wait_before_incu_get_1st[2])],
                3: [robots.wait_for(DispFinished(plate.id)) + (p.incu[2] * 60 - p.wait_before_incu_get_1st[3])],
                4: [robots.wait_for(DispFinished(plate.id)) + (p.incu[3] * 60 - p.wait_before_incu_get_1st[4])],
                5: [robots.wait_for(DispFinished(plate.id)) + (p.incu[4] * 60 - p.wait_before_incu_get_1st[5])],
            }
        elif plate is second_plate:
            wait_before_incu_get: dict[int, list[robots.wait_for]] = {
                1: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_2nd[1]],
                2: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_2nd[2]],
                3: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_2nd[3]],
                4: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_2nd[4]],
                5: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_2nd[5]],
            }
        else:
            wait_before_incu_get: dict[int, list[robots.wait_for]] = {
                1: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_rest[1]],
                2: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_rest[2]],
                3: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_rest[3]],
                4: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_rest[4]],
                5: [robots.wait_for(WashStarted()) + p.wait_before_incu_get_rest[5]],
            }


        chunks[plate, 'Mito', 'to h21']            = [*wait_before_incu_get[1], *incu_get]
        chunks[plate, 'Mito', 'to wash']           = wash(wait_before_wash_start[1], p.wash[1], p.prime[1], add_time=False)
        chunks[plate, 'Mito', 'to disp']           = disp(p.disp[1])
        chunks[plate, 'Mito', 'to incu via h21']   = disp_to_incu

        chunks[plate, 'PFA', 'to h21']             = [*wait_before_incu_get[2], *incu_get]
        chunks[plate, 'PFA', 'to wash']            = wash(wait_before_wash_start[2], p.wash[2], p.prime[2])
        chunks[plate, 'PFA', 'to disp']            = disp(p.disp[2])
        chunks[plate, 'PFA', 'to incu via h21']    = disp_to_RT

        chunks[plate, 'Triton', 'to h21']          = [*wait_before_incu_get[3], *RT_get]
        chunks[plate, 'Triton', 'to wash']         = wash(wait_before_wash_start[3], p.wash[3], p.prime[3])
        chunks[plate, 'Triton', 'to disp']         = disp(p.disp[3])
        chunks[plate, 'Triton', 'to incu via h21'] = disp_to_RT

        chunks[plate, 'Stains', 'to h21']          = [*wait_before_incu_get[4], *RT_get]
        chunks[plate, 'Stains', 'to wash']         = wash(wait_before_wash_start[4], p.wash[4], p.prime[4])
        chunks[plate, 'Stains', 'to disp']         = disp(p.disp[4])
        chunks[plate, 'Stains', 'to incu via h21'] = disp_to_RT

        chunks[plate, 'Final', 'to h21']           = [*wait_before_incu_get[5], *RT_get]
        chunks[plate, 'Final', 'to wash']          = wash(wait_before_wash_start[5], p.wash[5])
        chunks[plate, 'Final', 'to h21 from wash'] = [
            *robotarm_cmds('wash get', before_pick=[robots.wait_for(Ready('wash'))])
        ]
        chunks[plate, 'Final', 'to out via h21'] = [
            *lid_mount,
            *robotarm_cmds(plate.out_put)
        ]

    from collections import defaultdict
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

    parts = ['Mito', 'PFA', 'Triton', 'Stains', 'Final']

    if short_test_paint:
        skip = ['Triton', 'Stains']
        parts = [part for part in parts if part not in skip]
        chunks = {
            desc: cmd
            for desc, cmd in chunks.items()
            for _, part, _ in [desc]
            if part not in skip
        }

    for part, next_part in utils.iterate_with_next(parts):
        if next_part:
            seq([
                desc(last_plate, part, 'to incu via h21'),
                desc(first_plate, next_part, 'to h21'),
            ])

    for A, B, C in utils.iterate_with_context(batch):
        for part in parts:
            if part != 'Final':
                seq([
                    desc(A, part, 'to h21'),
                    desc(A, part, 'to wash'),
                    desc(A, part, 'to disp'),
                    desc(A, part, 'to incu via h21'),
                    desc(B, part, 'to h21'),
                    desc(B, part, 'to wash'),
                    desc(B, part, 'to disp'),
                    desc(B, part, 'to incu via h21'),
                    desc(C, part, 'to h21'),
                    desc(C, part, 'to wash'),
                ])
            else:
                assert part == 'Final'
                seq([
                    desc(A, part, 'to h21'),
                    desc(A, part, 'to wash'),
                    desc(A, part, 'to h21 from wash'),
                    desc(A, part, 'to out via h21'),
                    desc(B, part, 'to h21'),
                    desc(B, part, 'to wash'),
                    desc(B, part, 'to h21 from wash'),
                    desc(B, part, 'to out via h21'),
                    desc(C, part, 'to h21'),
                    desc(C, part, 'to wash'),
                ])

    deps: dict[Desc, set[Desc]] = defaultdict(set)
    for node, nexts in adjacent.items():
        for next in nexts:
            deps[next] |= {node}

    linear = list(graphlib.TopologicalSorter(deps).static_order())

    if 0:
        pr([
            ' '.join((desc[1], desc[0].id, desc[2]))
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

    return prep_events + plate_events

def define_plates(batch_sizes: list[int]) -> list[Plate]:
    plates: list[Plate] = []

    index = 0
    for batch_index, batch_size in enumerate(batch_sizes):
        for index_in_batch in range(batch_size):
            plates += [Plate(
                id=f'{index+1}',
                incu_loc=incu_locs[index],
                r_loc=r_locs[index_in_batch],
                lid_loc=lid_locs[index_in_batch],
                out_loc=out_locs[index],
                batch_index=batch_index,
            )]
            index += 1

    for i, p in enumerate(plates):
        for j, q in enumerate(plates):
            if i != j:
                assert p.id != q.id, (p, q)
                assert p.incu_loc != q.incu_loc, (p, q)
                assert p.out_loc not in [q.out_loc, q.r_loc, q.lid_loc, q.incu_loc], (p, q)
                if p.batch_index == q.batch_index:
                    assert p.r_loc != q.r_loc, (p, q)
                    assert p.lid_loc != q.lid_loc, (p, q)

    return plates

def group_by_batch(plates: list[Plate]) -> list[list[Plate]]:
    d: dict[int, list[Plate]] = defaultdict(list)
    for plate in plates:
        d[plate.batch_index] += [plate]
    return sorted(d.values(), key=lambda plates: plates[0].batch_index)

def eventlist(batch_sizes: list[int], protocol_config: ProtocolConfig, short_test_paint: bool = False, sleek: bool = True) -> list[Event]:
    all_events: list[Event] = []
    for batch in group_by_batch(define_plates(batch_sizes)):
        events = paint_batch(
            batch,
            protocol_config=protocol_config,
            short_test_paint=short_test_paint,
        )
        if sleek:
            def get_movelist(event: Event) -> moves.MoveList | None:
                if isinstance(event.command, robots.robotarm_cmd):
                    return movelists[event.command.program_name]
                else:
                    return None
            events = moves.sleek_movements(events, get_movelist)
        all_events += events
    return all_events

def test_circuit(config: RuntimeConfig) -> None:
    '''
    Test circuit: Short test paint on one plate, without incubator
    '''
    plate, = define_plates([1])
    events = eventlist([1], protocol_config=v3, short_test_paint=True)
    events = [
        event
        for event in events
        if isinstance(event.command, robots.robotarm_cmd)
    ] + [
        Event(plate.id, 'return', name, robots.robotarm_cmd(name))
        for name in [
            plate.out_get,
            'incu put'
        ]

    ]
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
    execute_events_with_logging(config, events, metadata={'options': 'test_circuit'})

def main(config: RuntimeConfig, protocol_config: ProtocolConfig, *, batch_sizes: list[int], short_test_paint: bool = False) -> None:
    events = eventlist(batch_sizes, protocol_config=protocol_config, short_test_paint=short_test_paint)
    metadata: dict[str, str] = {
        'batch_sizes': ','.join(str(bs) for bs in batch_sizes),
    }

    if short_test_paint:
        metadata = {
            **metadata,
            'options': 'short_test_paint'
        }
        robots.test_comm(config)
        ATTENTION('''
            Short test paint mode, NOT real cell painting
        ''')

    runtime = execute_events_with_logging(config, events, metadata)
    for k, v in runtime.times.items():
        print(k, v)

import contextlib

@contextlib.contextmanager
def runtime_with_logging(config: RuntimeConfig, metadata: dict[str, str]) -> Iterator[Runtime]:
    metadata = {
        'start_time': str(datetime.now()).split('.')[0],
        **metadata,
        'config_name': config.name(),
    }
    log_filename = ' '.join(['event log', *metadata.values()])
    log_filename = 'logs/' + log_filename.replace(' ', '_') + '.jsonl'
    os.makedirs('logs/', exist_ok=True)

    print(f'{log_filename=}')

    runtime = robots.Runtime(config=config, log_filename=log_filename)
    # Overrides for v3
    overrides: dict[robots.Estimated, float] = {
        ('disp', v3.disp.Mito): 73.11 - 15,
    }
    for (k, a), v in runtime.estimates.items():
        if '19' in a:
            for h in H:
                ah = a.replace('19', str(h))
                if (k, ah) not in runtime.estimates:
                    overrides[k, ah] = v
        if 'out1 ' in a:
            for h in H:
                ah = a.replace('out1 ', f'out{h} ')
                if (k, ah) not in runtime.estimates:
                    overrides[k, ah] = v
        if 'L1' in a:
            for i in incu_locs:
                ah = a.replace('L1', i)
                if (k, ah) not in runtime.estimates:
                    overrides[k, ah] = v
    pr({k: (runtime.estimates.get(k, None), '->', v) for k, v in overrides.items()})
    runtime.estimates.update(overrides)

    metadata['git_HEAD'] = utils.git_HEAD() or ''
    metadata['host']     = platform.node()
    with runtime.excepthook():
        with runtime.timeit('experiment', metadata=metadata):
            yield runtime

def execute_events_with_logging(config: RuntimeConfig, events: list[Event], metadata: dict[str, str]) -> Runtime:
    with runtime_with_logging(config, metadata) as runtime:
        execute_events(runtime, events)
        return runtime

