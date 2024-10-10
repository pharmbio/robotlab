from __future__ import annotations
from dataclasses import *
from typing import *

from datetime import timedelta

from .log import Log
from .commands import *

import pbutils

class EstEntry(TypedDict):
    cmd: PhysicalCommand
    datetime: str
    duration: float

def entry_order(entry: EstEntry):
    return pbutils.serializer.dumps(entry['cmd']), entry['datetime']

def avg(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs)

estimates_json_path = 'estimates.json'
estimates_jsonl_path = 'estimates.jsonl'

def read_estimates(path: str=estimates_jsonl_path) -> dict[PhysicalCommand, float]:
    entries: list[EstEntry] = list(pbutils.serializer.read_jsonl(path))
    groups = pbutils.group_by(entries, key=lambda entry: entry['cmd'])
    return {
        cmd: round(avg(ent['duration'] for ent in ents), 3)
        for cmd, ents in groups.items()
    }

def add_estimates_from(log_path: str, *, path: str=estimates_jsonl_path):
    entries: list[EstEntry] = list(pbutils.serializer.read_jsonl(path))

    size_0 = len(entries)

    if log_path == 'normalize':
        print(f'normalize: Adding no new entries, only normalizing the estimates file.')
    elif log_path == 'trim':
        print(f'trim: Adding no new entries, only trimming the estimates file (keep last 5 of each)')
        trimmed: list[EstEntry] = []
        groups = pbutils.group_by(entries, key=lambda entry: entry['cmd'])
        for cmd, ents in groups.items():
            ents = sorted(ents, key=lambda ent: ent['datetime'])
            for ent in ents[-5:]:
                trimmed += [
                    EstEntry(
                        cmd=cmd,
                        datetime=ent['datetime'],
                        duration=ent['duration'],
                    )
                ]
        entries = trimmed
    else:
        with Log.open(log_path) as log:
            rt = log.runtime_metadata()
            assert rt
            for e in log.command_states():
                if e.state == 'completed':
                    cmd = e.cmd
                    if isinstance(cmd, PhysicalCommand) and e.duration is not None:
                        cmd = cmd.normalize()
                        t_datetime = rt.start_time + timedelta(seconds=e.t)
                        t_str = t_datetime.replace(microsecond=0).isoformat(sep=' ')
                        entries += [
                            EstEntry(
                                cmd=cmd,
                                datetime=t_str,
                                duration=e.duration,
                            )
                        ]

    size_after = len(entries)

    entries = [
        EstEntry(
            cmd=entry['cmd'].normalize(),
            datetime=entry['datetime'],
            duration=entry['duration'],
        )
        for entry in entries
    ]
    entries = sorted(entries, key=entry_order)
    pbutils.serializer.write_jsonl(entries, path)
    print(f'Wrote {size_after - size_0} new estimates to {path} from {log_path}.')

def rewrite_estimates(in_path: str=estimates_json_path, out_path: str=estimates_jsonl_path):
    '''
    Converter from the old format to the new flat format
    '''
    class EstEntryGrouped(TypedDict):
        cmd: PhysicalCommand
        times: dict[str, float]

    entries: list[EstEntryGrouped] = pbutils.serializer.read_json(in_path)
    ests: dict[PhysicalCommand, dict[str, float]] = DefaultDict(dict)
    flat: list[EstEntry] = []

    for e in entries:
        cmd = e['cmd'].normalize()
        ests[cmd] = e['times']
        for datetime, duration in e['times'].items():
            flat += [
                EstEntry(
                    cmd=cmd,
                    datetime=datetime,
                    duration=duration,
                )
            ]
    flat = sorted(flat, key=entry_order)
    pbutils.serializer.write_jsonl(flat, out_path)

estimates = read_estimates()
guesses: dict[PhysicalCommand, float] = {}

estimates = {
    RobotarmCmd('noop'): 0.5,
    **estimates
}

for cmd, v in list(estimates.items()):
    if isinstance(cmd, BiotekCmd) and cmd.action =='Run':
        kv = cmd.replace(machine=cmd.machine, action='Validate')
        kr = cmd.replace(machine=cmd.machine, action='RunValidated')
        if kv not in estimates and kr not in estimates:
            estimates[kv] = 4.0 if cmd.machine == 'disp' else 1.5
            estimates[kr] = v - estimates[kv]

if 1:
    for k, v in list(estimates.items()):
        if isinstance(k, RobotarmCmd):
            estimates[k] = v / 1.0

import re

def estimate(cmd: PhysicalCommand) -> float:
    assert isinstance(cmd, PhysicalCommand), f'{cmd} is not estimatable'
    cmd = cmd.normalize()
    if cmd not in estimates:
        match cmd:
            case BiotekCmd(action='Validate'):
                guess = 2.5
            case BiotekCmd(action='Run') if other := estimates.get(cmd.replace(machine=cmd.machine, action='RunValidated')):
                guess = other + 2.5
            case BiotekCmd(action='RunValidated') if other := estimates.get(cmd.replace(machine=cmd.machine, action='Run')):
                guess = other - 2.5
            case BiotekCmd() if 'PRIME' in str(cmd.protocol_path):
                guess = 25.0
            case BiotekCmd(machine='wash'):
                guess = 100.0
            case BlueCmd(action='TestCommunications'):
                guess = 5.0
            case BlueCmd():
                guess = 60.0
            case BiotekCmd(machine='disp'):
                guess = 30.0
            case PFCmd():
                guess = 10.0
            case FridgeCmd(action='reset_and_activate'):
                guess = 60.0
            case FridgeInsert() | FridgeEject():
                guess = 20.0
            case SquidStageCmd():
                guess = 5.0
            case SquidAcquire():
                guess = 3 * 3600.0
            case NikonAcquire():
                x, s, n = cmd.job_name.partition('s')
                if s == 's' and not n and x.isnumeric():
                    guess = float(x)
                elif 'RD' in cmd.job_name:
                    guess = 1200.0
                else:
                    guess = 3.5 * 3600.0
            case RobotarmCmd():
                test = cmd.program_name
                test = test.replace('B21-to-disp', 'disp-to-B21')
                test = test.replace('blue', 'wash')
                if 'incu' not in test:
                    test = re.sub(r'A\d+', 'C21', test)
                test = re.sub(r'\d+', '21', test)
                if test != cmd.program_name:
                    guess = estimate(RobotarmCmd(test))
                else:
                    guess = 2.5
            case PFCmd(only_if_no_barcode=True):
                guess = 0.0
            case _:
                guess = 2.5
        guesses[cmd] = estimates[cmd] = guess
    return estimates[cmd]

