from __future__ import annotations
from typing import Literal, Any, cast
from dataclasses import dataclass
import abc

import time

import json
from urllib.request import urlopen

from datetime import datetime, timedelta

def curl(url: str) -> dict[str, Any]:
    ten_minutes = 60 * 10
    res = json.loads(urlopen(url, timeout=ten_minutes).read())
    assert isinstance(res, dict)
    return cast(dict[str, Any], res)

Resource = Literal['pf', 'imx']

@dataclass(frozen=True)
class Env:
    imx_url: str = 'localhost:1234'
    pf_url: str  = 'localhost:1235'

    def url_for(self, resource: Resource):
        match resource:
            case 'pf':
                return self.pf_url
            case 'imx':
                return self.imx_url


class Command(abc.ABC):
    def required_resource(self) -> Resource | None:
        return None

def wait_for(resource: Resource, env: Env):
    while True:
        res = curl(env.url_for(resource) + '/status')
        if res.get('value') != 'ready':
            time.sleep(1)

@dataclass(frozen=True)
class RobotarmCmd(Command):
    '''
    Run a program on the robotarm.
    '''
    program_name: str

    def required_resource(self):
        return 'pf'

@dataclass(frozen=True)
class Acquire(Command):
    '''
    Closes the IMX and acquires the plate.
    '''
    hts_file: str
    plate_id: str | None = None

    def required_resource(self):
        return 'imx'

@dataclass(frozen=True)
class Open(Command):
    '''
    Open the IMX.
    '''
    def required_resource(self):
        return 'imx'

@dataclass(frozen=True)
class Close(Command):
    '''
    Closes the IMX.
    '''
    def required_resource(self):
        return 'imx'

@dataclass(frozen=True)
class WaitUntil(Command):
    '''
    Wait until a given time has passed.
    '''
    timestamp: datetime

    def __repr__(self):
        return f'WaitUntil({self.timestamp.isoformat()!r})'

def execute(cmd: Command, env: Env):
    if resource := cmd.required_resource():
        wait_for(resource, env)
    match cmd:
        case Command():
            raise ValueError(cmd)

q: list[Command] = []
for i, _ in enumerate(range(3), start=1):
    h = f'h{i}'
    q += [
        WaitUntil(datetime.now() + timedelta(minutes=3*i)),
        Open(),
        RobotarmCmd(f'{h} to imx'),
        Acquire('test.hts', 'plate{i}'),
        Open(),
        RobotarmCmd(f'imx to {h}'),
        Close(),
    ]

from pprint import pprint
pprint(q)
