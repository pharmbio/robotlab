from __future__ import annotations
from dataclasses import *
from typing import *

from datetime import datetime, timedelta
from urllib.request import urlopen

import abc
import json
import re
import socket
import time
import threading
import traceback
from queue import SimpleQueue
from contextlib import contextmanager
from threading import RLock

from moves import movelists
from robotarm import Robotarm
import utils
from utils import Mutable

import timelike
from timelike import Timelike, WallTime, SimulatedTime
from collections import defaultdict

Estimated = tuple[Literal['wash', 'disp', 'robotarm', 'incu'], str]

def estimates_from(path: str) -> dict[Estimated, float]:
    ests: dict[Estimated, list[float]] = defaultdict(list)
    sources = {
        'wash',
        'disp',
        'robotarm',
        'incu',
    }
    for v in utils.read_json_lines(path):
        duration = v.get('duration')
        source = v.get('source')
        arg = v.get('arg')
        if duration is not None and source in sources:
            ests[source, arg].append(duration)
    return {est: sum(vs) / len(vs) for est, vs in ests.items()}

Estimates: dict[Estimated, float] = {
    **estimates_from('timings_v3.jsonl')
}

overrides: dict[Estimated, float] = {
    ('robotarm', 'noop'): 0.0,
    # ('robotarm', 'wash_to_disp prep'): 11.7,
    # ('robotarm', 'wash_to_disp return'): 8.5,
    # ('robotarm', 'wash put return'): 8.02,
    # ('robotarm', 'disp get prep'): 4.6,
    # ('robotarm', 'r11 put return'): 2.7,
    # ('robotarm', 'r9 put return'): 2.7,
    # ('robotarm', 'r7 put return'): 2.7,
    # ('robotarm', 'r11 get prep'): 3.0,
    # ('robotarm', 'r9 get prep'): 3.0,
    # ('robotarm', 'r7 get prep'): 3.0,
    # ('robotarm', 'r1 put transfer'): 6.0,
    # ('robotarm', 'r1 put return'): 6.0,
    # ('robotarm', 'out21 put return'): 6.0,
    # ('robotarm', 'out19 put return'): 6.0,
    # ('robotarm', 'out17 put return'): 6.0,
    # ('robotarm', 'out15 put return'): 6.0,
    # ('robotarm', 'out13 put return'): 6.0,
    # ('robotarm', 'out11 put return'): 6.0,
    # ('robotarm', 'out9 put return'): 6.0,
    # ('wash', 'automation_v3/9_W-5X_NoFinalAspirate.LHC'): 112.5, #4X
    # ('disp', 'automation_v3/2_D_P1_40ul_purge_mito.LHC'): 20
}
utils.pr({k: (Estimates.get(k, None), '->', v) for k, v in overrides.items()})
Estimates.update(overrides)

@dataclass(frozen=True)
class Env:
    robotarm_host: str = 'http://[100::]' # RFC 6666: A Discard Prefix for IPv6
    robotarm_port: int = 30001
    incu_url: str      = 'http://httpbin.org/anything'
    biotek_url: str    = 'http://httpbin.org/anything'

live_env = Env(
    robotarm_host = '10.10.0.112',
    incu_url      = 'http://10.10.0.56:5051',
    biotek_url    = 'http://10.10.0.56:5050',
)

live_arm_incu = Env(
    robotarm_host = live_env.robotarm_host,
    incu_url      = live_env.incu_url,
)

simulator_env = Env(
    robotarm_host = 'localhost',
)

forward_env = Env(
    robotarm_host = 'localhost',
)

dry_env = Env()

@dataclass(frozen=True)
class RuntimeConfig:
    timelike_factory:   Callable[[], Timelike]
    disp_and_wash_mode: Literal['noop', 'execute',                       ]
    incu_mode:          Literal['noop', 'execute',                       ]
    robotarm_mode:      Literal['noop', 'execute', 'execute no gripper', ]

    env: Env

    def name(self) -> str:
        for k, v in configs.items():
            if v is self:
                return k
        raise ValueError(f'unknown config {self}')

