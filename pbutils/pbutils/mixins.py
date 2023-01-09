from __future__ import annotations
from contextlib import contextmanager
from dataclasses import *
from dataclasses import _MISSING_TYPE
import apsw
import textwrap

from datetime import datetime
from . import serializer
from pathlib import Path

from pprint import pp

from typing import *
if TYPE_CHECKING:
    from typing_extensions import Self

from . import p

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
A = TypeVar('A')
SQLType: TypeAlias = str | int | float | bytes | None
S = TypeVar('S', str, int, float, bytes, None)
Py = TypeVar('Py')
K = TypeVar('K')
V = TypeVar('V')

@dataclass(frozen=True)
class Select(Generic[R], PrivateReplaceMixin):
    _db: DB               = cast(Any, None)
    _focus: Var           = cast(Any, None)
    _table: DataClassDesc = cast(Any, None)
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
        columns: set[str] = {
            col
            for col, in
            self._db.con.execute(
                'select name from pragma_table_info(?)',
                (self._table.table_name(),)
            )
        }
        selects: list[str] = []
        for conv in self._focus._follow().sql_columns_converters():
            c = conv.key
            if c in columns:
                selects += [
                    f'{self._table.var_name()}.{c}'
                ]
            else:
                print(f'Adding default {c}: {conv.default!r}')
                selects += [
                    to_sql(conv.conv_to_sql(conv.default))
                ]
        select = ', '.join(selects)
        where = [to_sql(w) for w in self._where]
        stmt = {
            'select': select,
            'from': f'{self._table.table_name()} {self._table.var_name()}',
        }
        if where:
            stmt['where'] = '\n  and '.join(where)
        if self._order is None:
            order, dir = self._table.var().id, 'asc'
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
        raise ValueError('TODO: Syntax needs a converter to convert an aggregated value back to python')
        focus = Syntax(fn, [thing, *args])
        if default is not None:
            focus = Syntax.ifnull(focus, default)
        focus = Syntax.json_quote(focus)
        return replace(self, _focus=focus).one()

    def count(self) -> int: return self._agg('count', Syntax('*', []))
    def max(self, v: A, default: A | None = None) -> A: return self._agg('max', v, default=default)
    def min(self, v: A, default: A | None = None) -> A: return self._agg('min', v, default=default)
    def avg(self, v: A, default: A | None = None) -> A: return self._agg('avg', v, default=default)
    def sum(self, v: A, default: A | None = None) -> A: return self._agg('sum', v, default=default)
    def total(self, v: A) -> A: return self._agg('total', v)
    def json_group_array(self, v: A) -> list[A]: return self._agg('json_group_array', v)
    def group_concat(self, v: Any, sep: str=',') -> str: return self._agg('group_concat', v, sep)

    def select(self, v: A) -> Select[A]:
        if isinstance(v, Var):
            return self._replace(_focus=v)
        else:
            raise ValueError(f'Can only select variables, not {v}')

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
        for row in self.limit(1, self._offset):
            return row
        else:
            raise ValueError('Empty select')

    def one_or(self, default: A) -> R | A:
        for row in self.limit(1, self._offset):
            return row
        else:
            return default

    def list(self) -> list[R]:
        stmt = self.sql()
        def throw(e: Exception):
            raise e
        rows = self._db.con.execute(stmt).fetchall()
        return self._focus._follow().from_sql_tuples(rows)

    def limit(self, bound: int | None = None, offset: int | None = None) -> Select[R]:
        return self._replace(_limit=bound, _offset=offset)

    def order(self, by: Any, dir: str='asc') -> Select[R]:
        return self._replace(_order=(by, dir))

    def __iter__(self):
        yield from self.list()

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

def getattrs(obj: Any, attrs: list[str]):
    for attr in attrs:
        obj = getattr(obj, attr)
    return obj

