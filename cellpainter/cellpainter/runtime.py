from __future__ import annotations
from dataclasses import *
from typing import *

import os
import signal
import sys
import threading
import traceback
import functools

from contextlib import contextmanager
from datetime import datetime, timedelta
from queue import Queue
from threading import RLock

import pbutils
from pbutils.mixins import DB, DBMixin

from .ur import UR
from .pf import PF
from .timelike import Timelike, WallTime, SimulatedTime
from .moves import World, Effect
from .log import Message, CommandState, CommandWithMetadata, ProgressText, Log

from labrobots import WindowsNUC, Biotek, Fridge, BlueWash, BarcodeReader
from labrobots import WindowsGBG, STX, BarcodeReader
from labrobots import MikroAsus, Squid

import contextlib

import sqlite3
from labrobots.sqlitecell import SqliteCell

LockName = Literal['PF and Fridge', 'Squid', 'Nikon']

@dataclass(frozen=True)
class UREnv:
    mode: Literal['noop', 'execute', 'execute no gripper']
    host: str
    port: int

class UREnvs:
    live      = UREnv('execute', '10.10.0.112', 30001)
    forward   = UREnv('execute', '127.0.0.1', 30001)
    simulator = UREnv('execute no gripper', '127.0.0.1', 30001)
    dry       = UREnv('noop', '', 0)

@dataclass(frozen=True)
class PFEnv:
    mode: Literal['noop', 'execute']
    host: str
    _: KW_ONLY
    port_rw: int
    port_ro: int

class PFEnvs:
    live      = PFEnv('execute', '10.10.0.98', port_rw=10100, port_ro=10000)
    forward   = PFEnv('execute', 'localhost',  port_rw=10100, port_ro=10000)
    dry       = PFEnv('noop', '', port_rw=0, port_ro=0)

@dataclass(frozen=True)
class RuntimeConfig(DBMixin):
    name:                   str = 'simulate'
    timelike:               Literal['WallTime', 'SimulatedTime'] = 'SimulatedTime'
    ur_env:                 UREnv = UREnvs.dry
    pf_env:                 PFEnv = PFEnvs.dry
    _: KW_ONLY
    run_incu_wash_disp:     bool = False
    run_fridge_squid_nikon: bool = False

    # ur_speed: int = 100
    # pf_speed: int = 50
    log_filename: str | None = None

    def only_arm(self) -> RuntimeConfig:
        return self.replace(
            run_incu_wash_disp=False,
            run_fridge_squid_nikon=False,
        )

    def make_runtime(self) -> Runtime:
        import weakref
        if self.run_fridge_squid_nikon or self.pf_env.mode == 'execute':
            # Activate this when Nikon is relevant:
            # # locks_db_filepath, cleanup = 'locks.db', lambda: None
            locks_db_filepath, cleanup = ResourceLock.make_temp_db_filepath()
        else:
            locks_db_filepath, cleanup = ResourceLock.make_temp_db_filepath()
        runtime = Runtime(
            config=self,
            time=self.make_timelike(),
            locks_db_filepath=locks_db_filepath,
            log_db=DB.connect(self.log_filename if self.log_filename else ':memory:'),
        )
        weakref.finalize(runtime, cleanup)
        return runtime

    def make_timelike(self) -> Timelike:
        if self.timelike == 'WallTime':
            return WallTime()
        elif self.timelike == 'SimulatedTime':
            return SimulatedTime()
        else:
            raise ValueError(f'No such {self.timelike=}')

    def __post_init__(self):
        if self.ur_env.mode != 'noop' and self.pf_env.mode != 'noop':
            raise ValueError(f'Not allowed: PF & UR ({self=})')
        if self.run_incu_wash_disp and self.run_fridge_squid_nikon:
            raise ValueError(f'Not allowed: cellpainting room and microscope room ({self=})')

