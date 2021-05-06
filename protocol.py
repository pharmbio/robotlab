from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta

from robots import *
from utils import show

import re

import textwrap

A = TypeVar('A')
def concat(xss: list[list[A]]) -> list[A]:
    return sum(xss, [])

@dataclass(frozen=False)
class Mutable(Generic[A]):
    value: A

@dataclass(frozen=True)
class Event:
    begin: float
    end: float
    plate_id: str | None
    command: Command
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

def skip(n, xs):
    for i, x in enumerate(xs):
        if i >= n:
            yield x

def sleek_h21_movements(events: list[Event]) -> None:
    out = [*events]

    for i, event in enumerate(events):
        if isinstance(event.command, robotarm_cmd):
            for j, next in skip(i+1, enumerate(events)):
                if isinstance(next.command, robotarm_cmd):
                    a = event.command.program_name
                    b = next.command.program_name
                    a += '_to_h21_drop'
                    b += '_from_h21_drop'
                    if a in programs and b in programs:
                        out[i] = replace(event, command=replace(event.command, program_name=a))
                        out[j] = replace(event, command=replace(event.command, program_name=b))
                    break

    return out

def cell_painting(plate_id: str, initial_wait_seconds: float, incu_loc: str, lid_loc: str, r_loc: str, out_loc: str) -> list[Event]:
    incu_to_wash = [
        robotarm_cmd('incu_get_part1', prep=True),
        wait_for_timer_cmd(plate_id),
        incu_cmd('get', incu_loc, est=10),
        wait_for_ready_cmd('incu'),
        robotarm_cmd('incu_get_part2'),
        robotarm_cmd(f'lid_{lid_loc}_put'),
        robotarm_cmd('wash_put'),
    ]

    wash_to_disp = [
        robotarm_cmd('wash_to_disp_part1', prep=True),
        wait_for_ready_cmd('wash'),
        robotarm_cmd('wash_to_disp_part2'),
    ]

    disp_get = [
        robotarm_cmd('disp_get_part1', prep=True),
        wait_for_ready_cmd('disp'),
        robotarm_cmd('disp_get_part2'),
    ]

    disp_to_incu = [
        *disp_get,
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd('incu_put_part1'),
        incu_cmd('put', incu_loc, est=0), # should be in 37°C within a second or so
        robotarm_cmd('incu_put_part2'),
        wait_for_ready_cmd('incu'), # make sure incu is finished to be on the safe side
    ]

    disp_to_RT_incu = [
        *disp_get,
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd(f'{r_loc}_put'),
    ]

    RT_incu_to_wash = [
        wait_for_timer_cmd(plate_id),
        robotarm_cmd(f'{r_loc}_get'),
        robotarm_cmd(f'lid_{lid_loc}_put'),
        robotarm_cmd('wash_put'),
    ]

    wash_to_RT_incu = [
        robotarm_cmd('wash_get_part1', prep=True),
        wait_for_ready_cmd('wash'),
        robotarm_cmd('wash_get_part2'),
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd(f'{r_loc}_put'),
    ]

    to_output_hotel = [
        robotarm_cmd(f'{r_loc}_get'),
        robotarm_cmd(f'{out_loc}_put'), # postponable=True
    ]

    cmds = [
        # 2 Compound treatment
        timer_cmd(initial_wait_seconds / 60.0, plate_id),

        # 3 Mitotracker staining
        *incu_to_wash,
        wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=90),
        *wash_to_disp,
        disp_cmd('automation/1_D_P1_30ul_mito.LHC', est=15),
        *disp_to_incu,
        timer_cmd(30, plate_id),

        # 4 Fixation
        *incu_to_wash,
        wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=90),
        *wash_to_disp,
        disp_cmd('automation/3_D_SA_384_50ul_PFA.LHC', est=19),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),

        # 5 Permeabilization
        *RT_incu_to_wash,
        wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=90),
        *wash_to_disp,
        disp_cmd('automation/5_D_SB_384_50ul_TRITON.LHC', est=21),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),

        # 6 Post-fixation staining
        *RT_incu_to_wash,
        wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=90),
        *wash_to_disp,
        disp_cmd('automation/7_D_P2_20ul_STAINS.LHC', est=22),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),

        # Last wash
        *RT_incu_to_wash,
        wash_cmd('automation/8_W-4X_NoFinalAspirate.LHC', est=120),

        # park it in RT, move to output hotel when there's time
        *wash_to_RT_incu,

        # # 7 Imaging
        # *to_output_hotel,
    ]

    t = 0.0
    events: list[Event] = []
    for cmd in cmds:
        est = cmd.time_estimate()
        t_begin = t
        t_end = t + est
        if cmd.is_prep():
            t_begin -= est
            t_end -= est
        event = Event(
            command=cmd,
            plate_id=plate_id, # (f'{plate_id}') if cmd.is_prep() else plate_id,
            begin=t_begin,
            end=t_end,
        )
        events += [event]
        t = t_end

    return events

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(22)]
Out = list(H)

h21 = 'h21'

incu_locs: list[str] = [f'L{i}' for i in I] + [f'R{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H]
out_locs:  list[str] = [f'out{i}' for i in Out]
lid_locs:  list[str] = [h for h in h_locs if h != h21]

# out_locs += r_locs

def cell_paint_smallest_delay(plates: int, offset: int=60) -> int:
    for delay in range(400):
        events = cell_paint_many(plates, delay, offset)
        if not any(e.overlap.value for e in events):
            return delay
    return delay

def cell_paint_many(plates: int, delay: int | Literal['auto'], offset: int=60) -> list[Event]:

    if delay == 'auto':
        delay = cell_paint_smallest_delay(plates, offset)

    N = plates
    D = delay
    O = 60

    events = concat([
        cell_painting(
            f'p{i}', O + i * D,
            incu_locs[i], lid_locs[i], r_locs[i], r_locs[i]
        )
        for i in range(N)
    ])

    events = sorted(events, key=lambda e: e.end)
    events = list(events)

    calculate_overlap(events)

    return events

