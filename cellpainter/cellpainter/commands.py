from __future__ import annotations
from dataclasses import *
from typing import *

import abc

from pbutils.mixins import DBMixin, ReplaceMixin

from .moves import Effect, World, effects, MovePlate
from .symbolic import Symbolic
import pbutils

@dataclass(frozen=True)
class Metadata:
    id: int = 0

    batch_index: int = 0   # not really used
    plate_id: str | None = None

    step_desc: str = ''    # 'Mito, incu -> B21' (f'{step}, {substep}', for debugging)
    slot: int = 0          # 1                   (for --visualize, derived from substep)
    section: str = ''      # 'Mito 0'            (f'{step} {batch_index}', for gui columns)
    stage: str = ''        # 'Mito, plate 1'     (f'{step}, {plate_id}', for start from stage)

    thread_resource: str | None = None

    est:        float | None = None
    sim_delay:  float | None = None

    gui_force_show: bool = False

    def merge(self, *others: Metadata) -> Metadata:
        repl: dict[str, Any] = {}
        for other in others:
            repl.update(pbutils.nub(other))
        out = replace(self, **repl)
        return out

class Command(ReplaceMixin, abc.ABC):
    @property
    def type(self) -> str:
        return self.__class__.__name__

    def required_resource(self) -> str | None:
        return None

    def add(self, m: Metadata):
        if isinstance(self, Meta):
            return Meta(command=self.command, metadata=self.metadata.merge(m))
        else:
            return Meta(command=self, metadata=m)

    def __matmul__(self, m: Metadata):
        return self.add(m)

    def peel_meta(self) -> Command:
        if isinstance(self, Meta):
            return self.command.peel_meta()
        else:
            return self

    def __rshift__(self, other: Command) -> Command:
        return Seq(self, other)

    def fork(self, assume: ForkAssumption = 'idle', align: Literal['begin', 'end'] = 'begin') -> Fork:
        return Fork(self, assume=assume, align=align)

    def add_to_physical_commands(self, m: Metadata):
        def Add(cmd: Command):
            if isinstance(cmd, PhysicalCommand):
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
            elif isinstance(cmd, PhysicalCommand):
                did_transform = True
                return f(cmd)
            else:
                return cmd
        return self.transform(F), did_transform

    def collect(self: Command) -> list[tuple[Command, Metadata]]:
        match self:
            case SeqCmd():
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
            case SeqCmd():
                return all(cmd.is_noop() for cmd in self.commands)
            case Fork() | Meta():
                return self.command.is_noop()
            case _:
                return False

    def transform(self: Command, f: Callable[[Command], Command], reverse: bool=False) -> Command:
        '''
        Bottom-up transformation a la "Uniform boilerplate and list processing"
        (Mitchell & Runciman, 2007) https://dl.acm.org/doi/10.1145/1291201.1291208
        '''
        match self:
            case SeqCmd():
                inner_commands = self.commands
                if reverse:
                    inner_commands = list(reversed(inner_commands))
                inner_commands = [cmd.transform(f, reverse=reverse) for cmd in inner_commands]
                if reverse:
                    inner_commands = list(reversed(inner_commands))
                return f(self.replace(commands=inner_commands))
            case Fork() | Meta():
                return f(self.replace(command=self.command.transform(f, reverse=reverse)))
            case _:
                return f(self)

    def universe(self: Command) -> Iterator[Command]:
        '''
        Universe of all subterms a la "Uniform boilerplate and list processing"
        (Mitchell & Runciman, 2007) https://dl.acm.org/doi/10.1145/1291201.1291208
        '''
        yield self
        match self:
            case SeqCmd():
                for cmd in self.commands:
                    yield from cmd.universe()
            case Fork() | Meta():
                yield from self.command.universe()
            case _:
                pass

    def push_metadata_into_forks(self) -> Command:
        res: list[Command] = []
        for cmd, meta in self.collect():
            if isinstance(cmd, Fork):
                res += [cmd.replace(command=cmd.command.add(meta))]
            else:
                res += [cmd.add(meta)]
        return Seq(*res)

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
        counts: dict[str, int] = DefaultDict(int)
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
                        prev_wait = Seq()
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

    def align_forks(self: Command) -> Command:
        '''
        Makes Fork with align='end' become Fork with align='begin' by gluing
        them on to the previous Fork of that resource.
        '''
        residuals: dict[str, list[Command]] = DefaultDict(list)
        count: int = 0
        ref_name = f'residue t0'
        def F(cmd: Command) -> Command:
            nonlocal count
            match cmd:
                case Fork():
                    resource = cmd.resource
                    if resource is None:
                        assert cmd.align == 'begin'
                        return cmd
                    elif cmd.align == 'end':
                        count += 1
                        name_wait = f'align {count}'
                        name_sync = f'align sync {count}'
                        name_sync_wait = f'align sync wait {count}'
                        residuals[resource] += [
                            Seq(
                                Checkpoint(name_wait),
                                # # not sure which one is best here:
                                # WaitForCheckpoint(ref_name, assume='nothing') + f'{name_wait} wait',
                                WaitForCheckpoint(name_wait, assume='nothing') + f'{name_wait} wait',
                                Duration(name_wait, Max(priority=-2)),
                                cmd.command,
                                Checkpoint(name_sync),
                            )
                        ]
                        return Seq(
                            Checkpoint(name_sync_wait),
                            WaitForCheckpoint(name_sync, assume='nothing') + f'{name_sync} wait',
                            Duration(name_sync_wait, Min(priority=-1)),
                        )
                    elif not residuals[resource]:
                        return cmd
                    else:
                        residue = residuals[resource]
                        residuals[resource] = []
                        return cmd.replace(
                            command=Seq(
                                cmd.command,
                                *reversed(residue),
                            ),
                        )
                case _:
                    return cmd
        res = self.push_metadata_into_forks().transform(F, reverse=True)
        for _resource, residue in residuals.items():
            if residue:
                res = Fork(Seq(*reversed(residue))) >> res
            # assert not cmds, f'{resource} has end-aligned commands but no begin-aligned Fork to attach them to ({cmds=})'
        return Checkpoint(ref_name) >> res

    def next_id(self: Command) -> int:
        next = 0
        for cmd in self.universe():
            if isinstance(cmd, Meta) and (i := cmd.metadata.id):
                next = max(next, i + 1)
        return next

    def assign_ids(self: Command) -> Command:
        count = self.next_id()
        def F(cmd: Command) -> Command:
            nonlocal count
            match cmd:
                case SeqCmd() | Fork() | Meta():
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
                case SeqCmd():
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

