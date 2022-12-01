from __future__ import annotations
from dataclasses import *
from typing import *

import math
from datetime import datetime, timedelta
from contextlib import contextmanager
from pathlib import Path

import pbutils
from .commands import Metadata, Command, Checkpoint, BiotekCmd, Duration, Info, IncuCmd, RobotarmCmd, ProgramMetadata, Program
from .moves import World

from pbutils.mixins import DB, DBMixin
import pbutils.mixins
import os
import platform

@dataclass(frozen=False)
class RuntimeMetadata(DBMixin):
    start_time:   datetime
    config_name:  str
    log_filename: str
    pid: int      = field(default_factory=lambda: os.getpid())
    host: str     = field(default_factory=lambda: platform.node())
    git_HEAD: str = field(default_factory=lambda: pbutils.git_HEAD() or '')
    completed: datetime | None = None
    id: int = -1

@dataclass(frozen=False)
class ExperimentMetadata(DBMixin):
    desc: str = ''
    operators: str = ''
    id: int = -1

@dataclass(frozen=True)
class Message(DBMixin):
    msg: str = ''
    t: float = -1
    cmd: Command | None       = None
    metadata: Metadata | None = None
    is_error: bool            = False
    traceback: str | None     = None
    id: int = -1

@dataclass(frozen=True)
class Note(DBMixin):
    note: str = ''
    time: datetime = field(default_factory=lambda: datetime.now())
    id: int = -1

@dataclass(frozen=True)
class CommandWithMetadata:
    cmd: Command
    metadata: Metadata

    def merge(self, *metadata: Metadata) -> CommandWithMetadata:
        return replace(self, metadata=self.metadata.merge(*metadata))

    def message(self, msg: str, is_error: bool=False):
        return Message(msg, cmd=self.cmd, metadata=self.metadata, is_error=is_error)

@dataclass
class CommandState(DBMixin):
    t0: float
    t: float
    cmd: Command
    metadata: Metadata
    state: Literal['completed', 'running', 'planned']
    id: int # should be Metadata.id

    # generated for the UI from cmd and metadata:
    cmd_type: str = ''
    gui_boring: bool = False
    resource: Literal['robotarm', 'incu', 'disp', 'wash'] | None = None

    # views={'duration': 'round(t - t0, 3)'},

    def __post_init__(self):
        self.resource = self.cmd.required_resource()
        self.cmd_type = self.cmd.type
        if isinstance(self.cmd, BiotekCmd):
            if self.cmd.action == 'Validate':
                self.gui_boring = True
            if self.cmd.action == 'TestCommunications':
                self.gui_boring = True
        if isinstance(self.cmd, IncuCmd):
            if self.cmd.action == 'get_status':
                self.gui_boring = True
        if self.metadata.gui_force_show:
            self.gui_boring = False


    @property
    def duration(self) -> float | None:
        return round(self.t - self.t0, 3)

    def machine(self):
        try:
            s = self.cmd.required_resource()
            return s
        except:
            return None

    def countdown(self, t_now: float):
        return countdown(t_now, self.t)

    # def strftime(self, format: str) -> str:
    #     return datetime.fromisoformat(self.log_time).strftime(format)

def countdown(t_now: float, to: float):
    return math.ceil(to - math.ceil(t_now))

@dataclass(frozen=True)
class Error:
    message: str
    traceback: str | None = None

@dataclass
class VisRow:
    t0: float
    t: float
    section: str
    section_column: int = -1
    section_t0: float = 0
    state: CommandState | None = None
    now: bool = False
    bg: bool = False


