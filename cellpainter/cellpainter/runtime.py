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
from pbutils import pp_secs, p
from pbutils.mixins import DB

from .timelike import Timelike, WallTime, SimulatedTime
from .moves import World, Effect

from .log import Message, CommandState, CommandWithMetadata, Metadata, Error, Log, RuntimeMetadata

from labrobots import WindowsNUC, Biotek, STX

import contextlib

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

    def make_runtime(self) -> Runtime:
        return Runtime(
            config=self,
            timelike=self.make_timelike(),
            log_db=DB.connect(self.log_filename if self.log_filename else ':memory:'),
        )

    def make_timelike(self) -> Timelike:
        return self.timelike_factory()

    def replace(self,
        robotarm_speed:       Keep | int                 = keep,
        log_filename:         Keep | str | None          = keep,
    ):
        next = self
        updates = dict(
            robotarm_speed=robotarm_speed,
            log_filename=log_filename,
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
    RuntimeConfig('live',         WallTime,      robotarm_env=RobotarmEnvs.live,      run_incu_wash_disp=True,),
    RuntimeConfig('ur-simulator', WallTime,      robotarm_env=RobotarmEnvs.simulator, run_incu_wash_disp=False),
    RuntimeConfig('forward',      WallTime,      robotarm_env=RobotarmEnvs.forward,   run_incu_wash_disp=False),
    RuntimeConfig('simulate-wall',     WallTime,      robotarm_env=RobotarmEnvs.dry,       run_incu_wash_disp=False),
    RuntimeConfig('simulate',          SimulatedTime, robotarm_env=RobotarmEnvs.dry,       run_incu_wash_disp=False),
]

def config_lookup(name: str) -> RuntimeConfig:
    for config in configs:
        if config.name == name:
            return config
    raise KeyError(name)

