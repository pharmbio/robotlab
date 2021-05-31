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
    events = sleek_put_get_movements(events)
    events = sleek_h21_movements(events)
    return events

def sleek_h21_movements(events: list[Event]) -> list[Event]:
    '''
    if programA ends by h21 drop and programB starts with h21 drop then instead run:
        programA_to_h21_drop
        programB_from_h21_drop
    '''

    out = [*events]

    for i, event in enumerate(events):
        if isinstance(event.command, robots.robotarm_cmd):
            for j, next in utils.skip(i+1, enumerate(events)):
                if isinstance(next.command, robots.robotarm_cmd):
                    a = event.command.program_name
                    b = next.command.program_name
                    a += '_to_h21_drop'
                    b += '_from_h21_drop'
                    if a in movelists and b in movelists:
                        out[i] = replace(event, command=replace(event.command, program_name=a))
                        out[j] = replace(event, command=replace(event.command, program_name=b))
                    break

    return out

def sleek_put_get_movements(events: list[Event]) -> list[Event]:
    '''
    don't go back to h21 when working by washer and dispenser if not needed
    '''

    out = [*events]

    to_remove: set[int] = set()

    for i, event in enumerate(events):
        if isinstance(event.command, robots.robotarm_cmd):
            if i in to_remove:
                continue
            for j, next in utils.skip(i+1, enumerate(events)):
                if isinstance(next.command, robots.robotarm_cmd):
                    a = event.command.program_name
                    b = next.command.program_name
                    if [a, b] == ['wash_put_part2', 'wash_get_part1']:
                        to_remove |= {i, j}
                    if [a, b] == ['wash_put_part2', 'wash_to_disp_part1/3']:
                        to_remove |= {i, j}
                    if [a, b] == ['wash_to_disp_part3/3', 'disp_get_part1']:
                        to_remove |= {i, j}
                    break

    out = [
        event
        for i, event in enumerate(events)
        if i not in to_remove
    ]

    return out


