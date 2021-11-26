from __future__ import annotations
from dataclasses import *
from typing import *

import abc
import time
import threading
from queue import Queue
from threading import Lock

from utils import pp_secs

A = TypeVar('A')

class Timelike(abc.ABC):
    @abc.abstractmethod
    def speedup(self) -> float:
        pass

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
    def thread_done(self):
        pass

from threading import Thread
from collections import defaultdict

@dataclass
class ThreadData:
    name: str = field(default_factory=lambda: threading.current_thread().name)
    state: Literal['busy', 'blocked', 'sleeping'] = 'busy'
    sleep_until: float = float('inf')
    inbox: Queue[None] = field(default_factory=Queue)
    blocked_at: Queue[Any] | None = None

@dataclass
class SimulatedTime(Timelike):
    threads: dict[Thread, ThreadData] = field(default_factory=lambda: defaultdict[Thread, ThreadData](ThreadData))
    skipped_time: float = 0.0
    lock: Lock = field(default_factory=Lock)
    qsize: dict[int, int] = field(default_factory=lambda: defaultdict[int, int](int))

    def speedup(self) -> float:
        return 1.0

    def log(self):
        return
        out: list[str] = [f' {pp_secs(self.monotonic())}']
        for v in list(self.threads.values()):
            out += [
                f'{v.name}: {v.state} to {pp_secs(v.sleep_until)}'
                if v.sleep_until != float('inf') else
                f'{v.name}: {v.state}'
            ]
        print(' | '.join(out))

    def monotonic(self):
        return self.skipped_time

    def register_thread(self, name: str):
        with self.lock:
            tid = threading.current_thread()
            self.threads[tid] = ThreadData(name)

    def current_thread_data(self) -> ThreadData:
        tid = threading.current_thread()
        return self.threads[tid]

    def thread_done(self):
        with self.lock:
            tid = threading.current_thread()
            del self.threads[tid]
            self.wake_up()

    def queue_put(self, queue: Queue[A], a: A) -> None:
        with self.lock:
            i = id(queue)
            self.qsize[i] += 1
        queue.put(a)
        with self.lock:
            self.wake_up()

    def queue_put_nowait(self, queue: Queue[A], a: A) -> None:
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

        thread_data.inbox.get()
        assert thread_data.state == 'busy'
        assert thread_data.sleep_until == float('inf')
        with self.lock:
            # take lock to make sure that the wake up procedure is finished
            # before proceeding (possibly started by some other thread)
            pass

    def wake_up(self):
        assert self.lock.locked()
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
        if states <= {'blocked'}:
            return
        if 'busy' in states:
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

    def speedup(self) -> float:
        return 1.0

    def monotonic(self):
        return (time.monotonic() - self.start_time) * self.speedup()

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
            time.sleep(seconds / self.speedup())

    def thread_done(self):
        pass

class FastForwardTime(WallTime):
    def speedup(self) -> float:
        return 10.0

