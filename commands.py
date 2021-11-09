from __future__ import annotations
from dataclasses import *
from typing import *

import abc
from moves import movelists, MoveList
import utils
from utils import Mutable

from symbolic import Symbolic
from runtime import Runtime
import bioteks
from bioteks import BiotekCommand
import incubator
import timings

from collections import defaultdict

class Command(abc.ABC):
    @abc.abstractmethod
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        raise NotImplementedError

    def est(self) -> float:
        raise ValueError(self.__class__)

    def required_resource(self) -> str | None:
        return None

    def with_metadata(self, metadata: dict[str, Any]={}, **metadata_kws: Any):
        metadata = {**metadata, **metadata_kws}
        if not metadata:
            return self
        elif isinstance(self, Meta) and metadata.keys().isdisjoint(self.metadata.keys()):
            return Meta(command=self.command, metadata={**metadata, **self.metadata})
        else:
            return Meta(command=self, metadata=metadata)

    def collect(self: Command) -> list[tuple[Command, dict[str, Any]]]:
        match self:
            case Seq():
                return [
                    tup
                    for cmd in self.commands
                    for tup in cmd.collect()
                ]
            case Meta():
                return [
                    (collected_cmd, {**self.metadata, **collected_metadata})
                    for collected_cmd, collected_metadata in self.command.collect()
                ]
            case _:
                return [(self, {})]

    def is_noop(self: Command) -> bool:
        match self:
            case Idle():
                try:
                    return not self.seconds.resolve()
                except KeyError:
                    return False
            case Seq():
                return all(cmd.is_noop() for cmd in self.commands)
            case Fork() | Meta():
                return self.command.is_noop()
            case _:
                return False

    def transform(self: Command, f: Callable[[Command], Command]) -> Command:
        '''
        Bottom-up transformation a la "Uniform boilerplate and list processing"
        (Mitchell & Runciman, 2007) https://dl.acm.org/doi/10.1145/1291201.1291208
        '''
        match self:
            case Seq():
                return f(self.replace(commands=[cmd.transform(f) for cmd in self.commands]))
            case Fork() | Meta():
                return f(self.replace(command=self.command.transform(f)))
            case _:
                return f(self)

    def universe(self: Command) -> Iterator[Command]:
        '''
        Universe of all subterms a la "Uniform boilerplate and list processing"
        (Mitchell & Runciman, 2007) https://dl.acm.org/doi/10.1145/1291201.1291208
        '''
        yield self
        match self:
            case Seq():
                for cmd in self.commands:
                    yield from cmd.universe()
            case Fork() | Meta():
                yield from self.command.universe()

    def make_resource_checkpoints(self: Command) -> Command:
        counts: dict[str, int] = defaultdict(int)
        def F(cmd: Command) -> Command:
            match cmd:
                case WaitForResource(resource=resource):
                    this = counts[resource]
                    this_name = f'{resource} #{counts[resource]}'
                    if this:
                        return WaitForCheckpoint(name=this_name, assume=cmd.assume, report_behind_time=False)
                    else:
                        return Sequence()
                case Fork(resource=resource):
                    assume = 'nothing'
                    match cmd.assume:
                        case 'busy':
                            assume = 'will wait'
                        case 'idle':
                            assume = 'no wait'
                    prev_wait = F(WaitForResource(resource, assume=assume))
                    counts[resource] += 1
                    this = counts[resource]
                    this_name = f'{resource} #{counts[resource]}'
                    return cmd.replace(
                        command=Sequence(
                            prev_wait,
                            cmd.command,
                            Checkpoint(this_name),
                        ),
                        thread_name=this_name,
                    )
                case _:
                    return cmd
        return self.transform(F)

    def assign_ids(self: Command, counter: Mutable[int] | None = None) -> Command:
        count = 0
        def F(cmd: Command) -> Command:
            nonlocal count
            match cmd:
                case Seq() | Fork() | Meta():
                    return cmd
                case _:
                    id = str(count)
                    count += 1
                    return cmd.with_metadata(id=id)
        return self.transform(F)

    def remove_scheduling_idles(self: Command) -> Command:
        def F(cmd: Command) -> Command:
            match cmd:
                case Idle(only_for_scheduling=True):
                    return Sequence()
                case _:
                    return Sequence(cmd)
        return self.transform(F)

    def remove_noops(self: Command) -> Command:
        def F(cmd: Command) -> Command:
            match cmd:
                case _ if cmd.is_noop():
                    return Sequence()
                case Seq():
                    return Sequence(*(c for c in cmd.commands if not c.is_noop()))
                case Fork() if all(isinstance(c, Meta | Checkpoint | Seq) for c in cmd.command.universe()):
                    return cmd.command.with_metadata({'thread_name': cmd.thread_name, 'resource': cmd.resource})
                case _:
                    return Sequence(cmd)
        return self.transform(F)

    def resolve(self: Command, env: dict[str, float]) -> Command:
        def F(cmd: Command) -> Command:
            match cmd:
                case Idle():
                    return cmd.replace(secs=cmd.seconds.resolve(env))
                case WaitForCheckpoint():
                    return cmd.replace(plus_secs=cmd.plus_seconds.resolve(env))
                case _:
                    return cmd
        return self.transform(F)

    def free_vars(self: Command) -> set[str]:
        out: set[str] = set()
        for cmd in self.universe():
            match cmd:
                case Idle():
                    out |= cmd.seconds.var_set()
                case WaitForCheckpoint():
                    out |= cmd.plus_seconds.var_set()
        return out

