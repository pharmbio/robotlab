from __future__ import annotations
from typing import *

from scriptparser import movel, movej as movejoint, gripper, section, resolve, parse
import os
import sys
from dataclasses import *
import re

from moves import Move, MoveList

h21_neu = 'h21 neu'
h21_drop_neu = 'h21 drop neu'

programs: dict[str, list[Move]] = {}

# puts h21 on h11
programs[f'h11_put'] = resolve('scripts/dan_lid_21_11.script', [
    gripper('Gripper Move30% (1)'),
    movejoint('h21_neu'),
    movel('h21_pick_neu'),
    section('from_h21_drop', [
        movel('h21_pick'),
        gripper('Gripper Close (1)'),
        movel('h21_pick_neu'),
        movel('h21_neu'),
        movel('h11_neu',                    tag='11/21'),
        movel('h11_drop_up',                tag='11/21'),
        movel('h11_drop',                   tag='11/21'),
        gripper('Gripper Move30% (1)'),
        movel('h11_drop_neu',               tag='11/21'),
        movel('h11_neu',                    tag='11/21'),
        movel('h21_neu'),
    ])
])

# gets h11 and puts it on h21
programs[f'h11_get'] = resolve('scripts/dan_lid_21_11.script', [
    section('to_h21_drop', [
        gripper('Gripper Move30% (1)'),
        movejoint('h21_neu'),
        movel('h11_neu',                    tag='11/21'),
        movel('h11_drop_neu',               tag='11/21'),
        movel('h11_pick',                   tag='11/21'),
        gripper('Gripper Close (1)'),
        movel('h11_drop_neu',               tag='11/21'),
        movel('h11_neu',                    tag='11/21'),
        movel('h21_neu'),
        movel('h21_pick_neu'),
        movel('h21_drop'),
        gripper('Gripper Move30% (1)'),
    ]),
    movel('h21_pick_neu'),
    movel('h21_neu'),
])

programs[f'lid_h19_put'] = resolve('scripts/dan_delid.script', [
    gripper('Gripper Move30% (1)'),
    movejoint('delid_neu'),
    movel('delid_pick_up'),
    section('from_h21_drop', [
        movel('delid_pick'),
        gripper('Gripper Close (1)'),
        movel('delid_pick_up'),
        movel('delid_neu2'),
        movel('lid_neu',                    tag='19/21'),
        movel('lid_drop',                   tag='19/21'),
        gripper('Gripper Move30% (1)'),
        movel('lid_neu2',                   tag='19/21'),
        movel('delid_neu3'),
    ]),
])

programs[f'lid_h19_get'] = resolve('scripts/dan_delid.script', [
    section('to_h21_drop', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu3'),
        movel('lid_neu3',                   tag='19/21'),
        movel('lid_pick',                   tag='19/21'),
        gripper('Gripper Close (1)'),
        movel('lid_pick_up',                tag='19/21'),
        movel('lid_neu4',                   tag='19/21'),
        movel('delid_neu4'),
        movel('delid_drop_up'),
        movel('delid_drop'),
        gripper('Gripper Move30% (1)'),
    ]),
    movel('delid_drop_up2'),
    movel('delid_neu5'),
])

programs[f'r21_put'] = resolve('scripts/dan_h21_r21.script', [
    gripper('Gripper Move30% (1)'),
    movejoint('h21_neu'),
    movel('h21_pick_neu'),
    section('from_h21_drop', [
        movel('h21_pick'),
        gripper('Gripper Close (1)'),
        movel('h21_pick_neu'),
        movel('h21_neu'),
        movel('r21_neu',                    tag='21/21'),
        movel('r21_drop_neu',               tag='21/21'),
        movel('r21_drop',                   tag='21/21'),
        gripper('Gripper Move30% (1)'),
        movel('r21_drop_neu',               tag='21/21'),
        movel('r21_neu',                    tag='21/21'),
        movel('h21_neu'),
    ])
])