simulate = config_lookup('simulate')

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

    log_db: DB = field(default_factory=lambda: DB.connect(':memory:'))

    incu: STX    | None = None
    wash: Biotek | None = None
    disp: Biotek | None = None

    lock: RLock = field(default_factory=RLock)

    start_time: datetime = field(default_factory=datetime.now)

    checkpoint_times: dict[str, float] = field(default_factory=dict)
    checkpoint_waits: dict[str, list[Queue[None]]] = field(default_factory=
        lambda: defaultdict[str, list[Queue[None]]](list)
    )

    world: World | None = None

    def __post_init__(self):
        self.register_thread('main')

        if self.log_db:
            self.log_db.con.execute('pragma synchronous=OFF;')

        if self.config.name != 'simulate':
            def handle_signal(signum: int, _frame: Any):
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                signal.signal(signal.SIGQUIT, signal.SIG_DFL)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                signal.signal(signal.SIGABRT, signal.SIG_DFL)
                pid = os.getpid()
                self.log(Message(f'Received {signal.strsignal(signum)}, shutting down ({pid=})', is_error=True))
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
        return Log(self.log_db)

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
            self.log(Message(f'{type(e).__name__}: {e}', traceback=traceback.format_exc(), is_error=True))
            if not isinstance(e, SystemExit):
                os.kill(os.getpid(), signal.SIGTERM)

    def log(self, message: Message) -> Message:
        with self.lock:
            t = round(self.monotonic(), 3)
            message = message.replace(t=t).save(self.log_db)
            if message.traceback:
                print(message.msg, file=sys.stderr)
                print(message.traceback, file=sys.stderr)
            return message

    def set_world(self, world: World | None):
        with self.lock:
            if world is not None:
                world = world.replace(t=round(self.timelike.monotonic(), 3))
                world = world.save(self.log_db)
            self.world = world

    def apply_effect(self, effect: Effect, entry: CommandWithMetadata | None):
        with self.lock:
            if self.world is None:
                return
            try:
                next = effect.apply(self.world)
            except Exception as error:
                fatal = self.config.name == 'simulate'
                msg = pbutils.show({
                    'message': 'Cannot apply effect at this world',
                    'effect': effect,
                    'world': self.world,
                    'error': error,
                    'entry': entry,
                }, use_color=False)
                if entry:
                    self.log(entry.message(msg, is_error=True))
                if fatal:
                    raise ValueError(msg)
            else:
                if next.data != self.world.data:
                    self.set_world(next)

    def log_state(self, state: CommandState) -> str | None:
        pass
        # with self.lock:
        #     print(f'{state.state: >10}', state.cmd_type, *astuple(state.cmd))
            # m = entry.metadata
            # if entry.err:
            #     pass
            # elif not self.config.log_filename:
            #     return
            # elif m.dry_run_sleep:
            #     return
            # t = self.pp_time_offset(entry.t)
            # if entry.cmd:
            #     desc = ', '.join(f'{k}={v}' for k, v in pbutils.nub(entry.cmd).items() if k != 'machine')
            # else:
            #     desc = ''
            # if entry.msg:
            #     desc = entry.msg
            # machine = entry.machine() or entry.cmd.__class__.__name__
            # if entry.cmd is None:
            #     machine = ''
            # if machine in ('WaitForCheckpoint', 'Idle'):
            #     machine = 'wait'
            # if machine in ('robotarm', 'wait') and entry.is_end():
            #     return
            # if entry.is_end() and machine in ('wash', 'disp', 'incu'):
            #     machine += ' done'
            # machine = machine.lower()
            # if machine == 'duration':
            #     desc = f"`{getattr(entry.cmd, 'name', '?')}` = {pbutils.pp_secs(entry.duration or 0)}"
            # desc = re.sub('^automation_', '', desc)
            # desc = re.sub(r'\.LHC', '', desc)
            # desc = re.sub(r'\w*path=', '', desc)
            # desc = re.sub(r'\w*name=', '', desc)
            # if not desc:
            #     desc = str(pbutils.nub(entry.metadata))

            # if entry.err and entry.err.message:
            #     desc = entry.err.message
            #     print(entry.err.message)

            # w = ','.join(f'{k}:{v}' for k, v in self.world.data.items())
            # parts = [
            #     t,
            #     f'{m.id or ""       : >4}',
            #     f'{machine[:12]     : <12}',
            #     f'{desc[:50]        : <50}',
            #     f'{m.plate_id or "" : >2}',
            #     f'{m.step           : <9}',
            #     f'{w                : <30}',
            # ]
            # return ' | '.join(parts)

    def timeit(self, entry: CommandWithMetadata) -> ContextManager[None]:
        # The inferred type for the decorated function is wrong hence this wrapper to get the correct type

        try:
            id = entry.metadata.id
            assert id
        except:
            pbutils.pr(('no id on:', entry))
            return contextlib.nullcontext()

        @contextmanager
        def worker():
            with self.lock:
                t0 = round(self.monotonic(), 3)
                state = CommandState(
                    t0=t0,
                    t=t0 + (entry.metadata.est or 3),
                    cmd=entry.cmd,
                    metadata=entry.metadata,
                    state='running',
                    id=id,
                ).save(self.log_db)
                self.log_state(state)
            yield
            with self.lock:
                t = round(self.monotonic(), 3)
                state.state='completed'
                state.t=t
                state = state.save(self.log_db)
                self.log_state(state)

        return worker()

    def timeit_end(self, entry: CommandWithMetadata, t0: float):
        # for Duration

        id = int(entry.metadata.id)
        assert id >= 0

        with self.lock:
            t0 = round(t0, 3)
            t = round(self.monotonic(), 3)
            state = CommandState(
                t0=t0,
                t=t,
                cmd=entry.cmd,
                metadata=entry.metadata,
                state='completed',
                id=id,
            ).save(self.log_db)
            self.log_state(state)

    def pp_time_offset(self, secs: int | float):
        dt = self.start_time + timedelta(seconds=secs)
        return dt.strftime('%H:%M:%S') # + dt.strftime('.%f')[:3]

    def now(self) -> datetime:
        return self.start_time + timedelta(seconds=self.monotonic())

    def monotonic(self) -> float:
        return self.timelike.monotonic()

    def sleep(self, secs: float, entry: CommandWithMetadata):
        secs = round(secs, 3)
        if abs(secs) < 0.1:
            _msg = f'on time {pp_secs(secs)}s'
        elif secs < 0:
            _msg = f'behind time {pp_secs(secs)}s'
        else:
            to = self.pp_time_offset(self.monotonic() + secs)
            _msg = f'sleeping to {to} ({pp_secs(secs)}s)'
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

    def checkpoint(self, name: str, entry: CommandWithMetadata):
        with self.lock:
            assert name not in self.checkpoint_times, f'{name!r} already checkpointed in {pbutils.show(self.checkpoint_times, use_color=False)}'
            self.checkpoint_times[name] = self.monotonic()
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

    def wait_for_checkpoint(self, name: str) -> float:
        q = self.enqueue_for_checkpoint(name)
        self.queue_get(q)
        with self.lock:
            return self.checkpoint_times[name]
