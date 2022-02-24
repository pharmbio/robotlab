from __future__ import annotations
from typing import Literal, Any, cast
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
from . import utils

from .robotarm import Robotarm

FRIDGE_LOCS = [f'L{i+1}' for i in range(18)]
EMPTY_FRIDGE: dict[str, str | None] = {loc: None for loc in FRIDGE_LOCS}

def curl(url: str, data: None | bytes = None) -> dict[str, Any]:
    ten_minutes = 60 * 10
    res = json.loads(urlopen(url, data=data, timeout=ten_minutes).read())
    assert isinstance(res, dict)
    return cast(dict[str, Any], res)

def post(url: str, data: dict[str, str]) -> dict[str, Any]:
    return curl(url, urlencode(data).encode())

def is_valid_plate_id(plate_id: str) -> bool:
    return bool(re.match(r'^[\w\d-_ ]+$', plate_id))

@dataclass(frozen=True)
class IMX:
    url: str
    def send(self, msg: str):
        return post(self.url, {'msg': msg})

    def open(self):
        return self.send('GOTO,LOAD')

    def close(self):
        return self.send('GOTO,SAMPLE')
        # does this work if there is no plate in?
        # otherwise use RUNJOURNAL on the close.JNL

    def online(self):
        return self.send('ONLINE')

    def status(self) -> str:
        res = self.send('STATUS')
        reply: str = res['value']
        _imx_id, status_code, *details = reply.split(',')
        print(f'imx {status_code=} {details=}')
        return status_code

    def is_running(self):
        return self.status() == 'RUNNING'

    def acquire(self, *, plate_id: str, hts_file: str):
        assert is_valid_plate_id(plate_id)
        return self.send(f'RUN,{plate_id},{hts_file}')

@dataclass(frozen=True)
class BarcodeReader:
    url: str
    def send(self, action: str) -> str:
        res = curl(f'{self.url}/{action}')
        assert res['success']
        if 'value' in res:
            barcode: str = res['value']['barcode']
            return barcode
        else:
            return ''

    def read(self):           return self.send('read')
    def clear(self):          return self.send('clear')
    def read_and_clear(self): return self.send('read_and_clear')

@dataclass(frozen=True)
class Env:
    fridge_json: str = 'fridge.json'
    imx_url: str     = '10.10.0.97:5050/imx'
    fridge_url: str  = '10.10.0.97:5050/fridge'
    barcode_url: str = '10.10.0.97:5050/barcode'
    pf_url: str      = '10.10.0.98:10100'

    @contextmanager
    def get_robotarm(self):
        host, _, port = self.pf_url.partition(':')
        arm = Robotarm.init(host, int(port))
        yield arm
        arm.close()

    @property
    def imx(self):
        return IMX(self.imx_url)

    @property
    def barcode_reader(self):
        return BarcodeReader(self.imx_url)

@dataclass(frozen=True)
class Runtime:
    checkpoints: dict[str, datetime] = field(default_factory=dict)

    # (Fridge location) -> (Plate barcode or empty)
    fridge: dict[str, str | None] = field(default_factory=lambda: EMPTY_FRIDGE)

    def get_empty_loc(self):
        empty_locs = [loc for loc, plate_barcode in self.fridge.items() if plate_barcode is None]
        return empty_locs.pop()

    def get_by_barcode(self, barcode: str):
        [loc] = [loc for loc, plate_barcode in self.fridge.items() if plate_barcode == barcode]
        return loc

class Command(abc.ABC):
    pass

@dataclass(frozen=True)
class RobotarmCmd(Command):
    '''
    Run a program on the robotarm.
    '''
    program_name: str
    keep_imx_open: bool = False

@dataclass(frozen=True)
class Acquire(Command):
    '''
    Acquires the plate on the IMX (closing it first if necessary).
    '''
    hts_file: str
    plate_id: str

@dataclass(frozen=True)
class Open(Command):
    '''
    Open the IMX.
    '''
    pass

@dataclass(frozen=True)
class Noop(Command):
    '''
    Do nothing.
    '''
    pass

@dataclass(frozen=True)
class Close(Command):
    '''
    Closes the IMX.
    '''
    pass

@dataclass(frozen=True)
class WaitForIMX(Command):
    '''
    Wait for IMX to finish imaging
    '''
    pass

