from __future__ import annotations
from dataclasses import dataclass, replace, field, fields
from typing import Any, Type, TypeVar, ParamSpec, Generic, cast, Callable, ClassVar
from typing_extensions import Self
from typing_extensions import Concatenate
import sqlite3
import textwrap
from . import serializer

def collect_fields(cls: Any, args: tuple[Any], kws: dict[str, Any]) -> dict[str, Any]:
    for field, arg in zip(fields(cls), args):
        kws[field.name] = arg
    return kws

class ReplaceMixin:
    @property
    def replace(self) -> Type[Self]:
        def replacer(*args: Any, **kws: Any) -> Self:
            return replace(self, **collect_fields(self, args, kws))
        return replacer # type: ignore

class PrivateReplaceMixin:
    @property
    def _replace(self) -> Type[Self]:
        def replacer(*args: Any, **kws: Any) -> Self:
            return replace(self, **collect_fields(self, args, kws))
        return replacer # type: ignore

P = ParamSpec('P')
R = TypeVar('R')

@dataclass(frozen=True)
class SelectOptions(ReplaceMixin):
    order: str = 'id'
    limit: int | None = None
    offset: int | None = None

@dataclass(frozen=True)
class Select(Generic[P, R], PrivateReplaceMixin):
    _opts: SelectOptions = SelectOptions()
    _where: Callable[Concatenate[SelectOptions, P], list[R]] = cast(Any, ...)

    def where(self, *args: P.args, **kws: P.kwargs) -> list[R]:
        return self._where(self._opts, *args, **kws)

    def get(self, *args: P.args, **kws: P.kwargs) -> R:
        return self._where(self._opts, *args, **kws)[0]

    def limit(self, bound: int | None = None, offset: int | None = None) -> Select[P, R]:
        return self._replace(self._opts.replace(limit=bound, offset=offset))

    def order(self, by: str) -> Select[P, R]:
        return self._replace(self._opts.replace(order=by))

    def __iter__(self):
        yield from self.where() # type: ignore

from dataclasses import is_dataclass

def sqlquote(s: str) -> str:
    c = "'"
    return c + s.replace(c, c+c) + c

import typing
import types
from dataclasses import Field
from datetime import datetime, timedelta

@dataclass
class DB:
    con: sqlite3.Connection

    def _create_table(self, t: Callable[P, Any]):
        Table = t.__name__
        self.con.executescript(textwrap.dedent(f'''
            create table if not exists {Table} (
                id integer as (value ->> 'id') unique,
                value text,
                check (typeof(id) = 'integer'),
                check (id >= 0),
                check (json_valid(value))
            );
            create index if not exists {Table}_id on {Table} (id);
        '''))
        if is_dataclass(t):
            TableView = f'{Table}View'
            has_view = any(
                self.con.execute(f'''
                    select 1 from sqlite_master where type = "view" and name = ?
                ''', [TableView])
            )
            if not has_view:
                def pick_value(f: Field[Any]):
                    # this is a bit silly, put these kind of hints in __meta__ instead
                    import re
                    ft = re.sub(r'\bNone\b\s*\|', '', f.type)
                    ft = re.sub(r'\|\s*\bNone\b', '', f.type)
                    ft = ft.replace(' ', '')
                    if ft == 'datetime' or ft == 'timedelta':
                        return sqlquote(f.name + '.value')
                    else:
                        return sqlquote(f.name)
                xs = [
                    f'(value ->> {pick_value(f)}) as {sqlquote(f.name)}'
                    for f in fields(t)
                ]
                # _ = lambda x: (print(x), x)[-1]
                def _(x: str) -> str: return x
                self.con.execute(_(f'''
                    create view {TableView} as select {', '.join(xs)} from {Table} order by id
                '''))
        return Table

    def get(self, t: Callable[P, R]) -> Select[P, R]:
        Table = self._create_table(t)
        def where(opts: SelectOptions, *args: P.args, **kws: P.kwargs) -> list[R]:
            clauses: list[str] = []
            for f, a in collect_fields(t, args, kws).items():
                clauses += [f"value -> {sqlquote(f)} = {sqlquote(serializer.dumps(a, with_nub=False))} -> '$'"]
            if clauses:
                where_clause = 'where ' + ' and '.join(clauses)
            else:
                where_clause = ''
            stmt = f'select value from {Table} {where_clause} order by value ->> {opts.order!r}'
            limit, offset = opts.limit, opts.offset
            if limit is None:
                limit = -1
            if offset is None:
                offset = 0
            if limit != -1 or offset != 0:
                stmt += f' limit {limit} offset {offset}'
            print(stmt)
            return [
                serializer.loads(v)
                for v, in self.con.execute(stmt).fetchall()
            ]
        return Select(_where=where)

    @classmethod
    def open(cls, s: str):
        db = DB(sqlite3.connect(s)) #check same thread?
        return db

