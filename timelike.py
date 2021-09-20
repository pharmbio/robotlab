from __future__ import annotations
from dataclasses import *
from typing import *

from datetime import datetime, timedelta
from urllib.request import urlopen

import abc
import json
import re
import socket
import time
import threading
from queue import SimpleQueue
from contextlib import contextmanager
from threading import Lock

from moves import movelists
from robotarm import Robotarm
import utils
from utils import Mutable

A = TypeVar('A')

class Timelike(abc.ABC):
    @abc.abstractmethod
    def monotonic(self) -> float:
        pass

    @abc.abstractmethod
    def register_thread(self, name: str):
        pass

    @abc.abstractmethod
    def queue_get(self, queue: SimpleQueue[A]) -> A:
        pass

    @abc.abstractmethod
    def sleep(self, seconds: float):
        pass

    @abc.abstractmethod
    def busywait_step(self):
        pass

    @abc.abstractmethod
    def thread_idle(self):
        pass

from threading import Thread
from collections import defaultdict

@dataclass
class ThreadData:
    name: str = field(default_factory=lambda: threading.current_thread().name)
    state: Literal['busy', 'blocked', 'sleeping', 'busywaiting', 'idle'] = 'busy'
    sleep_until: float = float('inf')
    inbox: SimpleQueue[None] = field(default_factory=SimpleQueue)

@dataclass
class SimulatedTime(Timelike):
    include_wall_time: bool
    start_time: float = field(default_factory=time.monotonic)
    threads: dict[Thread, ThreadData] = field(default_factory=lambda: cast(dict[Thread, ThreadData], defaultdict(ThreadData)))
    skipped_time: float = 0.0
    lock: Lock = field(default_factory=Lock)

    def log(self):
        return
        with self.lock:
            out: list[str] = ['... {self.monotonic()}']
            for v in self.threads.values():
                out += [
                    f'{v.name}: {v.state} to {v.sleep_until}'
                    if v.sleep_until != float('inf') else
                    f'{v.name}: {v.state}'
                ]
            print(' | '.join(out))

    def monotonic(self):
        if self.include_wall_time:
            return time.monotonic() - self.start_time + self.skipped_time
        else:
            return self.skipped_time

    def register_thread(self, name: str):
        with self.lock:
            tid = threading.current_thread()
            self.threads[tid] = ThreadData(name)

    def current_thread_data(self) -> ThreadData:
        tid = threading.current_thread()
        return self.threads[tid]

    def queue_get(self, queue: SimpleQueue[A]) -> A:
        thread_data = self.current_thread_data()
        with self.lock:
            thread_data.state = 'blocked'
            assert thread_data.sleep_until == float('inf')
            self.wake_up()
        res = queue.get()
        with self.lock:
            thread_data.state = 'busy'
            assert thread_data.sleep_until == float('inf')
            self.log()
        return res

    def busywait_step(self):
        thread_data = self.current_thread_data()
        with self.lock:
            thread_data.state = 'busywaiting'
            self.wake_up()
        thread_data.inbox.get()
        assert thread_data.state == 'busy'
        with self.lock:
            # take lock to make sure that the wake up procedure is finished
            # before proceeding (possibly started by some other thread)
            pass

    def sleep(self, seconds: float):
        if seconds <= 0:
            return
        thread_data = self.current_thread_data()
        with self.lock:
            thread_data.state = 'sleeping'
            thread_data.sleep_until = self.monotonic() + seconds
            self.wake_up()

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

    def thread_idle(self):
        with self.lock:
            self.current_thread_data().state = 'idle'
            self.wake_up()

    def wake_up(self):
        assert self.lock.locked()
        # Wake up next thread if all are sleeping or blocked
        self.log()
        states = {v.state for v in self.threads.values()}
        if states == {'blocked'}:
            raise ValueError(f'Threads blocked indefinitely')
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
            # print(f'... {now} | {skip_time=}')
        for v in self.threads.values():
            if now >= v.sleep_until:
                v.state = 'busy'
                v.sleep_until = float('inf')
                v.inbox.put_nowait(None)
            elif v.state == 'busywaiting':
                v.state = 'busy'
                v.inbox.put_nowait(None) # wake up and see if there is any progress
        self.log()


@dataclass(frozen=True)
class WallTime(Timelike):
    start_time: float = field(default_factory=time.monotonic)

    def monotonic(self):
        return time.monotonic() - self.start_time

    def register_thread(self, name: str):
        pass

    def queue_get(self, queue: SimpleQueue[A]) -> A:
        return queue.get()

    def set_blocked(self, value: bool):
        pass

    def sleep(self, seconds: float):
        if seconds < 0:
            print('Behind time:', fmt(-seconds), '!')
        else:
            print('Sleeping for', fmt(seconds), '...')
            time.sleep(seconds)

    def busywait_step(self):
        time.sleep(0.01)

    def thread_idle(self):
        pass

def fmt(s: float) -> str:
    m = int(s // 60)
    return f'{s:7.1f}s ({m}min {s - 60 * m:4.1f}s)'

