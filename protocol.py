from __future__ import annotations
from typing import *
from dataclasses import *

from datetime import datetime, timedelta
from moves import movelists
from robots import Config, configs, Command, par

from utils import pr, show
from utils import Mutable

import json
import os
import platform
import protocol
import re
import robots
import sys
import textwrap
import utils

@dataclass(frozen=True)
class Event:
    begin: float
    end: float
    plate_id: str | None
    command: robots.Command
    overlap: Mutable[bool] = field(default_factory=lambda: Mutable(False))

    def machine(self) -> str:
        return self.command.__class__.__name__.rstrip('cmd').strip('_')

def calculate_overlap(events: list[Event]) -> None:
    machines = {e.machine() for e in events}
    for m in machines:
        if m == 'timer':
            continue
        es = sorted((e for e in events if e.machine() == m), key=lambda e: e.begin)
        for fst, snd in zip(es, es[1:]):
            if fst.end > snd.begin:
                fst.overlap.value = True
                snd.overlap.value = True

def sleek_movements(events: list[Event]) -> list[Event]:
    '''
    if program A ends by h21 neu and program B by h21 neu then run:
        program A to h21 neu
        program B from h21 neu
    '''

    out = [*events]

    arm_indicies: list[int] = [
        i
        for i, event in enumerate(out)
        if isinstance(event.command, robots.robotarm_cmd)
    ]

    for i, j in utils.iterate_with_next(arm_indicies):
        if j is None:
            continue
        event_a = out[i]
        event_b = out[j]
        a = cast(robots.robotarm_cmd, event_a.command).program_name
        b = cast(robots.robotarm_cmd, event_b.command).program_name
        a_ml = movelists[a]
        b_ml = movelists[b]
        neu, a_opt, b_opt = a_ml.optimize_transition(b_ml)
        if neu:
            neu = neu.removesuffix('neu').strip()
            a2 = a + ' to ' + neu
            b2 = b + ' from ' + neu
            movelists[a2] = a_opt
            movelists[b2] = b_opt
            out[i] = replace(event_a, command=replace(event_a.command, program_name=a2))
            out[j] = replace(event_b, command=replace(event_b.command, program_name=b2))
    return out

@dataclass(frozen=True)
class Plate:
    id: str
    incu_loc: str
    r_loc: str
    lid_loc: str
    out_loc: str

