from __future__ import annotations
from dataclasses import *

import utils
from datetime import datetime
import pickle
import timelike
import time
import shutil
import os
from commands import (
    Checkpoint,
    WaitForCheckpoint,
    Command,
    Sequence,
    Meta,
)
from runtime import RuntimeConfig, Runtime

def resume_program(config: RuntimeConfig, log_filename_in: str) -> Runtime:
    entries = list(utils.read_json_lines(log_filename_in))
    entries = entries

    program: Command | None = None
    for e in entries:
        if (path := e.get('program_pickle_file')):
            with open(path, 'rb') as fp:
                program = pickle.load(fp)
                break
    assert program

    checkpoint_times: dict[str, float] = {}
    for e in entries:
        try:
            if e['kind'] == 'info' and e['source'] == 'checkpoint':
                k = e['arg']
                v = e['t']
                assert isinstance(k, str)
                assert isinstance(v, float)
                checkpoint_times[k] = v
        except KeyError:
            pass

    finished_ids: set[str] = set()
    for e in entries:
        try:
            if e['kind'] == 'end':
                cmd_id = e['id']
                assert isinstance(cmd_id, str)
                finished_ids.add(cmd_id)
        except KeyError:
            pass

    def Filter(cmd: Command):
        if isinstance(cmd, Meta) and cmd.metadata.get('id') in finished_ids:
            return Sequence()
        elif isinstance(cmd, Checkpoint) and cmd.name in checkpoint_times:
            return Sequence()
        elif isinstance(cmd, WaitForCheckpoint) and not cmd.plus_secs and cmd.name in checkpoint_times:
            return Sequence()
        elif cmd.is_noop():
            return Sequence()
        else:
            return cmd

    print(f'{len(checkpoint_times) = }')
    print(f'{len(finished_ids) = }')

    print('inital node count =', len(list(program.universe())))
    program = program.transform(Filter)
    print('final node count =', len(list(program.universe())))

    start_time = datetime.fromisoformat(entries[0]['log_time'])
    secs_ago = (datetime.now() - start_time).total_seconds()
    print('start_time =', str(start_time))
    print('secs_ago =', secs_ago)

    if config.timelike_factory is timelike.WallTime:
        config = replace(
            config,
            timelike_factory = lambda: timelike.WallTime(start_time=time.monotonic() - secs_ago)
        )
    elif config.timelike_factory is timelike.SimulatedTime:
        config = replace(
            config,
            timelike_factory = lambda: timelike.SimulatedTime(skipped_time=secs_ago)
        )
    else:
        raise ValueError('Unknown timelike factory on config object')

    log_filename = 'logs/resume-' + utils.now_str_for_filename() + '.jsonl'
    os.makedirs('logs/', exist_ok=True)
    print(f'{log_filename = }')
    shutil.copy2(log_filename_in, log_filename)

    runtime = Runtime(
        config=config,
        log_filename=log_filename,
        start_time=start_time,
        checkpoint_times=checkpoint_times,
    )
    with runtime.timeit('resume', log_filename_in, {}):
        program.execute(runtime, {})
    return runtime

