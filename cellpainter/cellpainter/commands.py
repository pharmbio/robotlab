from __future__ import annotations
from dataclasses import *
from typing import *

from collections import defaultdict

import abc

from pbutils.mixins import ReplaceMixin, DBMixin

from .moves import movelists, Effect, World, effects, InitialWorld, MovePlate
from . import moves
from .symbolic import Symbolic
import pbutils

@dataclass(frozen=True)
class Metadata:
    id: int = 0

    batch_index: int = 0
    plate_id: str | None = None

    step: str = ''         # 'Mito'
    substep: str = ''      # 'incu -> B21'
    slot: int = 0          # 1               (for --visualize, derived from substep)
    section: str = ''      # 'Mito 0'        (f'{step} {batch_index}', for gui columns)
    stage: str = ''        # 'Mito, plate 1' (f'{step}, {plate_id}', for start from stage)

    thread_resource: str | None = None
    predispense: bool = False

    dry_run_sleep: bool = False

    est:        float | None = None
    sim_delay:  float | None = None

    gui_force_show: bool = False

    def merge(self, *others: Metadata) -> Metadata:
        repl: dict[str, Any] = {}
        for other in others:
            repl.update(pbutils.nub(other))
        out = replace(self, **repl)
        return out

class Command(abc.ABC):
    @property
    def type(self) -> str:
        return self.__class__.__name__

    def required_resource(self) -> Literal['robotarm', 'incu', 'wash', 'disp', 'blue'] | None:
        return None

    def add(self, m: Metadata):
        if isinstance(self, Meta):
            return Meta(command=self.command, metadata=self.metadata.merge(m))
        else:
            return Meta(command=self, metadata=m)

    def add_to_physical_commands(self, m: Metadata):
        def Add(cmd: Command):
            if isinstance(cmd, BiotekCmd | RobotarmCmd | IncuCmd):
                return cmd.add(m)
            else:
                return cmd
        return self.transform(Add)

    def transform_first_physical_command(self, f: Callable[[Command], Command]) -> tuple[Command, bool]:
        did_transform = False
        def F(cmd: Command):
            nonlocal did_transform
            if did_transform:
                return cmd
            elif isinstance(cmd, BiotekCmd | RobotarmCmd | IncuCmd):
                did_transform = True
                return f(cmd)
            else:
                return cmd
        return self.transform(F), did_transform

    def collect(self: Command) -> list[tuple[Command, Metadata]]:
        match self:
            case Seq_():
                return [
                    tup
                    for cmd in self.commands
                    for tup in cmd.collect()
                ]
            case Meta():
                return [
                    (collected_cmd, collected_metadata.merge(self.metadata))
                    for collected_cmd, collected_metadata in self.command.collect()
                ]
            case _:
                return [(self, Metadata())]

    def is_noop(self: Command) -> bool:
        match self:
            case Idle():
                return False
                s = self.seconds
                if s.var_names:
                    return False
                else:
                    return float(s.offset) == 0.0
            case Seq_():
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
            case Seq_():
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
            case Seq_():
                for cmd in self.commands:
                    yield from cmd.universe()
            case Fork() | Meta():
                yield from self.command.universe()
            case _:
                pass

    def stages(self: Command) -> list[str]:
        return list(
            pbutils.uniq(
                stage
                for cmd in self.universe()
                if isinstance(cmd, Meta)
                if (stage := cmd.metadata.stage)
            )
        )

    def checkpoints(self: Command) -> set[str]:
        return {
            cmd.name
            for cmd in self.universe()
            if isinstance(cmd, Checkpoint)
        }

    def make_resource_checkpoints(self: Command) -> Command:
        '''
        This removes all WaitForResource by turning them into WaitForCheckpoint
        plus makes the required Checkpoints.
        '''
        counts: dict[str, int] = defaultdict(int)
        taken = self.checkpoints()
        def F(cmd: Command) -> Command:
            match cmd:
                case WaitForResource(resource=resource):
                    this = counts[resource]
                    this_name = f'{resource} #{counts[resource]}'
                    if this_name in taken:
                        raise ValueError('Cannot run make_resource_checkpoints twice')
                    if this:
                        return WaitForCheckpoint(name=this_name, assume=cmd.assume)
                    else:
                        return Seq()
                case Fork(resource=resource):
                    assume = 'nothing'
                    match cmd.assume:
                        case 'busy':
                            assume = 'will wait'
                        case 'idle':
                            assume = 'no wait'
                        case 'nothing':
                            pass
                    if resource is None:
                        prev_wait = Idle()
                        counts['None'] += 1
                        this = counts['None']
                        this_name = f'None #{counts["None"]}'
                    else:
                        prev_wait = F(WaitForResource(resource, assume=assume))
                        counts[resource] += 1
                        this = counts[resource]
                        this_name = f'{resource} #{counts[resource]}'
                    if this_name in taken:
                        raise ValueError('Cannot run make_resource_checkpoints twice')
                    return cmd.replace(
                        command=Seq(
                            prev_wait,
                            cmd.command,
                            Checkpoint(this_name),
                        ),
                    )
                case _:
                    return cmd
        return self.transform(F)

    def next_id(self: Command) -> int:
        next = 0
        for cmd in self.universe():
            if isinstance(cmd, Meta) and (i := cmd.metadata.id):
                next = max(next, i + 1)
        return next

    def assign_ids(self: Command) -> Command:
        count = 1 + max((m.metadata.id for m in self.universe() if isinstance(m, Meta)), default=0)
        def F(cmd: Command) -> Command:
            nonlocal count
            match cmd:
                case Seq_() | Fork() | Meta():
                    return cmd
                case _:
                    count += 1
                    return cmd.add(Metadata(id=count))
        return self.transform(F)

    def remove_scheduling_idles(self: Command) -> Command:
        def F(cmd: Command) -> Command:
            match cmd:
                case Idle(only_for_scheduling=True):
                    return Seq()
                case _:
                    return Seq(cmd)
        return self.transform(F)

    def remove_noops(self: Command) -> Command:
        def F(cmd: Command) -> Command:
            match cmd:
                case _ if cmd.is_noop():
                    return Seq()
                case Seq_():
                    return Seq(*(c for c in cmd.commands if not c.is_noop()))
                case _:
                    return Seq(cmd)
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
                case _:
                    pass
        return out

    def effect(self) -> Effect | None:
        match self:
            case RobotarmCmd():
                return effects.get(self.program_name)
            case IncuCmd() if self.action == 'put' and self.incu_loc:
                return MovePlate(source='incu', target=self.incu_loc)
            case IncuCmd() if self.action == 'get' and self.incu_loc:
                return MovePlate(source=self.incu_loc, target='incu')
            case _:
                return None


