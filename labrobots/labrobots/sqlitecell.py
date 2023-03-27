from __future__ import annotations
from dataclasses import *
from typing import *

import sqlite3
import contextlib
import json
import time
from datetime import datetime

A = TypeVar('A')

@dataclass(frozen=True)
class SqliteCell(Generic[A]):
    """
    A class that provides a wrapper around a SQLite database cell that stores
    JSON-serialized data in a specific table with a unique key. The class
    provides methods to read and write the data, as well as retrieve the
    log of changes made to the data.

    The class is defined as a generic class with a type parameter A that
    indicates the type of data stored in the cell.  The class has four
    attributes:

    con: A SQLite database connection object.

    table: The name of the table in the database where the cell is stored.

    key: The unique key that identifies the cell within the table.

    default: The default value to use for the cell if it has not been initialized.

    In the __post_init__ method, the cell is initialized by creating the
    table if it does not exist and inserting the default value if the cell
    has not been initialized.

    Use the exclusive method to acquire an exclusive lock on the cell to
    prevent other processes from accessing or modifying it while it is
    being updated.
    """
    con: sqlite3.Connection
    table: str
    key: str
    default: A

    def __post_init__(self):
        assert self.table.isidentifier() and self.table.isascii()
        self.con.executescript(f'''
            pragma journal_mode = WAL;
            create table if not exists {self.table}(
                key text unique,
                value text check (json_valid(value))
            );
            create table if not exists {self.table}Log(key text, value text, t timestamp);
            create trigger if not exists
                {self.table}Update after update on {self.table}
            begin
                insert into {self.table}Log values (
                    NEW.key,
                    NEW.value,
                    strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime')
                );
            end;
        ''')
        with self.exclusive():
            self.con.execute(
                f'''
                    insert into {self.table} values (?, json(?)) on conflict do nothing;
                ''',
                [self.key, json.dumps(self.default)]
            )

    @contextlib.contextmanager
    def exclusive(self):
        self.con.execute('begin exclusive;')
        yield
        self.con.execute('commit;')

    def read(self) -> A:
        [(value,)] = self.con.execute(
            f'''
                select value from {self.table} where key = ?
            ''',
            [self.key]
        )
        value = json.loads(value)
        return self.normalize(value)

    def write(self, value: A):
        value = self.normalize(value)
        self.con.execute(
            f'''
                update {self.table}
                set value = json(:value)
                where key = :key;
            ''',
            {
                'key': self.key,
                'value': json.dumps(value),
            }
        )

    def get_log(self) -> Iterator[tuple[A, datetime]]:
        for value, t in self.con.execute(
            f'''
                select value, t from {self.table}Log
                where key = ?
                order by t asc
            ''',
            [self.key]
        ):
            yield self.normalize(json.loads(value)), datetime.fromisoformat(t)

    def normalize(self, value: A) -> A:
        return value

def test_memory():
    with contextlib.closing(sqlite3.connect(':memory:')) as con:
        cell = SqliteCell(con, 'Data', 'test', {})
        with cell.exclusive():
            assert cell.read() == {}
            cell.write({'bla': 'bli'})
            assert cell.read() == {'bla': 'bli'}
        with cell.exclusive():
            assert cell.read() == {'bla': 'bli'}
        cell2 = SqliteCell(con, 'Data', 'test2', cast(Any, {}))
        assert cell2.read() == {}
        cell2.write([None])
        assert cell2.read() == [None]
        assert cell.read() == {'bla': 'bli'}

def test_file():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory(prefix='sqlitecell-') as tmpdir:
        db_name=str(Path(tmpdir)/'cell.db')
        with contextlib.closing(sqlite3.connect(db_name)) as con:
            with con:
                cell = SqliteCell(con, 'Data', 'test', 0)
                cell.write(1)
                assert cell.read() == 1
        with contextlib.closing(sqlite3.connect(db_name)) as con:
            with con:
                cell = SqliteCell(con, 'Data', 'test', 0)
                assert cell.read() == 1
                cell.write(2)
                assert cell.read() == 2
        with contextlib.closing(sqlite3.connect(db_name)) as con:
            with con:
                cell = SqliteCell(con, 'Data', 'test', 0)
                assert cell.read() == 2

def test_int_cell():
    @dataclass(frozen=True)
    class IntCell(SqliteCell[int]):
        table: str = 'Int'
        key: str = 'int'
        default: int = 0

    with contextlib.closing(sqlite3.connect(':memory:')) as con:
        cell = IntCell(con)
        assert cell.read() == 0
        cell.write(1)
        assert cell.read() == 1

def test_normalize_cell():
    @dataclass(frozen=True)
    class LowerStrCell(SqliteCell[str]):
        table: str = 'Str'
        key: str = 'str'
        default: str = ''

        def normalize(self, value: str):
            return value.lower()

    with contextlib.closing(sqlite3.connect(':memory:')) as con:
        cell = LowerStrCell(con)
        assert cell.read() == ''
        cell.write('Hello!')
        assert cell.read() == 'hello!'
        time.sleep(0.002)
        cell.write('Bye-bye!')
        assert cell.read() == 'bye-bye!'

def test_log():
    with contextlib.closing(sqlite3.connect(':memory:')) as con:
        cell = SqliteCell(con, 'Data', 'test', '')
        assert cell.read() == ''
        cell.write('one')
        assert cell.read() == 'one'
        time.sleep(0.002)
        cell.write('two')
        assert cell.read() == 'two'
        [(v1, t1), (v2, t2)] = cell.get_log()
        assert v1 == 'one'
        assert v2 == 'two'
        assert t1 < t2

