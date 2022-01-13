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

from .robotarm import Robotarm
from . import utils
from .utils import pp_secs

from .timelike import Timelike, WallTime, SimulatedTime
from collections import defaultdict
from .moves import World

import os
import sys
import signal

@dataclass(frozen=True)
class Env:
    robotarm_host: str = 'http://[100::]' # RFC 6666: A Discard Prefix for IPv6
    robotarm_port: int = 30001
    incu_url: str      = 'http://httpbin.org/anything'
    biotek_url: str    = 'http://httpbin.org/anything'

live_env = Env(
    robotarm_host = '10.10.0.112',
    incu_url      = 'http://10.10.0.56:5050/incu',
    biotek_url    = 'http://10.10.0.56:5050',
)

simulator_env = Env(
    robotarm_host = 'localhost',
)

forward_env = Env(
    robotarm_host = 'localhost',
)

dry_env = Env()

import time

@dataclass
class ResumeConfig:
    start_time: datetime
    checkpoint_times: dict[str, float]
    secs_ago: float = 0.0
    def __post_init__(self):
        self.secs_ago = (datetime.now() - self.start_time).total_seconds()

@dataclass(frozen=True)
class Keep:
    pass

keep = Keep()

@dataclass(frozen=True)
class RuntimeConfig:
    name:               str
    timelike_factory:   Callable[[], Timelike]
    disp_and_wash_mode: Literal['noop', 'execute',                       ]
    incu_mode:          Literal['noop', 'execute',                       ]
    robotarm_mode:      Literal['noop', 'execute', 'execute no gripper', ]
    env: Env
    robotarm_speed: int = 100
    log_filename: str | None = None
    log_to_file: bool = True
    resume_config: ResumeConfig | None = None

    def make_runtime(self) -> Runtime:
        resume_config = self.resume_config
        if resume_config:
            return Runtime(
                config=self,
                timelike=self.make_timelike(),
                start_time=resume_config.start_time,
                checkpoint_times=resume_config.checkpoint_times.copy(),
            )
        else:
            return Runtime(
                config=self,
                timelike=self.make_timelike(),
            )

    def make_timelike(self) -> Timelike:
        resume_config = self.resume_config
        if resume_config:
            if self.timelike_factory is WallTime:
                return WallTime(start_time=time.monotonic() - resume_config.secs_ago)
            elif self.timelike_factory is SimulatedTime:
                return SimulatedTime(skipped_time=resume_config.secs_ago)
            else:
                raise ValueError(f'Unknown timelike factory {self.timelike_factory} on config object')
        else:
            return self.timelike_factory()

    def replace(self,
        robotarm_speed: Keep | int                 = keep,
        log_filename:   Keep | str | None          = keep,
        log_to_file:    Keep | bool                = keep,
        resume_config:  Keep | ResumeConfig | None = keep,
    ):
        next = self
        updates = dict(
            robotarm_speed=robotarm_speed,
            log_filename=log_filename,
            log_to_file=log_to_file,
            resume_config=resume_config,
        )
        for k, v in updates.items():
            if v is keep:
                pass
            elif getattr(next, k) is v:
                pass
            else:
                next = replace(next, **{k: v})
        return next