class PhysicalCommand(Command, abc.ABC):
    def normalize(self) -> PhysicalCommand:
        return self

@dataclass(frozen=True, kw_only=True)
class Meta(Command):
    command: Command = field(default_factory=lambda: Noop())
    metadata: Metadata = field(default_factory=lambda: Metadata())

@dataclass(frozen=True)
class SeqCmd(Command):
    commands: list[Command]

Noop = lambda: SeqCmd([])

def Seq(*commands: Command) -> Command:
    flat: list[Command] = []
    for cmd in commands:
        match cmd:
            case SeqCmd():
                flat += cmd.commands
            case _:
                flat += [cmd]
    if len(flat) == 1:
        return flat[0]
    return SeqCmd(flat)

@dataclass(frozen=True)
class Idle(Command):
    secs: Symbolic | float | int = 0.0
    only_for_scheduling: bool = False

    @property
    def seconds(self) -> Symbolic:
        return Symbolic.wrap(self.secs)

    def __add__(self, other: float | int | str | Symbolic) -> Idle:
        return self.replace(secs = self.seconds + other)

@dataclass(frozen=True)
class Checkpoint(Command):
    name: str

WaitAssumption = Literal['nothing', 'will wait', 'no wait']

@dataclass(frozen=True)
class WaitForCheckpoint(Command):
    name: str = ''
    plus_secs: Symbolic | float | int = 0.0
    assume: WaitAssumption = 'will wait'

    @property
    def plus_seconds(self) -> Symbolic:
        return Symbolic.wrap(self.plus_secs)

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

    def negate(self):
        return Max(self.priority, -self.weight)

def Min(priority: int, weight: float = 1):
    return Max(priority, weight).negate()

