from __future__ import annotations
from dataclasses import *
from typing import *

import abc
import time
import threading
from queue import Queue
from contextlib import contextmanager
from threading import Lock

from utils import pp_secs

A = TypeVar('A')

class Timelike(abc.ABC):
    @abc.abstractmethod
    def monotonic(self) -> float:
        pass

    @abc.abstractmethod
    def register_thread(self, name: str):
        pass

    @abc.abstractmethod
    def queue_get(self, queue: Queue[A]) -> A:
        pass

    @abc.abstractmethod
    def queue_put(self, queue: Queue[A], a: A) -> None:
        pass

    @abc.abstractmethod
    def queue_put_nowait(self, queue: Queue[A], a: A) -> None:
        pass

    @abc.abstractmethod
    def sleep(self, seconds: float):
        pass

    @abc.abstractmethod
    def thread_idle(self):
        pass

    @abc.abstractmethod
    def thread_done(self):
        pass

    @abc.abstractmethod
    def spawning(self) -> ContextManager[None]:
        pass

from threading import Thread
from collections import defaultdict

@dataclass
class ThreadData:
    name: str = field(default_factory=lambda: threading.current_thread().name)
    state: Literal['busy', 'blocked', 'sleeping', 'idle'] = 'busy'
    sleep_until: float = float('inf')
    inbox: Queue[None] = field(default_factory=Queue)
    blocked_at: Queue[Any] | None = None

@dataclass
class SimulatedTime(Timelike):
    include_wall_time: bool
    start_time: float = field(default_factory=time.monotonic)
    threads: dict[Thread, ThreadData] = field(default_factory=lambda: defaultdict[Thread, ThreadData](ThreadData))
    skipped_time: float = 0.0
    lock: Lock = field(default_factory=Lock)
    qsize: dict[int, int] = field(default_factory=lambda: defaultdict[int, int](int))
    pending_spawns: int = 0

    @contextmanager
    def spawning(self):
        with self.lock:
            self.pending_spawns += 1
        yield

    def log(self):
        return
        out: list[str] = [f' {pp_secs(self.monotonic())}']
        for v in list(self.threads.values()):
            out += [
                f'{v.name}: {v.state} to {pp_secs(v.sleep_until)}'
                if v.sleep_until != float('inf') else
                f'{v.name}: {v.state}'
            ]
        out += [f'{self.pending_spawns=}']
        print(' | '.join(out))

    def monotonic(self):
        if self.include_wall_time:
            return time.monotonic() - self.start_time + self.skipped_time
        else:
            return self.skipped_time

    def register_thread(self, name: str):
        with self.lock:
            assert self.pending_spawns > 0
            self.pending_spawns -= 1
            tid = threading.current_thread()
            self.threads[tid] = ThreadData(name)

    def current_thread_data(self) -> ThreadData:
        tid = threading.current_thread()
        return self.threads[tid]

    def thread_idle(self):
        with self.lock:
            self.current_thread_data().state = 'idle'
            self.wake_up()

    def thread_done(self):
        with self.lock:
            tid = threading.current_thread()
            del self.threads[tid]
            self.wake_up()

    def queue_put(self, queue: Queue[A], a: A) -> None:
        thread_data = self.current_thread_data()
        with self.lock:
            i = id(queue)
            self.qsize[i] += 1
        queue.put(a)
        with self.lock:
            self.wake_up()

    def queue_put_nowait(self, queue: Queue[A], a: A) -> None:
        thread_data = self.current_thread_data()
        with self.lock:
            i = id(queue)
            self.qsize[i] += 1
        queue.put_nowait(a)

    def queue_get(self, queue: Queue[A]) -> A:
        thread_data = self.current_thread_data()
        with self.lock:
            thread_data.state = 'blocked'
            thread_data.blocked_at = queue
            assert thread_data.sleep_until == float('inf')
            self.wake_up()

        res = queue.get()

        with self.lock:
            i = id(queue)
            self.qsize[i] -= 1
            thread_data.state = 'busy'
            thread_data.blocked_at = None
            assert thread_data.sleep_until == float('inf')

        return res

    def sleep(self, seconds: float):
        if seconds <= 0:
            return
        thread_data = self.current_thread_data()
        with self.lock:
            thread_data.state = 'sleeping'
            thread_data.sleep_until = self.monotonic() + seconds
            self.wake_up()

        self.log()

        if self.include_wall_time:
            def wait():
                time.sleep(seconds)
                with self.lock:
                    if thread_data.state == 'sleeping':
                        self.wake_up()
            threading.Thread(target=wait, daemon=True)

        thread_data.inbox.get()
        assert thread_data.state == 'busy'
        assert thread_data.sleep_until == float('inf')
        with self.lock:
            # take lock to make sure that the wake up procedure is finished
            # before proceeding (possibly started by some other thread)
            pass

    def wake_up(self):
        assert self.lock.locked()
        # if self.pending_spawns > 0:
            # return
        # Wake up next thread if all are sleeping or blocked
        self.log()
        states = {v.state for v in self.threads.values()}
        for st in self.threads.values():
            if st.state == 'blocked' and self.qsize[id(st.blocked_at)]:
                # will receive a message soon
                return
        if states == {'blocked'}:
            raise ValueError(f'Threads blocked indefinitely')
            return
        if states <= {'blocked', 'idle'}:
            return
        if 'busy' in states and not self.include_wall_time:
            # there is still a thread busy, we exit here to let it proceed
            return
        now = self.monotonic()
        if 'sleeping' in states:
            skip_time = min(v.sleep_until for v in self.threads.values()) - now
            assert skip_time != float('inf')
            if skip_time > 0:
                self.skipped_time += skip_time
                now += skip_time
            # print(f'... {pp_secs(now)} | skip_time={pp_secs(skip_time)}')
        for v in self.threads.values():
            if v.sleep_until - now < 1e-4:
                v.state = 'busy'
                v.sleep_until = float('inf')
                v.inbox.put_nowait(None)
        self.log()


@dataclass(frozen=True)
class WallTime(Timelike):
    start_time: float = field(default_factory=time.monotonic)

    @contextmanager
    def spawning(self):
        yield

    def monotonic(self):
        return time.monotonic() - self.start_time

    def register_thread(self, name: str):
        pass

    def queue_get(self, queue: Queue[A]) -> A:
        return queue.get()

    def queue_put(self, queue: Queue[A], a: A) -> None:
        queue.put(a)

    def queue_put_nowait(self, queue: Queue[A], a: A) -> None:
        queue.put_nowait(a)

    def sleep(self, seconds: float):
        if seconds > 0:
            time.sleep(seconds)

    def thread_idle(self):
        pass

    def thread_done(self):
        pass

