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

programs: dict[str, str] = {}

# if programA ends by h21 drop and programB starts with h21 drop then instead run:
#     programA_to_h21_drop
#     programB_from_h21_drop

for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19]:
    dz = (i - 11) / 2 * hotel_dist
    # puts h21 on h{i}
    programs |= resolve(f'h{i}_put', 'scripts/dan_lid_21_11.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('h21_neu'),
        movel('h21_pick_neu'),
        section('from_h21_drop', [
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
    ])

    # gets h{i} and puts it on h21
    programs |= resolve(f'h{i}_get', 'scripts/dan_lid_21_11.script', [
        section('to_h21_drop', [
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
        ]),
        movel('h21_pick_neu'),
        movel('h21_neu'),
    ])

for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19]:
    dz = (i - 19) / 2 * hotel_dist

    programs |= resolve(f'lid_h{i}_put', 'scripts/dan_delid.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu'),
        movel('delid_pick_up'),
        section('from_h21_drop', [
            movel('delid_pick'),
            gripper('Gripper Close (1)'),
            movel('delid_pick_up'),
            movel('delid_neu2'),
            movel('lid_neu', dz=dz),
            movel('lid_drop', dz=dz),
            gripper('Gripper Move30% (1)'),
            movel('lid_neu2', dz=dz),
            movel('delid_neu3'),
        ]),
    ])

    programs |= resolve(f'lid_h{i}_get', 'scripts/dan_delid.script', [
        section('to_h21_drop', [
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
        ]),
        movel('delid_drop_up2'),
        movel('delid_neu5'),
    ])

