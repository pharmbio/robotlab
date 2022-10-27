from __future__ import annotations
from dataclasses import *
from typing import *

import os
import re
import signal
import sys
import threading
import traceback

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from queue import Queue
from threading import RLock

from .robotarm import Robotarm
import pbutils
from pbutils import pp_secs

from .timelike import Timelike, WallTime, SimulatedTime
from .moves import World, Effect

from .log import LogEntry, Metadata, Error, Running, Log

import time

from labrobots import WindowsNUC, Biotek, STX

@dataclass(frozen=True)
class RobotarmEnv:
    mode: Literal['noop', 'execute', 'execute no gripper', ]
    host: str # = 'http://[100::]' # RFC 6666: A Discard Prefix for IPv6
    port: int # = 30001

class RobotarmEnvs:
    live      = RobotarmEnv('execute', '10.10.0.112', 30001)
    forward   = RobotarmEnv('execute', 'localhost', 30001)
    simulator = RobotarmEnv('execute no gripper', 'localhost', 30001)
    dry       = RobotarmEnv('noop', '', 0)

@dataclass(frozen=True)
class ResumeConfig:
    start_time: datetime
    checkpoint_times: dict[str, float]
    secs_ago: float = 0.0

    @staticmethod
    def init(log: Log, now: datetime | None | str=None):
        if isinstance(now, str):
            now = datetime.fromisoformat(now)
        if now is None:
            now = datetime.now()
        start_time = log.zero_time()
        secs_ago = (now - start_time).total_seconds()
        return ResumeConfig(start_time, log.checkpoints(), secs_ago)

@dataclass(frozen=True)
class Keep:
    pass

keep = Keep()

@dataclass(frozen=True)
class RuntimeConfig:
    name:               str
    timelike_factory:   Callable[[], Timelike]
    robotarm_env:       RobotarmEnv
    run_incu_wash_disp: bool

    robotarm_speed: int = 100
    log_filename: str | None = None
    running_log_filename: str | None = None
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
        robotarm_speed:       Keep | int                 = keep,
        log_filename:         Keep | str | None          = keep,
        running_log_filename: Keep | str | None          = keep,
        log_to_file:          Keep | bool                = keep,
        resume_config:        Keep | ResumeConfig | None = keep,
    ):
        next = self
        updates = dict(
            robotarm_speed=robotarm_speed,
            log_filename=log_filename,
            running_log_filename=running_log_filename,
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
    RuntimeConfig('live',      WallTime,      robotarm_env=RobotarmEnvs.live,      run_incu_wash_disp=True,),
    RuntimeConfig('simulator', WallTime,      robotarm_env=RobotarmEnvs.simulator, run_incu_wash_disp=False),
    RuntimeConfig('forward',   WallTime,      robotarm_env=RobotarmEnvs.forward,   run_incu_wash_disp=False),
    RuntimeConfig('dry-wall',  WallTime,      robotarm_env=RobotarmEnvs.dry,       run_incu_wash_disp=False),
    RuntimeConfig('dry-run',   SimulatedTime, robotarm_env=RobotarmEnvs.dry,       run_incu_wash_disp=False),
]

def config_lookup(name: str) -> RuntimeConfig:
    for config in configs:
        if config.name == name:
            return config
    raise KeyError(name)

dry_run = config_lookup('dry-run')

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
    if config.robotarm_env.mode == 'noop':
        return Robotarm.init_noop(with_gripper=include_gripper, quiet=quiet)
    assert config.robotarm_env.mode == 'execute' or config.robotarm_env.mode == 'execute no gripper'
    with_gripper = config.robotarm_env.mode == 'execute'
    if not include_gripper:
        with_gripper = False
    return Robotarm.init(config.robotarm_env.host, config.robotarm_env.port, with_gripper, quiet=quiet)

import typing
class CheckpointLike(typing.Protocol):
    name: str

A = TypeVar('A')

