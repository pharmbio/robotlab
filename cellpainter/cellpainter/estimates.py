from __future__ import annotations
from dataclasses import *
from typing import *

from . import utils
from .log import Log

from collections import defaultdict

from .commands import (
    RobotarmCmd,
    IncuCmd,
    BiotekCmd,
)

EstCmd = RobotarmCmd | IncuCmd | BiotekCmd

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

def estimates_from(path: str) -> dict[EstCmd, float]:
    entries: list[EstEntry] = cast(Any, utils.serializer.read_json(path))
    return {
        e['cmd']: round(avg(e['times'].values()), 3)
        for e in entries
    }

def add_estimates_from(path: str, log_or_log_path: str | Log):
    entries: list[EstEntry] = cast(Any, utils.serializer.read_json(path))
    ests: dict[EstCmd, dict[str, float]] = defaultdict(dict)
    for e in entries:
        cmd = normalize(e['cmd'])
        ests[cmd] = e['times']
    if isinstance(log_or_log_path, Log):
        log = log_or_log_path
    else:
        log = Log.read_jsonl(log_or_log_path)
    for e in log:
        cmd = e.cmd
        if isinstance(cmd, EstCmd) and e.duration is not None:
            cmd = normalize(cmd)
            ests[cmd][e.log_time[:len('YYYY-MM-DD HH:MM:SS')]] = e.duration
    m = [
        {
            'cmd': cmd,
            'times': times,
        }
        for cmd, times in sorted(ests.items(), key=str)
    ]
    utils.serializer.write_json(m, path, indent=2)

estimates = estimates_from('estimates.json')
guesses: dict[EstCmd, float] = {}

estimates = {
    RobotarmCmd('noop'): 0.5,
    **estimates
}

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
            case _:
                guess = 2.5
        guesses[cmd] = estimates[cmd] = guess
    return estimates[cmd]