def Var_wrap(op: str):
    def inner(this: Any, other: Any) -> bool:
        assert isinstance(this, Var)
        d = this._follow()
        depth = len(this._attrs)
        if isinstance(d, DataClassDesc):
            lhs = [
                getattrs(this, k.split('$')[depth:])
                for k, _ in d.flat.items()
            ]
            rhs = [
                other_at_k if isinstance(other_at_k, Var | Syntax) else convs.conv_to_sql(other_at_k)
                for k, convs in d.flat.items()
                for other_at_k in [getattrs(other, k.split('$')[depth:])]
            ]
            lhs = Syntax(',', lhs)
            rhs = Syntax(',', rhs)
        else:
            lhs = this
            if isinstance(other, Var | Syntax):
                rhs = other
            else:
                rhs = d.conv_to_sql(other)
        s = Syntax(op, [lhs, rhs], binop=True)
        return cast(bool, s)
    return inner

@dataclass(frozen=True)
class Var(PrivateReplaceMixin):
    _head: str = ''
    _desc: DataClassDesc = cast(Any, None)
    _attrs: list[str] = field(default_factory=list)

    def _follow(self) -> DataClassDesc | Converters:
        desc: DataClassDesc | Converters = self._desc
        path: list[str] = []
        for attr in self._attrs:
            path += [attr]
            if not isinstance(desc, DataClassDesc):
                raise ValueError(f'Refusing to go into opaque {path} in var {self._head}.{self._attrs}')
            desc = desc.fields['$'.join(path)]
        return desc

    def __getattr__(self, attr: str):
        return self._replace(_attrs=[*self._attrs, attr])

    def startswith(self, prefix: str) -> bool:
        return sql.glob(self, prefix + '*')

    def endswith(self, suffix: str) -> bool:
        return sql.glob(self, '*' + suffix)

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
    return head + '(' + ', '.join(args) + ')'

def to_sql(v: Var | Syntax | Any) -> str:
    match v:
        case Var():
            return v._head + '.' + '$'.join(v._attrs)
            # return '.'.join([v._head, *v._attrs])
        case Syntax(',', args):
            # tuple (sqlite row value)
            return call_str('', *map(to_sql, args))
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
            raise ValueError(f'Cannot convert {v} to sql without more type info')
        # case _:
        #     return call_str('json', sqlquote(serializer.dumps(v, with_nub=False)))

import contextlib

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

    def get_desc(self, t: Type[Any]) -> tuple[str, DataClassDesc]:
        d = DataClassDesc.get(t)
        Table = d.table_name()
        if not self.has_table(Table):
            self.con.execute(d.schema())
        return Table, d

    def get(self, t: Type[R]) -> Select[R]:
        _, d = self.get_desc(t)
        return Select(self, d.var(), d)

    def __post_init__(self):
        self.con.execute('pragma journal_mode=WAL')

    @contextmanager
    @staticmethod
    def open(path: str | Path):
        db = DB.connect(path)
        yield db
        db.con.close()

    @staticmethod
    def connect(path: str | Path):
        con = apsw.Connection(str(path))
        con.setbusytimeout(2000)
        return DB(con)

class DBMixin(ReplaceMixin):
    id: int

    def save(self, db: DB) -> Self:
        with db.transaction:
            Table, d = db.get_desc(self.__class__)
            if self.id == -1:
                exists = False
            else:
                exists = any(
                    db.con.execute(f'''
                        select 1 from {Table} where id = ?
                    ''', [self.id])
                )
            if exists:
                pairs = dict(zip(d.sql_columns(), d.to_sql_tuple(self)))
                pairs.pop('id')
                rows = [f'{c} = ?' for c, v in pairs.items()]
                vals = [v          for c, v in pairs.items()]
                db.con.execute(
                    f'update {Table} set {", ".join(rows)} where id = ?',
                    [*vals, self.id]
                )
                return self
            else:
                if self.id == -1:
                    reply = db.con.execute(f'''
                        select ifnull(max(id) + 1, 0) from {Table};
                    ''').fetchone()
                    assert reply is not None
                    id, = reply
                    res = replace(self, id=id) # type: ignore
                else:
                    id = self.id
                    res = self

                vals = d.to_sql_tuple(res)
                qs = ','.join('?' for _ in vals)
                db.con.execute(
                    f'insert into {Table} values ({qs})',
                    vals
                )
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
    pass
    # log: bool = False
    # log_table: None | str = None
    # views: dict[str, str] = field(default_factory=dict)
    # indexes: dict[str, str] = field(default_factory=dict)

