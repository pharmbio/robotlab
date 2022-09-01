from __future__ import annotations
from flask.wrappers import Response
from typing import Any
from flask import after_this_request, request

import os
import secrets
import sqlite3
from threading import Lock

from . import serve

class DB:
    con: sqlite3.Connection

    def __init__(self, path: str):
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.executescript('''
            pragma locking_mode=EXCLUSIVE;
            pragma journal_mode=WAL;
            create table if not exists data (
                user text,
                key text,
                value text,
                ts timestamp default (datetime('now', 'localtime')),
                primary key (user, key)
            );
            create table if not exists meta (
                user text,
                key text,
                value text,
                ts timestamp default (datetime('now', 'localtime')),
                primary key (user, key)
            );
        ''')

    def user(self, shared: bool) -> str:
        if shared:
            return 'shared'
        user = getattr(request, 'user', None)
        if not user:
            user = request.cookies.get('u')
            if not user:
                user = secrets.token_urlsafe(9)
                self.con.executemany(
                    'insert into meta(user, key, value) values (?, ?, ?)',
                    [(user, k, v) for k, v in request.headers.items()]
                )
                self.con.commit()
                @after_this_request
                def later(response: Response) -> Response:
                    response.set_cookie('u', user)
                    return response
            setattr(request, 'user', user)
        return user

    def update(self, kvs: dict[str, str], shared: bool) -> dict[str, Any]:
        user = self.user(shared=shared)
        self.con.executemany(
            '''
                insert into data(user, key, value) values (?, ?, ?)
                on conflict(user, key)
                do update set value = excluded.value, ts = excluded.ts
            ''',
            [(user, k, v) for k, v in kvs.items()]
        )
        self.con.commit()
        # todo: do nothing if updated diff was zero
        if shared:
            serve.reload()
            gen = serve.generation
            @after_this_request
            def later(response: Response) -> Response:
                response.set_cookie('g', str(gen))
                return response
            return {'gen': gen}
        else:
            return {'refresh': True}

    def get(self, key: str, d: Any, shared: bool) -> Any:
        user = self.user(shared=shared)
        for v, in self.con.execute(
            'select value from data where user = ? and key = ?',
            [user, key]
        ):
            return v
        return d

_db: DB | None = None
_db_lock: Lock = Lock()

def get_viable_db() -> DB:
    global _db, _db_lock
    with _db_lock:
        if _db is None:
            _db = DB(os.environ.get('VIABLE_DB', 'viable.db'))
        return _db
