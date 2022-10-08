from __future__ import annotations
from dataclasses import *

import pbutils
import shutil
import os
from .commands import (
    Checkpoint,
    WaitForCheckpoint,
    Command,
    Seq,
    Meta,
    RobotarmCmd,
    Metadata,
    Info,
    Fork,
)
from .moves import InitialWorld
from .runtime import RuntimeConfig, ResumeConfig
from .execute import execute_program
from . import moves
from .log import Log

def execute_resume(config: RuntimeConfig, log_filename_in: str, resume_time_now: str | None = None, skip: list[str]=[], drop: list[str]=[]):
    entries = Log.read_jsonl(log_filename_in)

    program = resume_program(entries, skip=skip, drop=drop)

    log_filename = config.log_filename
    if not log_filename:
        log_filename = 'logs/resume-' + pbutils.now_str_for_filename() + '.jsonl'
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
    runtime_metadata = entries.runtime_metadata()
    assert runtime_metadata
    program = pbutils.serializer.read_json(runtime_metadata.program_filename)
    assert program and isinstance(program, Command)

    next_id = program.next_id()
    def get_fresh_id():
        nonlocal next_id
        next_id += 1
        return str(next_id)

    running_log = Log.read_jsonl(runtime_metadata.running_log_filename)
    running = running_log.running()
    pbutils.pr(running_log)
    assert running
    resumed_world = {
        location: thing
        for location, thing in running.world.items()
        if thing not in drop
        if thing not in [f'lid {plate_id}' for plate_id in drop]
    }
    pbutils.pr(dict(
        running=running,
        resumed_world=resumed_world,
    ))

    resumed_world_cmd = Info('resumed world').add(Metadata(effect=InitialWorld(resumed_world), id=get_fresh_id()))

    remove_ids: set[str] = entries.finished()

    drop_ids: set[str] = set()
    for cmd in program.universe():
        if isinstance(cmd, Meta) and cmd.metadata.plate_id in drop:
            for c2 in cmd.universe():
                if isinstance(c2, Meta) and c2.metadata.id:
                    drop_ids.add(c2.metadata.id)
    remove_ids |= drop_ids

    robotarm_prep_cmds: list[Command] = [
        RobotarmCmd('gripper check').add(Metadata(id=get_fresh_id()))
    ]
    for cmd, metadata in program.collect():
        # Make sure the first robotarm command starts from B21 neutral
        if isinstance(cmd, RobotarmCmd) and metadata.id not in remove_ids:
            tagged = moves.tagged_movelists[cmd.program_name]
            if tagged.is_ret:
                drop_ids |= {metadata.id}
            else:
                robotarm_prep_cmds = [
                    RobotarmCmd(p).add(Metadata(id=get_fresh_id()))
                    for p in tagged.prep
                ]
            break

    checkpoint_times: dict[str, float] = entries.checkpoints()

    def FixupForkMetadataBeforeFilter(cmd: Command):
        '''
        The commands with actual resource requirements might be removed later
        so we store what the fork was originally about (for presentation purposes)
        '''
        match cmd:
            case Fork():
                return cmd.add(Metadata(thread_resource=cmd.resource))
            case _:
                return cmd

    def Filter(cmd: Command):
        match cmd:
            case Checkpoint():
                if cmd.name in checkpoint_times:
                    return Seq()
                else:
                    return cmd
            case Meta() if cmd.metadata.id in remove_ids:
                return Seq()
            case Meta() if cmd.metadata.simple_id in skip:
                return Seq()
            case WaitForCheckpoint() if not cmd.plus_secs and cmd.name in checkpoint_times:
                return Seq()
            case _:
                return cmd

    print(f'{len(checkpoint_times) = }')
    print(f'{len(remove_ids) = }')

    # pbutils.pr(program)
    print('inital node count =', len(list(program.universe())))

    program = program.transform(FixupForkMetadataBeforeFilter)
    program = program.transform(Filter)
    program = Seq(resumed_world_cmd, *robotarm_prep_cmds, program)
    program = program.remove_noops()
    print('final node count =', len(list(program.universe())))

    print(f'{remove_ids=}')
    print(f'{next_id=}')
    pbutils.pr(program.collect()[:20])
    # pbutils.pr(program)
    return program

