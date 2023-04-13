from __future__ import annotations
from typing import *
from dataclasses import *

from typing_extensions import Self
from pathlib import Path
import contextlib
import sqlite3
import platform

from flask import Flask, jsonify, request
import flask

from .machine import Machine, Echo, json_request_args
from .git import Git

@dataclass
class Machines:
    ip: ClassVar[str]
    node_name: ClassVar[str]
    skip_up_check: ClassVar[bool] = False
    echo: Echo = Echo()
    git: Git = Git()

    @staticmethod
    def lookup_node_name(node_name: str | None=None) -> Machines:
        if node_name is None:
            node_name = platform.node()
        for m in Machines.__subclasses__():
            if m.node_name == node_name:
                return m()
        raise ValueError(f'{node_name} not configured (did you want to run with --test?)')

    @staticmethod
    def ip_from_node_name(node_name: str | None=None) -> str | None:
        try:
            return Machines.lookup_node_name(node_name=node_name).ip
        except ValueError:
            return None

    @classmethod
    def remote(cls, host: str | None = None, port: int = 5050) -> Self:
        if host is None:
            url = f'http://{cls.ip}:{port}'
        else:
            url = f'http://{host}:{port}'
        d = {}
        for f in fields(cls):
            d[f.name] = f.default.__class__.remote(f.name, url, skip_up_check=cls.skip_up_check) # type: ignore
        return cls(**d)

    def items(self) -> list[tuple[str, Machine]]:
        return list(self.__dict__.items())

    def serve(self, host: str | None = None, port: int = 5050):
        print('machines:')
        for k, v in self.items():
            print('    ' + k + ':', v)

        app = Flask(__name__)
        try:
            app.json.compact = False    # type: ignore
            app.json.sort_keys = False  # type: ignore
        except AttributeError:
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
            app.config['JSON_SORT_KEYS'] = False             # type: ignore

        for name, m in self.items():
            m.init()
            m.routes(name, app)

        @app.route('/<string:name>.db')
        def get_db(name: str):
            assert name.isascii() and name.isidentifier()
            name_db = f'{name}.db'
            with contextlib.closing(sqlite3.connect(name_db)) as con:
                con.execute('pragma wal_checkpoint(full);')
                return flask.send_file( # type: ignore
                    Path(name_db).resolve(),
                    download_name=name_db,
                    as_attachment=True
                )

        @app.route('/<string:name>.sql')
        def get_sql(name: str):
            assert name.isascii() and name.isidentifier()
            with contextlib.closing(sqlite3.connect(f'{name}.db')) as con:
                return '\n'.join(con.iterdump()) + '\n'

        @app.get('/tail/<int:n>') # type: ignore
        @app.get('/tail/') # type: ignore
        @app.get('/tail') # type: ignore
        def tail(n: int=10):
            assert isinstance(n, int)
            args = json_request_args()
            raw = args.pop('raw', None)
            sep = str(args.pop('sep', '  ')).replace('tab', '\t')
            where = ''
            if name := args.pop('name', None):
                where = f'where name = {name!r}'
            if args:
                return f'Unsupported arguments: {", ".join(args.keys())}\n', 400
            if raw is not None:
                select = 'select rowid as row, t, name, id, data'
            else:
                select = 'select rowid as row, t, name, id, coalesce(json_extract(data, "$.msg"), data) as data'
            sql = f'''
                select * from (
                    {select} from io {where} order by t desc limit {n}
                ) order by t asc
            '''
            with sqlite3.connect('io.db') as con:
                rows = ['row t name id data'.split()] + [
                    [str(x) for x in row]
                    for row in con.execute(sql).fetchall()
                ]
            lengths = [
                max(len(x) for x in col)
                for col in zip(*rows)
            ]
            lengths[-1] = 0
            lines = [
                sep.join(x.ljust(n) for n, x in zip(lengths, row))
                for row in rows
            ]
            return '\n'.join(lines) + '\n'

        @app.get('/') # type: ignore
        def root():
            url = request.url
            while url.endswith('/'):
                url = url[:-1]
            d: dict[str, str] = {}
            for name, m in self.items():
                d[url + '/' + name] = str(m)
            d[url + '/io.sql'] = 'Download the IO database as sqlite dump'
            d[url + '/io.db'] = 'Download the IO database in binary sqlite'
            d[url + '/tail'] = 'Show last 10 lines from the IO database'
            d[url + '/tail/<N>'] = 'Show last N lines from the IO database'
            return jsonify(d)

        if host is None:
            host = self.ip
        app.run(host=host, port=port, threaded=True, processes=1)
