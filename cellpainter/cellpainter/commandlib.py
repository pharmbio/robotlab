from __future__ import annotations
from dataclasses import *
from typing import *

import pbutils

from .commands import *
from . import commands
from . import moves
from . import constraints

def quicksim(program: Command, checkpoints: dict[str, float], estimate: Callable[[Command], float]):
    checkpoints = checkpoints.copy()

    @dataclass
    class Thread:
        todo: list[tuple[Command, Metadata]]
        running: tuple[Command, float] | None = None

    t_end: dict[int, float] = {}

    def advance_thread(t: float, thread: Thread) -> list[Thread]:
        match thread.running:
            case cmd, d:
                if d < -1e-6:
                    raise Exception('internal error: command should already have returned')
                elif d < 1e-6:
                    if isinstance(cmd, Meta):
                        t_end[cmd.metadata.id] = t
                    thread.running = None
                else:
                    return [thread]
            case _:
                pass
        if not thread.todo:
            return []
        (hd, meta), *tl = thread.todo
        match hd:
            case Checkpoint():
                checkpoints[hd.name] = t
                t_end[meta.id] = t
                thread.todo = tl
                return advance_thread(t, thread)
            case WaitForCheckpoint():
                checkpoint_t = checkpoints.get(hd.name)
                if checkpoint_t is None:
                    # blocked, waiting for checkpoint
                    return [thread]
                else:
                    thread.todo = tl
                    desired_t = checkpoint_t + hd.plus_seconds.unwrap()
                    thread.running = hd.add(meta), max(0.0, desired_t - t)
                    # "running" sleep
                    return [thread]
            case Fork():
                thread.todo = tl
                return [
                    *advance_thread(t, thread),
                    *advance_thread(t, Thread(hd.command.collect()))
                ]
            case Idle():
                thread.todo = tl
                thread.running = hd.add(meta), hd.seconds.unwrap()
                # running pseudo-physical command (these could be replaced with checkpoint...wait)
                return [thread]
            case Duration() | AcquireLock() | ReleaseLock():
                # nothing to do
                t_end[meta.id] = t
                thread.todo = tl
                return advance_thread(t, thread)
            case PhysicalCommand():
                # print(hd)
                thread.todo = tl
                est = estimate(hd)
                thread.running = hd.add(meta), est
                # running physical command
                return [thread]
            case _:
                raise ValueError(f'No case for cmd={hd}')

    def go(t: float, threads: list[Thread]) -> None:
        while True:
            # advance as much as possible
            while True:
                c0 = checkpoints.copy()
                new_threads: list[Thread] = []
                for thread in threads:
                    new_threads += advance_thread(t, thread)
                threads = new_threads
                if c0 == checkpoints:
                    break
            if not threads:
                return # done
            # pick the one closest in time
            candidates: list[float] = []
            for thread in threads:
                match thread.running:
                    case cmd, d:
                        candidates += [d]
                    case None:
                        pass
            if not candidates:
                raise ValueError('Threads blocked indefinitely')
            step_t = min(candidates)
            for thread in threads:
                match thread.running:
                    case cmd, d:
                        thread.running = cmd, d - step_t
                    case None:
                        pass
            t = round(t + step_t, 3)

    main = Thread(program.collect())

    go(0, [main])

    return t_end, checkpoints

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

def sleek_program(program: Command) -> Command:
    def get_movelist(cmd_and_metadata: tuple[Command, Metadata]) -> moves.MoveList | None:
        cmd, _ = cmd_and_metadata
        if isinstance(cmd, RobotarmCmd):
            if cmd.program_name in moves.sleeking_not_allowed:
                return None
            else:
                return moves.movelists.get(cmd.program_name)
        else:
            return None
    def pair_ok(cmd_and_metadata1: tuple[Command, Metadata], cmd_and_metadata2: tuple[Command, Metadata]) -> bool:
        _, m1 = cmd_and_metadata1
        _, m2 = cmd_and_metadata2
        p1 = m1.plate_id
        p2 = m2.plate_id
        return p1 == p2
    return Seq(
        *[
            cmd.add(metadata)
            for cmd, metadata
            in moves.sleek_movements(program.collect(), get_movelist, pair_ok)
        ]
    )

def prepare_program(program: Program, sim_delays: dict[int, float]) -> tuple[Program, dict[int, float]]:
    cmd = program.command
    cmd = sleek_program(cmd)
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

def check_correspondence(command: Command, **ends: dict[int, float]):
    by_id: dict[int, Command] = {
        i: c
        for c in command.universe()
        if isinstance(c, Meta)
        if (i := c.metadata.id)
    }

    mismatches = 0

    for a, b in pbutils.iterate_with_next(list(ends.items())):
        if b is None:
            continue
        src_a, ends_a = a
        src_b, ends_b = b

        for k in sorted({*ends_a.keys(), *ends_b.keys()}):
            end_a = round(ends_a.get(k, -1), 0)
            end_b = round(ends_b.get(k, -1), 0)
            if end_a == -1: end_a = 'missing'
            if end_b == -1: end_b = 'missing'
            if end_a != end_b:
                cmd = by_id.get(k)
                if cmd and isinstance(cmd.peel_meta(), AcquireLock | ReleaseLock):
                    pass
                else:
                    pbutils.pr({src_a: end_a, src_b: end_b, 'cmd': cmd})
                    mismatches += 1
                # if not cmd or not isinstance(cmd.peel_meta(), Checkpoint):

    if mismatches:
        raise ValueError(f'Correspondence check failed {mismatches=} ({" ".join(ends.keys())})')

def SCRATCH():

    def Transform(x: Any, F: Callable[[Any], Any]) -> Any:
        if is_dataclass(x):
            d = {}
            for f in fields(x):
                d[f.name] = Transform(getattr(x, f.name), F)
            return F(x.__class__(**d))
        elif isinstance(x, dict):
            return F({k: Transform(v, F) for k, v in cast(Any, x.items())})
        elif isinstance(x, list):
            return F([Transform(v, F) for v in cast(Any, x)])
        else:
            return F(x)

    def program_nub(p: Command) -> Command:
        def F1(cmd: Command):
            match cmd:
                case Meta() | Fork():
                    return cmd.command
                case SeqCmd():
                    return Seq(*cmd.commands)
                case _:
                    return cmd
        def F2(cmd: Command):
            match cmd:
                case SeqCmd():
                    return cmd.commands
                case _:
                    return cmd
        return Transform(Transform(p, F1), F2)

