from __future__ import annotations
from dataclasses import *
from typing import *

import math
from datetime import datetime

from . import utils
from .commands import Metadata, Command

@dataclass(frozen=True)
class Running:
    '''
    Anything that does not grow without bound
    '''
    entries: list[LogEntry] = field(default_factory=list)
    world: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class RuntimeMetadata:
    pid: int
    git_HEAD: str
    log_filename: str
    estimates_pickle_file: str
    program_pickle_file: str
    host: str

@dataclass(frozen=True)
class LogEntry:
    log_time: str           = ''
    t: float                = -1.0
    t0: float | None        = None
    metadata: Metadata      = field(default_factory=lambda: Metadata())
    cmd: Command | None     = None
    err: Error | None       = None
    msg: str | None         = None
    running: Running | None = None
    runtime_metadata: RuntimeMetadata | None = None

    def init(
        self,
        log_time: str,
        t: float,
        t0: float | None = None
    ) -> LogEntry:
        return replace(self, log_time=log_time, t=t, t0=t0)

    def add(
        self,
        metadata: Metadata = Metadata(),
        msg: str = '',
        err: Error | None = None
    ) -> LogEntry:
        if self.msg:
            msg = self.msg + '; ' + msg
        if err:
            assert not self.err
        return replace(self, metadata=self.metadata.merge(metadata), msg=msg, err=err)

    @property
    def duration(self) -> float | None:
        t0 = self.t0
        if isinstance(t0, float):
            return round(self.t - t0, 3)
        else:
            return None

    def is_end(self):
        return isinstance(self.t0, float)

    def is_end_or_section(self):
        return self.is_end() or self.metadata.section

    def machine(self):
        try:
            assert self.cmd
            s = self.cmd.required_resource()
            return s
        except:
            return None

    def countdown(self, t_now: float):
        return countdown(t_now, self.t)

    def strftime(self, format: str) -> str:
        return datetime.fromisoformat(self.log_time).strftime(format)

def countdown(t_now: float, to: float):
    return math.ceil(to - math.ceil(t_now))

@dataclass(frozen=True)
class Error:
    message: str
    traceback: str | None = None
    fatal: bool = True

utils.serializer.register(globals())