def cell_paint_one(plate: Plate, test_circuit: bool=False) -> list[Event]:

    incu_get = [
        robots.wait_for_timer_cmd(plate.id),
        par([
            robots.incu_cmd('get', plate.incu_loc, est=10),
            robots.robotarm_cmd('incu get prep'),
        ]),
        robots.wait_for_ready_cmd('incu'),
        robots.robotarm_cmd('incu get main'),
        robots.robotarm_cmd(f'lid_{plate.lid_loc} put'),
    ]

    incu_put_main_part = [
        robots.robotarm_cmd('incu put main'),
        par([
            robots.incu_cmd('put', plate.incu_loc, est=10),
            robots.robotarm_cmd('incu put return'),
        ]),
        robots.wait_for_ready_cmd('incu'),
    ]

    def incu_put(minutes: int):
        return [
            robots.robotarm_cmd(f'lid_{plate.lid_loc} get'),
            *incu_put_main_part,
            robots.timer_cmd(minutes, plate.id),
        ]

    def RT(minutes: int):
        return [
            robots.robotarm_cmd(f'lid_{plate.lid_loc} get'),
            robots.robotarm_cmd(f'{plate.r_loc} put'),
            robots.timer_cmd(minutes, plate.id),
            robots.wait_for_timer_cmd(plate.id),
            robots.robotarm_cmd(f'{plate.r_loc} get'),
            robots.robotarm_cmd(f'lid_{plate.lid_loc} put'),
        ]

    def wash(wash_path: str):
        return [
            robots.robotarm_cmd('wash put main'),
            par([
                robots.wash_cmd(wash_path, est=90),
                robots.robotarm_cmd('wash put return'),
            ]),

            robots.robotarm_cmd('wash get prep', prep=True),
            # Yields:
            robots.wait_for_ready_cmd('wash'),

            robots.robotarm_cmd('wash get main'),
        ]

    def wash_and_disp(
        wash_path: str,
        disp_pump: str,
        disp_priming_path: str,
        disp_path: str
    ):
        return [
            robots.robotarm_cmd('wash put main'),
            par([
                robots.wash_cmd(wash_path, est=90),
                # ensure this disp pump is primed:
                robots.disp_cmd(disp_priming_path, disp_pump=disp_pump, is_priming=True),
                robots.robotarm_cmd('wash put return'),
            ]),

            robots.robotarm_cmd('wash_to_disp prep', prep=True),
            # Yields:
            robots.wait_for_ready_cmd('wash'),

            robots.robotarm_cmd('wash_to_disp transfer'),
            robots.wait_for_ready_cmd('disp'),  # make sure dispenser priming is ready
            robots.disp_cmd(disp_path, disp_pump=disp_pump, est=15),
            robots.robotarm_cmd('wash_to_disp return'),
            robots.wait_for_ready_cmd('disp'),
            robots.robotarm_cmd('disp get main'),
            # (dispensing is so fast so we don't yield)
        ]

    to_out = [
        robots.robotarm_cmd(f'lid_{plate.lid_loc} get'),
        robots.robotarm_cmd(f'{plate.out_loc} put'),
    ]

    cmds: list[Command] = [
        # 2 Compound treatment
        robots.timer_cmd(plate.seconds_offset / 60.0, plate.id),

        # 3 Mitotracker staining
        *incu_get,
        *wash_and_disp(
            'automation/2_4_6_W-3X_FinalAspirate.LHC',
            'P1',
            'automation/1_D_P1_PRIME.LHC',
            'automation/1_D_P1_30ul_mito.LHC',
        ),
        *incu_put(30),

        # 4 Fixation
        *incu_get,
        *wash_and_disp(
            'automation/2_4_6_W-3X_FinalAspirate.LHC',
            'SA',
            'automation/3_D_SA_PRIME.LHC',
            'automation/3_D_SA_384_50ul_PFA.LHC',
        ),
        *RT(20),

        # 5 Permeabilization
        *wash_and_disp(
            'automation/2_4_6_W-3X_FinalAspirate.LHC',
            'SB',
            'automation/5_D_SB_PRIME.LHC',
            'automation/5_D_SB_384_50ul_TRITON.LHC',
        ),
        *RT(20),

        # 6 Post-fixation staining
        *wash_and_disp(
            'automation/2_4_6_W-3X_FinalAspirate.LHC',
            'P2',
            'automation/7_D_P2_PRIME.LHC',
            'automation/7_D_P2_20ul_STAINS.LHC',
        ),
        *RT(20),

        # Last wash
        *wash(
            'automation/8_W-4X_NoFinalAspirate.LHC',
        ),

        # Move to output hotel
        *to_out,
    ]

    if test_circuit:
        cmds += [
            # Return to home
            robots.timer_cmd(20, plate.id),
            robots.wait_for_timer_cmd(plate.id),
            robots.robotarm_cmd(f'{plate.out_loc} get'),
            *incu_put_main_part,
        ]

    t = 0.0
    events: list[Event] = []
    for cmd in cmds:
        est = cmd.time_estimate()
        t_begin: float = t
        t_ends: list[float] = []
        sub_cmds: tuple[Command, ...] = cmd.sub_cmds() if isinstance(cmd, robots.par) else (cmd,)
        for sub_cmd in sub_cmds:
            if sub_cmd.is_prep():
                my_begin = t_begin - sub_cmd.time_estimate()
            else:
                my_begin = t_begin
            event = Event(
                command=sub_cmd,
                plate_id=plate.id, # (f'{plate.id}') if cmd.is_prep() else plate.id,
                begin=my_begin,
                end=my_begin + sub_cmd.time_estimate(),
            )
            events += [event]
            t_ends += [event.end]
        t = max(t_ends)

    return events

def cell_paint_many(
    plates: list[Plate],
    test_circuit: bool,
) -> list[Event]:
    events = utils.flatten([cell_paint_one(plate) for plate in plates])
    events = sorted(events, key=lambda e: (e.begin if isinstance(e.command, robots.timer_cmd) else e.end))
    events = list(events)
    calculate_overlap(events)
    return events


H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(22)]

h21 = 'h21'
r21 = 'r21'

