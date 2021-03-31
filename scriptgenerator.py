from __future__ import annotations
from typing import *

from scriptparser import *
import os
import sys
from dataclasses import *

movejoint = movej

hotel_dist: float = 7.094 / 100

def programs(gripper: Callable[[str], ScriptStep]=gripper) -> dict[str, list[str]]:
    p: dict[str, list[str]] = {}

    for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19]:
        dz = (i - 11) / 2 * hotel_dist
        # puts h21 on h{i}
        p[f'h{i}_put'] = resolve('scripts/dan_lid_21_11.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('h21_neu'),
            movel('h21_pick_neu'),
            movel('h21_pick'),
            gripper('Gripper Close (1)'),
            movel('h21_pick_neu'),
            movel('h21_neu'),
            movel('h11_neu', dz=dz),
            movel('h11_drop_up', dz=dz),
            movel('h11_drop', dz=dz),
            gripper('Gripper Move30% (1)'),
            movel('h11_drop_neu', dz=dz),
            movel('h11_neu', dz=dz),
            movel('h21_neu'),
        ])

        # gets h{i} and puts it on h21
        p[f'h{i}_get'] = resolve('scripts/dan_lid_21_11.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('h21_neu'),
            movel('h11_neu', dz=dz),
            movel('h11_drop_neu', dz=dz),
            movel('h11_pick', dz=dz),
            gripper('Gripper Close (1)'),
            movel('h11_drop_neu', dz=dz),
            movel('h11_neu', dz=dz),
            movel('h21_neu'),
            movel('h21_pick_neu'),
            movel('h21_drop'),
            gripper('Gripper Move30% (1)'),
            movel('h21_pick_neu'),
            movel('h21_neu'),
        ])

    for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19]:
        dz = (i - 19) / 2 * hotel_dist

        p[f'lid_h{i}_put'] = resolve('scripts/dan_delid.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('delid_neu'),
            movel('delid_pick'),
            gripper('Gripper Close (1)'),
            movel('delid_pick_up'),
            movel('delid_neu2'),
            movel('lid_neu', dz=dz),
            movel('lid_drop', dz=dz),
            gripper('Gripper Move30% (1)'),
            movel('lid_neu2', dz=dz),
            movel('delid_neu3'),
        ])

        p[f'lid_h{i}_get'] = resolve('scripts/dan_delid.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('delid_neu3'),
            movel('lid_neu3', dz=dz),
            movel('lid_pick', dz=dz),
            gripper('Gripper Close (1)'),
            movel('lid_pick_up', dz=dz),
            movel('lid_neu4', dz=dz),
            movel('delid_neu4'),
            movel('delid_drop_up'),
            movel('delid_drop'),
            gripper('Gripper Move30% (1)'),
            movel('delid_drop_up2'),
            movel('delid_neu5'),
        ])

    for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
        dz = (i - 21) / 2 * hotel_dist
        p[f'r{i}_put'] = resolve('scripts/dan_h21_r21.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('h21_neu'),
            movel('h21_pick_neu'),
            movel('h21_pick'),
            gripper('Gripper Close (1)'),
            movel('h21_pick_neu'),
            movel('h21_neu'),
            movel('r21_neu', dz=dz),
            movel('r21_drop_neu', dz=dz),
            movel('r21_drop', dz=dz),
            gripper('Gripper Move30% (1)'),
            movel('r21_drop_neu', dz=dz),
            movel('r21_neu', dz=dz),
            movel('h21_neu'),
        ])

        p[f'r{i}_get'] = resolve('scripts/dan_h21_r21.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('h21_neu'),
            movel('r21_neu', dz=dz),
            movel('r21_drop_neu', dz=dz),
            movel('r21_pick', dz=dz),
            gripper('Gripper Close (1)'),
            movel('r21_drop_neu', dz=dz),
            movel('r21_neu', dz=dz),
            movel('h21_neu'),
            movel('h21_pick_neu'),
            movel('h21_drop'),
            gripper('Gripper Move30% (1)'),
            movel('h21_pick_neu'),
            movel('h21_neu'),
        ])

    for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
        dz = (i - 21) / 2 * hotel_dist
        p[f'out{i}_put'] = resolve('scripts/dan_to_out18.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('h21_neu'),
            movel('h21_pick_neu'),
            movel('h21_pick'),
            gripper('Gripper Close (1)'),
            movel('h21_pick_neu'),
            movel('h21_neu'),
            movel('out_neu'),
            movel('out_neu', dz=dz),
            movel('o18_drop_neu', dz=dz),
            movel('o18_drop', dz=dz),
            gripper('Gripper Move30% (1)'),
            movel('o18_drop_neu', dz=dz),
            movel('out_neu', dz=dz),
            movel('out_neu'),
            movel('h21_neu'),
        ])

    p['incu_get'] = resolve('scripts/dan_incu_to_delid.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu'),
        movel('incu_neu'),
        movel('incu_pick_above'),
        movel('incu_pick'),
        gripper('Gripper Close (1)'),
        movel('incu_pick_above'),
        movel('incu_neu'),
        movel('delid_neu'),
        movel('delid_drop_abov'),
        movel('delid_drop'),
        gripper('Gripper Move30% (1)'),
        movel('delid_drop_abov'),
        movel('delid_neu'),
    ])

    p['incu_get_part1'] = resolve('scripts/dan_incu_to_delid.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu'),
        movel('incu_neu'),
        movel('incu_pick_above'),
    ])

    p['incu_get_part2'] = resolve('scripts/dan_incu_to_delid.script', [
        movel('incu_pick'),
        gripper('Gripper Close (1)'),
        movel('incu_pick_above'),
        movel('incu_neu'),
        movel('delid_neu'),
        movel('delid_drop_abov'),
        movel('delid_drop'),
        gripper('Gripper Move30% (1)'),
        movel('delid_drop_abov'),
        movel('delid_neu'),
    ])

    p['incu_put'] = resolve('scripts/dan_incu_to_delid.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu'),
        movel('delid_pick_abov'),
        movel('delid_pick'),
        gripper('Gripper Close (1)'),
        movel('delid_pick_abov'),
        movel('delid_neu'),
        movel('incu_neu'),
        movel('incu_pick_above'),
        movel('incu_pick'),
        gripper('Gripper Move30% (1)'),
        movel('incu_pick_above'),
        movel('incu_neu'),
        movel('delid_neu'),
    ])

    p['wash_get'] = resolve('scripts/dan_wash_putget.script', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movel('safe_delid'),
        movejoint('safe_delid'),
        movejoint('above_washr'),
        movel('above_washr'),
        movel('near_wash_picku'),
        movel('pickup'),
        gripper('Gripper Close (1)'),
        movel('above_washr'),
        movejoint('above_washr'),
        movejoint('safe_delid'),
        movel('safe_delid'),
        movel('neu_deli'),
        movel('abov_dropoff'),
        movel('deli_dropoff'),
        gripper('Gripper Move35% (1)'),
        movel('abov_dropoff'),
        movel('neu_deli'),
    ])

    p['wash_put'] = resolve('scripts/dan_wash_putget.script', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movel('abov_dropoff'),
        movel('picku'),
        gripper('Gripper Close (1)'),
        movel('abov_dropoff'),
        movel('safe_delid'),
        movejoint('safe_delid'),
        movejoint('above_washr'),
        movel('above_washr'),
        movel('near_wash_picku'),
        movel('dropoff'),
        gripper('Gripper Move35% (1)'),
        movel('above_washr'),
        movejoint('above_washr'),
        movejoint('safe_delid'),
        movel('safe_delid'),
        movel('neu_deli'),
    ])

    p['disp_get'] = resolve('scripts/dan_disp_putget.script', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movel('above_dis'),
        movel('disp_pickup'),
        gripper('Gripper Close (1)'),
        movel('above_dis'),
        movel('neu_deli'),
        movel('dropoff_above'),
        movel('delid_dropoff'),
        gripper('Gripper Move33% (1)'),
        movel('dropoff_above'),
        movel('neu_deli'),
    ])

    p['disp_put'] = resolve('scripts/dan_disp_putget.script', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movel('dropoff_above'),
        movel('delid_pickup'),
        gripper('Gripper Close (1)'),
        movel('abov_delid_pick'),
        movel('neu_deli'),
        movel('above_dis'),
        movel('disp_dropoff'),
        gripper('Gripper Move35% (1)'),
        movel('above_disp2'),
        movel('neu_deli'),
    ])

    return p

