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
from queue import SimpleQueue
from contextlib import contextmanager
from threading import RLock

from moves import movelists
from robotarm import Robotarm
import utils
from utils import Mutable

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
class Config:
    time_mode:          Literal['wall', 'fast forward',                  ]
    disp_and_wash_mode: Literal['noop', 'execute', 'execute short',      ]
    incu_mode:          Literal['noop', 'execute',                       ]
    robotarm_mode:      Literal['noop', 'execute', 'execute no gripper', ]

    env: Env

    def name(self) -> str:
        for k, v in configs.items():
            if v is self:
                return k
        raise ValueError(f'unknown config {self}')

configs: dict[str, Config]
configs = {
    'live':          Config('wall',         'execute',       'execute', 'execute',            live_env),
    'test-all':      Config('fast forward', 'execute short', 'execute', 'execute',            live_env),
    'test-arm-incu': Config('fast forward', 'noop',          'execute', 'execute',            live_arm_incu),
    'simulator':     Config('fast forward', 'noop',          'noop',    'execute no gripper', simulator_env),
    'forward':       Config('fast forward', 'noop',          'noop',    'execute',            forward_env),
    'dry-run':       Config('fast forward', 'noop',          'noop',    'noop',               dry_env),
}

def curl(url: str, print_result: bool = False) -> Any:
    if 'is_ready' not in url:
        print('curl', url)
    ten_minutes = 60 * 10
    res = json.loads(urlopen(url, timeout=ten_minutes).read())
    if 'is_ready' not in url:
        print_result and print('curl', url, '=', utils.show(res))
    return res

@dataclass(frozen=True)
class BiotekMessage:
    runtime: Runtime
    command: wash_cmd | disp_cmd
    metadata: dict[str, Any]

@dataclass
class Biotek:
    name: Literal['wash', 'disp']
    queue: SimpleQueue[BiotekMessage] = field(default_factory=SimpleQueue)
    state: Literal['ready', 'busy'] = 'ready'
    last_started: float | None = None
    last_finished: float | None = None
    last_finished_by_plate_id: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        t = threading.Thread(target=self.loop, daemon=True)
        t.start()

    def loop(self):
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
        while msg := self.queue.get():
            self.state = 'busy'
            runtime = msg.runtime
            command = msg.command
            metadata = msg.metadata
            del msg
            log_arg = command.protocol_path or command.sub_cmd
            if command.delay:
                with runtime.timeit(self.name + '_delay', log_arg, metadata):
                    command.delay.execute(runtime, metadata)
            with runtime.timeit(self.name, log_arg, metadata):
                while True:
                    self.last_started = runtime.monotonic()
                    if runtime.config.disp_and_wash_mode == 'noop':
                        est = 15
                        if command.protocol_path is None:
                            est = 0
                        elif '3X' in command.protocol_path:
                            est = 60 + 42
                        elif '4X' in command.protocol_path:
                            est = 60 + 52
                        runtime.log('info', self.name, f'pretending to run for {est}s', metadata)
                        while self.last_started + est > runtime.monotonic():
                            time.sleep(0.0001)
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
            self.last_finished = runtime.monotonic()
            if command.plate_id:
                self.last_finished_by_plate_id[command.plate_id] = self.last_finished
            print(self.name, 'ready')
            self.state = 'ready'

    def is_ready(self):
        return self.state == 'ready'

    def run(self, msg: BiotekMessage):
        assert self.is_ready()
        self.state = 'busy'
        self.queue.put_nowait(msg)

@dataclass(frozen=True)
class IncubatorMessage:
    runtime: Runtime
    command: incu_cmd
    metadata: dict[str, Any]

@dataclass
class Incubator:
    queue: SimpleQueue[IncubatorMessage] = field(default_factory=SimpleQueue)
    state: Literal['ready', 'busy'] = 'ready'

    def __post_init__(self):
        t = threading.Thread(target=self.loop, daemon=True)
        t.start()

    def loop(self):
        while msg := self.queue.get():
            self.state = 'busy'
            runtime = msg.runtime
            command = msg.command
            metadata = msg.metadata
            del msg
            if command.incu_loc is not None:
                metadata = {**metadata, 'loc': command.incu_loc}
            with runtime.timeit('incu', command.action, metadata):
                assert command.action in {'put', 'get', 'get_climate'}
                if runtime.config.incu_mode == 'noop':
                    pass
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
            print('incu', 'ready')
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