wall_time          = lambda: WallTime()
simulated_and_wall = lambda: SimulatedTime(include_wall_time=True)
simulated_no_wall  = lambda: SimulatedTime(include_wall_time=False)

configs: dict[str, RuntimeConfig]
configs = {
    'live':          RuntimeConfig(wall_time,          disp_and_wash_mode='execute', incu_mode='execute', robotarm_mode='execute',            env=live_env),
    'test-all':      RuntimeConfig(simulated_and_wall, disp_and_wash_mode='execute', incu_mode='execute', robotarm_mode='execute',            env=live_env),
    'test-arm-incu': RuntimeConfig(simulated_and_wall, disp_and_wash_mode='noop',    incu_mode='execute', robotarm_mode='execute',            env=live_arm_incu),
    'simulator':     RuntimeConfig(simulated_and_wall, disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='execute no gripper', env=simulator_env),
    'forward':       RuntimeConfig(simulated_no_wall,  disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='execute',            env=forward_env),
    'dry-wall':      RuntimeConfig(wall_time,          disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='noop',               env=dry_env),
    'dry-run':       RuntimeConfig(simulated_no_wall,  disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='noop',               env=dry_env),
}

def curl(url: str, print_result: bool = False) -> Any:
    # if 'is_ready' not in url:
        # print('curl', url)
    ten_minutes = 60 * 10
    res = json.loads(urlopen(url, timeout=ten_minutes).read())
    if 'is_ready' not in url:
        print_result and print('curl', url, '=', utils.show(res))
    return res

@dataclass(frozen=True)
class BiotekMessage:
    command: wash_cmd | disp_cmd
    metadata: dict[str, Any]

@dataclass
class Biotek:
    name: Literal['wash', 'disp']
    queue: SimpleQueue[BiotekMessage] = field(default_factory=SimpleQueue)
    state: Literal['ready', 'busy'] = 'ready'
    # last_started: float | None = None
    # last_finished: float | None = None
    # last_finished_by_plate_id: dict[str, float] = field(default_factory=dict)
    def start(self, runtime: Runtime):
        runtime.spawn(lambda: self.loop(runtime))

    def loop(self, runtime: Runtime):
        '''
        Repeatedly try to run the protocol until it succeeds or we get an unknown error.

        Success looks like this:

            {"err":"","out":{"details":"1 - eOK","status":"1","value":""}}

            {"err":"","out":{"details": "1 - eReady - the run completed
            successfully: stop polling for status", "status":"1", "value":""}}

        Acceptable failure looks like this:

            {"err":"","out":{"details":"Message - Exception calling cLHC method:
                LHC_TestCommunications, ErrorCode: 24673, ErrorString:
                Error code: 6061rnPort is no longer available - ...",
            "status":"99","value":"EXCEPTION"}}

        '''
        runtime.register_thread(self.name)
        while msg := runtime.queue_get(self.queue):
            self.state = 'busy'
            command = msg.command
            metadata = msg.metadata
            del msg
            for cmd in command.before:
                cmd.execute(runtime, {**metadata, 'origin': 'before ' + self.name})
            log_arg = command.protocol_path or command.sub_cmd
            with runtime.timeit(self.name, log_arg, metadata):
                while True:
                    if runtime.config.disp_and_wash_mode == 'noop':
                        est = command.est()
                        runtime.log('info', self.name, f'pretending to run for {est}s', metadata)
                        runtime.sleep(est)
                        res: Any = {"err":"","out":{"details":"1 - eOK","status":"1","value":""}}
                    else:
                        url = (
                            runtime.env.biotek_url +
                            '/' + self.name +
                            '/' + command.sub_cmd +
                            '/' + (command.protocol_path or '')
                        )
                        url = url.rstrip('/')
                        res: Any = curl(url)
                    out = res['out']
                    status = out['status']
                    details = out['details']
                    if status == '99' and 'Error code: 6061' in details and 'Port is no longer available' in details:
                        runtime.log('warn', self.name, 'got error code 6061, retrying...', {**metadata, **res})
                        continue
                    elif status == '1' and ('eOK' in details or 'eReady' in details):
                        break
                    else:
                        raise ValueError(res)
            for cmd in command.after:
                cmd.execute(runtime, {**metadata, 'origin': 'after ' + self.name})
            # print(self.name, 'ready')
            self.state = 'ready'

    def is_ready(self):
        return self.state == 'ready'

    def run(self, msg: BiotekMessage):
        assert self.is_ready(), self
        self.state = 'busy'
        self.queue.put_nowait(msg)