@dataclass
class Runtime:
    config: RuntimeConfig
    timelike: Timelike

    incu: STX    | None = None
    wash: Biotek | None = None
    disp: Biotek | None = None

    log_entries: list[LogEntry] = field(default_factory=list)
    lock: RLock = field(default_factory=RLock)

    start_time: datetime = field(default_factory=datetime.now)

    checkpoint_times: dict[str, float] = field(default_factory=dict)
    checkpoint_waits: dict[str, list[Queue[None]]] = field(default_factory=
        lambda: defaultdict[str, list[Queue[None]]](list)
    )

    def __post_init__(self):
        self.register_thread('main')

        if self.config.name != 'dry-run':
            def handle_signal(signum: int, _frame: Any):
                pid = os.getpid()
                self.log(LogEntry(err=Error(f'Received {signal.strsignal(signum)}, shutting down ({pid=})')))
                self.stop_arm()
                sys.exit(1)

            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGQUIT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGABRT, handle_signal)

            print('Signal handlers installed')

        if self.config.run_incu_wash_disp:
            nuc = WindowsNUC.remote()
            self.incu = nuc.incu
            self.wash = nuc.wash
            self.disp = nuc.disp

        self.set_robotarm_speed(self.config.robotarm_speed)

    def get_log(self) -> Log:
        return Log(self.log_entries)

    def kill(self):
        self.stop_arm()
        os.kill(os.getpid(), signal.SIGINT)

    def get_robotarm(self, quiet: bool = True, include_gripper: bool = True) -> Robotarm:
        return get_robotarm(self.config, quiet=quiet, include_gripper=include_gripper)

    def stop_arm(self):
        sync = Queue[None]()

        @pbutils.spawn
        def _():
            arm = self.get_robotarm(quiet=False, include_gripper=False)
            arm.stop()
            arm.close()
            sync.put_nowait(None)

        try:
            sync.get(block=True, timeout=3)
        except:
            pass

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
            self.log(LogEntry(err=Error(reprlib.repr(e), traceback.format_exc())))
            if not isinstance(e, SystemExit):
                os.kill(os.getpid(), signal.SIGTERM)

    def log(self, entry: LogEntry, t0: float | None = None) -> LogEntry:
        with self.lock:
            t = round(self.monotonic(), 3)
            log_time = self.now()
            entry = entry.init(
                log_time=str(log_time),
                t=t,
                t0=t0,
            )
            if entry.running:
                if self.config.running_log_filename:
                    pbutils.serializer.write_jsonl([entry], self.config.running_log_filename, mode='a')
                return entry
            # the logging logic is quite convoluted so let's safeguard against software errors in it
            try:
                line = self.log_entry_to_line(entry)
            except BaseException:
                traceback.print_exc()
                pbutils.pr(entry)
                line = None
            if line:
                print(line)
            if entry.err and entry.err.traceback:
                print(entry.err.traceback, file=sys.stderr)
            log_filename = self.config.log_filename
            if log_filename:
                pbutils.serializer.write_jsonl([entry], log_filename, mode='a')
            self.log_entries.append(entry)
            return entry

    def apply_effect(self, effect: Effect, entry: LogEntry | None = None):
        # return
        with self.lock:
            try:
                next = effect.apply(self.world)
            except Exception as error:
                import traceback as tb
                fatal = self.config.name == 'dry-run'
                message = pbutils.show({
                    'message': 'Can not apply effect at this world',
                    'effect': effect,
                    'world': self.world,
                    'error': error,
                }, use_color=False)
                self.log(LogEntry(
                    cmd=entry.cmd if entry else None,
                    err=Error(message, tb.format_exc())
                ))
                if fatal:
                    raise ValueError(message)
            else:
                if next != self.world:
                    self.world = next
                    self.log_running()

    def log_entry_to_line(self, entry: LogEntry) -> str | None:
        with self.lock:
            m = entry.metadata
            if entry.err:
                pass
            elif entry.cmd is None and entry.running:
                return
            elif not self.config.log_filename:
                return
            elif m.dry_run_sleep:
                return
            t = self.pp_time_offset(entry.t)
            if entry.cmd:
                desc = ', '.join(f'{k}={v}' for k, v in pbutils.nub(entry.cmd).items() if k != 'machine')
            else:
                desc = ''
            if entry.msg:
                desc = entry.msg
            machine = entry.machine() or entry.cmd.__class__.__name__
            if entry.cmd is None:
                machine = ''
            if machine in ('WaitForCheckpoint', 'Idle'):
                machine = 'wait'
            if machine in ('robotarm', 'wait') and entry.is_end():
                return
            if entry.is_end() and machine in ('wash', 'disp', 'incu'):
                machine += ' done'
            machine = machine.lower()
            if machine == 'duration':
                desc = f"`{getattr(entry.cmd, 'name', '?')}` = {pbutils.pp_secs(entry.duration or 0)}"
            desc = re.sub('^automation_', '', desc)
            desc = re.sub(r'\.LHC', '', desc)
            desc = re.sub(r'\w*path=', '', desc)
            desc = re.sub(r'\w*name=', '', desc)
            if not desc:
                desc = str(pbutils.nub(entry.metadata))

            if entry.err and entry.err.message:
                desc = entry.err.message
                print(entry.err.message)

            w = ','.join(f'{k}:{v}' for k, v in self.world.items())
            r = ', '.join(
                f'{e.metadata.thread_resource or "main"}:{c.__class__.__name__}'
                for e in self.running_entries
                if (c := e.cmd)
                if not e.metadata.dry_run_sleep
            )
            parts = [
                t,
                f'{m.id or ""       : >4}',
                f'{machine[:12]     : <12}',
                f'{desc[:50]        : <50}',
                f'{m.plate_id or "" : >2}',
                f'{m.step           : <9}',
                f'{w                : <30}',
                f'{r                     }',
            ]
            return ' | '.join(parts)

    running_entries: list[LogEntry] = field(default_factory=list)
    world: World = field(default_factory=dict)

    def running(self) -> Running:
        with self.lock:
            return Running(
                entries=self.running_entries,
                world=self.world,
            )

    def log_running(self):
        with self.lock:
            self.log(LogEntry(running=self.running()))

    def timeit(self, entry: LogEntry) -> ContextManager[None]:
        # The inferred type for the decorated function is wrong hence this wrapper to get the correct type

        @contextmanager
        def worker():
            with self.lock:
                e0 = self.log(entry)
                self.running_entries.append(e0)
                G = pbutils.group_by(self.running_entries, key=lambda e: e.metadata.thread_resource)
                if self.config.name == 'dry-run':
                    for thread_resource, v in G.items():
                        if thread_resource is not None:
                            assert len(v) <= 1, f'list for {thread_resource} should not have more than one element: {pbutils.pr(v)}'
                self.log_running()
            yield
            with self.lock:
                self.log(entry, t0=e0.t)
                self.running_entries.remove(e0)
                self.log_running()

        return worker()

    def pp_time_offset(self, secs: int | float):
        dt = self.start_time + timedelta(seconds=secs)
        return dt.strftime('%H:%M:%S') # + dt.strftime('.%f')[:3]

    def now(self) -> datetime:
        return self.start_time + timedelta(seconds=self.monotonic())

    def monotonic(self) -> float:
        return self.timelike.monotonic()

    def sleep(self, secs: float, entry: LogEntry):
        secs = round(secs, 3)
        entry = entry.add(Metadata(sleep_secs=secs))
        if abs(secs) < 0.1:
            self.log(entry.add(msg=f'on time {pp_secs(secs)}s'))
        elif secs < 0:
            self.log(entry.add(msg=f'behind time {pp_secs(secs)}s'))
        else:
            to = self.pp_time_offset(self.monotonic() + secs)
            self.log(entry.add(msg=f'sleeping to {to} ({pp_secs(secs)}s)'))
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

    def checkpoint(self, name: str, entry: LogEntry):
        with self.lock:
            assert name not in self.checkpoint_times, f'{name!r} already checkpointed in {pbutils.show(self.checkpoint_times, use_color=False)}'
            self.checkpoint_times[name] = self.log(entry).t
            for q in self.checkpoint_waits[name]:
                self.queue_put_nowait(q, None)
            self.checkpoint_waits[name].clear()

    def enqueue_for_checkpoint(self, name: str):
        q: Queue[None] = Queue()
        with self.lock:
            if name in self.checkpoint_times:
                self.queue_put_nowait(q, None) # prepopulate it
            else:
                self.checkpoint_waits[name] += [q]
        return q

    def wait_for_checkpoint(self, name: str):
        q = self.enqueue_for_checkpoint(name)
        self.queue_get(q)
        with self.lock:
            return self.checkpoint_times[name]

