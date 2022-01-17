from __future__ import annotations
from dataclasses import *

from . import utils
from datetime import datetime
import pickle
import shutil
import os
from .commands import (
    Checkpoint,
    WaitForCheckpoint,
    Command,
    Sequence,
    Meta,
    RobotarmCmd,
    Metadata,
)
from .runtime import RuntimeConfig, ResumeConfig
from .execute import execute_program
from . import moves

def resume_program(config: RuntimeConfig, log_filename_in: str, skip: list[str]=[], drop: list[str]=[]):
    entries = list(utils.read_json_lines(log_filename_in))
    entries = entries

    program: Command | None = None
    for e in entries[::-1]:
        if (path := e.get('runtime_metadata', {}).get('program_pickle_file')):
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
            is_finished = False
            if e.get('kind') == 'info' and e.get('source') == 'system':
                if 'section' in e:
                    is_finished = True
                if 'effect' in e:
                    is_finished = True
            if e.get('kind') == 'end' and e.get('source') in ('robotarm', 'incu', 'disp', 'wash'):
                is_finished = True
            if is_finished:
                cmd_id = e['id']
                assert isinstance(cmd_id, str)
                finished_ids.add(cmd_id)
        except KeyError:
            pass

    for e in entries:
        if e.get('kind') == 'end' and e.get('source') == 'wait':
            utils.pr(e)

    drop_ids: set[str] = set()
    for cmd in program.universe():
        if isinstance(cmd, Meta) and cmd.metadata.plate_id in drop:
            for c2 in cmd.universe():
                if isinstance(c2, Meta) and c2.metadata.id:
                    drop_ids.add(c2.metadata.id)

    finished_ids |= drop_ids
    def Filter(cmd: Command):
        match cmd:
            case Checkpoint():
                if cmd.name in checkpoint_times:
                    return Sequence()
                else:
                    return cmd
            case Meta() if cmd.metadata.id in finished_ids:
                return Sequence()
            case Meta() if cmd.metadata.simple_id in skip:
                return Sequence()
            case WaitForCheckpoint() if not cmd.plus_secs and cmd.name in checkpoint_times:
                return Sequence()
            case _ if cmd.is_noop():
                return Sequence()
            case _:
                return cmd

    print(f'{len(checkpoint_times) = }')
    print(f'{len(finished_ids) = }')


    # utils.pr(program)
    print('inital node count =', len(list(program.universe())))
    next_id = program.next_id()
    program = program.transform(Filter)
    program = program.remove_noops()

    is_first = True
    def FixFirstRobotarmCmd(cmd: Command) -> Command:
        '''
        Make sure the first robotarm command starts from B21 neutral
        '''
        nonlocal is_first
        if is_first and isinstance(cmd, RobotarmCmd):
            is_first = False
            tagged = moves.tagged_movelists[cmd.program_name]
            if tagged.is_ret:
                replacement = Sequence()
            else:
                prep = [
                    RobotarmCmd(p).add(Metadata(id=str(i + next_id)))
                    for i, p in enumerate(tagged.prep)
                ]
                replacement = Sequence(*prep, cmd)
            print('replacing:', cmd)
            print('     with:', utils.show(replacement))
            return replacement
        else:
            return cmd

    program = program.transform(FixFirstRobotarmCmd)
    program = program.remove_noops()
    print('final node count =', len(list(program.universe())))

    start_time = datetime.fromisoformat(entries[0]['log_time'])
    print('start_time =', str(start_time))

    print(f'{finished_ids=}')
    print(f'{next_id=}')
    # utils.pr(program)

    log_filename = config.log_filename
    if not log_filename:
        log_filename = 'logs/resume-' + utils.now_str_for_filename() + '.jsonl'
        os.makedirs('logs/', exist_ok=True)
    abspath = os.path.abspath(log_filename)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    print(f'{log_filename=}')
    shutil.copy2(log_filename_in, log_filename)

    config = config.replace(
        log_filename=log_filename,
        resume_config=ResumeConfig(
            start_time=start_time,
            checkpoint_times=checkpoint_times,
        )
    )
    execute_program(config, program, {})
