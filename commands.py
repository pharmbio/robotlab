from __future__ import annotations
from dataclasses import *
from typing import *

from datetime import datetime, timedelta
from urllib.request import urlopen

import abc
from moves import movelists, MoveList
from robotarm import Robotarm
import utils
from utils import Mutable

from symbolic import Symbolic
from runtime import Runtime, RuntimeConfig
import bioteks
from bioteks import BiotekCommand
import incubator
import timings

from queue import Queue

class Command(abc.ABC):
    @abc.abstractmethod
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        return NotImplementedError

    def est(self) -> float:
        raise ValueError(self.__class__)

    def required_resource(self) -> str | None:
        return None

    def vars_of(self) -> set[str]:
        return set()

@dataclass(frozen=True)
class Idle(Command):
    secs: Symbolic | float | int = 0.0
    only_for_scheduling: bool = False

    @property
    def seconds(self) -> Symbolic:
        return Symbolic.wrap(self.secs)

    def replace(self, secs: Symbolic | float | int) -> Idle:
        return replace(self, secs=secs)

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        if self.only_for_scheduling and not runtime.execute_scheduling_idles:
            return
        secs = self.secs
        assert isinstance(secs, (float, int))
        with runtime.timeit('idle', str(secs), metadata):
            runtime.sleep(secs, metadata)

    def __add__(self, other: float | int | str | Symbolic) -> Idle:
        return self.replace(secs = self.seconds + other)

    def vars_of(self) -> set[str]:
        return self.seconds.vars_of()

@dataclass(frozen=True)
class Checkpoint(Command):
    name: str
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.checkpoint(self.name, metadata=metadata)

@dataclass(frozen=True)
class WaitForCheckpoint(Command):
    name: str
    plus_secs: Symbolic | float | int = 0.0
    flexible: bool = False
    report_behind_time: bool = True

    @property
    def plus_seconds(self) -> Symbolic:
        return Symbolic.wrap(self.plus_secs)

    def replace(self, plus_secs: Symbolic | float | int) -> WaitForCheckpoint:
        return replace(self, plus_secs=plus_secs)

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        plus_secs = self.plus_secs
        assert isinstance(plus_secs, (float, int))
        arg = f'{Symbolic.var(str(self.name)) + plus_secs}'
        with runtime.timeit('wait', arg, metadata):
            t0 = runtime.wait_for_checkpoint(self.name)
            desired_point_in_time = t0 + plus_secs
            delay = desired_point_in_time - runtime.monotonic()
            if delay < 0 and not self.report_behind_time:
                metadata = {**metadata, 'silent': True}
            runtime.sleep(delay, metadata) # if plus seconds = 0 don't report behind time ... ?

    def __add__(self, other: float | int | str | Symbolic) -> WaitForCheckpoint:
        return self.replace(self.plus_seconds + other)

    def vars_of(self) -> set[str]:
        return self.plus_seconds.vars_of()

@dataclass(frozen=True)
class Duration(Command):
    name: str
    opt_weight: float = 0.0

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        t0 = runtime.wait_for_checkpoint(self.name)
        runtime.log('end', 'duration', self.name, t0=t0, metadata=metadata)

@dataclass(frozen=True)
class Fork(Command):
    '''
    if flexible the resource may be occupied and it will wait until it's free
    '''
    commands: list[Command]
    resource: str
    flexible: bool = False
    thread_name: str | None = None

    def __post_init__(self):
        for cmd in self.commands:
            assert not isinstance(cmd, WaitForResource) # only the main thread can wait for resources
            if self.resource is not None:
                assert cmd.required_resource() in {None, self.resource}

    def replace(self, commands: list[Command], thread_name: str | None = None) -> Fork:
        if thread_name is not None:
            return replace(self, commands=commands, thread_name=thread_name)
        else:
            return replace(self, commands=commands)

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        thread_name = self.thread_name
        assert thread_name
        fork_metadata = {**metadata, 'thread': thread_name}
        @runtime.spawn
        def fork():
            runtime.register_thread(thread_name)
            for cmd in self.commands:
                assert not isinstance(cmd, RobotarmCmd)
                cmd.execute(runtime, metadata=fork_metadata)
            runtime.thread_done()

    def est(self) -> float:
        raise ValueError('Fork.est')

    def vars_of(self) -> set[str]:
        return {
            v
            for c in self.commands
            for v in c.vars_of()
        }

    def __add__(self, other: float | int | str | Symbolic) -> Fork:
        return Fork(
            [Idle(Symbolic.wrap(other)), *self.commands],
            resource=self.resource,
            flexible=self.flexible,
        )

@dataclass(frozen=True)
class WaitForResource(Command):
    '''
    only the main thread can wait for resources
    '''
    resource: str
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        with runtime.timeit('wait', self.resource, metadata=metadata):
            runtime.wait_for_resource(self.resource)