@dataclass(frozen=True)
class IncubatorMessage:
    command: incu_cmd
    metadata: dict[str, Any]

@dataclass
class Incubator:
    queue: SimpleQueue[IncubatorMessage] = field(default_factory=SimpleQueue)
    state: Literal['ready', 'busy'] = 'ready'

    def start(self, runtime: Runtime):
        runtime.spawn(lambda: self.loop(runtime))

    def loop(self, runtime: Runtime):
        runtime.register_thread('incu')
        while msg := runtime.queue_get(self.queue):
            self.state = 'busy'
            command = msg.command
            metadata = msg.metadata
            del msg
            if command.incu_loc is not None:
                metadata = {**metadata, 'loc': command.incu_loc}
                arg = command.action # + ' ' + command.incu_loc
                time_tuple = command.incu_loc, 'incubator'
            else:
                arg = command.action
            with runtime.timeit('incu', arg, metadata):
                assert command.action in {'put', 'get', 'get_climate'}
                if runtime.config.incu_mode == 'noop':
                    est = command.est()
                    runtime.sleep(est)
                elif runtime.config.incu_mode == 'execute':
                    if command.action == 'put':
                        assert command.incu_loc is not None
                        action_path = 'input_plate/' + command.incu_loc
                    elif command.action == 'get':
                        assert command.incu_loc is not None
                        action_path = 'output_plate/' + command.incu_loc
                    elif command.action == 'get_climate':
                        assert command.incu_loc is None
                        action_path = 'getClimate'
                    else:
                        raise ValueError
                    url = runtime.env.incu_url + '/' + action_path
                    res = curl(url)
                    assert res['status'] == 'OK', res
                    while not self.is_endpoint_ready(runtime):
                        time.sleep(0.05)
                else:
                    raise ValueError
            for cmd in command.after:
                cmd.execute(runtime, {**metadata, 'origin': 'after incu'})
            # print('incu', 'ready')
            self.state = 'ready'

    def is_ready(self):
        return self.state == 'ready'

    def run(self, msg: IncubatorMessage):
        assert self.is_ready()
        self.state = 'busy'
        self.queue.put_nowait(msg)

    @staticmethod
    def is_endpoint_ready(runtime: Runtime):
        res = curl(runtime.env.incu_url + '/is_ready')
        assert res['status'] == 'OK', res
        return res['value'] is True

A = TypeVar('A')

