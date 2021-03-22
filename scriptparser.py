from utils import show
import snoop
snoop.install(pformat=show)

from math import pi, sqrt

import ast

import re
from textwrap import dedent

from utils import dotdict

def parse(filename):
    program = open(filename).readlines()
    cmds = []
    defs = {}
    subs = {}
    for i, line in enumerate(program):
        if 'end: URCap Installation Node' in line:
            last_header_line = i
        if m := re.match(' *global *(\w*) *= *p?(.*)$', line):
            name, value = m.groups()
            try:
                value = ast.literal_eval(value)
                defs[name] = value
            except:
                pass
        elif m := re.match(' *(move[lj]).*?(\w*)_[pq]', line):
            type, name = m.groups()
            cmds += [dotdict(type=type, name=name)]
            # print(
        elif m := re.match('( *)\$ \d* "(Gripper.*)"', line):
            indent, name = m.groups()
            subprogram = ['# ' + name]
            for line2 in program[i+1:]:
                subprogram += [line2[len(indent):].rstrip()]
                if '# end: URCap Program Node' in line2:
                    break
            subs[name] = subprogram
            cmds += [dotdict(type='gripper', name=name)]

    header = program[1:last_header_line]
    header_indent = re.match(' *', header[0]).end()
    subs['header'] = [line[header_indent:].rstrip() for line in header]

    return cmds, defs, subs

def resolve(filename, moves):
    cmds, defs, subs = parse(filename)
    out = []
    for move in moves:
        if move.type in {'movel', 'movej'}:
            q_name = move.name + '_q'
            p_name = move.name + '_p'
            out += [
                f'{p_name} = p{defs[p_name]}',
            ]
            for i, d_name in enumerate('dx dy dz'.split()):
                if d_name in move:
                    out += [
                        f'{p_name}[{i}] = {p_name}[{i}] + {move[d_name]}'
                    ]
            if move.type == 'movel':
                out += [
                    f'movel({p_name}, a=1.2, v=0.25)'
                ]
            elif move.type == 'movej':
                out += [
                    f'{q_name} = {defs[q_name]}',
                    f'movej(get_inverse_kin({p_name}, qnear={q_name}), a=1.4, v=1.05)',
                ]
        elif move.type == 'gripper':
            out += subs[move.name]
    return out

def generate_scriptgenerator_stub():
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
        cmds, defs, subs = parse(filename)
        print(f'\np[{short!r}] = resolve({filename!r}, [')
        for cmd in cmds:
            print(f'    {cmd.type}({cmd.name!r}),')
        print('])\n')

if __name__ == '__main__':
    generate_scriptgenerator_stub()


