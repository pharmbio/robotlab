
from math import pi, sqrt

import ast

import re

def coord_str(value, pq):
    out = []
    for i, v in enumerate(value):
        if i in [0, 1, 2] and pq == 'p':
            # v = v * 1000
            # v = round(v, 1)
            # out += [f'{v:6}mm']
            v = v * 100
            v = int(round(v, 0))
            out += [f'{v:3}cm']
            # out += [f'{v}cm']
        else:
            v = v * 180 / pi
            v = round(v, 1)
            out += [f'{v:6}°']
    return '(' + ', '.join(out) + ')'

ps = {}
qs = {}

from glob import glob

filenames = dict(
    L='programs/dan_delid.script',
    H='programs/dan_lid_21_11.script',
    I='programs/dan_incu_to_delid.script',
    W='programs/dan_wash_putget.script',
    D='programs/dan_disp_putget.script',
)

for script, filename in filenames.items():
    program = open(filename).readlines()
    for line in program:
        # print(line)
        if m := re.match(' *global *(\w*)_(p|q) *= *p?(.*)$', line):
            name, pq, value = m.groups()
            value = ast.literal_eval(value)
            # print(coord_str(value, pq), name)
            if pq == 'p':
                ps[script+'.'+name] = value
            if pq == 'q':
                qs[script+'.'+name] = value

for k in sorted(ps.keys() | qs.keys()):
    print(f'{k:>30}:', coord_str(ps[k], 'p'), coord_str(qs[k], 'q'))

print()

D = {}

for iter in [0, 1]:
    for k, v in ps.items():
        x, y, z, *rot = v
        # by entrance
        # xs = 2/sqrt(5)*x - 2/sqrt(5)*y
        # ys = 1/sqrt(5)*x + 1/sqrt(5)*y + z

        # from camera
        # xs = 2/sqrt(5)*x + 2/sqrt(5)*y
        # ys = - 1/sqrt(5)*x + 1/sqrt(5)*y + z

        # in wall
        # xs = - 2/sqrt(5)*x + 2/sqrt(5)*y
        # ys = - 1/sqrt(5)*x - 1/sqrt(5)*y + z

        # from operator table, slightly from entrance
        xs = x - y * 0.5
        ys = z

        xs *= 100
        ys *= 60
        xs = round(xs)
        ys = round(ys)
        if iter == 0:
            xs -= 1
            p = (ys, xs)
            c = k[0]
            D[p] = c if D.get(p, c) == c else '*'
        else:
            sk = D.get((ys, xs), 0)
            if isinstance(sk, str):
                sk = 0
            sk += 1
            D[ys, xs] = sk

min_y, min_x = list(D.keys())[0]
for y, x in D.keys():
    min_y = min(y, min_y)
    min_x = min(x, min_x)
min_x -= 2

E = {}
for y, x in D.keys():
    E[y - min_y, x - min_x] = D[y, x]

max_y, max_x = list(E.keys())[0]
for y, x in E.keys():
    max_y = max(y, max_y)
    max_x = max(x, max_x)

H, W = max_y, max_x

print()
print()
for y in range(H+1):
    for x in range(W+1):
        print(E.get((H-y, x), ' '), end='')
    print()