@dataclass(frozen=True)
class FridgeCmd(Command):
    '''
    Eject plates from or insert plates into the fridge

    get: gets the plate in loc `loc`
    put: puts the plate in loc `loc`
    get_by_barcode: gets the plate with barcode `barcode`
    put_by_barcode: reads the barcode reader and puts the plate in an empty location and remembers it
    '''
    action: Literal[
        'get',
        'put',
        'put_by_barcode',
        'get_by_barcode',
        'get_status',
        'reset_and_activate'
    ]
    _: dataclasses.KW_ONLY
    barcode: str | None = None
    loc: str | None = None

    def __post_init__(self):
        match self.action:
            case 'get' | 'put':
                assert self.loc
                assert not self.barcode
            case 'get_by_barcode':
                assert not self.loc
                assert self.barcode
            case 'put_by_barcode' | 'reset_and_activate' | 'get_status':
                assert not self.barcode
                assert not self.loc

@dataclass(frozen=True)
class BarcodeClear(Command):
    '''
    Clears the last seen barcode from the barcode reader memory
    '''
    pass

@dataclass(frozen=True)
class Checkpoint(Command):
    name: str

@dataclass(frozen=True)
class WaitForCheckpoint(Command):
    name: str
    plus_secs: timedelta | float | int = 0

    @property
    def plus_timedelta(self) -> timedelta:
        if isinstance(self.plus_secs, timedelta):
            return self.plus_secs
        else:
            return timedelta(seconds=self.plus_secs)

@dataclass(frozen=True)
class Queue:
    cmds: list[Command]
    runtime: Runtime

utils.serializer.register(globals())

def execute(cmds: list[Command]):
    env = Env()
    try:
        fridge = utils.serializer.read_json('fridge.json')
    except:
        fridge = EMPTY_FRIDGE
    runtime = Runtime(fridge=fridge)
    execute_many(cmds, env, runtime)

def execute_many(cmds: list[Command], env: Env, runtime: Runtime):
    for i, cmd in enumerate(cmds):
        while True:
            utils.serializer.write_json(Queue(cmds[i:], runtime), 'queue.json', indent=2) # for resuming
            res = execute_one(cmd, env, runtime)
            utils.serializer.write_json(runtime.fridge, 'fridge.json', indent=2)
            if res == 'wait':
                time.sleep(1)
            else:
                break

def execute_one(cmd: Command, env: Env, runtime: Runtime) -> None | Literal['wait']:
    match cmd:
        case RobotarmCmd():
            with env.get_robotarm() as arm:
                before_each = None
                if cmd.keep_imx_open:
                    before_each = lambda: (env.imx.open(), None)[-1]
                arm.execute_movelist(cmd.program_name, before_each=before_each)
        case Acquire():
            env.imx.acquire(plate_id=cmd.plate_id, hts_file=cmd.hts_file)
        case Open():
            env.imx.open()
        case Close():
            env.imx.close()
        case WaitForIMX():
            if env.imx.is_running():
                return 'wait'
        case FridgeCmd():
            # no need to check that the fridge is ready since there is only
            # one thread and all calls wait for completion
            if cmd.action == 'put_by_barcode':
                barcode = env.barcode_reader.read_and_clear()
                assert barcode
                empty_loc = runtime.get_empty_loc()
                runtime.fridge[empty_loc] = barcode
                return execute_one(FridgeCmd('put', loc=empty_loc), env, runtime)
            elif cmd.action == 'get_by_barcode':
                assert cmd.barcode
                loc = runtime.get_by_barcode(cmd.barcode)
                runtime.fridge[loc] = None
                return execute_one(FridgeCmd('get', loc=loc), env, runtime)
                # could check that the popped plate has the desired barcode
            elif cmd.loc:
                res = curl(f'{env.fridge_url}/{cmd.action}/{cmd.loc}')
                assert res['success']
            else:
                res = curl(f'{env.fridge_url}/{cmd.action}')
                assert res['success']
        case BarcodeClear():
            env.barcode_reader.clear()
        case Checkpoint():
            runtime.checkpoints[cmd.name] = datetime.now()
        case WaitForCheckpoint():
            if datetime.now() < runtime.checkpoints[cmd.name] + cmd.plus_timedelta:
                return 'wait'
        case Noop():
            pass
        case _:
            raise ValueError(cmd)

