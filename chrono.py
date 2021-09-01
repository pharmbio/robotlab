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
    def register_thread(self, name: str):
        pass

    @abc.abstractmethod
    def queue_get(self, queue: SimpleQueue[A]) -> A:
        pass

    @abc.abstractmethod
    def sleep(self, seconds: float):
        pass

from threading import Thread

@dataclass
class ThreadData:
    name: str
    state: Literal['busy', 'blocked', 'sleeping'] = 'busy'
    sleep_until: float = float('inf')
    sleep_inbox: SimpleQueue[None] = field(default_factory=SimpleQueue)

@dataclass
class SimulatedTime(Timelike):
    threads: dict[Thread, ThreadData] = field(default_factory=dict)
    skipped_time: float = 0
    lock: Lock = field(default_factory=Lock)

    def register_thread(self, name: str):
        tid = threading.current_thread()
        self.threads[tid] = ThreadData(name)

    def queue_get(self, queue: SimpleQueue[A]) -> A:
        tid = threading.current_thread()
        self.threads[tid].state = 'blocked'
        res = queue.get()
        self.threads[tid].state = 'busy'
        return res

    def sleep(self, seconds: float):
        if seconds <= 0:
            return
        tid = threading.current_thread()
        with self.lock:
            self.threads[tid].state = 'sleeping'
            self.threads[tid].sleep_until = self.skipped_time + seconds
            self.wake_up()

        self.threads[tid].sleep_inbox.get()
        assert self.threads[tid].sleep_until == float('inf')
        with self.lock:
            # make sure wake up procedure, started by some other thread,
            # is finished before proceeding
            pass

    def wake_up(self):
        assert self.lock.locked()
        states = {v.state for v in self.threads.values()}
        if states == {'blocked'}:
            raise ValueError('Threads deadlocked indefinitely waiting for message')
        if 'busy' in states:
            # there is still a thread busy, we exit here to let it proceed
            return
        assert 'sleeping' in states
        self.skipped_time = min(v.sleep_until for v in self.threads.values())
        assert self.skipped_time != float('inf')
        for v in self.threads.values():
            if self.skipped_time >= v.sleep_until:
                v.sleep_until = float('inf')
                v.sleep_inbox.put_nowait(None)

@dataclass(frozen=True)
class WallTime(Timelike):
    def register_thread(self, name: str):
        pass

    def queue_get(self, queue: SimpleQueue[A]) -> A:
        return queue.get()

    def set_blocked(self, value: bool):
        pass

    def sleep(self, seconds: float):
        time.sleep(seconds)
