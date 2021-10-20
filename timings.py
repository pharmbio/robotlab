from __future__ import annotations
from dataclasses import *
from typing import *

import utils

from collections import defaultdict

Estimated = tuple[Literal['wash', 'disp', 'robotarm', 'incu'], str]
def estimates_from(path: str) -> dict[Estimated, float]:
    ests: dict[Estimated, list[float]] = defaultdict(list)
    sources = {
        'wash',
        'disp',
        'robotarm',
        'incu',
    }
    for v in utils.read_json_lines(path):
        duration = v.get('duration')
        source = v.get('source')
        arg = v.get('arg')
        if duration is not None and source in sources:
            ests[source, arg].append(duration)
    return {est: sum(vs) / len(vs) for est, vs in ests.items()}

Estimates: dict[Estimated, float] = {
    **estimates_from('timings_v3.1.jsonl')
}

overrides: dict[Estimated, float] = {
    ('robotarm', 'noop'): 0.5,
    ('incu', 'get_climate'): 1.1,
    ('disp', 'TestCommunications'): 1.2,
    ('wash', 'TestCommunications'): 1.3,
    # ('robotarm', 'wash_to_disp prep'): 11.7,
    # ('robotarm', 'wash_to_disp return'): 8.5,
    # ('robotarm', 'wash put return'): 8.02,
    # ('robotarm', 'disp get prep'): 4.6,
    # ('robotarm', 'wash get prep'): 11.7,
    # ('robotarm', 'r11 put return'): 2.7,
    # ('robotarm', 'r9 put return'): 2.7,
    ('robotarm', 'r7 put return'): 2.7,
    ('robotarm', 'r5 put return'): 2.7,
    ('robotarm', 'r3 put return'): 2.7,
    # ('robotarm', 'r11 get prep'): 3.0,
    # ('robotarm', 'r9 get prep'): 3.0,
    ('robotarm', 'r7 get prep'): 3.0,
    ('robotarm', 'r5 get prep'): 4.0,
    ('robotarm', 'r3 get prep'): 5.0,
    ('robotarm', 'r1 get prep'): 6.0,
    ('robotarm', 'r1 get transfer'): 6.0,
    # ('robotarm', 'r1 put transfer'): 6.0,
    # ('robotarm', 'r1 put return'): 6.0,
    # ('robotarm', 'out21 put return'): 6.0,
    # ('robotarm', 'out19 put return'): 6.0,
    # ('robotarm', 'out17 put return'): 6.0,
    # ('robotarm', 'out15 put return'): 6.0,
    # ('robotarm', 'out13 put return'): 6.0,
    # ('robotarm', 'out9 put return'): 6.0,
    ('robotarm', 'out1 get prep'): 10.0,
    ('robotarm', 'out1 get transfer'): 10.0,
    # ('disp', 'automation_v3.1/2_D_P1_40ul_mito.LHC'): 31.6,
    # ('disp', 'automation_v3.1/8_D_P2_20ul_stains.LHC'): 21.3,
    # ('disp', 'automation_v3.1/2_D_P1_purge_then_prime.LHC'): 20.0,
    # ('disp', 'automation_v3.1/8_D_P2_purge_then_prime.LHC'): 20.0,
    # ('wash', 'automation_v3.1/3_W-3X_beforeFixation_leaves20ul.LHC'): 112.5 #4X
    ('wash',     'Validate automation_v3.1/9_10_W-3X_NoFinalAspirate.LHC'): 1.2,
    ('wash', 'RunValidated automation_v3.1/9_10_W-3X_NoFinalAspirate.LHC'): 94.0,
}
# utils.pr({k: (Estimates.get(k, None), '->', v) for k, v in overrides.items()})
Estimates.update(overrides)

Guesses: dict[Estimated, float] = {}

def estimate(source: Literal['wash', 'disp', 'robotarm', 'incu'], arg: str) -> float:
    t = (source, arg)
    if t not in Estimates:
        guess = 2.5
        if 'Validate ' in arg:
            guess = 2.5
        elif source == 'wash':
            guess = 100.0
        elif source == 'disp':
            guess = 30.0
        Guesses[t] = Estimates[t] = guess
    return Estimates[t]