ForkAssumption = Literal['nothing', 'busy', 'idle']

@dataclass(frozen=True)
class Fork(Command):
    command: Command
    assume: ForkAssumption = 'idle'
    # assume: ForkAssumption = 'nothing'
    align: Literal['begin', 'end'] = 'begin'

    @property
    def resource(self):
        for cmd, _ in self.command.collect():
            assert not isinstance(cmd, WaitForResource) # only the main thread can wait for resources
            if resource := cmd.required_resource():
                return resource
        return None

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
class RobotarmCmd(PhysicalCommand):
    program_name: str

    def required_resource(self):
        return 'robotarm'

BiotekAction = Literal[
    'Run',
    'Validate',
    'RunValidated',
    'TestCommunications',
]

@dataclass(frozen=True)
class BiotekCmd(PhysicalCommand):
    machine: Literal['wash', 'disp']
    action: BiotekAction
    protocol_path: str | None = None

    def required_resource(self):
        return self.machine

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

def ValidateThenRun(
    machine: Literal['wash', 'disp', 'blue'],
    protocol_path: str,
) -> Command:
    if machine == 'blue':
        return Seq(
            BlueCmd('Validate',     protocol_path),
            BlueCmd('RunValidated', protocol_path),
        )
    else:
        return Seq(
            BiotekCmd(machine, 'Validate',     protocol_path),
            BiotekCmd(machine, 'RunValidated', protocol_path),
        )

BlueWashAction = Union[
    BiotekAction,
    Literal[
        'reset_and_activate',
        'get_working_plate',
    ],
]

@dataclass(frozen=True)
class BlueCmd(PhysicalCommand):
    action: BlueWashAction
    protocol_path: str | None = None

    def required_resource(self):
        return 'blue'

@dataclass(frozen=True)
class IncuCmd(PhysicalCommand):
    action: Literal['put', 'get', 'get_status', 'reset_and_activate']
    incu_loc: str | None = None

    def normalize(self):
        return IncuCmd(action=self.action, incu_loc=None)

    def required_resource(self):
        return 'incu'

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

'''

Delay from relative time better than idle:

    - Prime
    - Mix, align=end
    - Dispense
    - Mix, align=end
    - Dispense

    becomes

    - Fork (Prime >> Idle(X) >> Mix)
    - Fork (Dispense >> Idle(Y) >> Mix)
    - Fork (Dispense)

    If the Dispense estimate is too low (takes longer in reality),
    we will also wait for the fixed Idle time before Validating.
    Better to use WaitForCheckpoint relative to some reference time such as batch start:

    - Checkpoint(ref)
    - Fork (Prime >> WaitForCheckpoint(ref + X) >> Mix)
    - Fork (Dispense >> WaitForCheckpoint(ref + Y) >> Mix)
    - Fork (Dispense)

    Same example. If Dispense estimate is too low (takes shorter in reality),
    we will wait the correct amount of time!

Delay from relative time better than from zero:

    Consider a few steps A B C and B takes shorter time than expected, and
    C could start whenever everything is ready before it.
    The times inside C should be relative to its start so its internal times
    are correct. It should not reference times from A or B (such as time zero).



With implicit enqueue:

    fork (a; b) = fork a; fork b

Without

    fork (a; b) = wait for resource; fork a; wait for resource; fork b

Am I ever using the implicit enqueue?
If you need it you could do align='end' and slap on an Idle
The more surprising choise is to use implict queue.

Preforking and min/max

    x || a
    prefork b
    y

-->

    x || a
         sleep d
         b
    wait
    y

Highest prio is to minimize the wait to start y, and with lower priority
postpone starting b as late as possible.

    x || a
         max(sleep d, prio=low)
         b
    min(wait, prio=high)
    y


    min x -> checkpoint c
             x
             wait for c + d
             min duration c


'''

