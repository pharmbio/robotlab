from __future__ import annotations
from typing import Any, Iterator
from dataclasses import *

import contextlib
import os
import pickle
import platform

from .commands import (
    Command,
    Info,
    Meta,
    Sequence,
)
from .runtime import RuntimeConfig, Runtime, dry_run
from . import commands
from . import constraints

from . import utils

def group_times(times: dict[str, list[float]]):
    groups = utils.group_by(list(times.items()), key=lambda s: s[0].rstrip(' 0123456789'))
    out: dict[str, list[str]] = {}
    def key(kv: tuple[str, Any]):
        s, _ = kv
        if s.startswith('plate'):
            _plate, i, *what = s.split(' ')
            return f' plate {" ".join(what)} {int(i):03}'
        else:
            return s
    for k, vs in sorted(groups.items(), key=key):
        if k.startswith('plate'):
            _plate, i, *what = k.split(' ')
            k = f'plate {int(i):>2} {" ".join(what)}'
        out[k] = [utils.pp_secs(v) for _, [v] in vs]
    return out

def display_times(times: dict[str, list[float]]):
    for k, vs in group_times(times).items():
        print(k, '[' + ', '.join(vs) + ']')

@contextlib.contextmanager
def make_runtime(config: RuntimeConfig, metadata: dict[str, str]) -> Iterator[Runtime]:
    metadata = {
        'start_time': utils.now_str_for_filename(),
        **metadata,
        'config_name': config.name,
    }
    if config.log_to_file:
        log_filename = config.log_filename
        if not log_filename:
            log_filename = ' '.join(['event log', *metadata.values()])
            log_filename = 'logs/' + log_filename.replace(' ', '_') + '.jsonl'
        abspath = os.path.abspath(log_filename)
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        print(f'{log_filename=}')
    else:
        log_filename = None

    config = config.replace(log_filename=log_filename)

    runtime = config.make_runtime()

    with runtime.excepthook():
        yield runtime

def check_correspondence(program: Command, est_entries: list[dict[str, Any]], expected_ends: dict[str, float]):
    matches = 0
    mismatches = 0
    seen: set[str] = set()
    for e in est_entries:
        i = e.get('id')
        if i and (e.get('kind') == 'end' or e.get('kind') == 'info' and e.get('source') == 'checkpoint'):
            seen.add(i)
            if abs(e['t'] - expected_ends[i]) > 0.1:
                utils.pr(('no match!', i, e, expected_ends[i]))
                mismatches += 1
            else:
                matches += 1
            # utils.pr((f'{matches=}', i, e, ends[i]))
    by_id: dict[str, Command] = {
        i: c
        for c in program.universe()
        if isinstance(c, commands.Meta)
        if (i := c.metadata.get('id')) and isinstance(i, str)
    }

    for i, e in expected_ends.items():
        if i not in seen:
            cmd = by_id.get(i)
            match cmd:
                case Meta(command=Info()):
                    continue
            print('not seen:', i, e, cmd, sep='\t')

    if mismatches or not matches:
        print(f'{matches=} {mismatches=} {len(expected_ends)=}')

def execute_program(config: RuntimeConfig, program: Command, metadata: dict[str, str], for_visualizer: bool = False) -> list[dict[str, Any]]:
    program = program.remove_noops()
    resume_config = config.resume_config
    if not resume_config:
        program = program.assign_ids()

    if not resume_config:
        with utils.timeit('constraints'):
            program, expected_ends = constraints.optimize(program)
    else:
        expected_ends = {}

    with utils.timeit('estimates'):
        with make_runtime(dry_run.replace(log_to_file=False, resume_config=config.resume_config), {}) as runtime_est:
            program.execute(runtime_est, {})
        est_entries = runtime_est.log_entries

    if for_visualizer:
        return est_entries

    if not resume_config:
        with utils.timeit('check correspondence'):
            check_correspondence(program, est_entries, expected_ends)

    # if config is visualize, then just start visualizer here instead ... we already have the estimates

    with make_runtime(config, metadata) as runtime:
        try:
            print('Expected finish:', runtime.pp_time_offset(max(expected_ends.values())))
        except:
            pass

        program = program.remove_scheduling_idles()

        runtime_metadata: dict[str, str | int | float | None] = {
            'pid': os.getpid(),
            'host': platform.node(),
            'git_HEAD': utils.git_HEAD() or '',
            'log_filename': config.log_filename,
        }

        os.makedirs('cache/', exist_ok=True)
        base = 'cache/' + utils.now_str_for_filename() + '_'
        save = {
            'estimates_pickle_file': est_entries,
            'program_pickle_file': program,
        }
        for k, v in save.items():
            with open(base + k, 'wb') as fp:
                pickle.dump(v, fp)
            runtime_metadata[k] = base + k

        runtime.log('info', 'system', None, {'runtime_metadata': runtime_metadata, 'silent': True})
        program.execute(runtime, {})
        runtime.log('info', 'system', None, {'completed': True, 'silent': True})

        display_times(runtime.times)

        return runtime.log_entries

def RemoveBioteks(program: Command) -> Command:
    def Filter(cmd: Command) -> Command:
        match cmd:
            case commands.BiotekCmd() | commands.Idle():
                return Sequence()
            case commands.WaitForCheckpoint() if 'incu #' not in cmd.name:
                return Sequence()
            case _:
                return cmd
    program = program.transform(Filter)
    program = program.remove_noops()
    return program