import sys, functools, inspect

@functools.cache
def get_annotations(cls: Type[Any]):
    return inspect.get_annotations(
        cls,
        globals=sys.modules[cls.__module__].__dict__,
        locals=dict(vars(cls)),
        eval_str=True,
    )

@dataclass
class Converter(Generic[S, Py]):
    sql_type: Type[S]
    py_type: Type[Py]
    to_py: Callable[[S], Py] | None = field(default=None, repr=False)
    to_sql: Callable[[Py], S] | None = field(default=None, repr=False)

serializer_converter = Converter(str, object, serializer.loads, serializer.dumps)

from datetime import datetime, timedelta, date, time
from types import UnionType

@functools.cache
def make_converter(t: Type[Any]) -> list[Converter[Any, Any]]:
    if t in (str, int, bytes, type(None)):
        return [Converter(t, t)]
    elif t == float:
        return [
            Converter(t, t),
            Converter(float, int, None, float),
        ]
    elif t == bool:
        return [Converter(int, bool, bool, int)]
    elif t == datetime:
        return [Converter(str, datetime, datetime.fromisoformat, lambda d: datetime.isoformat(d, sep=' '))]
    elif t == date:
        return [Converter(str, date, date.fromisoformat, lambda d: date.isoformat(d))]
    elif t == time:
        return [Converter(str, t, time.fromisoformat, lambda d: time.isoformat(d))]
    elif t == timedelta:
        return [Converter(float, timedelta, lambda d: timedelta(seconds=d), timedelta.total_seconds)]
    elif get_origin(t) in (UnionType, Union):
        res = DefaultDict[SQLType, list[Any]](list)
        for alt in get_args(t):
            for conv in make_converter(alt):
                res[conv.sql_type] += [conv]
        # pp((t, res))
        needs_json = any(len(convs) > 1 for convs in res.values())
        if needs_json:
            no_serializer = [
                convs[0]
                for sql_type, convs in res.items()
                if len(convs) == 1 and sql_type != str
            ]
            return no_serializer + [serializer_converter]
        else:
            return [
                convs[0]
                for convs in res.values()
            ]
    elif get_origin(t) is Literal:
        types = {type(a) for a in get_args(t)}
        if len(types) != 1:
            raise ValueError(f'Literals need to be of one type for now ({types=})')
        return make_converter(types.pop())
    else:
        return [serializer_converter]

@dataclass
class Converters:
    xs: list[Converter[Any, Any]]
    key: str
    default: Any

    def sql_columns(self) -> list[str]:
        return [self.key]

    def sql_columns_converters(self) -> list[Converters]:
        return [self]

    def sql_columns_with_type(self) -> list[tuple[str, str]]:
        return [
            (self.key, 'integer primary key' if self.key == 'id' else type_as_sql(self))
        ]

    def conv_to_py(self, val: SQLType):
        for conv in self.xs:
            if isinstance(val, conv.sql_type):
                return conv.to_py(val) if conv.to_py else val
        raise ValueError(f'Cannot convert {val=} {self=}')

    def conv_to_sql(self, val: Any):
        for conv in self.xs:
            if isinstance(val, conv.py_type):
                return conv.to_sql(val) if conv.to_sql else val
        raise ValueError(f'No converter! {val=} {self}')

    def from_sql_tuple(self, row: tuple[SQLType, ...]) -> Any:
        assert len(row) == 1
        return self.conv_to_py(row[0])

    def from_sql_tuples(self, rows: list[tuple[SQLType, ...]]) -> list[Any]:
        return [self.from_sql_tuple(row) for row in rows]

