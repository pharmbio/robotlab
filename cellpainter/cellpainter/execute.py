from __future__ import annotations
from typing import *
from dataclasses import *

import contextlib
import os
import pickle

from pathlib import Path

from . import commands

from .log import (
    CommandState,
    RuntimeMetadata,
    Log,
    CommandWithMetadata,
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
    Seq_,
    WaitForCheckpoint,
    WaitForResource,
)
from .runtime import RuntimeConfig, Runtime, dry_run
from . import commands
from . import constraints
import pbutils
from .symbolic import Symbolic
from .moves import movelists, MoveList
from . import bioteks
from . import incubator
from .estimates import estimate, EstCmd
from . import estimates
from datetime import datetime

from pbutils.mixins import DB, DBMixin

def execute(cmd: Command, runtime: Runtime, metadata: Metadata):
    if isinstance(cmd, EstCmd) and metadata.est is None:
        metadata = metadata.merge(Metadata(est=estimate(cmd)))
    entry = CommandWithMetadata(cmd=cmd, metadata=metadata)
    match cmd:
        case Meta():
            execute(cmd.command, runtime, metadata.merge(cmd.metadata))

        case Seq_():
            for c in cmd.commands:
                execute(c, runtime, metadata)

        case Info():
            runtime.log(entry.message(cmd.msg))

        case Idle():
            secs = cmd.secs
            assert isinstance(secs, (float, int))
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
            runtime.log(entry.message(msg))
            if entry.metadata.id:
                with runtime.timeit(entry):
                    runtime.sleep(delay, entry)
            else:
                runtime.sleep(delay, entry)

        case Duration():
            t0 = runtime.wait_for_checkpoint(cmd.name)
            runtime.timeit_end(entry, t0=t0)

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
                    if metadata.sim_delay:
                        print(metadata.sim_delay)
                    runtime.sleep(
                        estimate(cmd) + (metadata.sim_delay or 0),
                        entry.merge(Metadata(dry_run_sleep=True))
                    )
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
        'start_time': pbutils.now_str_for_filename(),
        **metadata,
        'config_name': config.name,
    }
    if config.log_to_file:
        log_filename = config.log_filename
        if not log_filename:
            log_filename = ' '.join(['event log', *metadata.values()])
            log_filename = 'logs/' + log_filename.replace(' ', '_') + '.db'
        abspath = os.path.abspath(log_filename)
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        print(f'{log_filename=}')
        with open(log_filename, 'w') as fp:
            fp.write('') # clear file
    else:
        log_filename = None

    config = config.replace(log_filename=log_filename)

    runtime = config.make_runtime()

    with runtime.excepthook():
        yield runtime

def check_correspondence(program: Command, states: list[CommandState], expected_ends: dict[str, float]):
    matches = 0
    mismatches = 0
    seen: set[str] = set()
    for state in states:
        i = state.metadata.id
        if i:
            seen.add(i)
            if abs(state.t - expected_ends[i]) > 0.3:
                pbutils.pr(('mismatch!', i, state, expected_ends[i]))
                mismatches += 1
            else:
                matches += 1
            # pbutils.pr((f'{matches=}', i, e, ends[i]))
    by_id: dict[str, Command] = {
        i: c
        for c in program.universe()
        if isinstance(c, commands.Meta)
        if (i := c.metadata.id)
    }

    not_seen = 0
    for i, e in expected_ends.items():
        if i not in seen:
            cmd = by_id.get(i)
            match cmd:
                case Meta(command=Info() | Checkpoint()):
                    continue
                case _:
                    pass
            print('not seen:', i, e, cmd, sep='\t')
            not_seen += 1

    if mismatches or not matches or not_seen:
        raise ValueError(f'Correspondence check failed {matches=} {mismatches=} {len(expected_ends)=} {not_seen=}')

@dataclass(frozen=True)
class Program(DBMixin):
    program: Command

def execute_program(config: RuntimeConfig, program: Command, metadata: dict[str, str], for_visualizer: bool = False, sim_delays: dict[str, float] = {}) -> Log:
    program = program.remove_noops()
    program = program.assign_ids()

    with pbutils.timeit('constraints'):
        program, expected_ends = constraints.optimize(program)

    def AddSimDelays(cmd: commands.Command) -> commands.Command:
        if isinstance(cmd, commands.Meta):
            if sim_delay := sim_delays.get(cmd.metadata.id):
                return cmd.add(commands.Metadata(sim_delay=sim_delay))
        return cmd
    program = program.transform(AddSimDelays)

    with pbutils.timeit('estimates'):
        with make_runtime(dry_run.replace(log_to_file=False, log_filename=None), {}) as runtime_est:
            execute(program, runtime_est, Metadata())

    if for_visualizer:
        return runtime_est.get_log()

    with pbutils.timeit('get estimates'):
        states = runtime_est.log_db.get(CommandState).list()

    with pbutils.timeit('check correspondence'):
        check_correspondence(program, states, expected_ends)

    cache = Path('cache/')
    cache.mkdir(parents=True, exist_ok=True)

    now_str = pbutils.now_str_for_filename()

    program_filename = cache / (now_str + '_program.json')

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
        with pbutils.timeit('write estimates'):
            with runtime.log_db.transaction:
                for state in states:
                    if isinstance(state.cmd, WaitForCheckpoint | Checkpoint | Idle):
                        continue
                    state.state = 'planned'
                    state.save(runtime.log_db)
        with pbutils.timeit('write program'):
            with open(program_filename, 'wb') as fp:
                pickle.dump(program, fp)

        num_plates = max(
            (
                int(p)
                for x in program.universe()
                if isinstance(x, Meta)
                if (p := x.metadata.plate_id)
            ),
            default=0
        )

        runtime_metadata = RuntimeMetadata(
            start_time         = runtime.start_time,
            num_plates         = num_plates,
            log_filename       = config.log_filename,
            program_filename   = str(program_filename),
        )
        runtime_metadata = runtime_metadata.save(runtime.log_db)

        with pbutils.timeit('execute'):
            execute(program, runtime, Metadata())

        runtime_metadata.completed = datetime.now()
        runtime_metadata = runtime_metadata.save(runtime.log_db)

        for line in runtime.get_log().group_durations_for_display():
            print(line)

        return runtime.get_log()

