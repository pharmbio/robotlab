from __future__ import annotations
from contextlib import contextmanager
from dataclasses import *
import apsw
import textwrap

from datetime import datetime
from . import serializer

from typing import *
if TYPE_CHECKING:
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
class Select(Generic[R], PrivateReplaceMixin):
    _db: DB                    = cast(Any, None)
    _focus: Syntax | Var       = cast(Any, None)
    _var: Var                  = cast(Any, None)
    _table: str                = cast(Any, None)
    _where: list[Syntax | Var] = field(default_factory=list)
    _order: tuple[Any, str] | None = None
    _limit: int | None             = None
    _offset: int | None            = None

    def where(self, *cond: bool):
        return self._replace(_where=[*self._where, *cond]) # type: ignore

    def where_some(self, *cond: bool) -> Select[R]:
        if not cond:
            syntax = 0
        else:
            syntax = cond[0]
            for c in cond[1:]:
                syntax = Syntax('or', [syntax, c], binop=True)
        return self._replace(_where=[*self._where, syntax]) # type: ignore

    def sql(self) -> str:
        def join(none: str, sep: str, values: list[Any]):
            if not values:
                return none
            else:
                return sep.join(values)
        select = to_sql(self._focus)
        where = [to_sql(w) for w in self._where]
        stmt = {
            'select': select,
            'from': f'{self._table} {self._var._head}',
        }
        if where:
            stmt['where'] = '\n  and '.join(where)
        if self._order is None:
            order, dir = self._var.id, 'asc'
        else:
            order, dir = self._order
        assert dir.lower() in ('desc', 'asc', 'desc nulls last', 'asc nulls first')
        stmt['order by'] = to_sql(order) + ' ' + dir
        if self._limit:
            stmt['limit'] = str(self._limit)
        if self._offset:
            stmt['offset'] = str(self._offset)
        return '\n'.join(k + '\n  ' + v for k, v in stmt.items()) + ';'

    def _agg(self, fn: str, thing: Any, *args: Any, default: Any = None) -> Any:
        focus = Syntax(fn, [thing, *args])
        if default is not None:
            focus = Syntax.ifnull(focus, default)
        focus = Syntax.json_quote(focus)
        return replace(self, _focus=focus).show().one()

    def count(self) -> int: return self._agg('count', Syntax('*', []))
    def max(self, v: A, default: A | None = None) -> A: return self._agg('max', v, default=default)
    def min(self, v: A, default: A | None = None) -> A: return self._agg('min', v, default=default)
    def avg(self, v: A, default: A | None = None) -> A: return self._agg('avg', v, default=default)
    def sum(self, v: A, default: A | None = None) -> A: return self._agg('sum', v, default=default)
    def total(self, v: A) -> A: return self._agg('total', v)
    def json_group_array(self, v: A) -> list[A]: return self._agg('json_group_array', v)
    def group_concat(self, v: Any, sep: str=',') -> str: return self._agg('group_concat', v, sep)

    def group(self, by: K) -> Group[K, list[R]]:
        assert not self._order
        assert not self._limit
        assert not self._offset
        focus = Syntax.json_group_array(Syntax.json(self._focus))
        return Group(replace(self, _focus=focus), by)

    def show(self) -> Select[R]:
        print(self.sql())
        return self

    def one(self) -> R:
        return self.limit(1, self._offset).list()[0]

    def list(self) -> list[R]:
        stmt = self.sql()
        def throw(e: Exception):
            raise e
        return [
            serializer.loads(v) if isinstance(v, str) else throw(ValueError(f'{v} is not string'))
            for v, in self._db.con.execute(stmt).fetchall()
        ]

    def limit(self, bound: int | None = None, offset: int | None = None) -> Select[R]:
        return self._replace(_limit=bound, _offset=offset)

    def order(self, by: Any, dir: str='asc') -> Select[R]:
        return self._replace(_order=(by, dir))

    def __iter__(self):
        yield from self.list()

K = TypeVar('K')
V = TypeVar('V')

