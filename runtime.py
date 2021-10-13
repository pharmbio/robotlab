from __future__ import annotations
from dataclasses import *
from typing import *

from datetime import datetime, timedelta
from urllib.request import urlopen

import abc
import json
import re
import time
import threading
import traceback
from queue import Queue
from contextlib import contextmanager
from threading import RLock

from moves import movelists
from robotarm import Robotarm
import utils
from utils import Mutable
from utils import pp_secs

import timelike
from timelike import Timelike, WallTime, SimulatedTime
from collections import defaultdict

import os
import signal

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

    robotarm_speed: int = 100

    def name(self) -> str:
        for k, v in configs.items():
            if v is self:
                return k
        raise ValueError(f'unknown config {self}')

    def with_speed(self, robotarm_speed: int) -> RuntimeConfig:
        if robotarm_speed == self.robotarm_speed:
            return self
        else:
            conf = replace(self, robotarm_speed=robotarm_speed)
            # have to make up a name (this is a bit silly)
            name = f'{self.name()}({robotarm_speed=})'
            configs[name] = conf
            return conf

wall_time          = lambda: WallTime()
simulated_and_wall = lambda: SimulatedTime(include_wall_time=True)
simulated_no_wall  = lambda: SimulatedTime(include_wall_time=False)

configs: dict[str, RuntimeConfig]
configs = {
    'live':           RuntimeConfig(wall_time,          disp_and_wash_mode='execute', incu_mode='execute', robotarm_mode='execute',            env=live_env),
    'test-all':       RuntimeConfig(simulated_and_wall, disp_and_wash_mode='execute', incu_mode='execute', robotarm_mode='execute',            env=live_env),
    'test-arm-incu':  RuntimeConfig(simulated_and_wall, disp_and_wash_mode='noop',    incu_mode='execute', robotarm_mode='execute',            env=live_arm_incu),
    'simulator':      RuntimeConfig(simulated_no_wall,  disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='execute no gripper', env=simulator_env),
    'forward':        RuntimeConfig(simulated_no_wall,  disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='execute',            env=forward_env),
    'dry-run':        RuntimeConfig(simulated_no_wall,  disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='noop',               env=dry_env),
}

def curl(url: str, print_result: bool = False) -> Any:
    # if 'is_ready' not in url:
        # print('curl', url)
    ten_minutes = 60 * 10
    res = json.loads(urlopen(url, timeout=ten_minutes).read())
    if 'is_ready' not in url:
        print_result and print('curl', url, '=', utils.show(res))
    return res

def trim_LHC_filenames(s: str) -> str:
    if '.LHC' in s:
        parts = s.split(' ')
        return ' '.join(
            part.split('/')[-1]
            if part.endswith('.LHC') else
            part
            for part in parts
        )
    else:
        return s

def get_robotarm(config: RuntimeConfig, quiet: bool = False, include_gripper: bool = True) -> Robotarm:
    if config.robotarm_mode == 'noop':
        return Robotarm.init_noop(with_gripper=include_gripper, quiet=quiet)
    assert config.robotarm_mode == 'execute' or config.robotarm_mode == 'execute no gripper'
    with_gripper = config.robotarm_mode == 'execute'
    if not include_gripper:
        with_gripper = False
    return Robotarm.init(config.env.robotarm_host, config.env.robotarm_port, with_gripper, quiet=quiet)

A = TypeVar('A')

