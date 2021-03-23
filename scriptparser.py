from utils import show
import snoop
snoop.install(pformat=show)

import ast

import re
from textwrap import dedent

from utils import dotdict
import sys

def parse(filename):
    '''
    The parser extracts and returns a tuple of:
    - cmds: moves and gripper commands,
    - defs: coordinates,
    - subs: dict of extracted gripper subprograms and the header.
    The header sets up the env and gripper.

    The moves are used to generate program stubs which
    are manually rewritten to cut up the program loops to atomic programs.

    The coordinates in these programs are then resolved using the
    parsed coordinates. The gripper commands and the header are
    also resolved using the result from the parser.
    '''
    return parse_lines(list(open(filename, 'r')))

def parse_lines(lines):
    cmds = []
    defs = {}
    subs = {}
    last_header_line = None
    for i, line in enumerate(lines):
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
            for line2 in lines[i+1:]:
                subprogram += [line2[len(indent):].rstrip()]
                if '# end: URCap Program Node' in line2:
                    break
            subs[name] = subprogram
            cmds += [dotdict(type='gripper', name=name)]

    header = lines[1:last_header_line]
    header_indent = re.match(' *', header[0]).end()
    subs['header'] = [line[header_indent:].rstrip() for line in header]

    return cmds, defs, subs

def resolve(filename, moves):
    return resolve_with(parse(filename), moves)

def resolve_with(parse_result, moves):
    cmds, defs, subs = parse_result
    out = []
    for move in moves:
        move = dotdict(move)
        if move.type in ('movel', 'movej'):
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

def test_parse_and_resolve():
    example_script = dedent('''
        def example():
            set_gravity([0.0, 0.0, 9.8])
            # end: URCap Installation Node
            global h21_neu_p=p[.2, -.4, .8, 1.6, -.0, .0]
            global h21_neu_q=[1.6, -1.9, 1.5, 0.4, 1.6, 0.0]
            global above_washr_p=p[-.2, .1, .3, 1.2, -1.2, -1.2]
            global above_washr_q=[-1.6, -2.2, 2.5, -0.3, -0.0, 0.0]
            $ 3 "Gripper Move30% (1)"
            # ...omitted gripper code...
            # end: URCap Program Node
            $ 4 "h21_neu"
            movel(h21_neu_p, a=1.2, v=0.2)
            $ 9 "MoveJ"
            $ 10 "above_washr"
            movej(get_inverse_kin(above_washr_p, qnear=above_washr_q), a=1.3, v=1.0)
        end
    '''.strip())

    lines = example_script.split('\n')

    def test_parse(self):
        cmds, defs, subs = parse(self.lines)

        assert cmds == [
            {'type': 'gripper', 'name': 'Gripper Move30% (1)' },
            {'type': 'movel', 'name': 'h21_neu' },
            {'type': 'movej', 'name': 'above_washr' },
        ]

        assert defs == {
            'h21_neu_p': [0.2, -0.4, 0.8, 1.6, -0.0, 0.0],
            'h21_neu_q': [1.6, -1.9, 1.5, 0.4, 1.6, 0.0],
            'above_washr_p': [-0.2, 0.1, 0.3, 1.2, -1.2, -1.2],
            'above_washr_q': [-1.6, -2.2, 2.5, -0.3, -0.0, 0.0],
        }

        assert subs == {
            'Gripper Move30% (1)': [
                '# Gripper Move30% (1)',
                '# ...omitted gripper code...',
                '# end: URCap Program Node',
            ],
            'header': ['set_gravity([0.0, 0.0, 9.8])'],
        }

    def test_resolve(self):

        moves = [
            {'type': 'gripper', 'name': 'Gripper Move30% (1)' },
            {'type': 'movel', 'name': 'h21_neu' },
            {'type': 'movel', 'name': 'h21_neu', 'dy': -0.3 },
            {'type': 'movej', 'name': 'above_washr' },
        ]

        resolved = resolve_with(parse(self.lines), moves)
        resolved = '\n'.join(resolved)

        assert resolved == dedent('''
            # Gripper Move30% (1)
            # ...omitted gripper code...
            # end: URCap Program Node
            h21_neu_p = p[0.2, -0.4, 0.8, 1.6, -0.0, 0.0]
            movel(h21_neu_p, a=1.2, v=0.25)
            h21_neu_p = p[0.2, -0.4, 0.8, 1.6, -0.0, 0.0]
            h21_neu_p[1] = h21_neu_p[1] + -0.3
            movel(h21_neu_p, a=1.2, v=0.25)
            above_washr_p = p[-0.2, 0.1, 0.3, 1.2, -1.2, -1.2]
            above_washr_q = [-1.6, -2.2, 2.5, -0.3, -0.0, 0.0]
            movej(get_inverse_kin(above_washr_p, qnear=above_washr_q), a=1.4, v=1.05)
        ''').strip()

    if '-v' in sys.argv:
        print(__file__, 'passed tests')

test_parse_and_resolve()