class DBMixin(ReplaceMixin):
    id: int

    def save(self, db: DB) -> Self:
        Table = db._create_table(self.__class__)
        meta = getattr(self.__class__, '__meta__', None)

        if isinstance(meta, Meta) and meta.log:
            LogTable = meta.log_table or f'{Table}Log'
            exists = any(
                db.con.execute(f'''
                    select 1 from sqlite_master where type = "table" and name = ?
                ''', [LogTable])
            )
            if not exists:
                db.con.executescript(textwrap.dedent(f'''
                    create table {LogTable} (
                        t timestamp default (strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime')),
                        action text,
                        id integer,
                        new json
                    );
                    create trigger
                        {Table}_insert after insert on {Table}
                    begin
                        insert into {LogTable}(id, new, action) values (NEW.id, NEW.value, "insert");
                    end;
                    create trigger
                        {Table}_update after update on {Table}
                    begin
                        insert into {LogTable}(id, new, action) values (OLD.id, NEW.value, "update");
                    end;
                    create trigger
                        {Table}_delete after delete on {Table}
                    begin
                        insert into {LogTable}(id, new, action) values (OLD.id, NULL, "delete");
                    end;
                '''))
        if self.id == -1:
            exists = False
        else:
            exists = any(
                db.con.execute(f'''
                    select 1 from {Table} where id = ?
                ''', [self.id])
            )
        if exists:
            db.con.execute(f'''
                update {Table} set value = ? -> '$' where id = ?
            ''', [serializer.dumps(self, with_nub=False), self.id])
            db.con.commit()
            return self
        else:
            if self.id == -1:
                id, = db.con.execute(f'''
                    select ifnull(max(id) + 1, 0) from {Table};
                ''').fetchone()
                res = self.replace(id=id) # type: ignore
            else:
                id = self.id
                res = self
            db.con.execute(f'''
                insert into {Table} values (? -> '$')
            ''', [serializer.dumps(res, with_nub=False)])
            db.con.commit()
            return res

    def delete(self, db: DB) -> int:
        Table = self.__class__.__name__
        c = db.con.execute(f'''
            delete from {Table} where id = ?
        ''', [self.id])
        return c.rowcount

    def reload(self, db: DB) -> Self:
        return db.get(self.__class__).where(id=self.id)[0]

@dataclass(frozen=True)
class Meta:
    log: bool = False
    log_table: None | str = None

if __name__ == '__main__':
    '''
    python -m imager.utils.mixins
    '''
    from datetime import datetime

    @dataclass
    class Todo(DBMixin):
        msg: str = ''
        done: bool = False
        deleted: None | datetime = None
        created: datetime = field(default_factory=lambda: datetime.now())
        id: int = -1
        __meta__: ClassVar = Meta(log=True)

    serializer.register(globals())

    db = DB.open(':memory:')
    t0 = Todo('hello world').save(db)
    t1 = Todo('hello again').save(db)
    t2 = Todo('hello there').save(db)
    t3 = Todo('goodbye world').save(db)
    Todos = db.get(Todo)
    print(list(Todos))
    print()
    t2.replace(done=True).save(db)
    print(list(Todos.where(done=False)))
    print()
    print(list(Todos.where(done=True)))
    t2.delete(db)
    print()
    print(*db.con.execute('select * from Todo where value ->> "msg" glob "*world"').fetchall(), sep='\n')
    print()
    print(*db.con.execute('select * from TodoLog').fetchall(), sep='\n')