configs: list[RuntimeConfig]
configs = [
    # UR:
    RuntimeConfig('live',          'WallTime',      UREnvs.live,      PFEnvs.dry,     run_incu_wash_disp=True,   run_fridge_squid_nikon=False),
    RuntimeConfig('ur-simulator',  'WallTime',      UREnvs.simulator, PFEnvs.dry,     run_incu_wash_disp=False,  run_fridge_squid_nikon=False),
    RuntimeConfig('forward',       'WallTime',      UREnvs.forward,   PFEnvs.dry,     run_incu_wash_disp=False,  run_fridge_squid_nikon=False),

    # PF:
    RuntimeConfig('pf-live',       'WallTime',      UREnvs.dry,       PFEnvs.live,    run_incu_wash_disp=False,  run_fridge_squid_nikon=True),
    RuntimeConfig('pf-forward',    'WallTime',      UREnvs.dry,       PFEnvs.forward, run_incu_wash_disp=False,  run_fridge_squid_nikon=False),

    # Simulate:
    RuntimeConfig('simulate-wall', 'WallTime',      UREnvs.dry,       PFEnvs.dry,     run_incu_wash_disp=False,  run_fridge_squid_nikon=False),
    RuntimeConfig('simulate',      'SimulatedTime', UREnvs.dry,       PFEnvs.dry,     run_incu_wash_disp=False,  run_fridge_squid_nikon=False),
]

def config_from_argv(argv: list[str]=sys.argv) -> RuntimeConfig:
    for c in configs:
        if '--' + c.name in sys.argv:
            return c
    else:
        raise ValueError('Start with one of ' + ', '.join('--' + c.name for c in configs))

def config_lookup(name: str) -> RuntimeConfig:
    return {c.name: c for c in configs}[name]

simulate = config_lookup('simulate')

def make_process_name():
    import platform
    import os
    pid = os.getpid()
    node = platform.node()
    return f'{pid}@{node}'

process_name = make_process_name()

A = TypeVar('A')