@dataclass(frozen=True)
class Log:
    db: DB

    @staticmethod
    def connect(filename: str | Path):
        return Log(DB.connect(filename))

    @staticmethod
    @contextmanager
    def open(filename: str | Path):
        with DB.open(filename) as db:
            yield Log(db)

    def command_states(self):
        q = self.db.get(CommandState)
        return q

    def gui_query(self):
        q = self.db.get(CommandState)
        q = q.where(CommandState.resource != None)
        q = q.where(CommandState.gui_boring != True)
        return q

    def world(self, t: float | None = None) -> dict[str, str]:
        q = self.db.get(World).order(World.t, 'desc')
        if t is not None:
            q = q.where(World.t <= t)
        for w in q:
            return w.data
        else:
            return {}

    def running(self, t: float | None = None) -> list[CommandState]:
        q = self.db.get(CommandState)
        q = q.where(CommandState.cmd_type != 'Duration')
        q = q.where(CommandState.gui_boring != True)
        if t is None:
            return q.where(CommandState.state == 'running').list()
        else:
            return q.where(
                CommandState.t0 <= t,
                t <= CommandState.t,
            ).list()

    def section_starts(self) -> dict[str, float]:
        q = self.gui_query()
        out: dict[str, float] = {}
        for k in q.select(CommandState.metadata.section):
            if k in out:
                continue
            out[k] = q.select(CommandState.t0).order(CommandState.t0).where(CommandState.metadata.section == k).one()
        if '' in out and len(out) >= 2:
            empty = out.pop('')
            first, *_ = out.keys()
            out[first] = min(out[first], empty)
        return out
        # g = q.group(CommandState.metadata.section)
        # return {
        #     k: v
        #     for k, v in sorted(g.min(CommandState.t0).items(), key=lambda kv: kv[1])
        # }

    def time_end(self):
        q = self.gui_query()
        q = q.where(CommandState.state == 'completed')
        q = q.order(CommandState.t, 'desc').limit(1)
        q = q.select(CommandState.t)
        for t in q:
            return t + 10.0
        else:
            return 0.0
        # return self.gui_query().max(CommandState.t) or 0.0

    def section_starts_with_endpoints(self) -> dict[str, float]:
        return {
            'begin': 0.0,
            **self.section_starts(),
            'end': self.time_end()
        }

    def vis(self, t: float | None = None) -> list[VisRow]:
        section_starts = self.section_starts()
        if not section_starts:
            return []
        first_section, *_ = section_starts.keys()
        section_starts[first_section] = 0.0
        section_columns = {section: i for i, section in enumerate(section_starts.keys())}

        def time_to_section(t: float):
            for section, t0 in reversed(section_starts.items()):
                if t >= t0:
                    return section
            return 'before time'

        rows: list[VisRow] = []
        for (section_name, section_t0), next in pbutils.iterate_with_next(section_starts.items()):
            if next:
                _, section_t = next
            else:
                section_t = self.time_end()
            bg_row = VisRow(
                t0 = section_t0,
                t = section_t,
                section = section_name,
                bg = True,
            )
            rows += [bg_row]

        q = self.gui_query()
        states = q.where_some(CommandState.resource == 'disp', CommandState.resource == 'wash')
        if not states.list():
            # show incu if no bioteks (for incu load)
            states = q.where_some(CommandState.resource == 'incu')
        for state in states:
            if t is not None:
                if state.t0 > t:
                    state.state = 'planned'
                elif state.t < t:
                    state.state = 'completed'
                else:
                    state.state = 'running'
            row = VisRow(
                t0 = state.t0,
                t = state.t,
                state = state,
                section = state.metadata.section,
            )
            rows += [row]

        if t is not None:
            now_row = VisRow(
                t0 = t,
                t = t,
                section = time_to_section(t),
                now = True,
            )
            rows += [now_row]

        for row in rows:
            if row.section == '':
                row.section = time_to_section(row.t)
            row.section_column = section_columns[row.section]
            row.section_t0 = section_starts[row.section]

        return rows

    def durations(self) -> dict[str, float]:
        return {
            e.cmd.name: d
            for e in self.db.get(CommandState).where(CommandState.cmd_type == 'Duration')
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

    def errors(self) -> list[Message]:
        return self.db.get(Message).where(Message.is_error == True).list()

    def runtime_metadata(self) -> RuntimeMetadata | None:
        return self.db.get(RuntimeMetadata).one_or(None)

    def experiment_metadata(self) -> ExperimentMetadata | None:
        return self.db.get(ExperimentMetadata).one_or(None)

    def program_metadata(self) -> ProgramMetadata | None:
        return self.db.get(ProgramMetadata).one_or(None)

    def program(self) -> Program | None:
        return self.db.get(Program).one_or(None)

    def notes(self, order: Literal['asc', 'desc']='asc') -> Any:
        raise ValueError('Remove notes')

pbutils.serializer.register(globals())