@dataclass(frozen=True)
class Runtime:
    config: RuntimeConfig
    var_values: dict[str, float] = field(default_factory=dict)
    log_filename: str | None = None
    wash: Biotek     = field(default_factory=lambda: Biotek('wash'))
    disp: Biotek     = field(default_factory=lambda: Biotek('disp'))
    incu: Incubator  = field(default_factory=lambda: Incubator())
    log_lock: RLock  = field(default_factory=RLock)
    time_lock: RLock = field(default_factory=RLock)
    timelike: Mutable[Timelike] = Mutable.factory(cast(Any, 'initialize in __post_init__ based on config.timelike_factory'))
    times: dict[str, list[float]] = field(default_factory=lambda: cast(Any, defaultdict(list)))

    def __post_init__(self):
        self.timelike.value = self.config.timelike_factory()
        self.register_thread('main')
        self.wash.start(self)
        self.disp.start(self)
        self.incu.start(self)

        if self.config.robotarm_mode != 'noop':
            def change_robotarm_speed():
                while True:
                    with self.log_lock:
                        print('Press escape to set speed to 1%, enter to return it to 100%')
                    c = utils.getchar()
                    speed: None | int = None
                    ESCAPE = '\x1b'
                    RETURN = '\n'
                    if c == ESCAPE: speed = 1
                    if c == RETURN: speed = 100
                    if c == '1': speed = 10
                    if c == '2': speed = 20
                    if c == '3': speed = 30
                    if c == '4': speed = 40
                    if c == '5': speed = 50
                    if c == '6': speed = 60
                    if c == '7': speed = 70
                    if c == '8': speed = 80
                    if c == '9': speed = 90
                    if speed:
                        arm = get_robotarm(self.config, quiet=False)
                        arm.set_speed(speed)
                        arm.close()
            self.spawn(change_robotarm_speed)

    def spawn(self, f: Callable[[], None]) -> None:
        def F():
            with self.excepthook():
                f()
        threading.Thread(target=F, daemon=True).start()

    @contextmanager
    def excepthook(self):
        try:
            yield
        except BaseException as e:
            self.log('error', 'exception', traceback.format_exc())
            raise

    @property
    def env(self):
        '''
        The runtime environment, forwarded from the config
        '''
        return self.config.env

    def log(self,
        kind: Literal['begin', 'end', 'info', 'warn', 'error'],
        source: str,
        arg: str | int | None = None,
        metadata: dict[str, Any] = {},
        t0: None | float = None
    ) -> float:
        with self.time_lock:
            t = round(self.monotonic(), 3)
            log_time = self.now()
        if isinstance(t0, (float, int)):
            duration = round(t - t0, 3)
        else:
            duration = None
        entry = {
            'log_time': str(log_time),
            't': t,
            't0': t0,
            'duration': duration,
            'kind': kind,
            'source': source,
            'arg': arg,
            **metadata
        }
        if source == 'checkpoint' and kind == 'end' and duration is not None:
            self.times[str(arg)].append(duration)
        if 1:
            # if 1 or kind == 'end': # and source in {'time', 'wait'}: # not in {'robotarm', 'wait', 'wash_delay', 'disp_delay', 'experiment'}:
            # if source == 'time':
            with self.log_lock:
                print(' | '.join(
                    ' ' * 8
                    if v is None else
                    f'{str(v).removeprefix("automation_v3/"): <64}'
                    if k == 'arg' else
                    f'{str(v): <10}'
                    if k == 'source' else
                    f'{v:8.2f}'
                    if isinstance(v, float) else
                    f'{str(v): <8}'

                    for k, v in entry.items()
                    if k not in {'log_time', 't0', 'event_machine', 'event_id'}
                    if (v is not None and v != '') or k in 'duration'
                ))
        if 0:
            utils.pr(entry)
        if self.log_filename:
            with self.log_lock:
                with open(self.log_filename, 'a') as fp:
                    json.dump(entry, fp)
                    fp.write('\n')
        return t

    def timeit(self, source: str, arg: str | int | None = None, metadata: dict[str, Any] = {}) -> ContextManager[None]:
        # The inferred type for the decorated function is wrong hence this wrapper to get the correct type

        @contextmanager
        def worker(source: str, arg: str | int | None, metadata: dict[str, Any]):
            t0 = self.log('begin', source, arg=arg, metadata=metadata)
            yield
            self.log('end', source, arg=arg, metadata=metadata, t0=t0)

        return worker(source, arg, metadata)

    start_time: datetime = field(default_factory=datetime.now)

    def now(self) -> datetime:
        return self.start_time + timedelta(seconds=self.monotonic())

    def monotonic(self) -> float:
        return self.timelike.value.monotonic()

    def sleep(self, secs: float):
        return self.timelike.value.sleep(secs)

    def busywait_step(self):
        return self.timelike.value.busywait_step()

    def queue_get(self, queue: SimpleQueue[A]) -> A:
        return self.timelike.value.queue_get(queue)

    def register_thread(self, name: str):
        return self.timelike.value.register_thread(name)

    def thread_idle(self):
        return self.timelike.value.thread_idle()

    checkpoints: dict[str, float] = field(default_factory=dict)
    def checkpoint(self, kind: Literal['info', 'begin', 'end'], name: str, *, strict: bool=True, metadata: dict[str, Any] = {}):
        with self.time_lock:
            if kind == 'info':
                t0 = self.checkpoints.get(name)
                self.checkpoints[name] = self.log(kind, 'checkpoint', name, metadata=metadata, t0=t0)
            elif kind == 'begin':
                if strict:
                    assert name not in self.checkpoints
                self.checkpoints[name] = self.log(kind, 'checkpoint', name, metadata=metadata)
            elif kind == 'end':
                try:
                    t0 = self.checkpoints.pop(name)
                except KeyError:
                    if strict:
                        raise
                    else:
                        return
                self.log(kind, 'checkpoint', name, metadata=metadata, t0=t0)
            else:
                raise ValueError(kind)

