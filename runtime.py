from __future__ import annotations
from dataclasses import *
from typing import *

from datetime import datetime, timedelta
from urllib.request import urlopen

import json
import threading
import traceback
from queue import Queue
from contextlib import contextmanager
from threading import RLock

from robotarm import Robotarm
import utils
from utils import Mutable
from utils import pp_secs

from timelike import Timelike, WallTime, SimulatedTime, FastForwardTime
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
    incu_url      = 'http://10.10.0.56:5050',
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
    name:               str
    timelike_factory:   Callable[[], Timelike]
    disp_and_wash_mode: Literal['noop', 'execute',                       ]
    incu_mode:          Literal['noop', 'execute',                       ]
    robotarm_mode:      Literal['noop', 'execute', 'execute no gripper', ]
    env: Env
    robotarm_speed: int = 100
    log_filename: str = ''
    log_to_file: bool = True

    def replace(self,
        robotarm_speed: int  | None = None,
        log_filename:   str  | None = None,
        log_to_file:    bool | None = None,
    ):
        next = self
        updates = dict(
            robotarm_speed=robotarm_speed,
            log_filename=log_filename,
            log_to_file=log_to_file,
        )
        for k, v in updates.items():
            if v is None:
                pass
            elif getattr(next, k) is v:
                pass
            else:
                next = replace(next, **{k: v})
        return next

configs: list[RuntimeConfig]
configs = [
    RuntimeConfig('live',          WallTime,              disp_and_wash_mode='execute', incu_mode='execute', robotarm_mode='execute',            env=live_env),
    RuntimeConfig('test-all',      WallTime,              disp_and_wash_mode='execute', incu_mode='execute', robotarm_mode='execute',            env=live_env),
    RuntimeConfig('test-arm-incu', WallTime,              disp_and_wash_mode='noop',    incu_mode='execute', robotarm_mode='execute',            env=live_arm_incu),
    RuntimeConfig('simulator',     WallTime,              disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='execute no gripper', env=simulator_env),
    RuntimeConfig('forward',       WallTime,              disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='execute',            env=forward_env),
    RuntimeConfig('dry-ff',        FastForwardTime(50.0), disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='noop',               env=dry_env),
    RuntimeConfig('dry-wall',      WallTime,              disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='noop',               env=dry_env),
    RuntimeConfig('dry-run',       SimulatedTime,         disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='noop',               env=dry_env),
]

def config_lookup(name: str) -> RuntimeConfig:
    for config in configs:
        if config.name == name:
            return config
    raise KeyError(name)

dry_run = config_lookup('dry-run')

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
    log_filename: str | None = None
    log_entries: list[dict[str, Any]] = field(default_factory=list)
    log_lock: RLock  = field(default_factory=RLock)
    time_lock: RLock = field(default_factory=RLock)
    timelike: Mutable[Timelike] = Mutable.factory(cast(Any, 'initialize in __post_init__ based on config.timelike_factory'))
    times: dict[str, list[float]] = field(default_factory=lambda: cast(Any, defaultdict(list)))

    start_time: datetime = field(default_factory=datetime.now)

    checkpoint_times: dict[str, float] = field(default_factory=dict)
    checkpoint_waits: dict[str, list[Queue[None]]] = field(default_factory=
        lambda: defaultdict[str, list[Queue[None]]](list)
    )

    def __post_init__(self):
        self.timelike.value = self.config.timelike_factory()
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
        threading.Thread(target=F, daemon=True).start()

    @contextmanager
    def excepthook(self):
        try:
            yield
        except BaseException:
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

        # the logging logic is quite convoluted so let's safeguard against software errors in it
        try:
            line = self.log_entry_to_line(entry)
        except BaseException:
            traceback.print_exc()
            utils.pr(entry)
            line = None
        if line:
            with self.log_lock:
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

    active: set[str] = field(default_factory=set)

    def log_entry_to_line(self, entry: dict[str, Any]) -> str | None:
        source = entry.get('source') or ''
        kind = entry.get('kind') or ''
        plate_id = entry.get('event_plate_id') or ''
        part = entry.get('event_part') or ''

        if not self.log_filename:
            return
        if entry.get('silent'):
            return
        if source == 'robotarm' and kind == 'end':
            return
        if source in ('wait', 'idle'):
            if kind != 'info':
                return
            if entry.get('thread'):
                if entry.get('log_sleep'):
                    pass
                else:
                    return
        if source == 'checkpoint':
            return

        t = entry.get('t')
        if isinstance(t, (int, float)):
            t = self.pp_time_offset(t)
        else:
            t = '--:--:--'

        arg = str(entry.get('arg'))
        last = ' '
        if source == 'duration' and kind == 'end':
            secs = float(entry.get("duration", 0.0) or 0.0)
            arg = f'`{arg}` = {utils.pp_secs(secs)}'
        elif (incu_loc := entry.get("incu_loc")):
            arg = f'{arg} {incu_loc} {kind}'
        elif source in ('wash', 'disp'):
            if 'Validate ' in arg and kind == 'begin':
                return
            arg = arg.replace('RunValidated ', '')
            arg = arg.replace('Run ', '')
            arg = trim_LHC_filenames(arg)
            arg = arg + ' '
            arg = f'{arg:─<50}'
            if (T := entry.get('duration')):
                r = f'─ {utils.pp_secs(T)}s ─'
            else:
                r = ''
            arg = arg[:len(arg)-len(r)] + r
            last = '─'

        if source == 'robotarm' and 'return' in arg:
            return

        def color(src: str, s: str):
            if src == 'wash':
                return utils.Color().cyan(s)
            elif src == 'disp':
                return utils.Color().lightred(s)
            else:
                return utils.Color().none(s)

        if source in ('idle', 'wait'):
            for machine in ('wash', 'disp', 'incu'):
                thread = str(entry.get('thread', ''))
                if thread.startswith(machine):
                    source = machine + ' ' + source
                    # arg = f'{machine}: {arg}'

        column_order = 'disp wash'.split()
        columns = ''
        for c in column_order:
            s = source if 'Validate ' not in arg else ''
            if s == c and kind == 'begin':
                self.active.add(c)
                columns += color(c, '┬')
            elif s == c and kind == 'end':
                self.active.remove(c)
                columns += color(c, '┴')
            elif c in self.active:
                columns += color(c, '│')
            else:
                columns += color(source, last)
            columns += color(source, last)

        src = dict(
            wash='washer',
            incu='incubator',
            disp='dispenser',
        ).get(source, source)

        parts = [
            t,
            f'{src     : <9}',
            f'{arg     : <50}' + columns,
            f'{plate_id: >2}',
            f'{part    : <6}',
        ]

        parts = [color(source, part) for part in parts]
        line = color(source, ' | ').join(parts)
        return line

    def timeit(self, source: str, arg: str | int | None = None, metadata: dict[str, Any] = {}) -> ContextManager[None]:
        # The inferred type for the decorated function is wrong hence this wrapper to get the correct type

        @contextmanager
        def worker(source: str, arg: str | int | None, metadata: dict[str, Any]):
            t0 = self.log('begin', source, arg=arg, metadata=metadata)
            yield
            self.log('end', source, arg=arg, metadata=metadata, t0=t0)

        return worker(source, arg, metadata)

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

