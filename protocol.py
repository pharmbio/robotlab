from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta

from robots import *

@dataclass(frozen=True)
class Event:
    begin: float
    end: float
    plate_id: str | None
    command: Command

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
        robotarm_cmd('wash_get_part1', prep=True),
        wait_for_ready_cmd('wash'),
        robotarm_cmd('wash_get_part2'),
        robotarm_cmd('disp_put'), # todo merge move wash -> disp
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
        *incu_to_wash,
        wash_cmd('', est=90),
        *wash_to_disp,

        # 3 Mitotracker staining
        disp_cmd('peripump 1, mitotracker solution', est=15),
        *disp_to_incu,
        timer_cmd(30, plate_id),
        *incu_to_wash,
        wash_cmd('pump D, PBS', est=90),
        *wash_to_disp,

        # 4 Fixation
        disp_cmd('Syringe A, 4% PFA', est=19),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS', est=90),
        *wash_to_disp,

        # 5 Permeabilization
        disp_cmd('Syringe B, 0.1% Triton X-100 in PBS', est=21),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS', est=90),
        *wash_to_disp,

        # 6 Post-fixation staining
        disp_cmd('peripump 2, staining mixture in PBS', est=22),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS', est=120),

        # park it in RT, move to output hotel when there's time
        *wash_to_RT_incu,

        # 7 Imaging
        *to_output_hotel,
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
            plate_id=None if cmd.is_prep() else plate_id,
            begin=t_begin,
            end=t_end,
        )
        events += [event]
        t = t_end

    return events

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(42)]
Out = list(H)

h21 = 'h21'

incu_locs: list[str] = [f'i{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H]
out_locs:  list[str] = [f'out{i}' for i in Out]
lid_locs:  list[str] = [h for h in h_locs if h != h21]

# out_locs += r_locs

N = 3
D = 210

events = [
    cell_painting(f'p{i}', i * D, incu_loc, lid_loc, r_loc, out_loc)
    for i,                       (incu_loc, lid_loc, r_loc, out_loc) in
              enumerate(list(zip(incu_locs, lid_locs, r_locs, out_locs))[:N])
]

events = sum(events, [])
events = sorted(events, key=lambda e: e.begin)
events = list(events)

pp(events)

def execute(events: list[Event], config: Config) -> None:
    for event in events:
        event.command.execute(config) # some of the execute events are just wait until ready commands

