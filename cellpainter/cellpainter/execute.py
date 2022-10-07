from __future__ import annotations
from typing import Iterator

import contextlib
import os
import platform

from pathlib import Path

from . import commands

from .log import (
    RuntimeMetadata,
    LogEntry,
    Log,
)

from .commands import (
    Metadata,
    Command,
    BiotekCmd,
    Checkpoint,
    Duration,
    Fork,
    Idle,
    IncuCmd,
    Info,
    Meta,
    RobotarmCmd,
    Seq,
    WaitForCheckpoint,
    WaitForResource,
)
from .runtime import RuntimeConfig, Runtime, dry_run
from . import commands
from . import constraints
from . import utils
from .symbolic import Symbolic
from .moves import movelists, MoveList
from . import bioteks
from . import incubator
from .estimates import estimate, EstCmd
from . import estimates

def execute(cmd: Command, runtime: Runtime, metadata: Metadata):
    if isinstance(cmd, EstCmd) and metadata.est is None:
        metadata = metadata.merge(Metadata(est=estimate(cmd)))
    entry = LogEntry(cmd=cmd, metadata=metadata)
    match cmd:
        case Meta():
            execute(cmd.command, runtime, metadata.merge(cmd.metadata))

        case Seq():
            for c in cmd.commands:
                execute(c, runtime, metadata)

        case Info():
            runtime.log(entry.add(msg=cmd.msg))

        case Idle():
            secs = cmd.secs
            assert isinstance(secs, (float, int))
            entry = entry.add(Metadata(sleep_secs=secs))
            with runtime.timeit(entry):
                runtime.sleep(secs, entry)

        case Checkpoint():
            runtime.checkpoint(cmd.name, entry)

        case WaitForCheckpoint():
            plus_secs = cmd.plus_secs
            assert isinstance(plus_secs, (float, int))
            msg = f'{Symbolic.var(str(cmd.name)) + plus_secs}'
            t0 = runtime.wait_for_checkpoint(cmd.name)
            desired_point_in_time = t0 + plus_secs
            delay = desired_point_in_time - runtime.monotonic()
            secs = round(delay, 3)
            entry = entry.add(msg=msg, metadata=Metadata(sleep_secs=secs))
            with runtime.timeit(entry):
                runtime.sleep(delay, entry)

        case Duration():
            t0 = runtime.wait_for_checkpoint(cmd.name)
            runtime.log(entry, t0=t0)

        case Fork():
            thread_name = cmd.thread_name
            assert thread_name
            fork_metadata = metadata.merge(Metadata(thread_name=thread_name, thread_resource=cmd.resource))
            @runtime.spawn
            def fork():
                assert thread_name
                runtime.register_thread(thread_name)
                execute(cmd.command, runtime, fork_metadata)
                runtime.thread_done()

        case RobotarmCmd():
            with runtime.timeit(entry):
                if runtime.config.robotarm_env.mode == 'noop':
                    runtime.sleep(estimate(cmd), entry.add(Metadata(dry_run_sleep=True)))
                else:
                    movelist = MoveList(movelists[cmd.program_name])
                    arm = runtime.get_robotarm(include_gripper=movelist.has_gripper())
                    arm.execute_moves(movelist, name=cmd.program_name)
                    arm.close()

        case BiotekCmd():
            with runtime.timeit(entry):
                bioteks.execute(runtime, entry, cmd.machine, cmd.protocol_path, cmd.action)

        case IncuCmd():
            with runtime.timeit(entry):
                incubator.execute(runtime, entry, cmd.action, cmd.incu_loc)

        case WaitForResource():
            raise ValueError('Cannot execute WaitForResource, run Command.make_resource_checkpoints first')

        case _:
            raise ValueError(cmd)

    match cmd:
        case IncuCmd() | RobotarmCmd() | Info():
            if effect := metadata.effect:
                runtime.apply_effect(effect, entry)
        case _:
            pass

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
        if not config.resume_config:
            with open(log_filename, 'w') as fp:
                fp.write('') # clear file
    else:
        log_filename = None

    config = config.replace(log_filename=log_filename)

    runtime = config.make_runtime()

    with runtime.excepthook():
        yield runtime

def check_correspondence(program: Command, est_entries: Log, expected_ends: dict[str, float]):
    matches = 0
    mismatches = 0
    seen: set[str] = set()
    for e in est_entries:
        i = e.metadata.id
        if i and (e.is_end() or isinstance(e.cmd, Checkpoint)):
            seen.add(i)
            if abs(e.t - expected_ends[i]) > 0.3:
                utils.pr(('mismatch!', i, e, expected_ends[i]))
                mismatches += 1
            else:
                matches += 1
            # utils.pr((f'{matches=}', i, e, ends[i]))
    by_id: dict[str, Command] = {
        i: c
        for c in program.universe()
        if isinstance(c, commands.Meta)
        if (i := c.metadata.id)
    }

    for i, e in expected_ends.items():
        if i not in seen:
            cmd = by_id.get(i)
            match cmd:
                case Meta(command=Info()):
                    continue
                case _:
                    pass
            print('not seen:', i, e, cmd, sep='\t')

    if mismatches or not matches:
        print(f'{matches=} {mismatches=} {len(expected_ends)=}')

def execute_program(config: RuntimeConfig, program: Command, metadata: dict[str, str], for_visualizer: bool = False) -> Log:
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
            execute(program, runtime_est, Metadata())
        est_entries = runtime_est.get_log()

    if for_visualizer:
        return est_entries

    if not resume_config:
        with utils.timeit('check correspondence'):
            check_correspondence(program, est_entries, expected_ends)

    cache = Path('cache/')
    cache.mkdir(parents=True, exist_ok=True)

    now_str = utils.now_str_for_filename()

    estimates_filename     = cache / (now_str + '_estimates.jsonl')
    program_filename       = cache / (now_str + '_program.json')
    running_log_filename   = cache / (now_str + '_running.jsonl')

    config = config.replace(running_log_filename=str(running_log_filename))

    if metadata.get('program') == 'cell_paint':
        missing: list[str] = []
        for k, _v in estimates.guesses.items():
            if isinstance(k, BiotekCmd) and k.protocol_path:
                missing += [k.protocol_path]
        if missing:
            raise ValueError('Missing timings for the following biotek paths:', ', '.join(sorted(set(missing))))

    with make_runtime(config, metadata) as runtime:
        try:
            print('Expected finish:', runtime.pp_time_offset(max(expected_ends.values())))
        except:
            pass

        program = program.remove_scheduling_idles()

        utils.serializer.write_jsonl(est_entries, estimates_filename)
        utils.serializer.write_json(program, program_filename, indent=2)
        running_log_filename.touch()

        runtime_metadata = RuntimeMetadata(
            pid                  = os.getpid(),
            host                 = platform.node(),
            git_HEAD             = utils.git_HEAD() or '',
            log_filename         = config.log_filename or '',
            estimates_filename   = str(estimates_filename) ,
            program_filename     = str(program_filename),
            running_log_filename = str(running_log_filename),
        )

        runtime.log(LogEntry(runtime_metadata=runtime_metadata))
        execute(program, runtime, Metadata())
        runtime.log(LogEntry(metadata=Metadata(completed=True)))

        for line in runtime.get_log().group_durations_for_display():
            print(line)

        return runtime.get_log()

