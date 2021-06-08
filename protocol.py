from __future__ import annotations
from typing import *
from dataclasses import *

from datetime import datetime, timedelta
from moves import movelists
from robots import Config, configs, Command, par, Time
from robots import DispFinished, WashStarted, Now, Ready

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
    plate_id: str
    part: str
    subpart: str
    command: robots.Command

    def machine(self) -> str:
        return self.command.__class__.__name__.rstrip('cmd').strip('_')

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

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(22)]

h21 = 'h21'
r21 = 'r21'

incu_locs: list[str] = [f'L{i}' for i in I] + [f'R{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H][1:]
out_locs:  list[str] = [f'out{i}' for i in reversed(H)] + list(reversed(r_locs))
lid_locs:  list[str] = [h for h in h_locs if h != h21]

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
                robots.incu_cmd('get', plate.incu_loc),
                robots.robotarm_cmd('incu get prep'),
            ]),
            robots.wait_for(Ready('incu')),
            robots.robotarm_cmd('incu get main'),
            *lid_unmount,
        ]

        incu_put = [
            *lid_mount,
            robots.robotarm_cmd('incu put main'),
            par([
                robots.incu_cmd('put', plate.incu_loc),
                robots.robotarm_cmd('incu put return'),
            ]),
            robots.wait_for(Ready('incu')),
        ]

        RT_get = [
            robots.robotarm_cmd(f'{plate.r_loc} get'),
            *lid_unmount,
        ]

        RT_put = [
            *lid_mount,
            robots.robotarm_cmd(f'{plate.r_loc} put'),
        ]


        def wash(wait_in_wash: list[robots.wait_for], wash_path: str, disp_prime_path: str | None=None):
            if plate is first_plate and disp_prime_path is not None:
                disp_prime = [robots.disp_cmd(disp_prime_path)]
            else:
                disp_prime = []
            return [
                robots.robotarm_cmd('wash put main'),
                *wait_in_wash,
                *disp_prime,
                robots.wash_cmd(wash_path),
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
            robots.robotarm_cmd('disp get main'),
            *incu_put,
        ]

        disp_to_RT = [
            robots.robotarm_cmd('disp get prep'),
            robots.wait_for(Ready('disp')),
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

        guesstimate_time_wash_3X_minus_incu_pop = 45
        guesstimate_time_wash_3X_minus_RT_pop   = 60
        guesstimate_time_wash_4X_minus_RT_pop   = 80
        guesstimate_time_wash_4X_minus_wash_3X  = 20 # most critical of the guesstimates (!)

        if p is first_plate:
            incu_wait_1 = []
            wash_wait_1 = []
            incu_wait_2 = [robots.wait_for(DispFinished(p.id)) + 29 * 60]
            incu_wait_3 = [robots.wait_for(DispFinished(p.id)) + 19 * 60]
            incu_wait_4 = [robots.wait_for(DispFinished(p.id)) + 19 * 60]
            incu_wait_5 = [robots.wait_for(DispFinished(p.id)) + 19 * 60]
        else:
            incu_wait_1 = [robots.wait_for(WashStarted()) + guesstimate_time_wash_3X_minus_incu_pop]
            wash_wait_1 = [robots.wait_for(Now())         + guesstimate_time_wash_4X_minus_wash_3X]
            incu_wait_2 = [robots.wait_for(WashStarted()) + guesstimate_time_wash_3X_minus_incu_pop]
            incu_wait_3 = [robots.wait_for(WashStarted()) + guesstimate_time_wash_3X_minus_incu_pop]
            incu_wait_4 = [robots.wait_for(WashStarted()) + guesstimate_time_wash_3X_minus_incu_pop]
            incu_wait_5 = [robots.wait_for(WashStarted()) + guesstimate_time_wash_3X_minus_incu_pop]

        wash_wait_2 = [robots.wait_for(DispFinished(p.id)) + 30 * 60]
        wash_wait_3 = [robots.wait_for(DispFinished(p.id)) + 20 * 60]
        wash_wait_4 = [robots.wait_for(DispFinished(p.id)) + 20 * 60]
        wash_wait_5 = [robots.wait_for(DispFinished(p.id)) + 20 * 60]

        chunks[p, 'Mito', 'to h21']            = [*incu_wait_1, *incu_get]
        chunks[p, 'Mito', 'to wash']           = wash(wash_wait_1, wash_3X, Mito_prime)
        chunks[p, 'Mito', 'to disp']           = disp(Mito_disp)
        chunks[p, 'Mito', 'to incu via h21']   = disp_to_incu

        chunks[p, 'PFA', 'to h21']             = [*incu_wait_2, *incu_get]
        chunks[p, 'PFA', 'to wash']            = wash(wash_wait_2, wash_3X, PFA_prime)
        chunks[p, 'PFA', 'to disp']            = disp(PFA_disp)
        chunks[p, 'PFA', 'to incu via h21']    = disp_to_RT

        chunks[p, 'Triton', 'to h21']          = [*incu_wait_3, *RT_get]
        chunks[p, 'Triton', 'to wash']         = wash(wash_wait_3, wash_3X, Triton_prime)
        chunks[p, 'Triton', 'to disp']         = disp(Triton_disp)
        chunks[p, 'Triton', 'to incu via h21'] = disp_to_RT

        chunks[p, 'Stains', 'to h21']          = [*incu_wait_4, *RT_get]
        chunks[p, 'Stains', 'to wash']         = wash(wash_wait_4, wash_3X, Stains_prime)
        chunks[p, 'Stains', 'to disp']         = disp(Stains_disp)
        chunks[p, 'Stains', 'to incu via h21'] = disp_to_RT

        chunks[p, 'Final', 'to h21']           = [*incu_wait_5, *RT_get]
        chunks[p, 'Final', 'to wash']          = wash(wash_wait_5, wash_4X)
        chunks[p, 'Final', 'to r21 from wash'] = [
            robots.robotarm_cmd('wash_to_r21 get prep'),
            robots.wait_for(Ready('wash')),
            robots.robotarm_cmd('wash_to_r21 get main')
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

    short = 0
    if short:
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
                # seq(A, B) := t[A] < t[B]
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
    return [
        Event(
            plate_id=plate.id,
            part =part,
            subpart=subpart,
            command=command,
        )
        for desc in linear
        for plate, part, subpart in [desc]
        for command in chunks[desc]
    ]


def define_plates(n: int) -> list[Plate]:
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

# lin = paint_batch(define_plates(4))

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
        pr(astuple(event))
        start_time = Time.now(config)
        event.command.execute(config)
        stop_time = Time.now(config)
        entry: dict[str, str | int | float] = dict(
            start_time = str(start_time),
            stop_time = str(stop_time),
            duration=(stop_time - start_time).total_seconds(),
            command=event.machine(),
            **asdict(event.command),
        )
        entry['plate_id'] = event.plate_id
        if config.time_mode == 'fast forward':
            entry['skipped_time'] = config.skipped_time.value
        # pr(entry)
        pr(('duration:', entry['duration'], 'skipped_time:', config.skipped_time.value))
        entry = {**entry, **metadata}
        log += [entry]
        with open(log_name, 'w') as fp:
            json.dump(log, fp, indent=2)

def main(
    config: Config,
    *,
    # num_batches: int,
    # batch_size: int,
    # test_circuit: bool=False
    num_plates: int,
) -> None:
    events = paint_batch(define_plates(num_plates))
    events = sleek_movements(events)
    execute(events, config)

def paint_batches(batches: list[list[Plate]]):
    assert not 'TODO'
    for batch in batches:
        paint_batch(batch)