@dataclass(frozen=True, kw_only=True)
class Meta(Command):
    metadata: dict[str, Any]
    command: Command

    def est(self) -> float:
        return self.command.est()

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        self.command.execute(runtime, {**metadata, **self.metadata})

    def replace(self, command: Command):
        return command.with_metadata(self.metadata)

@dataclass(frozen=True)
class Seq(Command):
    commands: list[Command]

    def replace(self, commands: list[Command]):
        return replace(self, commands=commands)

    def est(self) -> float:
        return sum((cmd.est() for cmd in self.commands), 0.0)

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        for cmd in self.commands:
            cmd.execute(runtime, metadata)

def Sequence(*commands: Command) -> Command:
    flat: list[Command] = []
    for cmd in commands:
        match cmd:
            case Seq():
                flat += cmd.commands
            case _:
                flat += [cmd]
    if len(flat) == 1:
        return flat[0]
    return Seq(flat)

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
        secs = self.secs
        assert isinstance(secs, (float, int))
        with runtime.timeit('idle', str(secs), metadata):
            runtime.sleep(secs, metadata)

    def __add__(self, other: float | int | str | Symbolic) -> Idle:
        return self.replace(secs = self.seconds + other)

@dataclass(frozen=True)
class Checkpoint(Command):
    name: str
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.checkpoint(self.name, metadata=metadata)

WaitAssumption = Literal['nothing', 'will wait', 'no wait']

@dataclass(frozen=True)
class WaitForCheckpoint(Command):
    name: str
    plus_secs: Symbolic | float | int = 0.0
    report_behind_time: bool = True
    assume: WaitAssumption = 'will wait'

    @property
    def plus_seconds(self) -> Symbolic:
        return Symbolic.wrap(self.plus_secs)

    def replace(self, plus_secs: Symbolic | float | int | None = None, assume: WaitAssumption | None = None) -> WaitForCheckpoint:
        next = self
        if plus_secs is not None:
            next = replace(next, plus_secs=plus_secs)
        if assume is not None:
            next = replace(next, assume=assume)
        return next

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        plus_secs = self.plus_secs
        assert isinstance(plus_secs, (float, int))
        arg = f'{Symbolic.var(str(self.name)) + plus_secs}'
        with runtime.timeit('wait', arg, metadata):
            t0 = runtime.wait_for_checkpoint(self.name)
            desired_point_in_time = t0 + plus_secs
            delay = desired_point_in_time - runtime.monotonic()
            if delay < 1 and not self.report_behind_time:
                metadata = {**metadata, 'silent': True}
            runtime.sleep(delay, metadata)

    def __add__(self, other: float | int | str | Symbolic) -> WaitForCheckpoint:
        return self.replace(plus_secs=self.plus_seconds + other)

@dataclass(frozen=True)
class Duration(Command):
    name: str
    opt_weight: float = 0.0
    exactly: Symbolic | float | None = None

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        t0 = runtime.wait_for_checkpoint(self.name)
        runtime.log('end', 'duration', self.name, t0=t0, metadata=metadata)

ForkAssumption = Literal['nothing', 'busy', 'idle']

@dataclass(frozen=True)
class Fork(Command):
    command: Command
    resource: str
    thread_name: str | None = None
    assume: ForkAssumption = 'idle'

    def __post_init__(self):
        for cmd, _ in self.command.collect():
            assert not isinstance(cmd, WaitForResource) # only the main thread can wait for resources
            if self.resource is not None:
                assert cmd.required_resource() in {None, self.resource}

    def replace(self, command: Command, thread_name: str | None = None):
        if thread_name is not None:
            return replace(self, command=command, thread_name=thread_name)
        else:
            return replace(self, command=command)

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        thread_name = self.thread_name
        assert thread_name
        fork_metadata = {**metadata, 'thread': thread_name, 'resource': self.resource}
        @runtime.spawn
        def fork():
            runtime.register_thread(thread_name)
            self.command.execute(runtime, metadata=fork_metadata)
            runtime.thread_done()

    def est(self) -> float:
        raise ValueError('Fork.est')

    def delay(self, other: float | int | str | Symbolic) -> Fork:
        return self.replace(
            command = Sequence(
                Idle(Symbolic.wrap(other)),
                self.command,
            )
        )

@dataclass(frozen=True)
class WaitForResource(Command):
    '''
    only the main thread can wait for resources
    '''
    resource: str
    assume: WaitAssumption = 'nothing'

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        raise ValueError('Cannot execute WaitForResource, run Command.make_resource_checkpoints first')

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
    assume: ForkAssumption = 'nothing',
):
    return Fork(WashCmd(protocol_path, cmd), resource='wash', assume=assume)

def DispFork(
    protocol_path: str | None,
    cmd: BiotekCommand = 'Run',
    assume: ForkAssumption = 'nothing',
):
    return Fork(DispCmd(protocol_path, cmd), resource='disp', assume=assume)

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
    assume: ForkAssumption = 'nothing',
):
    return Fork(IncuCmd(action, incu_loc), resource='incu', assume=assume)