@dataclass(frozen=True, kw_only=True)
class Meta(Command):
    command: Command
    metadata: Metadata = field(default_factory=lambda: Metadata())


    def replace(self, command: Command):
        return command.add(self.metadata)

@dataclass(frozen=True)
class Seq_(Command):
    commands: list[Command]

    def replace(self, commands: list[Command]):
        return replace(self, commands=commands)


def Seq(*commands: Command) -> Command:
    flat: list[Command] = []
    for cmd in commands:
        match cmd:
            case Seq_():
                flat += cmd.commands
            case _:
                flat += [cmd]
    if len(flat) == 1:
        return flat[0]
    return Seq_(flat)

@dataclass(frozen=True)
class Info(Command):
    msg: str = ''

@dataclass(frozen=True)
class Idle(Command):
    secs: Symbolic | float | int = 0.0
    only_for_scheduling: bool = False

    @property
    def seconds(self) -> Symbolic:
        return Symbolic.wrap(self.secs)

    def replace(self, secs: Symbolic | float | int) -> Idle:
        return replace(self, secs=secs)

    def __add__(self, other: float | int | str | Symbolic) -> Idle:
        return self.replace(secs = self.seconds + other)

@dataclass(frozen=True)
class Checkpoint(Command):
    name: str

WaitAssumption = Literal['nothing', 'will wait', 'no wait']

@dataclass(frozen=True)
class WaitForCheckpoint(Command):
    name: str
    plus_secs: Symbolic | float | int = 0.0
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

    def __add__(self, other: float | int | str | Symbolic) -> WaitForCheckpoint:
        return self.replace(plus_secs=self.plus_seconds + other)

@dataclass(frozen=True)
class Duration(Command):
    name: str # constraint since this reference checkpoint
    constraint: None | Max = None

