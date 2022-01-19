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

    ('robotarm', 'lid_B17 get return'): 1.5,

    ('robotarm', 'B1 put transfer'): 7.5,
    ('robotarm', 'B1 put return'):   7.5,
    ('robotarm', 'B3 put transfer'): 7.5,
    ('robotarm', 'B3 put return'):   7.5,

    ('robotarm', 'B3 put return'):   7.5,
    ('robotarm', 'B3 put return'):   7.5,

    ('disp', 'Validate automation_v3.1/2_D_P1_20ul_mito.LHC'): 4.2,
    ('disp', 'RunValidated automation_v3.1/2_D_P1_20ul_mito.LHC'): 24.2,
}
# utils.pr({k: (Estimates.get(k, None), '->', v) for k, v in overrides.items()})
Estimates.update(overrides)

if 0:
    for k, v in list(Estimates.items()):
        if 'Validate ' in str(k).lower():
            v = 0.1
        elif 'test' in str(k).lower():
            v = 0.1
        elif 'arm' in str(k).lower():
            v = 0.1
        elif 'wash' in str(k).lower():
            v = 5.0
        elif 'disp' in str(k).lower():
            v = 1.0
        else:
            v = 0.1
        Estimates[k] = v

Guesses: dict[Estimated, float] = {}

def estimate(source: Literal['wash', 'disp', 'robotarm', 'incu'], arg: str) -> float:
    t = (source, arg)
    if t not in Estimates:
        guess = 2.5
        if 'Validate ' in arg:
            guess = 2.5
        elif 'PRIME' in arg:
            guess = 25.0
        elif source == 'wash':
            guess = 100.0
        elif source == 'disp':
            guess = 30.0
        Guesses[t] = Estimates[t] = guess
    return Estimates[t]