configs: list[RuntimeConfig]
configs = [
    RuntimeConfig('live',          WallTime,        disp_and_wash_mode='execute', incu_mode='execute', robotarm_mode='execute',            env=live_env),
    RuntimeConfig('live-no-incu',  WallTime,        disp_and_wash_mode='execute', incu_mode='noop',    robotarm_mode='execute',            env=live_env),
    RuntimeConfig('simulator',     WallTime,        disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='execute no gripper', env=simulator_env),
    RuntimeConfig('forward',       WallTime,        disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='execute',            env=forward_env),
    RuntimeConfig('dry-wall',      WallTime,        disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='noop',               env=dry_env),
    RuntimeConfig('dry-run',       SimulatedTime,   disp_and_wash_mode='noop',    incu_mode='noop',    robotarm_mode='noop',               env=dry_env),
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
    timelike: Timelike
    log_entries: list[dict[str, Any]] = field(default_factory=list)
    log_lock: RLock  = field(default_factory=RLock)
    time_lock: RLock = field(default_factory=RLock)
    times: dict[str, list[float]] = field(default_factory=lambda: cast(Any, defaultdict(list)))

    start_time: datetime = field(default_factory=datetime.now)

    checkpoint_times: dict[str, float] = field(default_factory=dict)
    checkpoint_waits: dict[str, list[Queue[None]]] = field(default_factory=
        lambda: defaultdict[str, list[Queue[None]]](list)
    )

    def __post_init__(self):
        self.register_thread('main')

        if self.config.name != 'dry-run':
            def handle_signal(signum: int, _frame: Any):
                self.log('error', 'system', f'Received {signal.strsignal(signum)}, shutting down', {'signum': signum})
                self.stop_arm()
                sys.exit(1)

            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGQUIT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGABRT, handle_signal)

            print('Signal handlers installed')

        self.set_robotarm_speed(self.config.robotarm_speed)

    def kill(self):
        self.stop_arm()
        os.kill(os.getpid(), signal.SIGINT)

    def get_robotarm(self, quiet: bool = True, include_gripper: bool = True) -> Robotarm:
        return get_robotarm(self.config, quiet=quiet, include_gripper=include_gripper)

    def stop_arm(self):
        arm = self.get_robotarm(quiet=False, include_gripper=False)
        arm.stop()
        arm.close()

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
        except BaseException as e:
            import reprlib
            self.log('error', 'exception', reprlib.repr(e), {'traceback': traceback.format_exc(), 'repr': repr(e)})
            if not isinstance(e, SystemExit):
                os.kill(os.getpid(), signal.SIGINT)

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
        if tb := entry.get('traceback'):
            print(tb)
        log_filename = self.config.log_filename
        if log_filename:
            with self.log_lock:
                with open(log_filename, 'a') as fp:
                    json.dump(entry, fp)
                    fp.write('\n')
        else:
            self.log_entries.append(entry)
        return t

    active: set[str] = field(default_factory=set)

    def log_entry_to_line(self, entry: dict[str, Any]) -> str | None:
        kind = entry.get('kind') or ''
        step = entry.get('step') or ''
        source = entry.get('source') or ''
        plate_id = entry.get('plate_id') or ''

        log_filename = self.config.log_filename

        if not log_filename:
            return
        if entry.get('silent'):
            return
        if source == 'robotarm' and kind == 'end':
            return
        if source in ('wait', 'idle') and 0:
            if kind != 'info':
                return
            if entry.get('thread'):
                if entry.get('log_sleep'):
                    pass
                else:
                    return
        if source == 'checkpoint' and 0:
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

        diff = entry.get('effect')

        parts = [
            t,
            f'{src     : <9}',
            f'{arg     : <50}' + columns,
            f'{plate_id: >2}',
            f'{entry.get("id", "None"): >4}',
            f'{step    : <6}',
            f'{diff}',
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
        return self.timelike.monotonic()

    def sleep(self, secs: float, metadata: dict[str, Any]):
        if abs(secs) < 0.1:
            self.log('info', 'wait', f'on time {pp_secs(secs)}s', metadata={**metadata, 'secs': secs})
        elif secs < 0:
            self.log('info', 'wait', f'behind time {pp_secs(secs)}s', metadata={**metadata, 'secs': secs})
        else:
            to = self.pp_time_offset(self.monotonic() + secs)
            with self.timeit('wait', f'sleeping to {to} ({pp_secs(secs)}s)', metadata={**metadata, 'secs': secs}):
                self.timelike.sleep(secs)

    def queue_get(self, queue: Queue[A]) -> A:
        return self.timelike.queue_get(queue)

    def queue_put(self, queue: Queue[A], a: A) -> None:
        return self.timelike.queue_put(queue, a)

    def queue_put_nowait(self, queue: Queue[A], a: A) -> None:
        return self.timelike.queue_put_nowait(queue, a)

    def register_thread(self, name: str):
        return self.timelike.register_thread(name)

    def thread_done(self):
        return self.timelike.thread_done()

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

