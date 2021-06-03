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

    for _, i, j in utils.context(arm_indicies):
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
    seconds_offset: int
    incu_loc: str
    r_loc: str
    lid_loc: str
    out_loc: str
    batch: int

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
        robots.incu_cmd('put', plate.incu_loc, est=0),
        robots.robotarm_cmd('incu put return'),
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
    events = sorted(events, key=lambda e: e.end)
    events = list(events)
    calculate_overlap(events)
    return events


H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(22)]

h21 = 'h21'

incu_locs: list[str] = [f'L{i}' for i in I] + [f'R{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H]
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
                seconds_offset=batch*between_batch_delay + batch_index*within_batch_delay,
                incu_loc=incu_locs[index],
                r_loc=r_locs[batch_index],
                lid_loc=lid_locs[batch_index],
                out_loc=out_locs[index],
                batch=batch,
            )]
            index += 1

    for i, p in enumerate(plates):
        for j, q in enumerate(plates):
            if i != j:
                assert p.id != q.id
                assert p.incu_loc != q.incu_loc
                assert p.out_loc not in [q.out_loc, q.r_loc, q.lid_loc, q.incu_loc]
                if p.batch == q.batch:
                    assert p.r_loc != q.r_loc
                    assert p.lid_loc != q.lid_loc

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

