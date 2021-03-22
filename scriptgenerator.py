from scriptparser import resolve, parse
from utils import dotdict

def movel(name, **kws):
    return dotdict(type='movel', name=name, **kws)

def movej(name, **kws):
    return dotdict(type='movel', name=name, **kws)

def gripper(name):
    return dotdict(type='gripper', name=name)

p = {}

p['delid'] = resolve('scripts/dan_delid.script', [
    gripper('Gripper Move30% (1)'),
    movel('delid_neu'),
    movel('delid_pick'),
    gripper('Gripper Close (1)'),
    movel('delid_pick_up'),
    movel('delid_neu2'),
    movel('lid_neu'),
    movel('lid_drop'),
    gripper('Gripper Move30% (1)'),
    movel('lid_neu2'),
    movel('delid_neu3'),
    movel('lid_neu3'),
    movel('lid_pick'),
    gripper('Gripper Close (1)'),
    movel('lid_pick_up'),
    movel('lid_neu4'),
    movel('delid_neu4'),
    movel('delid_drop_up'),
    movel('delid_drop'),
    gripper('Gripper Move30% (1)'),
    movel('delid_drop_up2'),
    movel('delid_neu5'),
])

for i in [1, 3, 5, 7, 9, 11, 13, 15, 19]:
    dz = (i - 11) * 0.07094
    # puts h21 on h{i}
    p[f'h{i}_put'] = resolve('scripts/dan_lid_21_11.script', [
        gripper('Gripper Move30% (1)'),
        movel('h21_neu'),
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
    p['h{i}_get'] = resolve('scripts/dan_lid_21_11.script', [
        gripper('Gripper Move30% (1)'),
        movel('h21_neu'),
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

p['h11'] = resolve('scripts/dan_lid_21_11.script', [
    gripper('Gripper Move30% (1)'),
    movel('h21_neu'),
    movel('h21_pick_neu'),
    movel('h21_pick'),
    gripper('Gripper Close (1)'),
    movel('h21_pick_neu'),
    movel('h21_neu'),
    movel('h11_neu'),
    movel('h11_drop_up'),
    movel('h11_drop'),
    gripper('Gripper Move30% (1)'),
    movel('h11_drop_neu'),
    movel('h11_neu'),
    movel('h11_drop_neu'),
    movel('h11_pick'),
    gripper('Gripper Close (1)'),
    movel('h11_drop_neu'),
    movel('h11_neu'),
    movel('h21_neu'),
    movel('h21_pick_neu'),
    movel('h21_drop'),
    gripper('Gripper Move30% (1)'),
    movel('h21_pick_neu'),
    movel('h21_neu'),
])


p['incu'] = resolve('scripts/dan_incu_to_delid.script', [
    gripper('Gripper Move30% (1)'),
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
])


p['wash'] = resolve('scripts/dan_wash_putget.script', [
    gripper('Gripper Move35% (1)'),
    movel('above_washr'),
    movel('near_wash_picku'),
    movel('pickup'),
    gripper('Gripper Close (1)'),
    movel('above_washr'),
    movej('above_washr'),
    movej('safe_delid'),
    movel('safe_delid'),
    movel('neu_deli'),
    movel('abov_dropoff'),
    movel('deli_dropoff'),
    gripper('Gripper Move35% (1)'),
    movel('abov_dropoff'),
    movel('picku'),
    gripper('Gripper Close (1)'),
    movel('abov_dropoff'),
    movel('safe_delid'),
    movej('safe_delid'),
    movej('above_washr'),
    movel('above_washr'),
    movel('near_wash_picku'),
    movel('dropoff'),
    gripper('Gripper Move35% (1)'),
    movel('above_washr'),
])


p['disp'] = resolve('scripts/dan_disp_putget.script', [
    movel('above_dis'),
    gripper('Gripper Move35% (1)'),
    movel('disp_pickup'),
    gripper('Gripper Close (1)'),
    movel('above_dis'),
    movel('neu_deli'),
    movel('dropoff_above'),
    movel('delid_dropoff'),
    gripper('Gripper Move33% (1)'),
    movel('dropoff_above'),
    movel('delid_pickup'),
    gripper('Gripper Close (1)'),
    movel('abov_delid_pick'),
    movel('neu_deli'),
    movel('above_dis'),
    movel('disp_dropoff'),
    gripper('Gripper Move35% (1)'),
    movel('above_disp2'),
])

from textwrap import indent

_, _, subs = parse('scripts/dan_delid.script')
header = subs['header']

for name, cmds in p.items():
    if 'h19' in name:
        print(f'def {name}():')
        print(indent('\n'.join(header + cmds), prefix='  '))
        print(f'end')
