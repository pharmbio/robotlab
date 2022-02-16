from __future__ import annotations
from typing import Literal, Any, cast
from dataclasses import dataclass, field
from contextlib import contextmanager
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen
import abc
import json
import re
import time

from ..pf.robotarm import Robotarm

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
    def send(self, cmd: str):
        return post(self.url, {'msg': f'1,{cmd}'})

    def open(self):
        return self.send('GOTO,LOAD')

    def close(self):
        return self.send('GOTO,SAMPLE')
        # does this work if there is no plate in?
        # otherwise use RUNJOURNAL on a close JNL

    def online(self):
        return self.send('ONLINE')

    def status(self):
        return self.send('STATUS')

    def is_running(self):
        res = self.status()
        reply = res['reply']
        _imx_id, status_code, *details = reply.split(',')
        print(f'imx {status_code=} {details=}')
        return status_code == 'RUNNING'

    def acquire(self, *, plate_id: str, hts_file: str):
        assert is_valid_plate_id(plate_id)
        return self.send(f'RUN,{plate_id},{hts_file}')

@dataclass(frozen=True)
class Env:
    imx_url: str    = 'localhost:1234'
    pf_url: str     = 'localhost:1235'
    fridge_url: str = 'localhost:1233'

    @contextmanager
    def get_robotarm(self):
        host, _, port = self.pf_url.partition(':')
        arm = Robotarm.init(host, int(port))
        yield arm
        arm.close()

    @property
    def imx(self):
        return IMX(self.imx_url)

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
    Eject or insert plates with the fridge
    '''
    action: Literal['get', 'put']
    loc: str

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
class Plate:
    plate_id: str
    fridge_loc: str
    hotel_loc: str

'''
# this is also a possible way to interleave it, but let's do that later
fridge -> RT
          RT -> imx
fridge -> RT
                imx -> fridge
          RT -> imx
fridge -> RT
                imx -> fridge
          RT -> imx
                imx -> fridge
'''

def load_batch(plates: list[Plate]):
    cmds: list[Command] = []
    for plate in plates:
        cmds += [
            RobotarmCmd('H{hotel_loc} to H1'),
            RobotarmCmd('H1 to fridge'),
            FridgeCmd('put', plate.fridge_loc),
        ]
    return cmds

def image_batch(plates: list[Plate], hts_file: str, thaw_time: timedelta):
    cmds: list[Command] = []
    for plate in plates:
        cmds += [
            FridgeCmd('get', plate.fridge_loc),
            RobotarmCmd('fridge to H1'),
            Checkpoint('RT {plate.plate_id}'),
        ]
        cmds += [
            WaitForCheckpoint('RT {plate.plate_id}', plus_secs=thaw_time),
            Open(), # continuously
            RobotarmCmd('H1 to imx'), # or add imx_keep_open=True here
            Close(),
            Checkpoint('image {plate.plate_id}'),
            Acquire(hts_file=hts_file, plate_id=plate.plate_id),
        ]
        cmds += [
            WaitForIMX(),
            RobotarmCmd('H1 to fridge'),
            FridgeCmd('put', plate.fridge_loc),
        ]
    return cmds

def execute(cmd: Command, env: Env, checkpoints: dict[str, datetime]) -> None | Literal['wait']:
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
            res = curl(f'{env.fridge_url}/{cmd.action}/{cmd.loc}')
            assert res['success']
        case Checkpoint():
            checkpoints[cmd.name] = datetime.now()
        case WaitForCheckpoint():
            if datetime.now() < checkpoints[cmd.name] + cmd.plus_timedelta:
                return 'wait'
        case _:
            raise ValueError(cmd)

'''
the idea is to execute until you get either wait or an exception and store the state after each
"runtime" state is

    (
        checkpoint times,
        remaining command queue,
        error | None
    )
'''

