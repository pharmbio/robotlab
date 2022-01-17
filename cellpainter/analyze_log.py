from __future__ import annotations
from typing import *

from datetime import datetime, timedelta

from .log import LogEntry, Metadata, RuntimeMetadata, Running, Error
from .commands import Checkpoint, BiotekCmd, Duration

from . import utils

class Log(list[LogEntry]):
    def finished(self) -> set[str]:
        return {
            i
            for x in self
            if x.is_end_or_section()
            if (i := x.metadata.id)
        }

    def ids(self) -> set[str]:
        return {
            i
            for x in self
            if (i := x.metadata.id)
        }

    def checkpoints(self) -> dict[str, float]:
        return {
            x.cmd.name: x.t
            for x in self
            if isinstance(x.cmd, Checkpoint)
        }

    def durations(self) -> dict[str, float]:
        return {
            x.cmd.name: d
            for x in self
            if isinstance(x.cmd, Duration)
            if (d := x.duration) is not None
        }

    def group_durations(self: Log):
        groups = utils.group_by(self.durations().items(), key=lambda s: s[0].rstrip(' 0123456789'))
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
            out[k] = [utils.pp_secs(v) for _, v in vs]
        return out

    def group_durations_for_display(self):
        for k, vs in self.group_durations().items():
            yield k + ' [' + ', '.join(vs) + ']'

    def errors(self) -> list[tuple[Error, LogEntry]]:
        return [
            (err, x)
            for x in self
            if (err := x.err)
        ]

    def section_starts(self) -> dict[str, float]:
        return {
            section: x.t
            for x in self
            if (section := x.metadata.section)
        }

    def min_t(self):
        return min((x.t for x in self), default=0.0)

    def max_t(self):
        return max((x.t for x in self), default=0.0)

    def length(self):
        return self.max_t() - self.min_t()

    def group_by_section(self, first_section_name: str='begin') -> dict[str, Log]:
        out = {first_section_name: Log()}
        xs = Log()
        for x in sorted(self, key=lambda e: e.t):
            if section := x.metadata.section:
                xs = Log()
                out[section] = xs
            xs.append(x)
        if not out[first_section_name]:
            out.pop(first_section_name)
        out = {
            k: v if not next_kv else Log(v + [LogEntry(t=next_kv[1].min_t() - 0.05)])
            for (k, v), next_kv in utils.iterate_with_next(list(out.items()))
        }
        return out

    def running(self) -> Running | None:
        for x in self[::-1]:
            if m := x.running:
                return m

    def runtime_metadata(self) -> RuntimeMetadata | None:
        for x in self[::-1]:
            if m := x.runtime_metadata:
                return m

    def zero_time(self) -> datetime:
        for x in self[::-1]:
            return datetime.fromisoformat(x.log_time) - timedelta(seconds=x.t)
        raise ValueError('Empty log')

    def is_completed(self) -> bool:
        return any(
            x.metadata.completed
            for x in self
        )

    def num_plates(self) -> int:
        return int(max((p for x in self if (p := x.metadata.plate_id)), default='0'))

    def drop_boring(self) -> Log:
        return Log(
            x
            for x in self
            if not isinstance(x.cmd, BiotekCmd) or not x.cmd.action == 'Validate'
        )

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