def indent(lines: list[str]) -> list[str]:
    return ['  ' + line for line in lines]

def generate_scripts() -> None:
    # The header sets up the env and gripper, it's the same for all scripts
    header = parse('scripts/dan_h21_r21.script').subs['header']

    class Conf(NamedTuple):
        dirname: str
        gripper: Callable[[str], ScriptStep]
        header: list[str]

    # The gripper is not simulated so also make scripts without gripper commands
    confs: list[Conf] = [
        Conf(dirname='generated', gripper=gripper, header=header),
        Conf(dirname='generated_nogripper', gripper=comment, header=[]),
    ]

    for conf in confs:
        os.makedirs(conf.dirname, exist_ok=True)

        for name, steps in programs(gripper=conf.gripper).items():
            body = [
                *conf.header,
                *steps,
                f'textmsg("Program {name} completed")',
            ]
            prog = [
                f'def {name}():',
                *indent(body),
                'end',
            ]
            path = f'{conf.dirname}/{name}'
            with open(path, 'w') as f:
                print('\n'.join(prog), file=f)
            print(f'generated {path}')

def generate_stubs() -> None:
    filenames = dict(
        h19_lid='scripts/dan_delid.script',
        h11='scripts/dan_lid_21_11.script',
        r21='scripts/dan_h21_r21.script',
        out18_put='scripts/dan_to_out18.script',
        incu='scripts/dan_incu_to_delid.script',
        wash='scripts/dan_wash_putget.script',
        disp='scripts/dan_disp_putget.script',
    )

    for short, filename in filenames.items():
        script = parse(filename)
        print()
        print(f'    p[{short!r}] = resolve({filename!r}, [')
        for step in script.steps:
            if isinstance(step, movel):
                con, arg = 'movel', step.name
            elif isinstance(step, movej):
                con, arg = 'movejoint', step.name
            elif isinstance(step, gripper):
                con, arg = 'gripper', step.name
            else:
                raise ValueError
            print(f'        {con}({arg!r}),')
        print('    ])')
        print()

if __name__ == '__main__':
    if '-h' in sys.argv or '--help' in sys.argv:
        print('''
            --generate-stubs:
                writes stub programs for manual editing to stdout

            (default, no command line option)
                generates new scripts to generated/
        ''')
    elif '--generate-stubs' in sys.argv:
        generate_stubs()
    else:
        generate_scripts()

