from __future__ import annotations
from typing import *
from dataclasses import *

import contextlib

from . import commands

from .log import (
    CommandState,
    RuntimeMetadata,
    CommandWithMetadata,
)

from .commands import (
    Program,
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
from .runtime import RuntimeConfig, Runtime, simulate
from . import commands
from . import constraints
import pbutils
from .moves import movelists, MoveList
from . import moves
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

        case Idle():
            secs = cmd.secs
            assert isinstance(secs, (float, int))
            entry = entry.merge(Metadata(est=round(secs, 3)))
            with runtime.timeit(entry):
                runtime.sleep(secs, entry)

        case Checkpoint():
            runtime.checkpoint(cmd.name, entry)

        case WaitForCheckpoint():
            plus_secs = cmd.plus_secs
            assert isinstance(plus_secs, (float, int))
            t0 = runtime.wait_for_checkpoint(cmd.name)
            desired_point_in_time = t0 + plus_secs
            delay = desired_point_in_time - runtime.monotonic()
            entry = entry.merge(Metadata(est=round(delay, 3)))
            if entry.metadata.id:
                with runtime.timeit(entry):
                    runtime.sleep(delay, entry)
            else:
                runtime.sleep(delay, entry)

        case Duration():
            t0 = runtime.wait_for_checkpoint(cmd.name)
            runtime.timeit_end(entry, t0=t0)

        case Fork():
            thread_resource = cmd.resource
            thread_metadata = metadata.merge(Metadata(thread_resource=thread_resource))

            @runtime.spawn
            def fork():
                runtime.register_thread(f'{thread_resource} {thread_metadata.id}')
                execute(cmd.command, runtime, thread_metadata)
                runtime.thread_done()

        case RobotarmCmd():
            with runtime.timeit(entry):
                if runtime.config.robotarm_env.mode == 'noop':
                    if cmd.program_name not in movelists:
                        raise ValueError(f'Missing robotarm move {cmd.program_name}')
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

    if effect := cmd.effect():
        runtime.apply_effect(effect, entry)

@contextlib.contextmanager
def make_runtime(config: RuntimeConfig, program: Program) -> Iterator[Runtime]:
    runtime = config.make_runtime()
    with runtime.excepthook():
        program.save(runtime.log_db)
        if program.world0:
            runtime.set_world(program.world0)
        yield runtime

def check_correspondence(program: Command, states: list[CommandState], expected_ends: dict[int, float]):
    matches = 0
    mismatches = 0
    seen: set[int] = set()
    for state in states:
        i = state.metadata.id
        if i:
            seen.add(i)
            if abs(state.t - expected_ends[i]) > 0.3:
                pbutils.pr(('mismatch!', i, expected_ends[i], state))
                mismatches += 1
            else:
                matches += 1
    by_id: dict[int, Command] = {
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
            pbutils.pr(('not seen in simulation:', i, e, cmd))
            not_seen += 1

    if mismatches or not matches or not_seen:
        raise ValueError(f'Correspondence check failed {matches=} {mismatches=} {len(expected_ends)=} {not_seen=}')

def remove_stages(program: Program, until_stage: str) -> Program:
    cmd = program.command
    stages = cmd.stages()
    until_index = stages.index(until_stage)

    effects: list[moves.Effect] = []
    def FilterStage(cmd: Command):
        if isinstance(cmd, Meta) and (stage := cmd.metadata.stage):
            if stages.index(stage) < until_index:
                for c in cmd.universe():
                    if (effect := c.effect()) is not None:
                        effects.append(effect)
                return Seq()
        return cmd
    cmd = cmd.transform(FilterStage)
    cmd = cmd.remove_noops()

    world0 = program.world0
    if world0:
        for effect in effects:
            world0 = effect.apply(world0)
        # could prune plates from world here that are never moved in the program

    checkpoints = cmd.checkpoints()
    dangling: set[str] = set()
    i = 0
    def FixDanglingCheckpoints(cmd: Command):
        nonlocal i
        if isinstance(cmd, WaitForCheckpoint | Duration) and cmd.name not in checkpoints:
            i += 1
            name = f'(partial) {cmd.name}'
            dangling.add(name)
            replacement = WaitForCheckpoint(name, assume='nothing') + f'wiggle {i}'
            if isinstance(cmd, Duration):
                replacement = Seq(replacement, Duration(name))
            return replacement
        else:
            return cmd

    cmd = cmd.transform(FixDanglingCheckpoints)
    cmd = Seq(
        *[Checkpoint(dang) for dang in dangling],
        cmd,
    )
    return program.replace(
        command=cmd,
        world0=world0,
        metadata=program.metadata.replace(
            from_stage=until_stage,
        )
    )

def prepare_program(program: Program, sim_delays: dict[int, float]) -> tuple[Program, dict[int, float]]:
    cmd = program.command
    cmd = cmd.remove_noops()

    with pbutils.timeit('scheduling'):
        cmd, expected_ends = constraints.optimize(cmd)

    def AddSimDelays(cmd: commands.Command) -> commands.Command:
        if isinstance(cmd, commands.Meta):
            if sim_delay := sim_delays.get(cmd.metadata.id):
                return cmd.add(commands.Metadata(sim_delay=sim_delay))
        return cmd
    if sim_delays:
        cmd = cmd.transform(AddSimDelays)

    program = program.replace(command=cmd)
    return program, expected_ends

def simulate_program(program: Program, sim_delays: dict[int, float] = {}, log_filename: str | None=None) -> DB:
    program, expected_ends = prepare_program(program, sim_delays=sim_delays)
    cmd = program.command
    with pbutils.timeit('simulating'):
        config = simulate.replace(log_filename=log_filename)
        with make_runtime(config, program) as runtime_est:
            execute(cmd, runtime_est, Metadata())

    if not sim_delays:
        with pbutils.timeit('get simulation estimates'):
            states = runtime_est.log_db.get(CommandState).list()

        with pbutils.timeit('check schedule and simulation correspondence'):
            check_correspondence(cmd, states, expected_ends)

    return runtime_est.log_db

def execute_simulated_program(config: RuntimeConfig, sim_db: DB, metadata: list[DBMixin]):
    programs = sim_db.get(Program).list()
    if len(programs) == 0:
        raise ValueError(f'No program stored in {sim_db.con.filename}')
    elif len(programs) > 1:
        raise ValueError(f'More than one program stored in {sim_db.con.filename}')
    else:
        [program] = programs
    cmd = program.command

    if program.metadata.protocol == 'cell-paint':
        missing: list[BiotekCmd] = []
        for k, _v in estimates.guesses.items():
            if isinstance(k, BiotekCmd) and k.protocol_path:
                missing += [k]
        if missing:
            from pprint import pformat
            raise ValueError('Missing timings for the following biotek commands:\n' + pformat(missing))

    with make_runtime(config, program) as runtime:
        states = sim_db.get(CommandState).list()
        with runtime.log_db.transaction:
            for state in states:
                if isinstance(state.cmd, WaitForCheckpoint | Checkpoint | Idle):
                    continue
                state.state = 'planned'
                state.save(runtime.log_db)

        runtime_metadata = RuntimeMetadata(
            start_time     = runtime.start_time,
            config_name    = config.name,
            log_filename   = config.log_filename or ':memory:',
        )
        runtime_metadata = runtime_metadata.save(runtime.log_db)

        for data in metadata:
            data.save(runtime.log_db)

        cmd = program.command
        cmd = cmd.remove_scheduling_idles()
        with pbutils.timeit('execute'):
            execute(cmd, runtime, Metadata())

        runtime_metadata.completed = datetime.now()
        runtime_metadata = runtime_metadata.save(runtime.log_db)

        for line in runtime.get_log().group_durations_for_display():
            print(line)

def execute_program(config: RuntimeConfig, program: Program, metadata: list[DBMixin]=[], sim_delays: dict[int, float] = {}):
    db = simulate_program(program, sim_delays=sim_delays)
    execute_simulated_program(config, db, metadata)
