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

    def source(self) -> str:
        return self.__class__.__name__.removesuffix('_cmd')

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

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        if self.only_for_scheduling and not runtime.execute_scheduling_idles:
            return
        seconds = self.seconds.resolve(runtime.var_values)
        if seconds == 0.0:
            return
        with runtime.timeit('idle', str(self.secs), metadata):
            runtime.sleep(seconds)

    def __add__(self, other: float | int | str | Symbolic) -> Idle:
        return Idle(self.seconds + other, only_for_scheduling=self.only_for_scheduling)

    def vars_of(self) -> set[str]:
        return set(self.seconds.var_names)

@dataclass(frozen=True)
class Checkpoint(Command):
    name: str
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.checkpoint(self.name, metadata=metadata)

@dataclass(frozen=True)
class WaitForCheckpoint(Command):
    name: str
    plus_seconds: Symbolic = Symbolic.const(0)
    flexible: bool = False

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        arg = f'{Symbolic.var(str(self.name)) + self.plus_seconds}'
        with runtime.timeit('wait', arg, metadata):
            t0 = runtime.wait_for_checkpoint(self.name)
            plus_seconds = self.plus_seconds.resolve(runtime.var_values)
            desired_point_in_time = t0 + plus_seconds
            delay = desired_point_in_time - runtime.monotonic()
            runtime.log('info', 'wait', f'sleeping for {round(delay, 2)}s', metadata)
            runtime.sleep(delay)

    def __add__(self, other: float | int | str | Symbolic) -> WaitForCheckpoint:
        return WaitForCheckpoint(
            name=self.name,
            plus_seconds=self.plus_seconds + other,
            flexible=self.flexible,
        )

    def vars_of(self) -> set[str]:
        return set(self.plus_seconds.var_names)


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

    def __post_init__(self):
        for cmd in self.commands:
            assert not isinstance(cmd, WaitForResource) # only the main thread can wait for resources
            if self.resource is not None:
                assert cmd.required_resource() in {None, self.resource}

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        q, name = runtime.enqueue_for_resource_production(self.resource)
        fork_metadata = {**metadata, 'origin': name}
        @runtime.spawn
        def fork():
            runtime.register_thread(name)
            with runtime.timeit('wait', self.resource, metadata=fork_metadata):
                runtime.queue_get(q)
            for cmd in self.commands:
                assert not isinstance(cmd, RobotarmCmd)
                cmd.execute(runtime, metadata=fork_metadata)
            runtime.checkpoint(name, metadata=fork_metadata)
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
                runtime.sleep(self.est())
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

    def source(self) -> str:
        return self.machine

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

def test_comm(config: RuntimeConfig):
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    print('Testing communication with robotarm, washer, dispenser and incubator.')
    runtime = Runtime(config=config)
    cmds = [
        DispFork(cmd='TestCommunications', protocol_path=None),
        IncuFork(action='get_climate', incu_loc=None),
        RobotarmCmd('noop'),
        WaitForResource('disp'),
        WashCmd(cmd='TestCommunications', protocol_path=None),
        WaitForResource('incu'),
    ]
    for cmd in cmds:
        cmd.execute(runtime, {})
    print('Communication tests ok.')