@dataclass(frozen=True)
class Group(Generic[K, V], PrivateReplaceMixin):
    _select: Select[Any]
    _by: K = cast(Any, None)

    def sql(self) -> str:
        def join(none: str, sep: str, values: list[Any]):
            if not values:
                return none
            else:
                return sep.join(values)
        k = self._by
        v = self._select._focus
        select = Syntax.json_array(k, v)
        where = [to_sql(w) for w in self._select._where]
        stmt = {
            'select': to_sql(select),
            'from': f'{self._select._table} {self._select._var._head}',
        }
        if where:
            stmt['where'] = '\n  and '.join(where)
        stmt['group by'] = to_sql(self._by)
        if self._select._limit:
            stmt['limit'] = str(self._select._limit)
        if self._select._offset:
            stmt['offset'] = str(self._select._offset)
        return '\n'.join(k + '\n  ' + v for k, v in stmt.items()) + ';'

    def dict(self) -> dict[K, V]:
        stmt = self.sql()
        def throw(e: Exception):
            raise e
        return dict(self.list())

    def items(self) -> list[tuple[K, V]]:
        return self.list()

    def list(self) -> list[tuple[K, V]]:
        stmt = self.sql()
        def throw(e: Exception):
            raise e
        res = [
            serializer.loads(v) if isinstance(v, str) else throw(ValueError(f'{v} is not string'))
            for v, in self._select._db.con.execute(stmt).fetchall()
        ]
        return [(k, v) for k, v in res]

    def values(self) -> list[V]:
        return [v for _k, v in self.list()]

    def keys(self) -> list[K]:
        return [k for k, _v in self.list()]

    def __iter__(self):
        yield from self.list()

    def _agg(self, fn: str, thing: Any, *args: Any, default: Any = None) -> Any:
        focus = Syntax(fn, [thing, *args])
        if default is not None:
            focus = Syntax.ifnull(focus, default)
        focus = Syntax.json_quote(focus)
        return Group(
            _select = replace(self._select, _focus=focus),
            _by = self._by
        )

    def count(self) -> Group[K, int]: return self._agg('count', Syntax('*', []))
    def max(self, v: A, default: A | None = None) -> Group[K, A]: return self._agg('max', v, default=default)
    def min(self, v: A, default: A | None = None) -> Group[K, A]: return self._agg('min', v, default=default)
    def avg(self, v: A, default: A | None = None) -> Group[K, A]: return self._agg('avg', v, default=default)
    def sum(self, v: A, default: A | None = None) -> Group[K, A]: return self._agg('sum', v, default=default)
    def total(self, v: A) -> Group[K, A]: return self._agg('total', v)
    def json_group_array(self, v: A) -> Group[K, list[A]]: return self._agg('json_group_array', v)
    def group_concat(self, v: Any, sep: str=',') -> Group[K, str]: return self._agg('group_concat', v, sep)

    def limit(self, bound: int | None = None, offset: int | None = None) -> Group[K, V]:
        return self._replace(_select=self._select.limit(bound, offset))

    def order(self, by: Any) -> Group[K, V]:
        return self._replace(_select=self._select.order(by))

def sqlquote(s: str) -> str:
    c = "'"
    return c + s.replace(c, c+c) + c

from typing import *
import typing_extensions as tx
from datetime import datetime

def Var_wrap(op: str):
    def inner(this: Any, other: Any) -> bool:
        if isinstance(other, datetime):
            return Var_wrap(op)(
                Syntax.julianday(this.isoformat()),
                Syntax.julianday(other.isoformat()),
            )
        s = Syntax(op, [this, other], binop=True)
        return cast(bool, s)
    return inner

@dataclass(frozen=True)
class Var(PrivateReplaceMixin):
    _head: str = ''
    _attrs: list[str] = field(default_factory=list)

    def __getattr__(self, attr: str):
        return self._replace(_attrs=[*self._attrs, attr])

    def startswith(self, prefix: str) -> bool:
        return sql.glob(self, prefix + '*')

    def endswith(self, suffix: str) -> bool:
        return sql.glob(self, '*' + suffix)

    def isoformat(self) -> str:
        return self.value

    __eq__      = Var_wrap('is')
    __ne__      = Var_wrap('is not')
    __ge__      = Var_wrap('>=')
    __gt__      = Var_wrap('>')
    __le__      = Var_wrap('<=')
    __lt__      = Var_wrap('<')

class sql:
    @staticmethod
    def glob(v: str, pattern: str) -> bool:
        return Syntax('GLOB', [v, pattern], binop=True)

    @staticmethod
    def like(v: str, pattern: str) -> bool:
        return Syntax('LIKE', [v, pattern], binop=True)

    @staticmethod
    def either(x: bool, y: bool) -> bool:
        return Syntax('or', [x, y], binop=True)

    @staticmethod
    def both(x: bool, y: bool) -> bool:
        return Syntax('and', [x, y], binop=True)

    @staticmethod
    def nt(x: bool) -> bool:
        return Syntax('not', [x])

    @staticmethod
    def iif(c: bool, t: bool, f: bool) -> bool:
        return Syntax('iif', [c, t, f])

@dataclass(frozen=True)
class Syntax(PrivateReplaceMixin):
    op: str
    args: list[Syntax | Any]
    binop: bool = False

    @staticmethod
    def ifnull(a: Any, b: Any):   return Syntax('ifnull', [a, b])
    @staticmethod
    def json_array(*args: Any):   return Syntax('json_array', [*args])
    @staticmethod
    def json_group_array(a: Any): return Syntax('json_group_array', [a])
    @staticmethod
    def json_quote(a: Any):       return Syntax('json_quote', [a])
    @staticmethod
    def json(a: Any):             return Syntax('json', [a])
    @staticmethod
    def julianday(a: Any):        return Syntax('julianday', [])

def call_str(head: str, *args: str):
    return head + '(' + ','.join(args) + ')'