for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
    dz = (i - 21) / 2 * hotel_dist
    programs |= resolve(f'r{i}_put', 'scripts/dan_h21_r21.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('h21_neu'),
        movel('h21_pick_neu'),
        section('from_h21_drop', [
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
    ])

    programs |= resolve(f'r{i}_get', 'scripts/dan_h21_r21.script', [
        section('to_h21_drop', [
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
        ]),
        movel('h21_pick_neu'),
        movel('h21_neu'),
    ])

for i in [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21]:
    dz = (i - 21) / 2 * hotel_dist
    programs |= resolve(f'out{i}_put', 'scripts/dan_to_out18.script', [
        gripper('Gripper Move30% (1)'),
        movejoint('h21_neu'),
        movel('h21_pick_neu'),
        section('from_h21_drop', [
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
    ])

programs |= resolve('incu_put', 'scripts/dan_incu_to_delid.script', [
    section('part1', [
        gripper('Gripper Move30% (1)'),
        movejoint('delid_neu'),
        movel('delid_pick_abov'),
        section('from_h21_drop', [
            movel('delid_pick'),
            gripper('Gripper Close (1)'),
            movel('delid_pick_abov'),
        ]),
    ]),
    section('part2', [
        movel('delid_neu'),
        movel('incu_neu'),
        movel('incu_pick_above'),
        movel('incu_pick'),
        gripper('Gripper Move30% (1)'),
        movel('incu_pick_above'),
        movel('incu_neu'),
        movel('delid_neu'),
    ]),
])

programs |= resolve('incu_get', 'scripts/dan_incu_to_delid.script', [
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

programs |= resolve('wash_put', 'scripts/dan_wash_putget.script', [
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
])

programs |= resolve('wash_get', 'scripts/dan_wash_putget.script', [
    section('part1', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movel('safe_delid'),
        movejoint('safe_delid'),
        movejoint('above_washr'),
        movel('above_washr'),
        movel('near_wash_picku'),
    ]),
    section('part2', [
        section('to_h21_drop', [
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
        ]),
        movel('abov_dropoff'),
        movel('neu_deli'),
    ])
])

programs |= resolve('disp_put', 'scripts/dan_disp_putget.script', [
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

programs |= resolve('disp_get', 'scripts/dan_disp_putget.script', [
    section('part1', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movel('above_dis'),
        movel('disp_pickup'),
    ]),
    section('part2', [
        section('to_h21_drop', [
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

programs |= resolve('wash_to_disp', 'scripts/dan_wash_to_disp.script', [
    section('part1', [
        gripper('Gripper Move35% (1)'),
        movejoint('neu_deli'),
        movejoint('above_washr'),
        movel('pickup', dz=0.03),
    ]),
    section('part2', [
        movel('pickup'),
        gripper('Gripper Close (1)'),
        movel('above_washr'),
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
        print(f'programs |= resolve({short!r}, {filename!r}, [')
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

import hashlib
import json
from datetime import datetime
from textwrap import dedent

def reindent(s: str) -> str:
    out: list[str] = []
    i = 0
    for line in s.strip().split('\n'):
        line = line.strip()
        if line == 'end' or line.startswith('elif') or line.startswith('else'):
            i -= 2
        if line:
            out += [' ' * i + line]
        if line.endswith(':') and not line.startswith('#'):
            i += 2
    return '\n'.join(out)

def checksum(s: str) -> str:
    hash = hashlib.sha256(s.encode()).hexdigest()
    return hash[:6]

num_bits: index = 10
assert num_bits <= 31
version_program_index = 2**num_bits - 1
assert len(programs) < version_program_index, 'num_bits too small'

def generate_robot_main(with_gripper=True) -> str:
    # The header sets up the env and gripper, it's the same for all scripts
    if with_gripper:
        one_script = parse('scripts/dan_h21_r21.script')
        header = '\n'.join(one_script.subs['header'] + one_script.subs['gripper_init'])
    else:
        header = '''
            def rq_set_pos_spd_for(a, b, c, d):
                return 1
            end
            def rq_go_to(a):
                return 1
            end
            def rq_wait(a):
                return 1
            end
        '''

    contents: str = ''.join(f'''
        elif program_index == {program_index}:
            textmsg("log: exec {program_name} {checksum(program_body)}")
            {program_body}
            textmsg("log: done {program_name} {checksum(program_body)}")
        '''
        for program_index, (program_name, program_body) in enumerate(programs.items())
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hash = checksum(header + contents)
    prog_id = f'{now} {hash}'
    newline = '\n'
    if with_gripper:
        def_name = f'robot_main_{hash}'
    else:
        def_name = f'robot_main_nogripper_{hash}'
    return reindent(f'''
        # newline
        def {def_name}():
            textmsg("log: running {prog_id}")
            {header}
            while True:
                set_flag(31, False)
                textmsg("log: ready")
                while not get_flag(31):
                    sleep(0.02)
                end

                # 2**{num_bits} possible message types
                bits =
                [ {', '.join(f'get_flag({i}){newline}' for i in range(num_bits))}
                ]
                program_index = binary_list_to_integer(bits)

                if program_index == {version_program_index}:
                    textmsg("log: version {prog_id}")
                {contents}
                else:
                    textmsg("log: unknown program_index=", program_index)
                end
            end
        end
        # newline
    ''')

def generate_robot_send(program_name: str) -> str:
    if program_name == 'version':
        program_index = version_program_index
        program_hash = ''
    else:
        for program_index, (name, program_body) in enumerate(programs.items()):
            if name == program_name:
                program_hash = checksum(program_body)
                break
        else:
            raise ValueError(f'Unknown program: {program_name} in {list(programs.keys())}')
    newline = '\n'
    return reindent(f'''
        # newline
        sec robot_send_{program_index}():
            if get_flag(31):
                textmsg("log: error already busy")
            else:
                bits = integer_to_binary_list({program_index})
                {newline.join(f'set_flag({i}, bits[{i}])' for i in range(num_bits))}
                set_flag(31, True)
                textmsg("log: sent {program_name} {program_hash}")
            end
        end
        # newline
    ''')

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
        open('./generated/robot_main', 'w').write(generate_robot_main())
        open('./generated/robot_main_nogripper', 'w').write(generate_robot_main(with_gripper=False))
        open('./generated/robot_send_version', 'w').write(generate_robot_send('version'))

        # pp(list(enumerate(programs.keys())))