programs[f'r21_get'] = resolve('scripts/dan_h21_r21.script', [
    section('to_h21_drop', [
        gripper('Gripper Move30% (1)'),
        movejoint('h21_neu'),
        movel('r21_neu',                    tag='21/21'),
        movel('r21_drop_neu',               tag='21/21'),
        movel('r21_pick',                   tag='21/21'),
        gripper('Gripper Close (1)'),
        movel('r21_drop_neu',               tag='21/21'),
        movel('r21_neu',                    tag='21/21'),
        movel('h21_neu'),
        movel('h21_pick_neu'),
        movel('h21_drop'),
        gripper('Gripper Move30% (1)'),
    ]),
    movel('h21_pick_neu'),
    movel('h21_neu'),
])

programs[f'out21_put'] = resolve('scripts/dan_to_out18.script', [
    gripper('Gripper Move30% (1)'),
    movejoint('h21_neu'),
    movel('h21_pick_neu'),
    section('from_h21_drop', [
        movel('h21_pick'),
        gripper('Gripper Close (1)'),
        movel('h21_pick_neu'),
        movel('h21_neu'),
        movel('out_neu'),
        movel('out_neu',                    tag='21/21'),
        movel('o18_drop_neu',               tag='21/21'),
        movel('o18_drop',                   tag='21/21'),
        gripper('Gripper Move30% (1)'),
        movel('o18_drop_neu',               tag='21/21'),
        movel('out_neu',                    tag='21/21'),
        movel('out_neu'),
        movel('h21_neu'),
    ])
])

programs['incu_put'] = resolve('scripts/dan_incu_to_delid.script', [
    section('part1', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu'),
        movel('delid_pick_abov'),
        section('from_h21_drop', [
            movel('delid_pick'),
            gripper('Gripper Close (1)'),
            movel('delid_pick_abov'),
            movel('delid_neu'),
            movel('incu_neu'),
            movel('incu_pick_above'),
            movel('incu_pick'),
            gripper('Gripper Move30% (1)'),
            movel('incu_pick_above'),
        ]),
    ]),
    section('part2', [
        movel('incu_pick_above'),
        movel('incu_neu'),
        movel('delid_neu'),
    ]),
])

programs['incu_get'] = resolve('scripts/dan_incu_to_delid.script', [
    section('part1', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu'),
        movel('incu_neu'),
        movel('incu_pick_above'),
    ]),
    section('part2', [
        section('to_h21_drop', [
            movel('incu_pick'),
            gripper('Gripper Close (1)'),
            movel('incu_pick_above'),
            movel('incu_neu'),
            movel('delid_neu'),
            movel('delid_drop_abov'),
            movel('delid_drop'),
            gripper('Gripper Move30% (1)'),
        ]),
        movel('delid_drop_abov'),
        movel('delid_neu'),
    ])
])

programs['wash_put'] = resolve('scripts/dan_wash_putget.script', [
    gripper('Gripper Move35% (1)'),
    movejoint('neu_deli'),
    movel('abov_dropoff'),
    section('from_h21_drop', [
        movel('picku'),
        gripper('Gripper Close (1)'),
        movel('abov_dropoff'),
        movel('safe_delid'),
        movejoint('safe_delid'),
        movejoint('above_washr'),
        movel('above_washr',     slow=True),
        movel('near_wash_picku', slow=True),
        movel('dropoff',         slow=True),
        gripper('Gripper Move35% (1)'),
        movel('above_washr',     slow=True),
        movejoint('above_washr'),
        movejoint('safe_delid'),
        movel('safe_delid'),
        movel('neu_deli'),
    ])
])

programs['wash_get'] = resolve('scripts/dan_wash_putget.script', [
    section('part1', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movel('safe_delid'),
        movejoint('safe_delid'),
        movejoint('above_washr'),
        movel('above_washr',     slow=True),
        movel('near_wash_picku', slow=True),
    ]),
    section('part2', [
        section('to_h21_drop', [
            movel('pickup',      slow=True),
            gripper('Gripper Close (1)'),
            movel('above_washr', slow=True),
            movejoint('above_washr'),
            movejoint('safe_delid'),
            movel('safe_delid'),
            movel('neu_deli'),
            movel('abov_dropoff'),
            movel('deli_dropoff'),
            gripper('Gripper Move35% (1)'),
        ]),
        movel('abov_dropoff'),
        movel('neu_deli'),
    ])
])