@dataclass
class Runtime:
    config: RuntimeConfig

    time: Timelike

    locks_db_filepath: str

    log_db: DB = field(default_factory=lambda: DB.connect(':memory:'))

    lock: RLock = field(default_factory=RLock)

    start_time: datetime = field(default_factory=datetime.now)

    checkpoint_times: dict[str, float] = field(default_factory=dict)
    checkpoint_waits: dict[str, list[Queue[None]]] = field(default_factory=
        lambda: DefaultDict[str, list[Queue[None]]](list)
    )

    ur: UR | None = None
    pf: PF | None = None

    incu: STX      | None = None
    wash: Biotek   | None = None
    disp: Biotek   | None = None
    blue: BlueWash | None = None

    fridge: Fridge | None = None
    barcode_reader: BarcodeReader | None = None
    squid: Squid | None = None
    nikon: None = None

    @property
    def fridge_and_barcode_reader(self):
        if self.fridge and self.barcode_reader:
            return self.fridge, self.barcode_reader
        else:
            return None

    def __post_init__(self):
        self.init()

    def init(self):
        self.time.register_thread('main')

        if self.log_db:
            self.log_db.con.execute('pragma synchronous=OFF;')

        install_handlers='simulate' not in self.config.name

        if install_handlers:
            def handle_signal(signum: int, _frame: Any):
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                signal.signal(signal.SIGQUIT, signal.SIG_DFL)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                signal.signal(signal.SIGABRT, signal.SIG_DFL)
                pid = os.getpid()
                self.log(Message(f'Received {signal.strsignal(signum)}, shutting down ({pid=})', is_error=True))
                self.stop_arms()
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
            self.blue = nuc.blue

        if self.config.ur_env.mode != 'noop':
            self.ur = UR(
                host=self.config.ur_env.host,
                port=self.config.ur_env.port,
            )

        if self.config.pf_env.mode != 'noop':
            self.pf = PF(
                host=self.config.pf_env.host,
                port_rw=self.config.pf_env.port_rw,
                port_ro=self.config.pf_env.port_ro,
            )

        if self.config.run_fridge_squid_nikon:
            gbg = WindowsGBG.remote()
            mikro_asus = MikroAsus.remote()
            self.fridge = gbg.fridge
            self.barcode_reader = gbg.barcode
            self.squid = mikro_asus.squid

    def stop_arms(self):
        sync = Queue[None]()

        @pbutils.spawn
        def _():
            if self.ur:
                self.ur.stop()
            sync.put_nowait(None)

        try:
            sync.get(block=True, timeout=3)
        except:
            pass

    def get_log(self) -> Log:
        return Log(self.log_db)

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
            t = self.monotonic()
            message = message.replace(t=t).save(self.log_db)
            if message.traceback:
                print(message.msg, file=sys.stderr)
                print(message.traceback, file=sys.stderr)
            return message

    world: World | None = None

    def set_world(self, world: World | None):
        with self.lock:
            if world is not None:
                world = world.replace(t=self.time.monotonic())
                world = world.save(self.log_db)
            self.world = world

    def apply_effect(self, effect: Effect, entry: CommandWithMetadata | None, fatal_errors: bool=False):
        with self.lock:
            if self.world is None:
                return
            try:
                next = effect.apply(self.world)
            except Exception as error:
                msg = pbutils.show({
                    'message': 'Cannot apply effect at this world',
                    'effect': effect,
                    'world': self.world,
                    'error': error,
                    'entry': entry,
                }, use_color=False)
                if entry:
                    self.log(entry.message(msg, is_error=True))
                if fatal_errors:
                    raise ValueError(msg)
            else:
                if next.data != self.world.data:
                    self.set_world(next)

    def log_state(self, state: CommandState) -> str | None:
        if 0:
            if state.cmd_type == 'RobotarmCmd':
                return
            if state.cmd_type == 'Checkpoint' and state.state == 'running':
                return
        if 0:
            with self.lock:
                print(
                    f'{state.metadata.step_desc or "": >13}',
                    f'plate {state.metadata.plate_id or "": >2}',
                    f'{self.time.current_thread_name()   : >10}',
                    f'{state.state                  : >10}',
                    state.cmd_type,
                    *astuple(state.cmd), # type: ignore
                    f'{self.world}',
                    sep=' | ',
                )

    def time_resource_use(self, entry: CommandWithMetadata, resource: A | None) -> Iterator[A]:
        '''
        The loop will be run once if the resource exists, otherwise not run.
        '''
        with self.timeit(entry):
            if resource:
                print(entry, 'yields', resource)
                yield resource
                print(entry, 'finished with', resource)
            else:
                est = entry.metadata.est
                if est is None:
                    raise ValueError(f'No estimate for {entry}')
                total = est + (entry.metadata.sim_delay or 0.0)
                if self.config.name == 'simulate-wall' and 'squid' in entry.cmd.type.lower():
                    t0 = self.monotonic()
                    while True:
                        elapsed = self.monotonic() - t0
                        remain = total - elapsed
                        self.set_progress_text(entry, f'progress: {round(100 * elapsed / total)}%')
                        if remain > 1.0:
                            self.sleep(1.0)
                        else:
                            self.sleep(remain)
                            break
                else:
                    self.sleep(total)

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
                t0 = self.monotonic()
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
                t = self.monotonic()
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
            t = self.monotonic()
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
        return round(self.time.monotonic(), 3)

    def sleep(self, secs: float | int):
        self.time.sleep(secs)

    def register_thread(self, name: str):
        self.time.register_thread(name)

    def thread_done(self):
        self.time.thread_done()

    def checkpoint(self, name: str, entry: CommandWithMetadata):
        with self.lock:
            assert name not in self.checkpoint_times, f'{name!r} already checkpointed in {pbutils.show(self.checkpoint_times, use_color=False)}'
            self.checkpoint_times[name] = t = self.monotonic()
            for q in self.checkpoint_waits[name]:
                self.time.queue_put_nowait(q, None)
            self.checkpoint_waits[name].clear()
            return t

    def enqueue_for_checkpoint(self, name: str):
        q: Queue[None] = Queue()
        with self.lock:
            if name in self.checkpoint_times:
                self.time.queue_put_nowait(q, None) # prepopulate it
            else:
                self.checkpoint_waits[name] += [q]
        return q

    def wait_for_checkpoint(self, name: str) -> float:
        q = self.enqueue_for_checkpoint(name)
        self.time.queue_get(q)
        with self.lock:
            return self.checkpoint_times[name]

    def set_progress_text(self, entry: CommandWithMetadata, text: str):
        id = int(entry.metadata.id)
        assert id >= 0
        with self.lock:
            ProgressText(text=text, id=id).save(self.log_db)

    def runtime_name(self):
        parts = [
            self.config.log_filename or
            self.start_time.replace(microsecond=0).isoformat(sep=' ') + ' ' + self.config.name,
            process_name,
        ]
        return ' '.join(parts)

    def resource_lock(self, lock_name: LockName):
        return ResourceLock(
            db_filepath=self.locks_db_filepath,
            process_name=self.runtime_name(),
            lock_name=lock_name,
        )

    def acquire_lock(self, lock_name: LockName, num_tries: int = -1, entry: CommandWithMetadata | None = None):
        while num_tries != 0:
            if self.resource_lock(lock_name).acquire_lock():
                return
            text = f'Waiting for lock: {lock_name} ({abs(num_tries)}...)'
            print(text)
            if entry:
                self.set_progress_text(entry, text=text)
            self.sleep(1.0)
            num_tries -= 1
        raise ValueError(f'Failed to acquire {lock_name!r}')

    def assert_lock(self, lock_name: LockName):
        self.resource_lock(lock_name).assert_lock()

    def release_lock(self, lock_name: LockName):
        self.resource_lock(lock_name).release_lock()

