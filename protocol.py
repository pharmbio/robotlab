
from robots import *
from moves import *
from controller import *

# Cell Painting Workflow
protocol: list[ProtocolStep] = [
    # 2 Compound treatment: Remove (80%) media of all wells
    wash(''),

    # 3 Mitotracker staining
    disp('peripump 1, mitotracker solution'),
    # RT_incu(minutes(20)),
    incu(minutes(30)),
    wash('pump D, PBS'),

    # 4 Fixation
    disp('Syringe A, 4% PFA'),
    RT_incu(minutes(20)),
    wash('pump D, PBS'),

    # 5 Permeabilization
    disp('Syringe B, 0.1% Triton X-100 in PBS'),
    RT_incu(minutes(20)),
    wash('pump D, PBS'),

    # 6 Post-fixation staining
    disp('peripump 2, staining mixture in PBS'),
    RT_incu(minutes(20)),
    wash('pump D, PBS'),

    # 7 Imaging
    to_output_hotel(),
]


p0: list[Plate] = [
    Plate('Ada', incu_locs[0], queue=protocol),
    Plate('Bob', incu_locs[1], queue=protocol),
    Plate('Cal', incu_locs[2], queue=protocol),
    Plate('Deb', incu_locs[3], queue=protocol),
    Plate('Eve', incu_locs[4], queue=protocol),
    Plate('Fei', incu_locs[5], queue=protocol),
    Plate('Gil', incu_locs[6], queue=protocol),
    Plate('Hal', incu_locs[7], queue=protocol),
    Plate('Ivy', incu_locs[8], queue=protocol),
    Plate('Joe', incu_locs[9], queue=protocol),
    Plate('Ad2', incu_locs[10], queue=protocol),
    Plate('Bo2', incu_locs[11], queue=protocol),
    Plate('Ca2', incu_locs[12], queue=protocol),
    Plate('De2', incu_locs[13], queue=protocol),
    Plate('Ev2', incu_locs[14], queue=protocol),
    Plate('Fe2', incu_locs[15], queue=protocol),
    Plate('Gi2', incu_locs[16], queue=protocol),
    Plate('Ha2', incu_locs[17], queue=protocol),
    Plate('Iv2', incu_locs[18], queue=protocol),
    Plate('Jo2', incu_locs[19], queue=protocol),
    Plate('Ad3', incu_locs[20], queue=protocol),
    Plate('Bo3', incu_locs[21], queue=protocol),
    Plate('Ca3', incu_locs[22], queue=protocol),
    Plate('De3', incu_locs[23], queue=protocol),
    Plate('Ev3', incu_locs[24], queue=protocol),
    Plate('Fe3', incu_locs[25], queue=protocol),
    Plate('Gi3', incu_locs[26], queue=protocol),
    Plate('Ha3', incu_locs[27], queue=protocol),
    Plate('Iv3', incu_locs[28], queue=protocol),
    Plate('Jo3', incu_locs[29], queue=protocol),
][:len(out_locs)][:13]

w0 = World(dict({p.id: p for p in p0}))

execute(w0, dry_run)