@dataclass
class DataClassDesc:
    con: Any
    fields: dict[str, DataClassDesc | Converters]
    flat: dict[str, Converters] = field(default_factory=dict, repr=False)

    def sql_columns(self) -> list[str]:
        return list(self.flat.keys())

    def sql_columns_converters(self) -> list[Converters]:
        return list(self.flat.values())

    def sql_columns_with_type(self) -> list[tuple[str, str]]:
        return [
            (k, 'integer primary key' if k == 'id' else type_as_sql(convs))
            for k, convs in self.flat.items()
        ]

    def table_name(self) -> str:
        return self.con.__name__

    def var_name(self):
        return self.table_name().lower()

    def var(self) -> Var:
        return Var(self.table_name().lower(), self, [])

    def schema(self):
        rows: list[str] = []
        for k, t in self.sql_columns_with_type():
            rows += [f'{k} {t}']
        rows += ['check (id >= 0)']
        body = ','.join('\n    ' + row for row in rows)
        return f'create table if not exists {self.table_name()} ({body}) strict;'

    def to_sql_tuple(self, value: Any) -> list[SQLType]:
        out: list[SQLType] = []
        for k, f in self.fields.items():
            v = getattr(value, k.split('$')[-1])
            if isinstance(f, DataClassDesc):
                out += f.to_sql_tuple(v)
            else:
                out += [f.conv_to_sql(v)]
        return out

    def from_sql_tuple(self, row: tuple[SQLType, ...]) -> Any:
        kv = {
            k: convs.conv_to_py(v)
            for v, (k, convs) in zip(row, self.flat.items())
        }
        def unflatten(d: DataClassDesc):
            args: list[Any] = []
            for k, f in d.fields.items():
                if isinstance(f, Converters):
                    args += [kv.get(k)]
                else:
                    args += [unflatten(f)]
            return d.con(*args)
        return unflatten(self)

    def from_sql_tuples(self, rows: list[tuple[SQLType, ...]]) -> list[Any]:
        return [self.from_sql_tuple(row) for row in rows]

    def __post_init__(self):
        def flatten(d: DataClassDesc):
            out: dict[str, Converters] = {}
            for k, f in d.fields.items():
                if isinstance(f, Converters):
                    out[k] = f
                else:
                    for kk, li in flatten(f).items():
                        out[kk] = li
            return out
        self.flat = flatten(self)

    @functools.cache
    @staticmethod
    def get(dc: Type[Any] | Callable[..., Any]) -> DataClassDesc:
        ret = desc(dc)
        assert isinstance(ret, DataClassDesc)
        def scope_names(d: DataClassDesc | Converters, path: list[str]) -> DataClassDesc | Converters:
            if isinstance(d, Converters):
                return Converters(d.xs, '$'.join(path), d.default)
            else:
                return DataClassDesc(
                    d.con,
                    {
                        '$'.join([*path, k]): scope_names(f, path=[*path, k])
                        for k, f in d.fields.items()
                    }
                )
        scoped = scope_names(ret, [])
        assert isinstance(scoped, DataClassDesc)
        for k, _ in scoped.fields.items():
            setattr(dc, k, getattr(scoped.var(), k))
        return scoped

# from pbutils import p

def desc(dc: Type[Any], default: Any=None) -> DataClassDesc | Converters:
    if not is_dataclass(dc) or dc.__subclasses__():
        return Converters(make_converter(dc), '<converter key to be filled in by scope_names>', default)
    field_dict = {
        field.name: field for field in fields(dc)
    }
    def get_default(field: Field):
        if callable(field.default_factory):
            return field.default_factory()
        else:
            return field.default
    return DataClassDesc(
        dc,
        {
            k: desc(v, get_default(field))
            for k, v in get_annotations(dc).items()
            if (field := field_dict.get(k))
        }
    )

def type_as_sql(t: SQLType | Converter[Any, Any] | Converters) -> str:
    if isinstance(t, Converter):
        return type_as_sql(t.sql_type)
    elif isinstance(t, Converters):
        ts = [type_as_sql(x) for x in t.xs]
        non_nulls = [t for t in ts if t != 'null']
        nulls =     [t for t in ts if t == 'null']
        if not non_nulls:
            return 'null'
        else:
            head, *_ = non_nulls
            if all(head == t for t in non_nulls):
                repr = head
            else:
                repr = 'any'
            if nulls:
                return repr
            else:
                return repr + ' not null'
    elif t == str:
        return 'text'
    elif t == int:
        return 'integer'
    elif t == float:
        return 'real'
    elif t == type(None):
        return 'null'
    elif t == bytes:
        return 'blob'
    else:
        raise ValueError(t)

