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
from pbutils.mixins import DB

from .ur import UR
from .pf import PF
from .xarm import XArm
from .timelike import Timelike
from .moves import World, Effect
from .log import Message, CommandState, CommandWithMetadata, ProgressText, Log

from labrobots import (
    BarcodeReader,
    Biotek,
    BlueWash,
    DLid,
    Fridge,
    MikroAsus,
    Squid,
    STX,
    WindowsGBG,
    WindowsNUC,
    Nikon,
    NikonPi,
    NikonNIS,
    NikonStage,
)

import contextlib

from .config import RuntimeConfig

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

    ur: UR | None = None
    pf: PF | None = None
    xarm: XArm | None = None

    incu: STX      | None = None
    wash: Biotek   | None = None
    disp: Biotek   | None = None
    blue: BlueWash | None = None
    dlid: DLid     | None = None

    fridge: Fridge                | None = None
    barcode_reader: BarcodeReader | None = None
    squid: Squid                  | None = None
    nikon: NikonNIS               | None = None
    nikon_stage: NikonStage       | None = None

    @property
    def fridge_and_barcode_reader(self):
        if self.fridge and self.barcode_reader:
            return self.fridge, self.barcode_reader
        else:
            return None

    @property
    def nikon_and_stage(self):
        if self.nikon and self.nikon_stage:
            return self.nikon, self.nikon_stage
        else:
            return None

    @staticmethod
    def init(config: RuntimeConfig) -> Runtime:
        runtime = Runtime(
            config=config,
            time=config.make_timelike(),
            log_db=DB.connect(config.log_filename if config.log_filename else ':memory:'),
        )
        return runtime

    def __post_init__(self):
        self.time.register_thread('main')

        if self.log_db:
            self.log_db.con.execute('pragma synchronous=OFF;')

        if self.config.signal_handlers == 'install':
            def handle_signal(signum: int, _frame: Any):
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                signal.signal(signal.SIGQUIT, signal.SIG_DFL)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                signal.signal(signal.SIGABRT, signal.SIG_DFL)
                pid = os.getpid()
                self.log(Message(f'Shutting down... (signal={signal.strsignal(signum)}, {pid=})', is_error=True))
                self.stop_arms()
                sys.exit(1)

            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGQUIT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGABRT, handle_signal)

            print('Signal signal_handlers installed')

        if self.config.run_incu_wash_disp:
            nuc = WindowsNUC.remote(timeout_secs=1800) # Spheroid washer protocols have long waits
            self.incu = nuc.incu
            self.wash = nuc.wash
            self.disp = nuc.disp
            self.blue = nuc.blue

        if self.config.ur_env.mode != 'noop':
            nuc = WindowsNUC.remote(timeout_secs=1800) # Spheroid washer protocols have long waits
            self.ur = UR(
                host=self.config.ur_env.host,
                port=self.config.ur_env.port,
            )
            self.dlid = nuc.dlid

        if self.config.pf_env.mode != 'noop':
            self.pf = PF(
                host=self.config.pf_env.host,
                port_rw=self.config.pf_env.port_rw,
                port_ro=self.config.pf_env.port_ro,
            )

        if self.config.xarm_env.mode != 'noop':
            self.xarm = XArm(
                host=self.config.xarm_env.host,
            )

        if self.config.run_fridge_squid_nikon:
            gbg = WindowsGBG.remote()
            self.fridge = gbg.fridge
            self.barcode_reader = gbg.barcode

            if 1:
                try:
                    mikro_asus = MikroAsus.remote()
                    self.squid = mikro_asus.squid
                except:
                    raise ValueError('Squid: cannot connect to squid, is squid web service running?')

            if 1:
                class NikonDisabled:
                    pass
                try:
                    self.nikon = NikonDisabled() # type: ignore
                    # self.nikon = Nikon.remote().nikon
                except:
                    raise ValueError('Nikon: cannot connect to nikon')
                try:
                    self.nikon_stage = NikonDisabled() # type: ignore
                    # self.nikon_stage = NikonPi.remote().nikon_stage
                except:
                    raise ValueError('NikonPi: cannot connect to nikon stage')

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
        except SystemExit:
            pass
        except BaseException as e:
            self.log(Message(str(e), traceback=traceback.format_exc(), is_error=True))
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

    def wait_while(self, k: Callable[[], bool]):
        while k():
            self.sleep(1.0)

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

