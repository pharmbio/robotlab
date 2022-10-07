from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, Iterator
from typing import Protocol, Callable
from urllib.parse import urlencode
from urllib.request import urlopen
import json
import re
import time

import pbutils
from pbutils.mixins import DBMixin, DB, Meta
from .robotarm import Robotarm

@dataclass(frozen=True)
class Curl(DBMixin):
    url: str = ''
    data: Any = None
    res: Any = None
    started: datetime | None = None
    finished: datetime | None = None
    id: int = -1
    __meta__: ClassVar = Meta(
        views={
            'success': 'value ->> "res.success"',
            'started': 'value ->> "started.value"',
            'finished': 'value ->> "finished.value"',
            'lines': 'value ->> "value.res.lines"',
            'success': 'value ->> "value.res.success"',
            'valval': 'value ->> "value.res.value"',
        },
    )

pbutils.serializer.register(globals())

def curl(url: str, data: None | dict[str, str] = None) -> dict[str, Any]:
    with DB.open('curl.db') as db:
        log = Curl(url=url, data=data, started=datetime.now()).save(db)

        ten_minutes = 60 * 10
        binary: bytes | None = data if data is None else urlencode(data).encode()
        res: dict[str, Any] = json.loads(urlopen(url, data=binary, timeout=ten_minutes).read())

        log = log.replace(res=res, finished=datetime.now()).save(db)

        assert isinstance(res, dict)
        if not res.get('success'):
            pbutils.pr(res)
        return res

def post(url: str, data: dict[str, str]) -> dict[str, Any]:
    return curl(url, data)

@dataclass(frozen=True)
class IMXStatus:
    code: str
    details: str

class RobotarmLike(Protocol):
    def execute_movelist(self, name: str, before_each: Callable[[], None] | None = None):
        pass

    def set_speed(self, value: int):
        pass

class RobotarmSim:
    def execute_movelist(self, name: str, before_each: Callable[[], None] | None = None):
        if before_each:
            before_each()
            before_each()

    def set_speed(self, value: int):
        pass

class IMXLike:
    def open(self, sync: bool=True) -> None:
        pass

    def close(self) -> None:
        pass

    def is_ready(self) -> bool:
        return True

    def acquire(self, *, plate_id: str, hts_file: str):
        pass

@dataclass(frozen=True)
class IMX(IMXLike):
    url: str
    def send(self, msg: str):
        res = post(self.url, {'msg': msg})
        if not res['success']:
            nl = '\n'
            if isinstance(v := res.get('value'), str):
                raise ValueError(f'IMX errored!{nl}{res}{nl}{v}')
            else:
                raise ValueError(f'IMX errored!{nl}{res}')
        return res

    def open(self, sync: bool=True):
        try:
            _res = self.send('GOTO,LOAD')
        except ValueError as e:
            print('ignoring', e)
        while True:
            time.sleep(0.1)
            if self.status() == IMXStatus('READY', 'LOAD'):
                break

        '''
        self.ensure_ready()
        _res = self.send('GOTO,LOAD')
        if sync:
            self.ensure_ready()
        '''

    def close(self):
        try:
            _res = self.send('GOTO,SAMPLE')
        except ValueError as e:
            print('ignoring', e)
        while True:
            time.sleep(0.1)
            if self.status() == IMXStatus('READY', 'SAMPLE'):
                break
        # does this work if there is no plate in?
        # otherwise use RUNJOURNAL on the close.JNL

    def online(self):
        return self.send('ONLINE')

    def status(self) -> IMXStatus:
        res = self.send('STATUS')
        reply: str = res['value']
        _imx_id, status_code, details, *more_details = reply.split(',')
        ret = IMXStatus(code=status_code, details=details)
        print('imx:', ret, more_details)
        if ret.code == 'ERROR':
            nl = '\n'
            raise ValueError(f'IMX errored!{nl}{ret}')
        return ret

    def is_ready(self):
        return self.status().code in ('READY', 'DONE')

    def acquire(self, *, plate_id: str, hts_file: str):
        plate_id = ''.join(
            char if re.match(r'^[\w\d_ ]$', char) else '-'
            for char in plate_id
        )
        _res = self.send(f'RUN,{plate_id},{hts_file}')
        time.sleep(1)
        while self.status().code not in ('RUNNING', 'DONE'):
            time.sleep(1)
        return

import random

class BarcodeReaderLike:
    def read(self) -> str:
        x = random.randint(0, 999_999)
        return f'SYN-{x:06d}'

    def clear(self) -> None:
        pass

    def read_and_clear(self) -> str:
        return self.read()

class FridgeLike:
    def action(self, action: str, arg: str | None = None) -> None:
        pass

    def put(self, loc: str):
        return self.action('put', loc)

    def get(self, loc: str):
        return self.action('get', loc)

@dataclass(frozen=True)
class Fridge(FridgeLike):
    url: str
    def action(self, action: str, arg: str | None = None):
        if arg:
            res = curl(f'{self.url}/{action}/{arg}')
        else:
            res = curl(f'{self.url}/{action}')
        assert res['success']

@dataclass(frozen=True)
class BarcodeReader(BarcodeReaderLike):
    url: str
    def send(self, action: str) -> str:
        res = curl(f'{self.url}/{action}')
        assert res['success']
        if 'value' in res:
            barcode: str = res['value']['barcode']
            return barcode
        else:
            return ''

    def read(self):
        return self.send('read')

    def clear(self):
        self.send('clear')
        return

    def read_and_clear(self):
        return self.send('read_and_clear')

@dataclass(frozen=True)
class Env:
    db: DB
    imx: IMXLike
    fridge: FridgeLike
    barcode_reader: BarcodeReaderLike
    pf_url: str | None
    is_sim: bool

    @contextmanager
    def get_robotarm(self) -> Iterator[RobotarmLike]:
        if self.pf_url:
            host, _, port = self.pf_url.partition(':')
            arm = Robotarm.init(host, int(port))
            yield arm
            arm.close()
            time.sleep(0.25)
        else:
            yield RobotarmSim()

    @staticmethod
    @contextmanager
    def real():
        with DB.open('imager.db') as db:
            yield Env(
                db             = db,
                imx            = IMX(          'http://10.10.0.97:5050/imx'),
                fridge         = Fridge(       'http://10.10.0.97:5050/fridge'),
                barcode_reader = BarcodeReader('http://10.10.0.97:5050/barcode'),
                pf_url         =                      '10.10.0.98:10100',
                is_sim = False,
            )

    @staticmethod
    @contextmanager
    def sim():
        with DB.open('imager-sim.db') as db:
            yield Env(
                db             = db,
                imx            = IMXLike(),
                fridge         = FridgeLike(),
                barcode_reader = BarcodeReaderLike(),
                pf_url         = None,
                is_sim = True,
            )

    @staticmethod
    @contextmanager
    def make(sim: bool):
        with (Env.sim() if sim else Env.real()) as env:
            yield env
