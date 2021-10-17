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
import traceback
from queue import Queue
from contextlib import contextmanager
from threading import RLock

from moves import movelists
import utils
from utils import Mutable

import timelike
from timelike import Timelike, WallTime, SimulatedTime
from collections import defaultdict

@dataclass(frozen=True)
class Symbolic:
    var_names: list[str]
    offset: float = 0

    def __post_init__(self):
        assert self.offset >= 0

    def __str__(self):
        xs = [
            f'`{x}`' if re.search(r'\W', x) else x
            for x in self.var_names
        ]
        if self.offset or not xs:
            xs += [str(round(self.offset, 1))]
        return '+'.join(xs)

    def __repr__(self):
        return f'Symbolic({str(self)})'

    def __add__(self, other: float | int | str | Symbolic) -> Symbolic:
        other = Symbolic.wrap(other)
        return Symbolic(
            self.var_names + other.var_names,
            float(self.offset + other.offset),
        )

    def resolve(self, env: dict[str, float] = {}) -> float:
        return sum(env[x] for x in self.var_names) + self.offset

    def var_set(self) -> set[str]:
        return set(self.var_names)

    @staticmethod
    def var(name: str) -> Symbolic:
        return Symbolic(var_names=[name])

    @staticmethod
    def const(value: float) -> Symbolic:
        return Symbolic(var_names=[], offset=value)

    @staticmethod
    def wrap(s: float | int | str | Symbolic) -> Symbolic:
        if isinstance(s, str):
            return Symbolic.var(s)
        elif isinstance(s, Symbolic):
            return s
        else:
            return Symbolic.const(float(s))

