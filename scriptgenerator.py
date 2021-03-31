from __future__ import annotations
from typing import *

from scriptparser import *
import os
import sys
from dataclasses import *

h21_neu = 'h21 neu'
h21_drop_neu = 'h21 drop neu'

movejoint = movej

hotel_dist: float = 7.094 / 100

programs: dict[str, list[ResolvedStep]] = {}

if 1:
    for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19]:
        dz = (i - 11) / 2 * hotel_dist
        # puts h21 on h{i}
        programs[f'h{i}_put'] = resolve('scripts/dan_lid_21_11.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('h21_neu', desc=h21_neu),
            movel('h21_pick_neu', desc=h21_drop_neu),
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
        programs[f'h{i}_get'] = resolve('scripts/dan_lid_21_11.script', [
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
            movel('h21_pick_neu', desc=h21_drop_neu),
            movel('h21_neu', desc=h21_neu),
        ])

    for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19]:
        dz = (i - 19) / 2 * hotel_dist

        programs[f'lid_h{i}_put'] = resolve('scripts/dan_delid.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('delid_neu', desc=h21_neu),
            movel('delid_pick_up', desc=h21_drop_neu),
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

        programs[f'lid_h{i}_get'] = resolve('scripts/dan_delid.script', [
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
            movel('delid_drop_up2', desc=h21_drop_neu),
            movel('delid_neu5', desc=h21_neu),
        ])

    for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
        dz = (i - 21) / 2 * hotel_dist
        programs[f'r{i}_put'] = resolve('scripts/dan_h21_r21.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('h21_neu', desc=h21_neu),
            movel('h21_pick_neu', desc=h21_drop_neu),
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

        programs[f'r{i}_get'] = resolve('scripts/dan_h21_r21.script', [
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
            movel('h21_pick_neu', desc=h21_drop_neu),
            movel('h21_neu', desc=h21_neu),
        ])

    for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
        dz = (i - 21) / 2 * hotel_dist
        programs[f'out{i}_put'] = resolve('scripts/dan_to_out18.script', [
            gripper('Gripper Move30% (1)'),
            movejoint('h21_neu', desc=h21_neu),
            movel('h21_pick_neu', desc=h21_drop_neu),
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

    programs['incu_get'] = resolve('scripts/dan_incu_to_delid.script', [
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
        movel('delid_drop_abov', desc=h21_drop_neu),
        movel('delid_neu', desc=h21_neu),
    ])

    programs['incu_get_part1'] = resolve('scripts/dan_incu_to_delid.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu'),
        movel('incu_neu'),
        movel('incu_pick_above'),
    ])

    programs['incu_get_part2'] = resolve('scripts/dan_incu_to_delid.script', [
        movel('incu_pick'),
        gripper('Gripper Close (1)'),
        movel('incu_pick_above'),
        movel('incu_neu'),
        movel('delid_neu'),
        movel('delid_drop_abov'),
        movel('delid_drop'),
        gripper('Gripper Move30% (1)'),
        movel('delid_drop_abov', desc=h21_drop_neu),
        movel('delid_neu', desc=h21_neu),
    ])

    programs['incu_put'] = resolve('scripts/dan_incu_to_delid.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu', desc=h21_neu),
        movel('delid_pick_abov', desc=h21_drop_neu),
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

    programs['wash_get'] = resolve('scripts/dan_wash_putget.script', [
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
        movel('abov_dropoff', desc=h21_drop_neu),
        movel('neu_deli', desc=h21_neu),
    ])

    programs['wash_put'] = resolve('scripts/dan_wash_putget.script', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli', desc=h21_neu),
        movel('abov_dropoff', desc=h21_drop_neu),
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

    programs['disp_get'] = resolve('scripts/dan_disp_putget.script', [
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
        movel('dropoff_above', desc=h21_drop_neu),
        movel('neu_deli', desc=h21_neu),
    ])

    programs['disp_put'] = resolve('scripts/dan_disp_putget.script', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli', desc=h21_neu),
        movel('dropoff_above', desc=h21_drop_neu),
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

def concat_scripts(A: list[ResolvedStep], B: list[ResolvedStep]) -> list[ResolvedStep]:
    pp(descs(A) + ['+'] + descs(B))
    peep = {h21_neu, h21_drop_neu}
    try:
        y, *ys = B
        if y.desc.startswith('Gripper Move'):
            last_A_gripper = ''
            for a in A:
                if a.desc.startswith('Gripper'):
                    last_A_gripper = a.desc
            if last_A_gripper.startswith('Gripper Move'):
                return concat_scripts(A, ys)
    except ValueError:
        pass
    try:
        *xs, x = A
        y, *ys = B
        if x.desc in peep and x.desc == y.desc:
            return concat_scripts(xs, ys)
    except ValueError:
        pass

    return A + B

# pp(descs(concat_scripts(programs['incu_get_part2'], programs['lid_h19_put'])))

def join_scripts(rss: list[list[ResolvedStep]]) -> list[ResolvedStep]:
    a, *bs = rss
    for b in bs:
        a = concat_scripts(a, b)
    return a

def indent(lines: list[str]) -> list[str]:
    return ['  ' + line for line in lines]

# The header sets up the env and gripper, it's the same for all scripts
header = parse('scripts/dan_h21_r21.script').subs['header']

def assemble_script(steps: list[ResolvedStep], name: str='assembled_script', include_gripper: bool=True) -> str:
    body: list[str] = []

    if include_gripper:
        body += header

    if not include_gripper:
        steps = [ step for step in steps if not step.desc.startswith('Gripper') ]

    body += flatten_resolved(steps)
    body += [
        f'textmsg("Program {name} completed")',
    ]

    prog: list[str] = [
        f'def {name}():',
        *indent(body),
        'end',
    ]
    return '\n'.join(prog)

def generate_scripts() -> None:
    # The gripper is not simulated so also make scripts without gripper commands
    for include_gripper in [True, False]:
        dirname = 'generated' if include_gripper else 'generated_nogripper'
        os.makedirs(dirname, exist_ok=True)

        for name, steps in programs.items():
            path = f'{dirname}/{name}'
            with open(path, 'w') as f:
                print(assemble_script(steps, name, include_gripper), file=f)
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
        print(f'programs[{short!r}] = resolve({filename!r}, [')
        for step in script.steps:
            if isinstance(step, movel):
                con, arg = 'movel', step.name
            elif isinstance(step, movej):
                con, arg = 'movejoint', step.name
            elif isinstance(step, gripper):
                con, arg = 'gripper', step.name
            else:
                raise ValueError
            print(f'    {con}({arg!r}),')
        print('])')
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