@dataclass(frozen=True)
class Runtime:
    config: Config
    log_filename: str | None = None
    wash: Biotek     = field(default_factory=lambda: Biotek('wash'))
    disp: Biotek     = field(default_factory=lambda: Biotek('disp'))
    incu: Incubator  = field(default_factory=lambda: Incubator())
    log_lock: RLock  = field(default_factory=RLock)
    time_lock: RLock = field(default_factory=RLock)
    skipped_time: Mutable[float] = Mutable.factory(0.0)
    start_time: float            = field(default_factory=time.monotonic)

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
        if isinstance(t0, float):
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
        if self.config.time_mode == 'fast forward':
            entry['skipped_time'] = round(self.skipped_time.value, 3)
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

    def now(self) -> datetime:
        if self.config.time_mode == 'wall':
            assert self.skipped_time.value == 0.0
        with self.time_lock:
            return datetime.now() + timedelta(seconds=self.skipped_time.value)

    def monotonic(self) -> float:
        if self.config.time_mode == 'wall':
            assert self.skipped_time.value == 0.0
        with self.time_lock:
            return time.monotonic() - self.start_time + self.skipped_time.value

    def sleep(self, secs: float):
        def fmt(s: float) -> str:
            m = int(s // 60)
            return f'{secs}s ({m}min {s - 60 * m - 0.05:.1f}s)'
        if secs < 0:
            print('Behind time:', fmt(-secs), '!')
            return
        if self.config.time_mode == 'wall':
            print('Sleeping for', fmt(secs), '...')
            time.sleep(secs)
        elif self.config.time_mode == 'fast forward':
            if secs > 1:
                print('Fast forwarding', fmt(secs))
            with self.time_lock:
                self.skipped_time.value += secs
        else:
            raise ValueError(self.config.time_mode)

class Command(abc.ABC):
    @abc.abstractmethod
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        pass

class Waitable(abc.ABC):
    pass

@dataclass(frozen=True)
class DispFinished(Waitable):
    plate_id: str

@dataclass(frozen=True)
class WashStarted(Waitable):
    pass

@dataclass(frozen=True)
class Now(Waitable):
    pass

@dataclass(frozen=True)
class Ready(Waitable):
    name: Literal['incu', 'wash', 'disp']
    def wait(self, runtime: Runtime):
        if self.name == 'incu':
            if runtime.config.incu_mode == 'execute':
                while not runtime.incu.is_ready():
                    time.sleep(0.01)
            elif runtime.config.incu_mode == 'noop':
                pass
            else:
                raise ValueError(runtime.config.incu_mode)
        elif self.name == 'wash':
            while not runtime.wash.is_ready():
                if runtime.config.disp_and_wash_mode == 'noop':
                    assert runtime.config.time_mode == 'fast forward'
                    time.sleep(0.00001)
                    runtime.sleep(1.00)
                else:
                    time.sleep(0.01)
        elif self.name == 'disp':
            while not runtime.disp.is_ready():
                if runtime.config.disp_and_wash_mode == 'noop':
                    assert runtime.config.time_mode == 'fast forward'
                    time.sleep(0.00001)
                    runtime.sleep(1.00)
                else:
                    time.sleep(0.01)
        else:
            raise ValueError(self.name)

@dataclass(frozen=True)
class wait_for(Command):
    base: Waitable
    plus_seconds: int = 0

    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        with runtime.timeit('wait', str(self), metadata):
            if isinstance(self.base, Ready):
                assert self.plus_seconds == 0
                self.base.wait(runtime)
            elif isinstance(self.base, WashStarted):
                assert runtime.wash.last_started is not None
                past_point_in_time = runtime.wash.last_started
                desired_point_in_time = past_point_in_time + self.plus_seconds
                delay = desired_point_in_time - runtime.monotonic()
                runtime.sleep(delay)
            elif isinstance(self.base, DispFinished):
                past_point_in_time = runtime.disp.last_finished_by_plate_id[self.base.plate_id]
                desired_point_in_time = past_point_in_time + self.plus_seconds
                delay = desired_point_in_time - runtime.monotonic()
                runtime.sleep(delay)
            elif isinstance(self.base, Now):
                runtime.sleep(self.plus_seconds)
            else:
                raise ValueError

    def __add__(self, other: int) -> wait_for:
        return wait_for(self.base, self.plus_seconds + other)

def get_robotarm(config: Config, quiet: bool = False) -> Robotarm:
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
            arm = get_robotarm(runtime.config)
            arm.execute_moves(movelists[self.program_name], name=self.program_name)
            arm.close()

@dataclass(frozen=True)
class wash_cmd(Command):
    protocol_path: str | None
    plate_id: str | None = None
    delay: wait_for | None = None
    sub_cmd: Literal['LHC_RunProtocol', 'LHC_TestCommunications'] = 'LHC_RunProtocol'
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.wash.run(BiotekMessage(runtime, self, metadata))

@dataclass(frozen=True)
class disp_cmd(Command):
    protocol_path: str | None
    plate_id: str | None = None
    delay: wait_for | None = None
    sub_cmd: Literal['LHC_RunProtocol', 'LHC_TestCommunications'] = 'LHC_RunProtocol'
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.disp.run(BiotekMessage(runtime, self, metadata))

@dataclass(frozen=True)
class incu_cmd(Command):
    action: Literal['put', 'get', 'get_climate']
    incu_loc: str | None
    def execute(self, runtime: Runtime, metadata: dict[str, Any]) -> None:
        runtime.incu.run(IncubatorMessage(runtime, self, metadata))

def test_comm(config: Config):
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
