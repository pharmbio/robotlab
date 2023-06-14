from __future__ import annotations
from typing import *
from dataclasses import *

import sqlite3
import json
import contextlib

def try_json_dumps(s: Any) -> str:
    try:
        return json.dumps(s)
    except:
        return json.dumps({'repr': repr(s)})

@dataclass(frozen=True)
class Log:
    _log: Callable[..., None]
    def __call__(self, *args: Any, **kwargs: Any):
        self._log(*args, **kwargs)

    @classmethod
    def without_db(cls, stdout: bool = False) -> Log:
        if stdout:
            return Log(print)
        else:
            return Log(lambda *args, **kws: None)

    @classmethod
    def make(cls, name: str, xs: List[str] | None = None, stdout: bool=True) -> Log:
        with contextlib.closing(sqlite3.connect('io.db')) as con:
            con.executescript('''
                pragma synchronous=OFF;
                pragma journal_mode=WAL;
                create table if not exists io (
                    t     timestamp default (strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime')),
                    name  text,
                    id    int,
                    data  json
                );
                create index if not exists io_name_id on io(name, id);
            ''')
        id: None | int = None
        def log(*args: Any, **kwargs: Any):
            nonlocal id
            msg = ' '.join(map(str, args))
            if msg:
                if stdout:
                    print(f'{name}:', msg)
                if xs is not None:
                    xs.append(msg)
            with contextlib.closing(sqlite3.connect('io.db', isolation_level=None)) as con:
                con.executescript('''
                    pragma synchronous=OFF;
                    pragma journal_mode=WAL;
                ''')
                if msg:
                    data = {'msg': msg, **kwargs}
                else:
                    data = kwargs
                needs_commit = False
                if id is None:
                    con.execute('begin exclusive')
                    [id] = con.execute('select ifnull(max(id) + 1, 0) from io where name = ?', [name]).fetchone()
                    needs_commit = True
                con.execute(
                    'insert into io (name, id, data) values (?, ?, json(?));',
                    [name, id, try_json_dumps(data)],
                )
                if needs_commit:
                    con.execute('commit')
        return Log(log)

system_default_log = Log.make('system')


