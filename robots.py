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
                cmd.execute(runtime, {'origin': 'before ' + self.name})
            log_arg = command.protocol_path or command.sub_cmd
            with runtime.timeit(self.name, log_arg, metadata):
                while True:
                    if runtime.config.disp_and_wash_mode == 'noop':
                        est = runtime.est(self.name, log_arg)
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
                    cmd.execute(runtime, {'origin': 'after ' + self.name})
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
                    est = runtime.est('incu', arg)
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
                    cmd.execute(runtime, {'origin': 'after incu'})
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
    log_filename: str | None = None
    wash: Biotek     = field(default_factory=lambda: Biotek('wash'))
    disp: Biotek     = field(default_factory=lambda: Biotek('disp'))
    incu: Incubator  = field(default_factory=lambda: Incubator())
    log_lock: RLock  = field(default_factory=RLock)
    time_lock: RLock = field(default_factory=RLock)
    estimates: dict[Estimated, float] = field(default_factory=dict)
    timelike: Mutable[Timelike] = Mutable.factory(cast(Any, 'initialize in __post_init__ based on config.timelike_factory'))
    times: dict[str, list[float]] = field(default_factory=lambda: cast(Any, defaultdict(list)))

    def __post_init__(self):
        self.timelike.value = self.config.timelike_factory()
        self.register_thread('main')
        self.wash.start(self)
        self.disp.start(self)
        self.incu.start(self)
        self.estimates.update(estimates_from('timings_v3.jsonl'))

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

    def est(self, source: Literal['wash', 'disp', 'robotarm', 'incu'], arg: str) -> float:
        if ret := self.estimates.get((source, arg)):
            return ret
        else:
            # raise ValueError(f'No timing for {(source, arg)=}')
            if source == 'wash':
                if '1X' in arg:
                    return 60.0 + 34 # ?
                elif '2X' in arg:
                    return 60.0 + 34 # ?
                elif '3X' in arg:
                    return 60.0 + 34
                elif '4X' in arg:
                    return 60.0 + 49
                else:
                    return 60.0
            elif source == 'disp':
                return 30.0
            else:
                return 15.0

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
            if 1:
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
        pass

class Waitable(abc.ABC):
    pass

@dataclass(frozen=True)
class Checkpoint(Waitable):
    command_name: str
    or_now: bool = False

@dataclass(frozen=True)
class Now(Waitable):
    pass

@dataclass(frozen=True)
class Ready(Waitable):
    name: Literal['incu', 'wash', 'disp']
    def wait(self, runtime: Runtime):
        if self.name == 'incu':
            while not runtime.incu.is_ready():
                runtime.busywait_step()
        elif self.name == 'wash':
            while not runtime.wash.is_ready():
                runtime.busywait_step()
        elif self.name == 'disp':
            while not runtime.disp.is_ready():
                runtime.busywait_step()
        else:
            raise ValueError(self.name)

@dataclass(frozen=True)
class checkpoint_cmd(Command):
    kind: Literal['info', 'begin', 'end']
    name: str
    strict: bool = True # if strict then kind == 'begin' must match up with kind == 'end'
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.checkpoint(self.kind, self.name, strict=self.strict, metadata=metadata)

@dataclass(frozen=True)
class wait_for(Command):
    base: Waitable
    plus_seconds: int = 0

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        with runtime.timeit('wait', str(self), metadata):
            if isinstance(self.base, Ready):
                assert self.plus_seconds == 0
                self.base.wait(runtime)
            elif isinstance(self.base, Checkpoint):
                if self.base.or_now and self.base.command_name not in runtime.checkpoints:
                    past_point_in_time = runtime.monotonic()
                else:
                    past_point_in_time = runtime.checkpoints[self.base.command_name]
                desired_point_in_time = past_point_in_time + self.plus_seconds
                delay = desired_point_in_time - runtime.monotonic()
                runtime.sleep(delay)
            elif isinstance(self.base, Now):
                runtime.sleep(self.plus_seconds)
            else:
                raise ValueError

    def __add__(self, other: int) -> wait_for:
        return wait_for(self.base, self.plus_seconds + other)

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
                est = runtime.est('robotarm', self.program_name)
                runtime.sleep(est)
            else:
                arm = get_robotarm(runtime.config, quiet=True)
                arm.execute_moves(movelists[self.program_name], name=self.program_name)
                arm.close()

@dataclass(frozen=True)
class wash_cmd(Command):
    protocol_path: str | None
    sub_cmd: Literal['LHC_RunProtocol', 'LHC_TestCommunications'] = 'LHC_RunProtocol'
    before: list[wait_for | checkpoint_cmd] = field(default_factory=list)
    after: list[checkpoint_cmd] = field(default_factory=list)
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.wash.run(BiotekMessage(self, metadata))

@dataclass(frozen=True)
class disp_cmd(Command):
    protocol_path: str | None
    sub_cmd: Literal['LHC_RunProtocol', 'LHC_TestCommunications'] = 'LHC_RunProtocol'
    before: list[wait_for | checkpoint_cmd] = field(default_factory=list)
    after: list[checkpoint_cmd] = field(default_factory=list)
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.disp.run(BiotekMessage(self, metadata))

@dataclass(frozen=True)
class incu_cmd(Command):
    action: Literal['put', 'get', 'get_climate']
    incu_loc: str | None
    after: list[checkpoint_cmd] = field(default_factory=list)
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.incu.run(IncubatorMessage(self, metadata))

def test_comm(config: RuntimeConfig):
    '''
    Test communication with robotarm, washer, dispenser and incubator.
    '''
    print('Testing communication with robotarm, washer, dispenser and incubator.')
    runtime = Runtime(config=config)
    disp_cmd(sub_cmd='LHC_TestCommunications', protocol_path=None).execute(runtime, {})
    incu_cmd(action='get_climate', incu_loc=None).execute(runtime, {})
    robotarm_cmd('noop').execute(runtime, {})
    wait_for(Ready('disp')).execute(runtime, {})
    wash_cmd(sub_cmd='LHC_TestCommunications', protocol_path=None).execute(runtime, {})
    wait_for(Ready('wash')).execute(runtime, {})
    wait_for(Ready('incu')).execute(runtime, {})
    print('Communication tests ok.')
