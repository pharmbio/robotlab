from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, replace, field, fields
from dataclasses import is_dataclass
from typing import Any, Type, TypeVar, ParamSpec, Generic, cast, Callable, ClassVar
from typing import Literal
import apsw
import textwrap

from . import serializer

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing_extensions import Concatenate
    from typing_extensions import Self

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
    where_str: list[str] = field(default_factory=list)
    where_ops: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)
    verbose: bool = False

    def add_where_op(self, op: str, *args: Any, **kws: Any) -> SelectOptions:
        return self.replace(where_ops=[*self.where_ops, (op, args, kws)])

    def add_where_str(self, *clauses: str) -> SelectOptions:
        return self.replace(where_str=[*self.where_str, *clauses])

@dataclass(frozen=True)
class Select(Generic[P, R], PrivateReplaceMixin):
    _opts: SelectOptions = SelectOptions()
    _where: Callable[[SelectOptions], list[R]] = cast(Any, ...)

    def list(self) -> list[R]:
        return self._where(self._opts)

    def where(self, *args: P.args, **kws: P.kwargs) -> list[R]:
        return self.where_eq(*args, **kws).list()

    def where_op_curry(self, op: str) -> Callable[P, Select[P, R]]:
        def where_op(*args: P.args, **kws: P.kwargs):
            return self._replace(_opts=self._opts.add_where_op(op, *args, **kws))
        return where_op

    @property
    def where_eq(self):   return self.where_op_curry('==')
    @property
    def where_not(self):  return self.where_op_curry('!=')
    @property
    def where_lt(self):   return self.where_op_curry('<')
    @property
    def where_le(self):   return self.where_op_curry('<=')
    @property
    def where_gt(self):   return self.where_op_curry('>')
    @property
    def where_ge(self):   return self.where_op_curry('>=')
    @property
    def where_like(self): return self.where_op_curry('LIKE')
    @property
    def where_glob(self): return self.where_op_curry('GLOB')

    def where_str(self, *clauses: str) -> Select[P, R]:
        return self._replace(_opts=self._opts.add_where_str(*clauses))

    def get(self, *args: P.args, **kws: P.kwargs) -> R:
        return self._where(self._opts, *args, **kws)[0]

    def limit(self, bound: int | None = None, offset: int | None = None) -> Select[P, R]:
        return self._replace(self._opts.replace(limit=bound, offset=offset))

    def order(self, by: str) -> Select[P, R]:
        return self._replace(self._opts.replace(order=by))

    @property
    def verbose(self) -> Select[P, R]:
        return self.set_verbose()

    def set_verbose(self, value: bool=True) -> Select[P, R]:
        return self._replace(self._opts.replace(verbose=value))

    def __iter__(self):
        yield from self.where() # type: ignore

def sqlquote(s: str) -> str:
    c = "'"
    return c + s.replace(c, c+c) + c

import contextlib

A = TypeVar('A')

@dataclass
class DB:
    con: apsw.Connection
    transaction_depth: int = 0

    @property
    @contextlib.contextmanager
    def transaction(self):
        '''
        Exclusive transaction (begin exclusive .. commit), context manager version.
        '''
        self.transaction_depth += 1
        if self.transaction_depth == 1:
            self.con.execute('begin exclusive')
            yield
            self.con.execute('commit')
        else:
            yield
        self.transaction_depth -= 1

    def with_transaction(self, do: Callable[[], A]) -> A:
        '''
        Exclusive transaction (begin exclusive .. commit), expression version.
        '''
        with self.transaction:
            return do()

    def has_table(self, name: str, type: Literal['table', 'view', 'index', 'trigger']="table") -> bool:
        return any(
            self.con.execute(f'''
                select 1 from sqlite_master where name = ? and type = ?
            ''', [name, type])
        )

    def table_name(self, t: Callable[P, Any]):
        Table = t.__name__
        TableView = f'{Table}View'
        if not self.has_table(Table):
            self.con.execute(textwrap.dedent(f'''
                create table if not exists {Table} (
                    id integer as (value ->> 'id') unique,
                    value text,
                    check (typeof(id) = 'integer'),
                    check (id >= 0),
                    check (json_valid(value))
                );
                create index if not exists {Table}_id on {Table} (id);
            '''))
        if is_dataclass(t) and not self.has_table(TableView, 'view'):
            meta = getattr(t, '__meta__', None)
            views: dict[str, str] = {
                f.name: f'value ->> {sqlquote(f.name)}'
                for f in sorted(
                    fields(t),
                    key=lambda f: f.name != 'id',
                )
            }
            if isinstance(meta, Meta):
                views.update(meta.views)
            xs = [
                f'({expr}) as {sqlquote(name)}'
                for name, expr in views.items()
            ]
            self.con.execute(textwrap.dedent(f'''
                create view {TableView} as select
                    {""",
                    """.join(xs)}
                    from {Table} order by id
            '''))
        return Table

    def get(self, t: Callable[P, R]) -> Select[P, R]:
        Table = self.table_name(t)
        def where(opts: SelectOptions) -> list[R]:
            clauses: list[str] = []
            for op, args, kws in opts.where_ops:
                for f, a in collect_fields(t, args, kws).items():
                    if op in ('==', '!='):
                        # can change to '->>' together with 'is' and 'is not'
                        # None needs to be NULL though
                        clauses += [f"(value -> {sqlquote(f)}) {op} ({sqlquote(serializer.dumps(a, with_nub=False))} -> '$')"]
                    else:
                        assert isinstance(a, (str, int, float))
                        clauses += [f"(value ->> {sqlquote(f)}) {op} {sqlquote(a) if isinstance(a, str) else a}"]
            clauses += [*opts.where_str]
            if clauses:
                where_clause = ''' and
                    '''.join(clauses)
            else:
                where_clause = 'TRUE'
            stmt = f'''
                select value
                from {Table}
                where
                    {where_clause}
                order by value ->> {sqlquote(opts.order)} nulls last
            '''
            stmt = textwrap.dedent(stmt).strip()
            limit, offset = opts.limit, opts.offset
            if limit is None:
                limit = -1
            if offset is None:
                offset = 0
            if limit != -1 or offset != 0:
                stmt += f' limit {limit} offset {offset}'
            if opts.verbose:
                print(stmt)
            def throw(e: Exception):
                raise e
            return [
                serializer.loads(v) if isinstance(v, str) else throw(ValueError(f'{v} is not string'))
                for v, in self.con.execute(stmt).fetchall()
            ]
        return Select(_where=where)

    def __post_init__(self):
        self.con.execute('pragma journal_mode=WAL')

    @contextmanager
    @staticmethod
    def open(path: str):
        db = DB.connect(path)
        yield db
        db.con.close()

    @staticmethod
    def connect(path: str):
        con = apsw.Connection(path)
        con.setbusytimeout(2000)
        return DB(con)