class Command(abc.ABC):
    @abc.abstractmethod
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        return NotImplementedError

    def est(self) -> float:
        raise ValueError(self.__class__)

@dataclass(frozen=True)
class checkpoint_cmd(Command):
    kind: Literal['info', 'begin', 'end']
    name: str
    strict: bool = True # if strict then kind == 'begin' must match up with kind == 'end'
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.checkpoint(self.kind, self.name, strict=self.strict, metadata=metadata)

@dataclass(frozen=True)
class Symbolic:
    var_names: list[str]
    offset: float = 0

    def __str__(self):
        xs = [
            f'`{x}`' if re.search(r'\W', x) else x
            for x in self.var_names
        ]
        if self.offset or not xs:
            xs += [str(round(self.offset, 1))]
        return '+'.join(xs)

    def __repr__(self):
        return f'Symbolic({str(self)})'

    def __add__(self, other: float | Symbolic) -> Symbolic:
        if isinstance(other, (float, int)):
            return Symbolic(self.var_names, self.offset + other)
        else:
            return Symbolic(
                self.var_names + other.var_names,
                self.offset + other.offset,
            )

    def resolve(self, var_values: dict[str, float]) -> float:
        return sum(var_values[x] for x in self.var_names) + self.offset

    @staticmethod
    def var(name: str) -> Symbolic:
        return Symbolic(var_names=[name])

    @staticmethod
    def const(value: float) -> Symbolic:
        return Symbolic(var_names=[], offset=value)

@dataclass(frozen=True)
class idle_cmd(Command):
    seconds: Symbolic = Symbolic.const(0)
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        seconds = self.seconds.resolve(runtime.var_values)
        with runtime.timeit('wait', str(self), metadata):
            runtime.sleep(seconds)

    def __add__(self, other: int | Symbolic) -> idle_cmd:
        return idle_cmd(self.seconds + other)

@dataclass(frozen=True)
class wait_for_checkpoint_cmd(Command):
    name: str
    plus_seconds: Symbolic = Symbolic.const(0)
    or_now: bool = False
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        plus_seconds = self.plus_seconds.resolve(runtime.var_values)
        arg = f'{Symbolic.var(self.name) + self.plus_seconds}'
        if self.or_now:
            arg += ' (or now)'
        with runtime.timeit('wait', arg, metadata):
            if self.name not in runtime.checkpoints:
                assert self.or_now
                past_point_in_time = runtime.monotonic()
            else:
                past_point_in_time = runtime.checkpoints[self.name]
            desired_point_in_time = past_point_in_time + plus_seconds
            delay = desired_point_in_time - runtime.monotonic()
            runtime.sleep(delay)

    def __add__(self, other: int | Symbolic) -> wait_for_checkpoint_cmd:
        return wait_for_checkpoint_cmd(
            name=self.name,
            plus_seconds=self.plus_seconds + other,
            or_now=self.or_now,
        )

@dataclass(frozen=True)
class wait_for_ready_cmd(Command):
    machine: Literal['incu', 'wash', 'disp']
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        with runtime.timeit('wait', str(self), metadata):
            if self.machine == 'incu':
                while not runtime.incu.is_ready():
                    runtime.busywait_step()
            elif self.machine == 'wash':
                while not runtime.wash.is_ready():
                    runtime.busywait_step()
            elif self.machine == 'disp':
                while not runtime.disp.is_ready():
                    runtime.busywait_step()
            else:
                raise ValueError(self.machine)