def te_st():
    '''
    python -m imager.utils.mixins
    '''
    from pprint import pp

    @dataclass(frozen=True, order=True)
    class Inner:
        x: int = 1
        y: float = 1.5
        # z: float | int = 2
        # u: float | None = 2.5
        # v: int | None = 3
        # w: float | int | None = None

    @dataclass
    class Todo(DBMixin):
        msg: str = ''
        done: bool = False
        created: datetime = field(default_factory=lambda: datetime.now())
        deleted: None | datetime = None
        # x: Union[None, datetime] = None
        # y: Union[None, Union[datetime, int]] = None
        # b: datetime | str | None = None
        inner: Inner = field(default_factory=Inner)
        id: int = -1

    @dataclass
    class TodoGroup(DBMixin):
        head: str = ''
        todos: list[Todo] = field(default_factory=list)
        id: int = -1

    @dataclass
    class Test(DBMixin):
        a: str = ''
        b: str | None = None
        c: Literal['a', 'b'] = 'a'
        d: Literal['a', 'b'] | None = None
        id: int = -1

    @dataclass
    class A(DBMixin):
        a: str | list[str] = ''
        id: int = -1

    @dataclass
    class Aw(DBMixin):
        a: A
        id: int = -1

    serializer.register(locals())

    with DB.open(':memory:') as db:
        # x = Test(a='a').save(db)
        # y = Test(a='a', b='b').save(db)
        # z = Test(a='a', b='b', d='b').save(db)
        # db.con.execute('select * from Test').fetchall() | p
        Aw(A(a='a').save(db)).save(db)
        Aw(A(a=['a']).save(db)).save(db)
        db.get(A).where(A.a == 'a').show().list() | p
        db.get(A).where(A.a == ['a']).show().list() | p
        db.get(Aw).where(Aw.a == A('a', id=0)).show().list() | p
        db.get(Aw).where(Aw.a == A(['a'], id=1)).show().list() | p
        quit()
        # pp(desc(Todo))
        t0 = Todo('hello world', inner=Inner()).save(db)
        t1 = Todo('hello again', inner=Inner(2, 3)).save(db)
        t2 = Todo('hello there', inner=Inner(False, 5)).save(db)
        t3 = Todo('goodbye world', inner=Inner(0, False)).save(db)
        now = datetime.now()
        t3.replace(deleted=now).save(db)
        Todos = db.get(Todo)
        p | Todos.where(Todo.id < 2).list()
        p | Todos.where(Todo.inner.y > 2).list()
        p | Todos.where(Todo.inner == Inner()).list()
        p | Todos.where(Todo.inner >= Inner()).list()
        p | Todos.where(
            Todo.msg > 'hello',
            Todo.id >= 1,
            Todo.created <= datetime.now(),
            Todo.deleted == None,
        ).list()
        if 1:
            p | Todos.select(Todo.inner).list()
            p | Todos.select(Todo.msg).list()
            p | Todos.select(Todo.inner.y).list()
            TodoGroup('todo group 1', [t0, t2]).save(db)
            TodoGroup('todo group 2', [t1, t3]).save(db)
            p | db.get(TodoGroup).list()
            p | db.get(TodoGroup).select(TodoGroup.todos).list()
            p | db.get(TodoGroup).select(TodoGroup.head).list()
            # pp(Todos.where(Todo.id == 2).list())

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
        print(*Todos.where(Todo.deleted != None), sep='\n')
        print(*Todos.where(Todo.deleted == now), sep='\n')
        print()
        t2.replace(done=True).save(db)
        print(*Todos.where(sql.nt(Todo.done)), sep='\n')
        print()
        print(*Todos.where(Todo.done), sep='\n')
        t1.delete(db)
        t3.replace(deleted=datetime.now()).save(db)

        from pathlib import Path
        Path("boo.db").unlink()
        db.con.execute('vacuum into ?', ["boo.db"])

        quit()

        print(Todos.max(Todo.msg))
        print(Todos.avg(Todo.id))
        print(Todos.max(Todo.created))
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