class DBMixin(ReplaceMixin):
    id: int

    def save(self, db: DB) -> Self:
        with db.transaction:
            Table = db.table_name(self.__class__)
            meta = getattr(self.__class__, '__meta__', None)

            if isinstance(meta, Meta) and meta.log:
                LogTable = meta.log_table or f'{Table}Log'
                exists = any(
                    db.con.execute(f'''
                        select 1 from sqlite_master where type = "table" and name = ?
                    ''', [LogTable])
                )
                if not exists:
                    db.con.execute(textwrap.dedent(f'''
                        create table {LogTable} (
                            t timestamp default (strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime')),
                            action text,
                            old json,
                            new json
                        );
                        create trigger {Table}_insert after insert on {Table} begin
                            insert into {LogTable}(action, old, new) values ("insert", NULL, NEW.value);
                        end;
                        create trigger {Table}_update after update on {Table} begin
                            insert into {LogTable}(action, old, new) values ("update", OLD.value, NEW.value);
                        end;
                        create trigger {Table}_delete after delete on {Table} begin
                            insert into {LogTable}(action, old, new) values ("delete", OLD.value, NULL);
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
                # db.con.commit()
                return self
            else:
                if self.id == -1:
                    reply = db.con.execute(f'''
                        select ifnull(max(id) + 1, 0) from {Table};
                    ''').fetchone()
                    assert reply is not None
                    id, = reply
                    res = self.replace(id=id) # type: ignore
                else:
                    id = self.id
                    res = self
                db.con.execute(f'''
                    insert into {Table} values (? -> '$')
                ''', [serializer.dumps(res, with_nub=False)])
                # db.con.commit()
                return res

    def delete(self, db: DB):
        Table = self.__class__.__name__
        db.con.execute(f'''
            delete from {Table} where id = ?
        ''', [self.id])

    def reload(self, db: DB) -> Self:
        return db.get(self.__class__).where(id=self.id)[0]

@dataclass(frozen=True)
class Meta:
    log: bool = False
    log_table: None | str = None
    views: dict[str, str] = field(default_factory=dict)

def test():
    '''
    python -m imager.utils.mixins
    '''
    from datetime import datetime

    @dataclass
    class Todo(DBMixin):
        msg: str = ''
        done: bool = False
        created: datetime = field(default_factory=lambda: datetime.now())
        deleted: None | datetime = None
        id: int = -1
        __meta__: ClassVar = Meta(
            log=True,
            views={
                'created': 'value ->> "created.value"',
                'deleted': 'value ->> "deleted.value"',
            },
        )

    Todo.__qualname__ = 'Todo'

    serializer.register({'Todo': Todo})

    with DB.open(':memory:') as db:
        t0 = Todo('hello world').save(db)
        t1 = Todo('hello again').save(db)
        t2 = Todo('hello there').save(db)
        t3 = Todo('goodbye world').save(db)
        Todos = db.get(Todo) # .verbose
        print(*Todos, sep='\n')
        print(*Todos.where_glob(msg='*world'), sep='\n')
        print(*Todos.where_like(msg='hello%'), sep='\n')
        print(*Todos.where_ge(id=1).where_le(id=2), sep='\n')
        now = datetime.now()
        t3.replace(deleted=now).save(db)
        print(*Todos.where_not(deleted=None), sep='\n')
        print(*Todos.where(deleted=now), sep='\n')
        quit()
        print()
        t2.replace(done=True).save(db)
        print(*Todos.where(done=False), sep='\n')
        print()
        print(*Todos.where(done=True), sep='\n')
        t1.delete(db)
        t3.replace(deleted=datetime.now()).save(db)
        import tempfile
        from subprocess import check_output
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            db.con.execute('vacuum into ?', [tmp.name])
            out = check_output([
                'sqlite3',
                tmp.name,
                '.mode box',
                'select t, action, ifnull(new, old) from TodoLog',
                'select * from TodoView where done',
                'select * from TodoView where not done',
                'select * from TodoView where msg glob "*world"',
            ], encoding='utf8')
            print(out)

if __name__ == '__main__':
    test()