@dataclass(frozen=True)
class RobotarmCmd(Command):
    program_name: str
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        with runtime.timeit('robotarm', self.program_name, metadata):
            if runtime.config.robotarm_mode == 'noop':
                runtime.sleep(self.est(), {**metadata, 'silent': True})
            else:
                movelist = MoveList(movelists[self.program_name])
                arm = runtime.get_robotarm(include_gripper=movelist.has_gripper())
                arm.execute_moves(movelist, name=self.program_name)
                arm.close()

    def est(self) -> float:
        return timings.estimate('robotarm', self.program_name)

    def required_resource(self):
        return 'robotarm'

@dataclass(frozen=True)
class BiotekCmd(Command):
    machine: Literal['wash', 'disp']
    protocol_path: str | None
    cmd: BiotekCommand = 'Run'
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        bioteks.execute(runtime, self.machine, self.protocol_path, self.cmd, metadata)

    def est(self):
        if self.cmd == 'TestCommunications':
            log_arg: str = self.cmd
        else:
            assert self.protocol_path, self
            log_arg: str = self.cmd + ' ' + self.protocol_path
        return timings.estimate(self.machine, log_arg)

    def required_resource(self):
        return self.machine

def WashCmd(
    protocol_path: str | None,
    cmd: BiotekCommand = 'Run',
):
    return BiotekCmd('wash', protocol_path, cmd)

def DispCmd(
    protocol_path: str | None,
    cmd: BiotekCommand = 'Run',
):
    return BiotekCmd('disp', protocol_path, cmd)

def WashFork(
    protocol_path: str | None,
    cmd: BiotekCommand = 'Run',
    flexible: bool = False,
):
    return Fork([WashCmd(protocol_path, cmd)], resource='wash', flexible=flexible)

def DispFork(
    protocol_path: str | None,
    cmd: BiotekCommand = 'Run',
    flexible: bool = False,
):
    return Fork([DispCmd(protocol_path, cmd)], resource='disp', flexible=flexible)

@dataclass(frozen=True)
class IncuCmd(Command):
    action: Literal['put', 'get', 'get_climate']
    incu_loc: str | None
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        incubator.execute(runtime, self.action, self.incu_loc, metadata=metadata)

    def est(self):
        return timings.estimate('incu', self.action)

    def required_resource(self):
        return 'incu'

def IncuFork(
    action: Literal['put', 'get', 'get_climate'],
    incu_loc: str | None,
    flexible: bool = False,
):
    return Fork([IncuCmd(action, incu_loc)], resource='incu', flexible=flexible)

from collections import defaultdict

def Resolve(cmds: list[Command], env: dict[str, float]) -> list[Command]:
    out: list[Command] = []
    for cmd in cmds:
        match cmd:
            case Idle():
                out += [cmd.replace(secs=cmd.seconds.resolve(env))]
            case WaitForCheckpoint():
                out += [cmd.replace(plus_secs=cmd.plus_seconds.resolve(env))]
            case Fork(commands):
                out += [cmd.replace(commands=Resolve(commands, env))]
            case _:
                out += [cmd]
    return out

def MakeResourceCheckpoints(cmds: list[Command], counts: dict[str, int] | None = None) -> list[Command]:
    if counts is None:
        counts = defaultdict(int)
    out: list[Command] = []
    for cmd in cmds:
        match cmd:
            case WaitForResource(resource):
                this = counts[resource]
                this_name = f'{resource} #{counts[resource]}'
                if this:
                    out += [WaitForCheckpoint(name=this_name, flexible=False)]
            case Fork(commands, resource, flexible):
                prev_wait = MakeResourceCheckpoints([WaitForResource(resource)], counts)
                counts[resource] += 1
                this = counts[resource]
                this_name = f'{resource} #{counts[resource]}'
                out += [
                    cmd.replace(
                        commands=[
                            *prev_wait,
                            *MakeResourceCheckpoints(commands, counts),
                            Checkpoint(this_name),
                        ],
                        thread_name=this_name,
                    )
                ]
            case _:
                out += [cmd]
    return out

def RemoveNoopIdles(cmds: list[Command]) -> list[Command]:
    out: list[Command] = []
    for cmd in cmds:
        match cmd:
            case Idle(only_for_scheduling=True):
                continue
            case Idle() if not cmd.seconds.resolve():
                continue
            case Fork(commands):
                out += [cmd.replace(commands=RemoveNoopIdles(commands))]
            case _:
                out += [cmd]
    return out

def FreeVars(cmds: list[Command]) -> set[str]:
    out: set[str] = set()
    for cmd in cmds:
        match cmd:
            case Idle():
                out |= cmd.seconds.vars_of()
            case WaitForCheckpoint():
                out |= cmd.plus_seconds.vars_of()
            case Fork():
                out |= FreeVars(cmd.commands)
    return out
