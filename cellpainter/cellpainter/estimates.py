from __future__ import annotations
from dataclasses import *
from typing import *

import pbutils
from .log import Log



from .commands import (
    RobotarmCmd,
    IncuCmd,
    BiotekCmd,
    BlueCmd,
)

EstCmd = RobotarmCmd | IncuCmd | BiotekCmd | BlueCmd

def normalize(cmd: EstCmd) -> EstCmd:
    if isinstance(cmd, IncuCmd):
        return IncuCmd(action=cmd.action, incu_loc=None)
    else:
        return cmd

class EstEntry(TypedDict):
    cmd: EstCmd
    times: dict[str, float]

def avg(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs)

estimates_json_path = 'estimates.json'

def read_estimates(path: str=estimates_json_path) -> dict[EstCmd, float]:
    entries: list[EstEntry] = pbutils.serializer.read_json(path)
    return {
        e['cmd']: round(avg(e['times'].values()), 3)
        for e in entries
    }

from datetime import timedelta

def add_estimates_from(log_path: str, *, path: str=estimates_json_path):
    entries: list[EstEntry] = pbutils.serializer.read_json(path)
    ests: dict[EstCmd, dict[str, float]] = DefaultDict(dict)

    def size(x: Dict[Any, dict[Any, Any]]) -> int:
        return sum(
            1
            for _, d in x.items()
            for _, _ in d.items()
        )

    for e in entries:
        cmd = normalize(e['cmd'])
        ests[cmd] = e['times']

    size_0 = size(ests)

    if log_path == 'normalize':
        print(f'normalize: Adding no new entries, only normalizing the estimates file.')
    else:
        with Log.open(log_path) as log:
            rt = log.runtime_metadata()
            assert rt
            for e in log.command_states():
                if e.state == 'completed':
                    cmd = e.cmd
                    if isinstance(cmd, EstCmd) and e.duration is not None:
                        cmd = normalize(cmd)
                        t_datetime = rt.start_time + timedelta(seconds=e.t)
                        t_str = t_datetime.replace(microsecond=0).isoformat(sep=' ')
                        ests[cmd][t_str] = e.duration

    size_after = size(ests)

    m = [
        {
            'cmd': cmd,
            'times': times,
        }
        for cmd, times in sorted(ests.items(), key=str)
    ]
    pbutils.serializer.write_json(m, path, indent=2)
    print(f'Wrote {size_after - size_0} new estimates to {path} from {log_path}.')

estimates = read_estimates('estimates.json')
guesses: dict[EstCmd, float] = {}

estimates = {
    RobotarmCmd('noop'): 0.5,
    **estimates
}

for k, v in list(estimates.items()):
    if isinstance(k, BiotekCmd) and k.action =='Run':
        kv = k.replace(action='Validate')
        kr = k.replace(action='RunValidated')
        if kv not in estimates and kr not in estimates:
            estimates[kv] = 4.0 if k.machine == 'disp' else 1.5
            estimates[kr] = v - estimates[kv]


if 0:
    for k, v in list(estimates.items()):
        name = k.program_name if isinstance(k, RobotarmCmd) else ''
        if 'wash' in name or 'disp' in name:
            if 'prep' in name or 'return' in name:
                v2 = 2.5
            elif 'wash_to_disp' not in name:
                v2 = 6.0
            else:
                v2 = round(v, 1)
            # print(v, '-> ' + str(v2), k, sep='\t')
            # estimates[k] = v2

import re

def estimate(cmd: EstCmd) -> float:
    assert isinstance(cmd, EstCmd)
    cmd = normalize(cmd)
    if cmd not in estimates:
        match cmd:
            case BiotekCmd(action='Validate'):
                guess = 2.5
            case BiotekCmd(action='Run') if other := estimates.get(cmd.replace(action='RunValidated')):
                guess = other + 2.5
            case BiotekCmd(action='RunValidated') if other := estimates.get(cmd.replace(action='Run')):
                guess = other - 2.5
            case BiotekCmd() if 'PRIME' in str(cmd.protocol_path):
                guess = 25.0
            case BiotekCmd(machine='wash'):
                guess = 100.0
            case BiotekCmd(machine='disp'):
                guess = 30.0
            case RobotarmCmd():
                test = cmd.program_name
                if 'incu' not in test:
                    test = re.sub(r'A\d+', 'C21', test)
                test = re.sub(r'\d+', '21', test)
                if test != cmd.program_name:
                    guess = estimate(RobotarmCmd(test))
                else:
                    guess = 2.5
            case _:
                guess = 2.5
        guesses[cmd] = estimates[cmd] = guess
    return estimates[cmd]