programs['disp_put'] = resolve('scripts/dan_disp_putget.script', [
    gripper('Gripper Move35% (1)'),
    movejoint('neu_deli'),
    movel('dropoff_above'),
    section('from_h21_drop', [
        movel('delid_pickup'),
        gripper('Gripper Close (1)'),
        movel('abov_delid_pick'),
        movel('neu_deli'),
        movel('above_dis'),
        movel('disp_dropoff'),
        gripper('Gripper Move35% (1)'),
        movel('above_disp2'),
        movel('neu_deli'),
    ]),
])

programs['disp_get'] = resolve('scripts/dan_disp_putget.script', [
    section('part1', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movel('above_dis'),
        movel('disp_pickup',                tag='dz=50'),
    ]),
    section('part2', [
        section('to_h21_drop', [
            movel('disp_pickup'),
            gripper('Gripper Close (1)'),
            movel('above_dis'),
            movel('neu_deli'),
            movel('dropoff_above'),
            movel('delid_dropoff'),
            gripper('Gripper Move33% (1)'),
        ]),
        movel('dropoff_above'),
        movel('neu_deli'),
    ])
])

programs['wash_to_disp'] = resolve('scripts/dan_wash_to_disp.script', [
    section('part1', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movejoint('above_washr'),
        movel('pickup',          slow=True, tag='dz=30'),
    ]),
    section('part2', [
        movel('pickup',          slow=True),
        gripper('Gripper Close (1)'),
        movel('above_washr',     slow=True),
        movejoint('above_washr'),
        movejoint('above_disp2'),
        movel('above_disp2'),
        movel('disp_drop'),
        gripper('Gripper Move35% (1)'),
        movel('above_disp2'),
        movel('neu_deli'),
    ]),
])

def generate_stubs() -> None:
    filenames = dict(
        h19_lid='scripts/dan_delid.script',
        h11='scripts/dan_lid_21_11.script',
        r21='scripts/dan_h21_r21.script',
        out18_put='scripts/dan_to_out18.script',
        incu='scripts/dan_incu_to_delid.script',
        wash='scripts/dan_wash_putget.script',
        disp='scripts/dan_disp_putget.script',
        wash_to_disp='scripts/dan_wash_to_disp.script',
    )

    for short, filename in filenames.items():
        script = parse(filename)
        print()
        print(f'programs[{short!r}] = resolve({filename!r}, [')
        for step in script.steps:
            if isinstance(step, movel):
                con, arg = 'movel', step.name
            elif isinstance(step, movejoint):
                con, arg = 'movejoint', step.name
            elif isinstance(step, gripper):
                con, arg = 'gripper', step.name
            else:
                raise ValueError
            print(f'    {con}({arg!r}),')
        print('])')
        print()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Bridge urscript files and our json format', )
    parser.add_argument('--generate-stubs', '--stubs', action='store_true', help='Generate stubs from urscript files')
    parser.add_argument('--generate-json', '--json', action='store_true', help='Generate json from stubs in this file')
    args = parser.parse_args()

    if args.generate_stubs:
        generate_stubs()
    elif args.generate_json:
        for name, movelist in programs.items():
            filename = f'./movelists/{name}.json'

            def apply_dz_tags(ml: MoveList) -> MoveList:
                '''
                This is a jig and can be removed when the json movelists are the
                source of truth
                '''
                dzs: dict[str, float] = {}
                for tag in ml.tags():
                    if tag.startswith('dz='):
                        dzs[tag] = float(tag[len('dz='):])
                res: MoveList = ml
                for tag, dz in dzs.items():
                    res = res.adjust_tagged(tag, dz=dz)
                return res

            ml = MoveList(movelist)
            ml = apply_dz_tags(ml).normalize()
            ml.write_json(filename)
    else:
        parser.print_help()