def get_robotarm(config: RuntimeConfig, quiet: bool = False) -> Robotarm:
    if config.robotarm_mode == 'noop':
        return Robotarm.init_noop(with_gripper=True, quiet=quiet)
    assert config.robotarm_mode == 'execute' or config.robotarm_mode == 'execute no gripper'
    with_gripper = config.robotarm_mode == 'execute'
    return Robotarm.init(config.env.robotarm_host, config.env.robotarm_port, with_gripper, quiet=quiet)

@dataclass(frozen=True)
class robotarm_cmd(Command):
    program_name: str
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        with runtime.timeit('robotarm', self.program_name, metadata):
            if runtime.config.robotarm_mode == 'noop':
                runtime.sleep(self.est())
            else:
                arm = get_robotarm(runtime.config, quiet=True)
                arm.execute_moves(movelists[self.program_name], name=self.program_name)
                arm.close()

    def est(self):
        arg = self.program_name
        guess = 2.5
        if 'transfer' in arg:
            guess = 10.0
        # assert ('robotarm', self.program_name) in Estimates, self.program_name
        return Estimates.get(('robotarm', self.program_name), guess)

@dataclass(frozen=True)
class wash_cmd(Command):
    protocol_path: str | None
    sub_cmd: Literal['LHC_RunProtocol', 'LHC_TestCommunications'] = 'LHC_RunProtocol'
    before: list[wait_for_checkpoint_cmd | idle_cmd | checkpoint_cmd] = field(default_factory=list)
    after: list[checkpoint_cmd] = field(default_factory=list)
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.wash.run(BiotekMessage(self, metadata))

    def est(self):
        arg = self.protocol_path or ''
        guess = 60.0
        if '2X' in arg:
            guess = 60.0 + 20
        elif '3X' in arg:
            guess = 60.0 + 35
        elif '4X' in arg:
            guess = 60.0 + 50
        elif '5X' in arg:
            guess = 60.0 + 65
        return Estimates.get(('wash', arg), guess)

@dataclass(frozen=True)
class disp_cmd(Command):
    protocol_path: str | None
    sub_cmd: Literal['LHC_RunProtocol', 'LHC_TestCommunications'] = 'LHC_RunProtocol'
    before: list[wait_for_checkpoint_cmd | idle_cmd | checkpoint_cmd] = field(default_factory=list)
    after: list[checkpoint_cmd] = field(default_factory=list)
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.disp.run(BiotekMessage(self, metadata))

    def est(self):
        arg = self.protocol_path or ''
        guess = 35
        return Estimates.get(('disp', arg), guess)

@dataclass(frozen=True)
class incu_cmd(Command):
    action: Literal['put', 'get', 'get_climate']
    incu_loc: str | None
    after: list[checkpoint_cmd] = field(default_factory=list)
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.incu.run(IncubatorMessage(self, metadata))

    def est(self):
        arg = self.action
        guess = 20
        return Estimates.get(('incu', arg), guess)

def test_comm(config: RuntimeConfig):
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    print('Testing communication with robotarm, washer, dispenser and incubator.')
    runtime = Runtime(config=config)
    disp_cmd(sub_cmd='LHC_TestCommunications', protocol_path=None).execute(runtime, {})
    incu_cmd(action='get_climate', incu_loc=None).execute(runtime, {})
    robotarm_cmd('noop').execute(runtime, {})
    wait_for_ready_cmd('disp').execute(runtime, {})
    wash_cmd(sub_cmd='LHC_TestCommunications', protocol_path=None).execute(runtime, {})
    wait_for_ready_cmd('wash').execute(runtime, {})
    wait_for_ready_cmd('incu').execute(runtime, {})
    print('Communication tests ok.')

def vars_of(cmd: Command) -> set[str]:
    if isinstance(cmd, wait_for_checkpoint_cmd):
        return set(cmd.plus_seconds.var_names)
    elif isinstance(cmd, idle_cmd):
        return set(cmd.seconds.var_names)
    elif isinstance(cmd, (wash_cmd, disp_cmd)):
        return {
            v
            for c in [*cmd.before, *cmd.after]
            for v in vars_of(c)
        }
    elif isinstance(cmd, incu_cmd):
        return {
            v
            for c in cmd.after
            for v in vars_of(c)
        }
    else:
        return set()