@dataclass(frozen=True, kw_only=True)
class ResourceLock:
    db_filepath: str
    process_name: str
    lock_name: LockName

    @contextlib.contextmanager
    def open_exclusive(self):
        con = sqlite3.connect(self.db_filepath, isolation_level=None)
        with contextlib.closing(con):
            lock = SqliteCell(con, table='Lock', key=self.lock_name, default='')
            with lock.exclusive():
                yield lock

    def acquire_lock(self) -> bool:
        with self.open_exclusive() as lock:
            current = lock.read()
            if current:
                # raise ValueError('Trying to acquire lock {name!r} but {current=!r} is holding it')
                return False
            else:
                lock.write(self.process_name)
                return True

    def assert_lock(self):
        with self.open_exclusive() as lock:
            current = lock.read()
            if current != self.process_name:
                raise ValueError(f'Expected to hold {self.lock_name!r} but {current=!r} is holding it (!= {self.process_name=!r})')

    def release_lock(self):
        with self.open_exclusive() as lock:
            current = lock.read()
            if current != self.process_name:
                raise ValueError(f'Trying to release lock {self.lock_name!r} but {current=!r} is holding it (!= {self.process_name=!r})')
            else:
                lock.write('')

    @staticmethod
    def make_temp_db_filepath():
        import tempfile
        import atexit
        import shutil
        from pathlib import Path
        tmpdir = tempfile.mkdtemp(prefix='robotlab-locks-db-')
        todo = True
        def cleanup():
            nonlocal todo
            if todo:
                todo = False
                shutil.rmtree(tmpdir, ignore_errors=True)
                0 and print('Cleaned up', tmpdir)
            else:
                0 and print('Already cleaned up', tmpdir)
        atexit.register(cleanup)
        return str(Path(tmpdir) / 'locks.db'), cleanup

def test_resource_locks():
    import pytest
    runtime = simulate.make_runtime()

    runtime.acquire_lock('Squid')
    runtime.assert_lock('Squid')

    with pytest.raises(ValueError):
        runtime.acquire_lock('Squid', num_tries=1)

    runtime.release_lock('Squid')

    with pytest.raises(ValueError):
        runtime.assert_lock('Squid')

    with pytest.raises(ValueError):
        runtime.release_lock('Squid')

    runtime.acquire_lock('Squid')
    with pytest.raises(ValueError):
        runtime.assert_lock('Nikon')
    runtime.acquire_lock('Nikon')

    runtime.assert_lock('Squid')
    runtime.assert_lock('Nikon')
    with pytest.raises(ValueError):
        runtime.assert_lock('PF and Fridge')
    runtime.release_lock('Nikon')
    with pytest.raises(ValueError):
        runtime.assert_lock('Nikon')
    runtime.release_lock('Squid')
