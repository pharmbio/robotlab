from __future__ import annotations
from dataclasses import *
from typing import *

import math
from datetime import datetime, timedelta

import pbutils
from .commands import Metadata, Command, Checkpoint, BiotekCmd, Duration, Info, IncuCmd, RobotarmCmd

from pbutils.mixins import DB, DBMixin
import pbutils.mixins
import os
import platform

@dataclass(frozen=False)
class RuntimeMetadata(DBMixin):
    start_time:         datetime
    num_plates:         int
    log_filename:       str | None
    estimates_filename: str
    program_filename:   str
    pid: int      = field(default_factory=lambda: os.getpid())
    host: str     = field(default_factory=lambda: platform.node())
    git_HEAD: str = field(default_factory=lambda: pbutils.git_HEAD() or '')
    completed: datetime | None = None
    id: int = -1

@dataclass(frozen=True)
class LogEntry(DBMixin):
    log_time: str       = ''
    t: float            = -1.0
    t0: float | None    = None
    metadata: Metadata  = field(default_factory=lambda: Metadata())
    cmd: Command | None = None
    err: Error | None   = None
    msg: str | None     = None
    is_running: bool    = False
    id: int             = -1

    __meta__: ClassVar = pbutils.mixins.Meta(
        views={
            k.name: f'value ->> "metadata.{k.name}"'
            for k in fields(Metadata)
            if k.name != 'id'
        } | {
            'metadata': '',
        },
        indexes={
            'cmd_type': 'value ->> "cmd.type"',
            't0': 'value ->> "t0"',
            't': 'value ->> "t"',
        }
    )

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

    def is_end_or_info(self):
        return self.is_end() or isinstance(self.cmd, Info)

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

@dataclass(frozen=True)
class Log:
    db: DB

    @staticmethod
    def open(filename: str):
        return Log(DB.connect(filename))

    def finished(self) -> set[str]:
        return {
            e.metadata.id
            for e in
            self.db.get(LogEntry).where_some(
                LogEntry.t0 != None,
                LogEntry.cmd.type == 'Info', # type: ignore
            )
        }

    def ids(self) -> set[str]:
        return {
            e.metadata.id
            for e in
            self.db.get(LogEntry)
        }

    def durations(self) -> dict[str, float]:
        return {
            e.cmd.name: d
            for e in self.db.get(LogEntry).where(
                LogEntry.t0 != None,
                LogEntry.cmd.type == 'Duration', # type: ignore
            )
            if isinstance(e.cmd, Duration)
            if (d := e.duration)
        }

    def group_durations(self: Log):
        groups = pbutils.group_by(self.durations().items(), key=lambda s: s[0].rstrip(' 0123456789'))
        out: dict[str, list[str]] = {}
        def key(kv: tuple[str, Any]):
            s, _ = kv
            if s.startswith('plate'):
                _plate, i, *what = s.split(' ')
                return f' plate {" ".join(what)} {int(i):03}'
            else:
                return s
        for k, vs in sorted(groups.items(), key=key):
            if k.startswith('plate'):
                _plate, i, *what = k.split(' ')
                k = f'plate {int(i):>2} {" ".join(what)}'
            out[k] = [pbutils.pp_secs(v) for _, v in vs]
        return out

    def group_durations_for_display(self):
        for k, vs in self.group_durations().items():
            yield k + ' [' + ', '.join(vs) + ']'

    def errors(self) -> list[tuple[Error, LogEntry]]:
        return [
            (err, e)
            for e in self.db.get(LogEntry).where(
                LogEntry.err != None,
            )
            if (err := e.err)
        ]

    def section_starts(self) -> dict[str, float]:
        g = self.db.get(LogEntry).where(LogEntry.metadata.section != '').group(LogEntry.metadata.section)
        return g.min(LogEntry.t).dict()

    def min_t(self):
        return self.db.get(LogEntry).min(LogEntry.t, default=0.0)

    def max_t(self):
        return self.db.get(LogEntry).max(LogEntry.t, default=0.0)

    def length(self):
        return self.max_t() - self.min_t()

    def group_by_section(self, first_section_name: str='begin') -> dict[str, list[LogEntry]]:
        g = self.db.get(LogEntry).where_some(
            LogEntry.cmd.type == 'BiotekCmd',     # type: ignore
            LogEntry.cmd.type == 'IncuCmd',       # type: ignore
            LogEntry.cmd.type == 'RobotarmCmd',   # type: ignore
        ).where(
            LogEntry.metadata.section != ''
        ).group(LogEntry.metadata.section)
        return g.dict()

    def zero_time(self) -> datetime:
        return self.db.get(RuntimeMetadata).one().start_time

    def is_completed(self) -> bool:
        return self.db.get(RuntimeMetadata).one().completed is not None

    def num_plates(self) -> int:
        return self.db.get(RuntimeMetadata).one().num_plates

    def drop_validate(self) -> Log:
        res = self
        res = res.drop(lambda e: isinstance(e.cmd, BiotekCmd) and e.cmd.action == 'Validate' and not e.metadata.gui_force_show)
        return res

    def drop_test_comm(self) -> Log:
        res = self
        res = res.drop(lambda e: isinstance(e.cmd, BiotekCmd) and e.cmd.action == 'TestCommunications' and not e.metadata.gui_force_show)
        res = res.drop(lambda e: isinstance(e.cmd, IncuCmd) and e.cmd.action == 'get_status' and not e.metadata.gui_force_show)
        return res

    def drop(self, p: Callable[[LogEntry], Any]) -> Log:
        return self.where(lambda x: not p(x))

    def where(self, p: Callable[[LogEntry], Any]) -> Log:
        return Log(
            x
            for x in self
            if p(x)
        )

    def add(self, metadata: Metadata) -> Log:
        return Log(
            x.add(metadata)
            for x in self
        )

    def drop_after(self, secs: float | int) -> Log:
        return Log([e for e in self if e.t <= secs])


pbutils.serializer.register(globals())
