from robots import *
from moves import *
from controller import *

def cell_painting(plate_id, incu_loc, lid_loc, r_loc, out_loc):
    incu_to_wash = [
        robotarm_prep('incu_get_part1')
        incu_cmd('get', incu_loc, est=10),
        robotarm_cmd('incu_get_part2'),
        robotarm_cmd(f'lid_{lid_loc}_put'),
        robotarm_cmd('wash_put'),
    ]

    wash_to_disp = [
        robotarm_prep('wash_get_part1'),
        robotarm_cmd('wash_get_part2'),
        robotarm_cmd('disp_put'), # todo merge move wash -> disp
    ]

    disp_to_incu = [
        robotarm_prep('disp_get_part1'),
        robotarm_cmd('disp_get_part2'),
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd('incu_put_part1'),
        incu_cmd('put', incu_loc), # should be in 37°C within a second or so
    ]

    disp_to_RT_incu = [
        robotarm_prep('disp_get_part1'),
        robotarm_cmd('disp_get_part2'),
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd(f'{r_loc}_put'),
    ]

    RT_incu_to_wash = [
        robotarm_cmd(f'{r_loc}_get'),
        robotarm_cmd(f'lid_{lid_loc}_put'),
        robotarm_cmd('wash_put'),
    ]

    disp_to_RT_incu = [
        robotarm_prep('wash_get_part1'),
        robotarm_cmd('wash_get_part2'),
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd(f'{r_loc}_put'),
    ]

    to_output_hotel = [
        robotarm_cmd(f'{r_loc}_get'),
        robotarm_cmd(f'{out_loc}_get'),
    ]

    cmds = [
        # 2 Compound treatment
        *incu_to_wash,
        wash_cmd('', est=90),
        *wash_to_disp,

        # 3 Mitotracker staining
        disp_cmd('peripump 1, mitotracker solution', est=15),
        *disp_to_incu,
        timer_cmd(minutes(30)),
        *incu_to_wash,
        wash_cmd('pump D, PBS', est=90),
        *wash_to_disp,

        # 4 Fixation
        disp_cmd('Syringe A, 4% PFA', est=19),
        *disp_to_RT_incu,
        timer_cmd(minutes(20))
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS'),
        *wash_to_disp,

        # 5 Permeabilization
        disp_cmd('Syringe B, 0.1% Triton X-100 in PBS', est=21),
        *disp_to_RT_incu,
        timer_cmd(minutes(20))
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS'),
        *wash_to_disp,

        # 6 Post-fixation staining
        disp_cmd('peripump 2, staining mixture in PBS', est=22),
        *disp_to_RT_incu,
        timer_cmd(minutes(20))
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS', est=120),

        # park it in RT, move to output hotel when there's time
        *wash_to_RT_incu,

        # 7 Imaging
        *to_output_hotel,
    ]

    t = 0
    return [
        Event(
            begin=t,
            end=(t := t + cmd.time_estimate())
            cmd=cmd,
            plate_id=plate_id
        )
        for cmd in cmds
    ]

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(42)]
Out = list(H)

h21 = 'h21'

incu_locs: list[str] = [f'i{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H]
out_locs:  list[str] = [f'out{i}' for i in Out]
lid_locs:  list[str] = [h for h in h_locs if h != h21]

out_locs += r_locs

protocols = [
    cell_painting(incu_loc, lid_loc, r_loc, out_loc)
    for           incu_loc, lid_loc, r_loc, out_loc in
         list(zip(incu_locs, lid_locs, r_locs, out_locs))[:6]
]

### todo schedule plan this too

