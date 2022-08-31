from __future__ import annotations
from typing import Literal, Any, cast, ClassVar, TypeAlias, Union, Iterator
from dataclasses import dataclass, field
from contextlib import contextmanager
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen
import dataclasses
import abc
import json
import re
import time
import sqlite3
import traceback as tb
from . import utils

from .robotarm import Robotarm
from .moves import movelists

def curl(url: str, data: None | bytes = None) -> dict[str, Any]:
    ten_minutes = 60 * 10
    res: dict[str, Any] = json.loads(urlopen(url, data=data, timeout=ten_minutes).read())
    assert isinstance(res, dict)
    if not res.get('success'):
        utils.pr(res)
    return res

def post(url: str, data: dict[str, str]) -> dict[str, Any]:
    return curl(url, urlencode(data).encode())

@dataclass(frozen=True)
class IMXStatus:
    code: str
    details: str

from typing import Protocol, Callable

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
        return post(self.url, {'msg': msg})

    def open(self, sync: bool=True):
        if not sync:
            _res = self.send('GOTO,LOAD')
        else:
            _res = self.send('GOTO,LOAD')
            while True:
                time.sleep(0.5)
                if self.status() == IMXStatus('READY', 'LOAD'):
                    break

    def close(self):
        _res = self.send('GOTO,SAMPLE')
        while True:
            time.sleep(0.5)
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
        return ret

    def is_ready(self):
        return self.status().code in ('READY', 'DONE')

    def acquire(self, *, plate_id: str, hts_file: str):
        plate_id = ''.join(
            char if re.match(r'^[\w\d_ ]$', char) else '-'
            for char in plate_id
        )
        _res = self.send(f'RUN,{plate_id},{hts_file}')
        while self.status().code not in ('RUNNING', 'DONE'):
            time.sleep(0.5)
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
        with sqlite3.connect('imager.db') as con:
            yield Env(
                db             = DB(con),
                imx            = IMX(          'http://10.10.0.97:5050/imx'),
                fridge         = Fridge(       'http://10.10.0.97:5050/fridge'),
                barcode_reader = BarcodeReader('http://10.10.0.97:5050/barcode'),
                pf_url         =                      '10.10.0.98:10100',
                is_sim = False,
            )

    @staticmethod
    @contextmanager
    def sim():
        with sqlite3.connect('imager-sim.db') as con:
            yield Env(
                db             = DB(con),
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

@dataclass(frozen=True)
class RobotarmCmd:
    '''
    Run a program on the robotarm.
    '''
    program_name: str
    keep_imx_open: bool = False

    def __post_init__(self):
        assert self.program_name in movelists, self.program_name

@dataclass(frozen=True)
class Noop:
    '''
    Do nothing.
    '''
    pass

@dataclass(frozen=True)
class Acquire:
    '''
    Acquires the plate on the IMX (closing it first if necessary).
    '''
    hts_file: str
    plate_id: str

@dataclass(frozen=True)
class Open:
    '''
    Open the IMX.
    '''
    pass

@dataclass(frozen=True)
class Close:
    '''
    Closes the IMX.
    '''
    pass

@dataclass(frozen=True)
class WaitForIMX:
    '''
    Wait for IMX to finish imaging
    '''
    pass

@dataclass(frozen=True)
class FridgeGet:
    loc: str
    check_barcode: bool = False

@dataclass(frozen=True)
class FridgePut:
    loc: str
    barcode: str

@dataclass(frozen=True)
class FridgePutByBarcode:
    '''
    Puts the plate on some empty location using its barcode
    '''
    pass

@dataclass(frozen=True)
class FridgeGetByBarcode:
    barcode: str

@dataclass(frozen=True)
class FridgeAction:
    action: Literal['get_status', 'reset_and_activate']

@dataclass(frozen=True)
class BarcodeClear:
    '''
    Clears the last seen barcode from the barcode reader memory
    '''
    pass

@dataclass(frozen=True)
class CheckpointCmd:
    name: str

@dataclass(frozen=True)
class WaitForCheckpoint:
    name: str
    plus_secs: timedelta | float | int = 0

    @property
    def plus_timedelta(self) -> timedelta:
        if isinstance(self.plus_secs, timedelta):
            return self.plus_secs
        else:
            return timedelta(seconds=self.plus_secs)

Command: TypeAlias = Union[
    Noop,
    RobotarmCmd,
    Acquire,
    Open,
    Close,
    WaitForIMX,
    FridgeGet,
    FridgePut,
    FridgePutByBarcode,
    FridgeGetByBarcode,
    FridgeAction,
    BarcodeClear,
    CheckpointCmd,
    WaitForCheckpoint,
]

# scheduler

from .utils.mixins import DBMixin, DB, Meta

@dataclass(frozen=True)
class FridgeSlot(DBMixin):
    loc: str = ""
    occupant: None | str = None
    id: int = -1
    __meta__: ClassVar = Meta(log=True)

@dataclass(frozen=True)
class Checkpoint(DBMixin):
    name: str = ""
    t: datetime = field(default_factory=datetime.now)
    id: int = -1

@dataclass(frozen=True)
class QueueItem(DBMixin):
    cmd: Command = field(default_factory=Noop)
    started: datetime | None = None
    finished: datetime | None = None
    error: str | None = None
    pos: int = -1
    id: int = -1
    __meta__: ClassVar = Meta(log=True)

utils.serializer.register(globals())

FRIDGE_LOCS = [
    f'{slot+1}x{level+1}'
    for slot in range(1)
    for level in range(17)
]

def initial_fridge(db: DB):
    FridgeSlots = db.get(FridgeSlot)
    for loc in FRIDGE_LOCS:
        if not FridgeSlots.where(loc=loc):
            FridgeSlot(loc).save(db)

def enqueue(env: Env, cmds: list[Command]):
    initial_fridge(env.db)
    last_pos = max((q.pos for q in env.db.get(QueueItem)), default=0)
    for pos, cmd in enumerate(cmds, start=last_pos + 1):
        QueueItem(cmd=cmd, pos=pos).save(env.db)

def execute(env: Env):
    while True:
        todo = env.db.get(QueueItem).order(by='pos').limit(1).where(finished=None)
        if not todo:
            print('nothing to do')
            return
        else:
            item = todo[0]
            print('item:', item)
            if item.started and item.error:
                print('the top of the queue has errored')
                return
            if item.started and not item.finished:
                print('the top of the queue is already running')
                return
            item = item.replace(started=datetime.now()).save(env.db)
            try:
                execute_one(item.cmd, env)
            except:
                item = item.replace(error=tb.format_exc()).save(env.db)
            else:
                item = item.replace(finished=datetime.now()).save(env.db)
            print('item:', item)

def execute_one(cmd: Command, env: Env) -> None:
    FridgeSlots = env.db.get(FridgeSlot)
    Checkpoints = env.db.get(Checkpoint)
    utils.pr(cmd)
    match cmd:
        case RobotarmCmd():
            with env.get_robotarm() as arm:
                before_each = None
                if cmd.keep_imx_open:
                    before_each = lambda: (env.imx.open(sync=False) , None)[-1]
                arm.execute_movelist(cmd.program_name, before_each=before_each)

        case Acquire():
            env.imx.acquire(plate_id=cmd.plate_id, hts_file=cmd.hts_file)
        case Open():
            env.imx.open(sync=True)
        case Close():
            env.imx.close()
        case WaitForIMX():
            while not env.imx.is_ready():
                time.sleep(1)

        case FridgePutByBarcode():
            barcode = env.barcode_reader.read_and_clear()
            assert barcode
            slot, *_ = FridgeSlots.where(occupant=None)
            return execute_one(FridgePut(slot.loc, barcode), env)

        case FridgeGetByBarcode():
            [slot] = FridgeSlots.where(occupant=cmd.barcode)
            return execute_one(FridgeGet(slot.loc, check_barcode=True), env)

        case FridgePut():
            [slot] = FridgeSlots.where(loc=cmd.loc)
            assert slot.occupant is None
            env.fridge.put(cmd.loc)
            slot.replace(occupant=cmd.barcode).save(env.db)

        case FridgeGet():
            [slot] = FridgeSlots.where(loc=cmd.loc)
            assert slot.occupant is not None
            env.fridge.get(cmd.loc)
            if cmd.check_barcode and not env.is_sim:
                # check that the popped plate has the desired barcode
                barcode = env.barcode_reader.read_and_clear()
                assert slot.occupant == barcode
            slot.replace(occupant=None).save(env.db)

        case FridgeAction():
            env.fridge.action(cmd.action)

        case BarcodeClear():
            env.barcode_reader.clear()

        case CheckpointCmd():
            for dup in Checkpoints.where(name=cmd.name):
                dup.delete(env.db)
            Checkpoint(name=cmd.name).save(env.db)
        case WaitForCheckpoint():
            [checkpoint] = Checkpoints.where(name=cmd.name)
            while datetime.now() < checkpoint.t + cmd.plus_timedelta:
                time.sleep(1)

        case Noop():
            pass

