from __future__ import annotations
from dataclasses import *
from typing import *

import os
import signal
import sys
import threading
import traceback


from contextlib import contextmanager
from datetime import datetime, timedelta
from queue import Queue
from threading import RLock

import pbutils
from pbutils.mixins import DB, DBMixin

from .robotarm import Robotarm
from .timelike import Timelike, WallTime, SimulatedTime
from .moves import World, Effect
from .log import Message, CommandState, CommandWithMetadata, Log

from labrobots import WindowsNUC, Biotek, STX, BlueWash
from labrobots import WindowsGBG, STX, BarcodeReader
from labrobots import MikroAsus, Squid

import contextlib

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
    port: int

class PFEnvs:
    live      = PFEnv('execute', '10.10.0.98', 10100)
    forward   = PFEnv('execute', '127.0.0.1', 10100)
    dry       = PFEnv('noop', '', 0)

@dataclass(frozen=True)
class RuntimeConfig(DBMixin):
    name:                   str = 'simulate'
    timelike:               Literal['WallTime', 'SimulatedTime'] = 'SimulatedTime'
    ur_env:                 UREnv = UREnvs.dry
    pf_env:                 PFEnv = PFEnvs.dry
    _: KW_ONLY
    run_incu_wash_disp:     bool = False
    run_fridge_squid_nikon: bool = False

    ur_speed: int = 100
    pf_speed: int = 100
    log_filename: str | None = None

    def only_arm(self) -> RuntimeConfig:
        return self.replace(
            run_incu_wash_disp=False,
            run_fridge_squid_nikon=False,
        )

    def make_runtime(self) -> Runtime:
        return Runtime(
            config=self,
            time=self.make_timelike(),
            log_db=DB.connect(self.log_filename if self.log_filename else ':memory:'),
        )

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
    RuntimeConfig('live',           'WallTime',      UREnvs.live,      PFEnvs.dry, run_incu_wash_disp=True,  run_fridge_squid_nikon=False),
    RuntimeConfig('ur-simulator',   'WallTime',      UREnvs.simulator, PFEnvs.dry, run_incu_wash_disp=False, run_fridge_squid_nikon=False),
    RuntimeConfig('forward',        'WallTime',      UREnvs.forward,   PFEnvs.dry, run_incu_wash_disp=False, run_fridge_squid_nikon=False),
    RuntimeConfig('simulate-wall',  'WallTime',      UREnvs.dry,       PFEnvs.dry, run_incu_wash_disp=False, run_fridge_squid_nikon=False),
    RuntimeConfig('simulate',       'SimulatedTime', UREnvs.dry,       PFEnvs.dry, run_incu_wash_disp=False, run_fridge_squid_nikon=False),
]

def config_lookup(name: str) -> RuntimeConfig:
    return {c.name: c for c in configs}[name]

simulate = config_lookup('simulate')

A = TypeVar('A')

@dataclass
class Runtime:
    config: RuntimeConfig

    time: Timelike

    log_db: DB = field(default_factory=lambda: DB.connect(':memory:'))

    lock: RLock = field(default_factory=RLock)

    start_time: datetime = field(default_factory=datetime.now)

    checkpoint_times: dict[str, float] = field(default_factory=dict)
    checkpoint_waits: dict[str, list[Queue[None]]] = field(default_factory=
        lambda: DefaultDict[str, list[Queue[None]]](list)
    )

    incu: STX      | None = None
    wash: Biotek   | None = None
    disp: Biotek   | None = None
    blue: BlueWash | None = None

    fridge: STX | None = None
    barcode_reader: BarcodeReader | None = None
    squid: Squid | None = None

    def __post_init__(self):
        self.init()

    def init(self):
        self.time.register_thread('main')

        if self.log_db:
            self.log_db.con.execute('pragma synchronous=OFF;')

        install_handlers=self.config.name != 'simulate'

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
            with self.get_ur() as arm:
                arm.set_speed(self.config.ur_speed)

        if self.config.run_fridge_squid_nikon:
            gbg = WindowsGBG.remote()
            mikro_asus = MikroAsus.remote()
            self.fridge = gbg.fridge
            self.barcode_reader = gbg.barcode
            self.squid = mikro_asus.squid

        if self.config.pf_env.mode != 'noop':
            raise ValueError('todo: set pf speed')
            # self.set_pf_speed(self.config.pf_speed)

    @contextlib.contextmanager
    def get_ur(self, quiet: bool = False, include_gripper: bool = True) -> Iterator[Robotarm]:
        config = self.config
        if config.ur_env.mode == 'noop':
            return Robotarm.init_noop(with_gripper=include_gripper, quiet=quiet)
        assert config.ur_env.mode == 'execute' or config.ur_env.mode == 'execute no gripper'
        with_gripper = config.ur_env.mode == 'execute'
        if not include_gripper:
            with_gripper = False
        arm = Robotarm.init(config.ur_env.host, config.ur_env.port, with_gripper, quiet=quiet)
        yield arm
        arm.close()

    def stop_arms(self):
        sync = Queue[None]()

        @pbutils.spawn
        def _():
            with self.get_ur(quiet=False, include_gripper=False) as arm:
                arm.stop()
                arm.close()
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
        return
        if state.cmd_type == 'RobotarmCmd':
            # pass
            return
        if state.cmd_type == 'Checkpoint' and state.state == 'running':
            return
        with self.lock:
            print(
                f'{state.metadata.step_desc or "": >13}',
                f'plate {state.metadata.plate_id or "": >2}',
                f'{self.current_thread_name()   : >10}',
                f'{state.state                  : >10}',
                state.cmd_type,
                *astuple(state.cmd),
                f'{self.world}',
                sep=' | ',
            )

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
            self.checkpoint_times[name] = self.monotonic()
            for q in self.checkpoint_waits[name]:
                self.time.queue_put_nowait(q, None)
            self.checkpoint_waits[name].clear()

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