'''

    primitives:

        physical commands
        checkpoint
        wait for checkpoint
        fork
        seq
        (duration)
        (meta)

    removables:

        prefork
        wait for resource
        maximize/minimize
        sleep
        (free variables)

    with one fork per resource:
        list[
            | physical commands
            | checkpoint
            | wait for checkpoint
        ]

    now the main thread is allowed to run the robotarm, but it would be
    symmetric if it did fork for each robotarm.


        prefork b21-to-disp <- new idea, is this useful?
        prefork prime
        fork disp


    make this simpler for presentation and testing:

        assign estimates to commands

        shrink all estimates by X to see why scheduling failed
            - deadlock or similar: can never be scheduled
            - to much to do: can report how much shorter physical commands
                             would have to be for successfull schedule
                    guess: last wash needs to be reduced (130s -> 95s) to schedule these plates

        change simulation delay easily, perhaps add name to metadata

    review:
        start from stage semantics

'''

def SCRATCH():
    def maximize(name: str, m: Max, cmd: Command):
        return Seq(
            Checkpoint(name),
            cmd,
            WaitForCheckpoint(name) + f'{name} delay',
            Duration(name, m)
        )

    def maximize_since(name: str, m: Max, cmd: Command):
        return Seq(
            Checkpoint(name),
            cmd,
            WaitForCheckpoint(name) + f'{name} delay',
            Duration(name, m)
        )

    @dataclass
    class Maximize(Command):
        command: Command
        priority: int
        weight: float = 1

    def Minimize(
        command: Command,
        priority: int,
        weight: float = 1,
    ) -> Command:
        return Maximize(command, priority, weight=-weight)

    def transform_maximize(self: Command):
        count = 0
        def F(cmd: Command) -> Command:
            nonlocal count
            if isinstance(cmd, Maximize):
                count += 1
                name = f'max {count}'
                return Seq(
                    Checkpoint(name),
                    cmd.command,
                    WaitForCheckpoint(name) + f'{name} delay',
                    Duration(name, Max(priority=cmd.priority, weight=cmd.weight))
                )
            else:
                return cmd
        return self.transform(F)

    def test():
        cmds = [
            RobotarmCmd('B21-to-blue prep'),

            Fork(BlueCmd('Run', 'prime'), align='end'),

            RobotarmCmd('B21-to-blue transfer'),

            Fork(BlueCmd('Validate', 'wash'), align='end'),

            Fork(BlueCmd('RunValidated', 'wash')),

            WaitForResource('blue'),

            RobotarmCmd('B21-to-blue return'),
        ]
        cmds

@dataclass(frozen=True)
class PFCmd(PhysicalCommand):
    '''
    Run a program on the robotarm.
    '''
    program_name: str
    def required_resource(self):
        return 'pf'

class SquidABC(PhysicalCommand, abc.ABC):
    def required_resource(self):
        return 'squid'

@dataclass(frozen=True)
class SquidAcquire(SquidABC):
    config_path: str
    project: str
    plate: str
    def normalize(self):
        return SquidAcquire(config_path=self.config_path, project='', plate='')

@dataclass(frozen=True)
class SquidStageCmd(SquidABC):
    action: Literal['goto_loading', 'leave_loading']

class FridgeABC(PhysicalCommand, abc.ABC):
    def required_resource(self):
        return 'fridge'

@dataclass(frozen=True)
class FridgeInsert(FridgeABC):
    '''
    Puts a plate with a known project on some empty location using the barcode reader
    '''
    project: str
    expected_barcode: str | None = None

    def normalize(self):
        return FridgeInsert('')

@dataclass(frozen=True)
class FridgeEject(FridgeABC):
    plate: str
    project: str

    def normalize(self):
        return FridgeEject('', '')

@dataclass(frozen=True)
class FridgeCmd(FridgeABC):
    action: Literal['get_status', 'reset_and_activate']

@dataclass(frozen=True)
class BarcodeClear(PhysicalCommand):
    '''
    Clears the last seen barcode from the barcode reader memory
    '''
    pass

LockName = Literal['PF and Fridge', 'Squid', 'Nikon']

@dataclass(frozen=True)
class AcquireLock(Command):
    name: LockName

@dataclass(frozen=True)
class ReleaseLock(Command):
    name: LockName

def WithLock(name: LockName, cmd: Command | list[Command]) -> Command:
    if isinstance(cmd, list):
        cmd = Seq(*cmd)
    return Seq(
        AcquireLock(name),
        cmd,
        ReleaseLock(name),
    )