def cell_painting(plate_id: str, initial_wait_seconds: float, incu_loc: str, lid_loc: str, r_loc: str, out_loc: str) -> list[Event]:
    incu_to_wash_part1 = [
        robots.wait_for_timer_cmd(plate_id),
        par(
            robots.incu_cmd('get', incu_loc, est=10),
            robots.robotarm_cmd('incu_get_part1'),
        ),
        robots.wait_for_ready_cmd('incu'),
        robots.robotarm_cmd('incu_get_part2'),
        robots.robotarm_cmd(f'lid_{lid_loc}_put'),
        robots.robotarm_cmd('wash_put_part1'),
    ]

    wash_to_disp = [
        robots.robotarm_cmd('wash_to_disp_part1/3', prep=True),
        robots.wait_for_ready_cmd('wash'),
        robots.robotarm_cmd('wash_to_disp_part2/3'),
    ]

    disp_get = [
        robots.robotarm_cmd('disp_get_part1', prep=True),
        robots.wait_for_ready_cmd('disp'),
        robots.robotarm_cmd('disp_get_part2'),
    ]

    disp_to_incu = [
        *disp_get,
        robots.robotarm_cmd(f'lid_{lid_loc}_get'),
        robots.robotarm_cmd('incu_put_part1'),
        robots.incu_cmd('put', incu_loc, est=0),
        robots.robotarm_cmd('incu_put_part2'),
        robots.wait_for_ready_cmd('incu'),
    ]

    disp_to_RT_incu = [
        *disp_get,
        robots.robotarm_cmd(f'lid_{lid_loc}_get'),
        robots.robotarm_cmd(f'{r_loc}_put'),
    ]

    RT_incu_to_wash_part1 = [
        robots.wait_for_timer_cmd(plate_id),
        robots.robotarm_cmd(f'{r_loc}_get'),
        robots.robotarm_cmd(f'lid_{lid_loc}_put'),
        robots.robotarm_cmd('wash_put_part1'),
    ]

    wash_to_RT_incu = [
        robots.robotarm_cmd('wash_get_part1', prep=True),
        robots.wait_for_ready_cmd('wash'),
        robots.robotarm_cmd('wash_get_part2'),
        robots.robotarm_cmd(f'lid_{lid_loc}_get'),
        robots.robotarm_cmd(f'{r_loc}_put'),
    ]

    wash_to_out = [
        robots.robotarm_cmd('wash_get_part1', prep=True),
        robots.wait_for_ready_cmd('wash'),
        robots.robotarm_cmd('wash_get_part2'),
        robots.robotarm_cmd(f'lid_{lid_loc}_get'),
        robots.robotarm_cmd(f'{out_loc}_put'),
    ]

    cmds: list[Command] = [
        # 2 Compound treatment
        robots.timer_cmd(initial_wait_seconds / 60.0, plate_id),

        # 3 Mitotracker staining
        *incu_to_wash_part1,
        par(
            robots.wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=90),
            robots.robotarm_cmd('wash_put_part2'),
        ),
        *wash_to_disp,
        par(
            robots.disp_cmd('automation/1_D_P1_30ul_mito.LHC', est=15),
            robots.robotarm_cmd('wash_to_disp_part3/3'),
        ),
        *disp_to_incu,
        robots.timer_cmd(30, plate_id),

        # 4 Fixation
        *incu_to_wash_part1,
        par(
            robots.wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=90),
            robots.robotarm_cmd('wash_put_part2'),
        ),
        *wash_to_disp,
        par(
            robots.disp_cmd('automation/3_D_SA_384_50ul_PFA.LHC', est=19),
            robots.robotarm_cmd('wash_to_disp_part3/3'),
        ),
        *disp_to_RT_incu,
        robots.timer_cmd(20, plate_id),

        # 5 Permeabilization
        *RT_incu_to_wash_part1,
        par(
            robots.wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=90),
            robots.robotarm_cmd('wash_put_part2'),
        ),
        *wash_to_disp,
        par(
            robots.disp_cmd('automation/5_D_SB_384_50ul_TRITON.LHC', est=21),
            robots.robotarm_cmd('wash_to_disp_part3/3'),
        ),
        *disp_to_RT_incu,
        robots.timer_cmd(20, plate_id),

        # 6 Post-fixation staining
        *RT_incu_to_wash_part1,
        par(
            robots.wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=90),
            robots.robotarm_cmd('wash_put_part2'),
        ),
        *wash_to_disp,
        par(
            robots.disp_cmd('automation/7_D_P2_20ul_STAINS.LHC', est=22),
            robots.robotarm_cmd('wash_to_disp_part3/3'),
        ),
        *disp_to_RT_incu,
        robots.timer_cmd(20, plate_id),

        # Last wash
        *RT_incu_to_wash_part1,
        par(
            robots.wash_cmd('automation/8_W-4X_NoFinalAspirate.LHC', est=120),
            robots.robotarm_cmd('wash_put_part2'),
        ),

        # move to output hotel now
        *wash_to_out,
    ]

    t = 0.0
    events: list[Event] = []
    for cmd in cmds:
        est = cmd.time_estimate()
        t_begin: float = t
        t_ends: list[float] = []
        sub_cmds: list[Command] = cmd.sub_cmds() if isinstance(cmd, robots.par) else [cmd]
        for sub_cmd in sub_cmds:
            if sub_cmd.is_prep():
                my_begin = t_begin - sub_cmd.time_estimate()
            else:
                my_begin = t_begin
            event = Event(
                command=sub_cmd,
                plate_id=plate_id, # (f'{plate_id}') if cmd.is_prep() else plate_id,
                begin=my_begin,
                end=my_begin + sub_cmd.time_estimate(),
            )
            events += [event]
            t_ends += [event.end]
        t = max(t_ends)

    return events

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(22)]
Out = list(reversed(H))

h21 = 'h21'

incu_locs: list[str] = [f'L{i}' for i in I] + [f'R{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H]
out_locs:  list[str] = [f'out{i}' for i in Out]
lid_locs:  list[str] = [h for h in h_locs if h != h21]

def cell_paint_get_smallest_delay(plates: int, offset: int=60) -> int:
    for delay in range(400):
        events = cell_paint_many(plates, delay, offset)
        if not any(e.overlap.value for e in events):
            return delay
    return 400

def cell_paint_many(num_plates: int, delay: int | Literal['auto'], offset: int=60) -> list[Event]:

    if delay == 'auto':
        delay = cell_paint_get_smallest_delay(num_plates, offset)

    events = utils.flatten([
        cell_painting(
            f'p{i}', offset + i * delay,
            incu_locs[i], lid_locs[i], r_locs[i], out_locs[i]
        )
        for i in range(num_plates)
    ])

    events = sorted(events, key=lambda e: e.end)
    events = list(events)

    calculate_overlap(events)

    return events

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

def main(num_plates: int, config: Config) -> None:
    events = protocol.cell_paint_many(num_plates, delay='auto')
    events = protocol.sleek_movements(events)
    execute(events, config)