@dataclass(frozen=True)
class Runtime:
    config: RuntimeConfig
    var_values: dict[str, float] = field(default_factory=dict)
    execute_scheduling_idles: bool = False
    log_filename: str | None = None
    log_entries: list[dict[str, Any]] = field(default_factory=list)
    log_lock: RLock  = field(default_factory=RLock)
    time_lock: RLock = field(default_factory=RLock)
    timelike: Mutable[Timelike] = Mutable.factory(cast(Any, 'initialize in __post_init__ based on config.timelike_factory'))
    times: dict[str, list[float]] = field(default_factory=lambda: cast(Any, defaultdict(list)))

    def __post_init__(self):
        self.timelike.value = self.config.timelike_factory()
        with self.timelike.value.spawning():
            self.register_thread('main')

        if self.config.robotarm_mode != 'noop':
            self.set_robotarm_speed(self.config.robotarm_speed)
            @self.spawn
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
                    if c == '0': speed = 100
                    if c == 'Q':
                        arm = self.get_robotarm(quiet=False, include_gripper=False)
                        arm.send('textmsg("log quit")\n')
                        arm.recv_until('quit')
                        arm.close()
                        os.kill(os.getpid(), signal.SIGINT)
                    if speed:
                        self.set_robotarm_speed(speed)

    def get_robotarm(self, quiet: bool = True, include_gripper: bool = True) -> Robotarm:
        return get_robotarm(self.config, quiet=quiet, include_gripper=include_gripper)

    def set_robotarm_speed(self, speed: int):
        arm = self.get_robotarm(quiet=False, include_gripper=False)
        arm.set_speed(speed)
        arm.close()

    def spawn(self, f: Callable[[], None]) -> None:
        def F():
            with self.excepthook():
                f()
        with self.timelike.value.spawning():
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
            **metadata,
        }
        if source == 'duration' and kind == 'end' and duration is not None:
            self.times[str(arg)].append(duration)
        write: bool = True
        if not self.log_filename:
            write = False
        if entry.get('silent'):
            write = False
        if entry.get('source') == 'robotarm' and entry.get('kind') == 'end':
            write = False
            # if 1 or kind == 'end': # and source in {'time', 'wait'}: # not in {'robotarm', 'wait', 'wash_delay', 'disp_delay', 'experiment'}:
            # if source == 'time':
        # if entry.get('source') == 'wait' and entry.get('kind') != 'info' and entry.get('arg') not in "wash disp incu".split():
            # write = False
        if entry.get('source') in {'wait', 'idle'} and (entry.get('kind') == 'end' or entry.get('origin') is not None):
            write = False
        if entry.get('source') == 'checkpoint':
            write = False
        if write:
            parts: list[str] = []
            color = utils.Color()
            for k, v in entry.items():
                if k in {'log_time', 't0', 'event_id', 'event_index', 'secs', 'duration', 'incu_loc', 'origin'}:
                    continue
                elif (v is None or v == '') and k != 'duration':
                    continue
                elif entry.get('source') == 'run' and len(parts) >= 4:
                    continue
                elif k == 'arg' and entry.get('source') == 'duration' and entry.get('kind') == 'end':
                    secs = float(entry.get("duration", 0.0) or 0.0)
                    part = f'{"`" + str(v) + "` = " + utils.pp_secs(secs): <50}'
                elif k == 'arg' and (incu_loc := entry.get("incu_loc")):
                    part = f'{str(v) + " " + str(incu_loc): <50}'
                elif k == 'arg':
                    part = f'{trim_LHC_filenames(str(v)): <50}'
                elif k == 't' and isinstance(v, (int, float)):
                    part = self.pp_time_offset(v)
                elif k in {'t', 'duration'} and isinstance(v, (int, float)):
                    part = f'{pp_secs(v): >9}'
                elif k == 'source':
                    part = f'{str(v): <8}'
                elif isinstance(v, float):
                    part = f'{v:8.2f}'
                elif k == 'kind':
                    part = f'{str(v): <5}'
                elif k == 'event_plate_id':
                    part = f'{str(v): >2}'
                elif k == 'event_part':
                    part = f'{str(v): <6}'
                elif k == 'event_subpart':
                    continue
                else:
                    part = f'{str(v): <8}'
                if entry.get('source') in {'wash', 'disp'} and k in {'arg', 'source'}:
                    part = re.sub('(?<= ) ', '-', part)
                parts += [part]
            # color =
            # parts += [str(entry)]
            with self.log_lock:
                line = ' | '.join(parts)
                if entry.get('source') == 'wash':
                    line = color.cyan(line)
                elif entry.get('source') == 'disp':
                    line = color.orange(line)
                elif entry.get('source') == 'incu':
                    line = color.green(line)
                print(line)

        if 0:
            utils.pr(entry)
        if self.log_filename:
            with self.log_lock:
                with open(self.log_filename, 'a') as fp:
                    json.dump(entry, fp)
                    fp.write('\n')
        else:
            self.log_entries.append(entry)
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

    def pp_time_offset(self, secs: int | float):
        dt = self.start_time + timedelta(seconds=secs)
        return dt.strftime('%H:%M:%S') # + dt.strftime('.%f')[:3]

    def now(self) -> datetime:
        return self.start_time + timedelta(seconds=self.monotonic())

    def monotonic(self) -> float:
        return self.timelike.value.monotonic()

    def sleep(self, secs: float, metadata: dict[str, Any]):
        if abs(secs) < 0.1:
            self.log('info', 'wait', f'on time {pp_secs(secs)}s', metadata={**metadata, 'secs': secs})
        elif secs < 0:
            self.log('info', 'wait', f'behind time {pp_secs(secs)}s', metadata={**metadata, 'secs': secs})
        else:
            to = self.pp_time_offset(self.monotonic() + secs)
            self.log('info', 'wait', f'sleeping to {to} ({pp_secs(secs)}s)', metadata={**metadata, 'secs': secs})
        return self.timelike.value.sleep(secs)

    def queue_get(self, queue: Queue[A]) -> A:
        return self.timelike.value.queue_get(queue)

    def queue_put(self, queue: Queue[A], a: A) -> None:
        return self.timelike.value.queue_put(queue, a)

    def queue_put_nowait(self, queue: Queue[A], a: A) -> None:
        return self.timelike.value.queue_put_nowait(queue, a)

    def register_thread(self, name: str):
        return self.timelike.value.register_thread(name)

    def thread_idle(self):
        return self.timelike.value.thread_idle()

    def thread_done(self):
        return self.timelike.value.thread_done()

    checkpoint_times: dict[str, float] = field(default_factory=dict)
    checkpoint_waits: dict[str, list[Queue[None]]] = field(default_factory=
        lambda: defaultdict[str, list[Queue[None]]](list)
    )

    def checkpoint(self, name: str, *, metadata: dict[str, Any] = {}):
        with self.time_lock:
            assert name not in self.checkpoint_times, f'{name!r} already checkpointed in {utils.show(self.checkpoint_times, use_color=False)}'
            self.checkpoint_times[name] = self.log('info', 'checkpoint', str(name), metadata=metadata)
            for q in self.checkpoint_waits[name]:
                self.queue_put_nowait(q, None)
            self.checkpoint_waits[name].clear()

    def enqueue_for_checkpoint(self, name: str):
        q: Queue[None] = Queue()
        with self.time_lock:
            if name in self.checkpoint_times:
                self.queue_put_nowait(q, None) # prepopulate it
            else:
                self.checkpoint_waits[name] += [q]
        return q

    def wait_for_checkpoint(self, name: str):
        q = self.enqueue_for_checkpoint(name)
        self.queue_get(q)
        with self.time_lock:
            return self.checkpoint_times[name]

    resource_counters: dict[str, int] = field(default_factory=
        lambda: defaultdict[str, int](int)
    )

    def enqueue_for_resource_production(self, resource: str):
        with self.time_lock:
            prev = self.resource_counters[resource]
            self.resource_counters[resource] += 1
            this = self.resource_counters[resource]

        prev_checkpoint = f'{resource} #{prev}'
        this_checkpoint = f'{resource} #{this}'

        if not prev:
            q = Queue[None]()
            self.queue_put_nowait(q, None) # prepopulate it
        else:
            q = self.enqueue_for_checkpoint(prev_checkpoint)

        return q, this_checkpoint

    def wait_for_resource(self, resource: str):
        with self.time_lock:
            current = self.resource_counters[resource]

        current_checkpoint = f'{resource} #{current}'

        if current:
            self.wait_for_checkpoint(current_checkpoint)

