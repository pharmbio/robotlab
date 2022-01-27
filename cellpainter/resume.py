from __future__ import annotations
from dataclasses import *

from . import utils
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
    Info,
)
from .moves import InitialWorld
from .runtime import RuntimeConfig, ResumeConfig
from .execute import execute_program
from . import moves
from .log import Log

def execute_resume(config: RuntimeConfig, log_filename_in: str, resume_time_now: str | None = None, skip: list[str]=[], drop: list[str]=[]):
    entries = Log.from_jsonl(log_filename_in)

    program = resume_program(entries, skip=skip, drop=drop)

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
        resume_config=ResumeConfig.init(entries, resume_time_now)
    )
    execute_program(config, program, {})

def resume_program(entries: Log, skip: list[str]=[], drop: list[str]=[]):

    program: Command | None = None
    rt = entries.runtime_metadata()
    assert rt
    with open(rt.program_pickle_file, 'rb') as fp:
        program = pickle.load(fp)
    assert program and isinstance(program, Command)

    next_id = program.next_id()
    def get_id():
        nonlocal next_id
        next_id += 1
        return str(next_id)

    running = entries.running()
    assert running
    resumed_world = Info('resumed world').add(Metadata(effect=InitialWorld(running.world), id=get_id()))
    utils.pr(running)

    finished_ids: set[str] = entries.finished()

    drop_ids: set[str] = set()
    for cmd in program.universe():
        if isinstance(cmd, Meta) and cmd.metadata.plate_id in drop:
            for c2 in cmd.universe():
                if isinstance(c2, Meta) and c2.metadata.id:
                    drop_ids.add(c2.metadata.id)

    robotarm_prep_cmds: list[Command] = []
    for cmd, metadata in program.collect():
        # Make sure the first robotarm command starts from B21 neutral
        if isinstance(cmd, RobotarmCmd) and metadata.id not in finished_ids:
            tagged = moves.tagged_movelists[cmd.program_name]
            if tagged.is_ret:
                drop_ids |= {metadata.id}
            else:
                robotarm_prep_cmds = [
                    RobotarmCmd(p).add(Metadata(id=get_id()))
                    for p in tagged.prep
                ]
            break

    checkpoint_times: dict[str, float] = entries.checkpoints()

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
            case _:
                return cmd

    print(f'{len(checkpoint_times) = }')
    print(f'{len(finished_ids) = }')

    # utils.pr(program)
    print('inital node count =', len(list(program.universe())))

    program = program.transform(Filter)
    program = Sequence(resumed_world, *robotarm_prep_cmds, program)
    program = program.remove_noops()
    print('final node count =', len(list(program.universe())))

    print(f'{finished_ids=}')
    print(f'{next_id=}')
    utils.pr(program.collect()[:20])
    # utils.pr(program)
    return program