def to_sql(v: Var | Syntax | Any) -> str:
    match v:
        case Var():
            path = '.'.join(['$', *v._attrs])
            return f"({v._head}.value ->> '{path}')"
        case Syntax('*', []):
            return '*'
        case Syntax(op, [lhs, rhs]) if v.binop:
            return f'({to_sql(lhs)} {op} {to_sql(rhs)})'
        case Syntax(op, args):
            return call_str(op, *map(to_sql, args))
        case str():
            return sqlquote(v)
        case float() | int():
            return str(v)
        case bool():
            return str(v).upper()
        case None:
            return 'NULL'
        case _:
            return call_str('json', sqlquote(serializer.dumps(v, with_nub=False)))

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
        if is_dataclass(t):
            meta = getattr(t, '__meta__', None)
            if isinstance(meta, Meta):
                for index_name, index_expr in meta.indexes.items():
                    self.con.execute(textwrap.dedent(f'''
                        create index if not exists {Table}_{index_name} on {Table} ({index_expr});
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
                if expr
            ]
            self.con.execute(textwrap.dedent(f'''
                create view {TableView} as select
                    {""",
                    """.join(xs)}
                    from {Table} order by id
            '''))
        return Table

    def get(self, t: Type[R]) -> Select[R]:
        Table = self.table_name(t)
        var = Var(Table.lower(), [])
        for f in fields(t):
            setattr(t, f.name, getattr(var, f.name))
        return Select(self, var, var, Table)

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
        cls = self.__class__
        return db.get(cls).where(cls.id == self.id).one()

@dataclass(frozen=True)
class Meta:
    log: bool = False
    log_table: None | str = None
    views: dict[str, str] = field(default_factory=dict)
    indexes: dict[str, str] = field(default_factory=dict)

def test():
    '''
    python -m imager.utils.mixins
    '''
    from pprint import pp

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

    @dataclass
    class TodoGroup(DBMixin):
        head: str = ''
        todos: list[Todo] = field(default_factory=list)
        id: int = -1

    Todo.__qualname__ = 'Todo'
    serializer.register({'Todo': Todo})
    TodoGroup.__qualname__ = 'TodoGroup'
    serializer.register({'TodoGroup': TodoGroup})

    with DB.open(':memory:') as db:
        t0 = Todo('hello world').save(db)
        t1 = Todo('hello again').save(db)
        t2 = Todo('hello there').save(db)
        t3 = Todo('goodbye world').save(db)
        tg = TodoGroup('todo group 1', [t0, t2, t3]).save(db)
        Todos = db.get(Todo)
        TodoGroups = db.get(TodoGroup)
        print(TodoGroup.head)
        pp(TodoGroups.list())
        pp(TodoGroups.group(TodoGroup.head).list())
        quit()
        pp(Todos.where(
            Todo.msg > 'hello',
            Todo.id >= 1,
            Todo.created <= datetime.now(),
            Todo.deleted == None,
            ).show().list())
        print(*Todos, sep='\n')
        print(*Todos.where(Todo.msg.endswith('world')), sep='\n')
        print(*Todos.where(Todo.msg.startswith('hello')), sep='\n')
        print(*Todos.where_some(
            Todo.msg.endswith('world'),
            Todo.msg.startswith('hello')
        ), sep='\n')
        print(*Todos.where(Todo.id>1, Todo.id<=2), sep='\n')
        now = datetime.now()
        t3.replace(deleted=now).save(db)
        print(*Todos.where(Todo.deleted != None), sep='\n')
        print(*Todos.where(Todo.deleted == now), sep='\n')
        print()
        t2.replace(done=True).save(db)
        print(*Todos.where(sql.nt(Todo.done)), sep='\n')
        print()
        print(*Todos.where(Todo.done), sep='\n')
        t1.delete(db)
        t3.replace(deleted=datetime.now()).save(db)
        print(Todos.max(Todo.msg))
        print(Todos.avg(Todo.id))
        print(Todos.max(Todo.created.isoformat()))
        print(Todos.count())
        print(Todos.group_concat(Todo.msg))
        print(Todos.group_concat(Todo.msg, ', '))
        print(Todos.json_group_array(Todo.msg))
        pp(Todos.group(Todo.deleted != None).list())
        pp(Todos.group(Todo.deleted != None).dict())
        g = Todos.group(Todo.msg.startswith('hello'))
        pp(a := g.max(Todo.id).dict())
        pp(a := g.dict())
        pp(a := g.json_group_array(Todo.id).dict())
        pp(a := g.json_group_array(Todo.created).dict())
        pp(Todos.group(Todo.msg.startswith('hello')).dict())
        pp(Todos.group(Todo.msg.startswith('hello')).count().dict())
        pp(Todos.group(Todo.msg.startswith('hello')).json_group_array(Todo.msg).dict())
        pp(Todos.group(Todo.msg.startswith('hello')).json_group_array(Todo.created.isoformat()).dict())
        pp(repr(Todos.where_some().max(Todo.id)))
        pp(repr(Todos.where_some().max(Todo.id, default=0)))
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