@dataclass(frozen=True)
class Max:
    priority: int
    weight: float = 1

def Min(priority: int, weight: float = 1):
    return Max(priority, -weight)

ForkAssumption = Literal['nothing', 'busy', 'idle']

@dataclass(frozen=True)
class Fork(Command):
    command: Command
    assume: ForkAssumption = 'idle'

    @property
    def resource(self):
        for cmd, _ in self.command.collect():
            assert not isinstance(cmd, WaitForResource) # only the main thread can wait for resources
            if resource := cmd.required_resource():
                return resource
        return None

    def __post_init__(self):
        self_resource = self.resource
        for cmd, _ in self.command.collect():
            assert not isinstance(cmd, WaitForResource) # only the main thread can wait for resources
            if resource := cmd.required_resource():
                assert resource == self_resource

    def replace(self, command: Command):
        return replace(self, command=command)


    def delay(self, other: float | int | str | Symbolic) -> Fork:
        return self.replace(
            command = Seq(
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

@dataclass(frozen=True)
class RobotarmCmd(Command):
    program_name: str
    def __post_init__(self):
        assert self.program_name in movelists


    def required_resource(self):
        return 'robotarm'

BiotekAction = Literal[
    'Run',
    'Validate',
    'RunValidated',
    'TestCommunications',
]

@dataclass(frozen=True)
class BiotekCmd(Command):
    machine: Literal['wash', 'disp']
    action: BiotekAction
    protocol_path: str | None = None

    def required_resource(self):
        return self.machine

    def replace(self, action: BiotekAction):
        return replace(self, action=action)

def WashCmd(
    cmd: BiotekAction,
    protocol_path: str | None,
):
    return BiotekCmd('wash', cmd, protocol_path)

def DispCmd(
    cmd: BiotekAction,
    protocol_path: str | None,
):
    return BiotekCmd('disp', cmd, protocol_path)

def BiotekValidateThenRun(
    machine: Literal['wash', 'disp'],
    protocol_path: str,
) -> Command:
    return Seq(
        BiotekCmd(machine, 'Validate',     protocol_path),
        BiotekCmd(machine, 'RunValidated', protocol_path),
    )

def WashFork(
    protocol_path: str | None,
    cmd: BiotekAction,
    assume: ForkAssumption = 'nothing',
):
    return Fork(WashCmd(cmd, protocol_path), assume=assume)

def DispFork(
    protocol_path: str | None,
    cmd: BiotekAction,
    assume: ForkAssumption = 'nothing',
):
    return Fork(DispCmd(cmd, protocol_path), assume=assume)

BlueWashAction = Literal[
    'run_prog',
    'write_prog',
    'init_all',
    'get_balance_plate',
    'get_working_plate',
    'get_info',
]

@dataclass(frozen=True)
class BlueCmd(Command):
    action: BlueWashAction
    protocol_path: str | None = None

    def required_resource(self):
        return 'blue'

def BlueFork(
    action: BlueWashAction,
    protocol_path: str | None = None,
    assume: ForkAssumption = 'nothing',
):
    return Fork(BlueCmd(action, protocol_path), assume=assume)

def BlueWriteThenRun(
    protocol_path: str,
) -> Command:
    return Seq(
        BlueCmd('write_prog', protocol_path),
        BlueCmd('run_prog', protocol_path),
    )

@dataclass(frozen=True)
class IncuCmd(Command):
    action: Literal['put', 'get', 'get_status', 'reset_and_activate']
    incu_loc: str | None

    def required_resource(self):
        return 'incu'

def IncuFork(
    action: Literal['put', 'get', 'get_status', 'reset_and_activate'],
    incu_loc: str | None = None,
    assume: ForkAssumption = 'nothing',
):
    return Fork(IncuCmd(action, incu_loc), assume=assume)

@dataclass(frozen=True)
class Program(DBMixin):
    command: Command = field(default_factory=lambda: Seq())
    world0: World | None = None
    metadata: ProgramMetadata = field(default_factory=lambda: ProgramMetadata())
    doc: str = ''
    id: int = -1

@dataclass(frozen=True)
class ProgramMetadata(DBMixin):
    protocol: str = ''
    num_plates: int = 0
    batch_sizes: str = ''
    from_stage: str | None = None
    id: int = -1

pbutils.serializer.register(globals())