incu_locs: list[str] = [f'L{i}' for i in I] + [f'R{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H][1:]
out_locs:  list[str] = [f'out{i}' for i in reversed(H)] + list(reversed(r_locs))
lid_locs:  list[str] = [h for h in h_locs if h != h21]

def cell_paint_batches(
    num_batches: int,
    batch_size: int,
    between_batch_delay: int,
    within_batch_delay: int,
    test_circuit: bool=False
) -> list[Event]:

    plates: list[Plate] = []

    index = 0
    for batch in range(num_batches):
        for batch_index in range(batch_size):
            plates += [Plate(
                id=f'p{index+1:02d}',
                incu_loc=incu_locs[index],
                r_loc=r_locs[batch_index],
                lid_loc=lid_locs[batch_index],
                out_loc=out_locs[index],
            )]
            index += 1

    for i, p in enumerate(plates):
        for j, q in enumerate(plates):
            if i != j:
                assert p.id != q.id
                assert p.incu_loc != q.incu_loc
                assert p.out_loc not in [q.out_loc, q.r_loc, q.lid_loc, q.incu_loc]
                assert p.r_loc != q.r_loc
                assert p.lid_loc != q.lid_loc
            else:
                assert 'h21' not in [p.lid_loc, p.r_loc, p.out_loc]
                assert 'r21' not in [p.lid_loc, p.r_loc, p.out_loc]

    return cell_paint_many(plates, test_circuit=test_circuit)

def cell_paint_batches_auto_delay(
    num_batches: int,
    batch_size: int,
    test_circuit: bool=False
) -> tuple[list[Event], int, int]:
    events: list[Event] = []

    within_batch_delay: int | None = None
    works: list[int] = []
    for test in range(400):
        events = cell_paint_batches(1, batch_size, 0, test, test_circuit=test_circuit)
        if not any(e.overlap.value for e in events):
            within_batch_delay = test
            break

    assert within_batch_delay is not None

    between_batch_delay: int | None = None
    hh = 60 * 60
    for test in range(hh, 3 * hh, 60):
        events = cell_paint_batches(num_batches, batch_size, test, within_batch_delay, test_circuit=test_circuit)
        if not any(e.overlap.value for e in events):
            between_batch_delay = test
            break

    assert between_batch_delay is not None

    return events, between_batch_delay, within_batch_delay

def cell_paint_batches_parse_delay(
    num_batches: int,
    batch_size: int,
    between_batch_delay_str: str,
    within_batch_delay_str: str,
    test_circuit: bool=False
) -> tuple[list[Event], int, int]:

    if (
        between_batch_delay_str == 'auto' or
        within_batch_delay_str == 'auto'
    ):
        return protocol.cell_paint_batches_auto_delay(num_batches, batch_size)
    else:
        between_batch_delay: int = int(between_batch_delay_str)
        within_batch_delay: int  = int(within_batch_delay_str)
        events = protocol.cell_paint_batches(num_batches, batch_size, between_batch_delay, within_batch_delay)
        return events, between_batch_delay, within_batch_delay

def execute(events: list[Event], config: Config) -> None:
    metadata = dict(
        experiment_time = str(datetime.now()).split('.')[0],
        host = platform.node(),
        config_name = config.name(),
    )
    log_name = ' '.join(['event log', *metadata.values()])
    log_name = 'logs/' + log_name.replace(' ', '_') + '.json'
    os.makedirs('logs/', exist_ok=True)
    log: list[dict[str, Any]] = []
    for i, event in enumerate(events):
        print(f'=== event {i+1}/{len(events)} ===')
        pr(event.command)
        start_time = datetime.now()
        event.command.execute(config)
        stop_time = datetime.now()
        entry = dict(
            start_time = str(start_time),
            stop_time = str(stop_time),
            duration=(stop_time - start_time).total_seconds(),
            plate_id=event.plate_id,
            command=event.machine(),
            **asdict(event.command),
        )
        pr(entry)
        entry = {**entry, **metadata}
        log += [entry]
        with open(log_name, 'w') as fp:
            json.dump(log, fp, indent=2)

def main(
    config: Config,
    *,
    num_batches: int,
    batch_size: int,
    between_batch_delay_str: str = 'auto',
    within_batch_delay_str: str = 'auto',
    test_circuit: bool=False
) -> None:
    events, between_batch_delay, within_batch_delay = protocol.cell_paint_batches_parse_delay(
        num_batches,
        batch_size,
        between_batch_delay_str,
        within_batch_delay_str,
        test_circuit=test_circuit
    )
    print(f'{between_batch_delay=}')
    print(f'{within_batch_delay=}')
    events = protocol.sleek_movements(events)
    execute(events, config)

def paint(batches: list[list[Plate]]):
    for batch in batches:
        paint_batch(batch) # TODO

Desc = tuple[Plate, str, str]

def paint_batch(batch: list[Plate]):

    first_plate = batch[0]
    last_plate = batch[-1]

    chunks: dict[Desc, Iterable[Command]] = {}
    for plate in batch:
        lid_mount = [
            robots.robotarm_cmd(f'lid_{plate.lid_loc} get'),
        ]

        lid_unmount = [
            robots.robotarm_cmd(f'lid_{plate.lid_loc} put'),
        ]

        incu_get = [
            par([
                robots.incu_cmd('get', plate.incu_loc, est=10),
                robots.robotarm_cmd('incu get prep'),
            ]),
            robots.wait_for_ready_cmd('incu'),
            robots.robotarm_cmd('incu get main'),
            *lid_unmount,
        ]

        incu_put = [
            *lid_mount,
            robots.robotarm_cmd('incu put main'),
            par([
                robots.incu_cmd('put', plate.incu_loc, est=10),
                robots.robotarm_cmd('incu put return'),
            ]),
            robots.wait_for_ready_cmd('incu'),
        ]

        RT_get = [
            robots.robotarm_cmd(f'{plate.r_loc} get'),
            *lid_unmount,
        ]

        RT_put = [
            *lid_mount,
            robots.robotarm_cmd(f'{plate.r_loc} put'),
        ]


        def wash(wash_path: str, disp_prime_path: str | None= None):
            if plate is first_plate and disp_prime_path is not None:
                disp_prime = [robots.disp_cmd(disp_prime_path)]
            else:
                disp_prime = []
            return [
                robots.robotarm_cmd('wash put main'),
                *disp_prime,
                robots.wash_cmd(wash_path, est=90), # this should be delayed appropriately ??
                robots.robotarm_cmd('wash put return'),
            ]

        def disp(disp_path: str):
            return [
                robots.robotarm_cmd('wash_to_disp prep'),
                robots.wait_for_ready_cmd('wash'),
                robots.robotarm_cmd('wash_to_disp transfer'),
                robots.wait_for_ready_cmd('disp'),  # ensure dispenser priming is done
                robots.disp_cmd(disp_path),
                robots.robotarm_cmd('wash_to_disp return'),
            ]

        disp_to_incu = [
            robots.robotarm_cmd('disp get prep'),
            robots.wait_for_ready_cmd('disp'),
            robots.robotarm_cmd('disp get main'),
            *incu_put,
        ]

        disp_to_RT = [
            robots.robotarm_cmd('disp get prep'),
            robots.wait_for_ready_cmd('disp'),
            robots.robotarm_cmd('disp get main'),
            *RT_put,
        ]

        Mito_prime   = 'automation/1_D_P1_PRIME.LHC'
        Mito_disp    = 'automation/1_D_P1_30ul_mito.LHC'
        PFA_prime    = 'automation/3_D_SA_PRIME.LHC'
        PFA_disp     = 'automation/3_D_SA_384_50ul_PFA.LHC'
        Triton_prime = 'automation/5_D_SB_PRIME.LHC'
        Triton_disp  = 'automation/5_D_SB_384_50ul_TRITON.LHC'
        Stains_prime = 'automation/7_D_P2_PRIME.LHC'
        Stains_disp  = 'automation/7_D_P2_20ul_STAINS.LHC'

        wash_3X = 'automation/2_4_6_W-3X_FinalAspirate.LHC'
        wash_4X = 'automation/8_W-4X_NoFinalAspirate.LHC'

        p = plate

        chunks[p, 'Mito', 'to h21']            = incu_get
        chunks[p, 'Mito', 'to wash']           = wash(wash_3X, Mito_prime)
        chunks[p, 'Mito', 'to disp']           = disp(Mito_disp)
        chunks[p, 'Mito', 'to incu via h21']   = disp_to_incu

        chunks[p, 'PFA', 'to h21']             = incu_get
        chunks[p, 'PFA', 'to wash']            = wash(wash_3X, PFA_prime)
        chunks[p, 'PFA', 'to disp']            = disp(PFA_disp)
        chunks[p, 'PFA', 'to incu via h21']    = disp_to_RT

        chunks[p, 'Triton', 'to h21']          = RT_get
        chunks[p, 'Triton', 'to wash']         = wash(wash_3X, Triton_prime)
        chunks[p, 'Triton', 'to disp']         = disp(Triton_disp)
        chunks[p, 'Triton', 'to incu via h21'] = disp_to_RT

        chunks[p, 'Stains', 'to h21']          = RT_get
        chunks[p, 'Stains', 'to wash']         = wash(wash_3X, Stains_prime)
        chunks[p, 'Stains', 'to disp']         = disp(Stains_disp)
        chunks[p, 'Stains', 'to incu via h21'] = disp_to_RT

        chunks[p, 'Final', 'to h21']           = RT_get
        chunks[p, 'Final', 'to wash']          = wash(wash_4X)
        chunks[p, 'Final', 'to r21 from wash'] = [
            robots.robotarm_cmd('wash to r21 prep'),
            robots.wait_for_ready_cmd('wash'),
            robots.robotarm_cmd('wash to r21 main')
        ]
        chunks[p, 'Final', 'to out via r21 and h21']   = [
            robots.robotarm_cmd('r21 get'),
            *lid_mount,
            robots.robotarm_cmd(f'{plate.out_loc} put'),
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

    for part, next_part in utils.iterate_with_next(parts):
        if next_part:
            seq([
                desc(last_plate, part, 'to incu via h21'),
                desc(first_plate, next_part, 'to h21'),
            ])

    for A, B, C in utils.iterate_with_context(batch):
        for part in parts:
            if part != 'Final':
                # seq = back to back, not a < constraint
                # seq(A, B) := t[A] + 1 = t[B]
                # seq(A, B) := t[B] = t[A] - 1
                seq([
                    desc(A, part, 'to h21'),
                    desc(A, part, 'to wash'),
                    desc(B, part, 'to h21'),
                    desc(A, part, 'to disp'),
                    desc(B, part, 'to wash'),
                    desc(A, part, 'to incu via h21'),
                    desc(C, part, 'to h21'),
                    desc(B, part, 'to disp'),
                    desc(C, part, 'to wash'),
                    desc(B, part, 'to incu via h21'),
                ])
            if part == 'Final':
                seq([
                    desc(A, part, 'to h21'),
                    desc(A, part, 'to wash'),
                    desc(B, part, 'to h21'),
                    desc(A, part, 'to r21 from wash'),
                    desc(B, part, 'to wash'),
                    desc(A, part, 'to out via r21 and h21'),
                    desc(C, part, 'to h21'),
                    desc(B, part, 'to r21 from wash'),
                    desc(C, part, 'to wash'),
                    desc(B, part, 'to out via r21 and h21'),
                ])

    import graphlib

    deps: dict[Desc, set[Desc]] = defaultdict(set)
    for node, nexts in adjacent.items():
        for next in nexts:
            deps[next] |= {node}

    linear = list(graphlib.TopologicalSorter(deps).static_order())

    pr([
        ' '.join((desc[1], desc[0].id, desc[2]))
        for desc in linear
    ])
    return [chunks[desc] for desc in linear]


def n_plates(n: int) -> list[Plate]:
    plates: list[Plate] = []

    for index in range(n):
        plates += [Plate(
            id=f'p{index+1:02d}',
            incu_loc=incu_locs[index],
            r_loc=r_locs[index],
            lid_loc=lid_locs[index],
            out_loc=out_locs[index],
        )]

    for i, p in enumerate(plates):
        for j, q in enumerate(plates):
            if i != j:
                assert p.id != q.id
                assert p.incu_loc != q.incu_loc
                assert p.out_loc not in [q.out_loc, q.r_loc, q.lid_loc, q.incu_loc]
                assert p.r_loc != q.r_loc
                assert p.lid_loc != q.lid_loc

    return plates

lin = paint_batch(n_plates(6))
# utils.pr(lin)
