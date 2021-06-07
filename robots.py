from __future__ import annotations
from dataclasses import *
from typing import *

from datetime import datetime, timedelta
from urllib.request import urlopen

import abc
import json
import os
import re
import socket
import time

from moves import movelists
from robotarm import Robotarm
import utils

@dataclass(frozen=True)
class Env:
    robotarm_host: str
    robotarm_port: int

    disp_url: str
    wash_url: str
    incu_url: str

ENV = Env(
    # Use start-proxies.sh to forward robot to localhost
    robotarm_host = os.environ.get('ROBOT_IP', 'localhost'),
    robotarm_port = 30001,
    disp_url = os.environ.get('DISP_URL', '?'),
    wash_url = os.environ.get('WASH_URL', '?'),
    incu_url = os.environ.get('INCU_URL', '?'),
)

@dataclass(frozen=True)
class Config:
    time_mode:          Literal['noop', 'wall', 'fast forward',          ]
    disp_and_wash_mode: Literal['noop', 'execute', 'execute short',      ]
    incu_mode:          Literal['noop', 'execute',                       ]
    robotarm_mode:      Literal['noop', 'execute', 'execute no gripper', ]
    timers: dict[str, datetime] = field(default_factory=dict)
    def name(self) -> str:
        for k, v in configs.items():
            if v is self:
                return k
        raise ValueError(f'unknown config {self}')


configs: dict[str, Config]
configs = {
    'live':          Config('wall',         'execute',       'execute', 'execute'),
    'test-all':      Config('fast forward', 'execute short', 'execute', 'execute'),
    'test-arm-incu': Config('fast forward', 'noop',          'execute', 'execute'),
    'simulator':     Config('fast forward', 'noop',          'noop',    'execute no gripper'),
    'dry-run':       Config('noop',         'noop',          'noop',    'noop'),
}

class Command(abc.ABC):
    @abc.abstractmethod
    def execute(self, config: Config) -> None:
        pass

    @abc.abstractmethod
    def time_estimate(self) -> float:
        pass

    def is_prep(self) -> bool:
        return False

@dataclass(frozen=True)
class timer_cmd(Command):
    minutes: float
    timer_id: str # one timer per plate

    def time_estimate(self) -> float:
        return self.minutes * 60.0

    def execute(self, config: Config) -> None:
        config.timers[self.timer_id] = datetime.now() + timedelta(minutes=self.minutes)

@dataclass(frozen=True)
class wait_for_timer_cmd(Command):
    timer_id: str # one timer per plate

    def time_estimate(self) -> float:
        return 0

    def execute(self, config: Config) -> None:
        if config.time_mode == 'wall' or config.time_mode == 'fast forward':
            remain = config.timers[self.timer_id] - datetime.now()
            remain_s = remain.total_seconds()
            if remain_s > 0:
                if config.time_mode == 'fast forward':
                    remain_s /= 1000
                print('Idle for', remain_s, 'seconds...')
                time.sleep(remain_s)
            else:
                print('Behind time:', -remain_s, 'seconds!')
        elif config.time_mode == 'noop':
            remain = config.timers[self.timer_id] - datetime.now()
            remain_s = remain.total_seconds()
            print('Dry run, pretending to sleep for', remain_s, 'seconds.')
        else:
            raise ValueError

def get_robotarm(config: Config, quiet: bool = False) -> Robotarm:
    if config.robotarm_mode == 'noop':
        return Robotarm.init_simulate(with_gripper=True, quiet=quiet)
    assert config.robotarm_mode == 'execute' or config.robotarm_mode == 'execute no gripper'
    with_gripper = config.robotarm_mode == 'execute'
    return Robotarm.init(ENV.robotarm_host, ENV.robotarm_port, with_gripper, quiet=quiet)

@dataclass(frozen=True)
class robotarm_cmd(Command):
    program_name: str
    prep: bool = False

    def is_prep(self) -> bool:
        return self.prep

    def time_estimate(self) -> float:
        return 5.0

    def execute(self, config: Config) -> None:
        arm = get_robotarm(config)
        arm.execute_moves(movelists[self.program_name], name=self.program_name)
        arm.close()

@dataclass(frozen=True)
class wash_cmd(Command):
    protocol_path: str

    def execute(self, config: Config) -> None:
        if config.disp_and_wash_mode == 'noop':
            # print('dry run', self)
            return
        elif config.disp_and_wash_mode == 'execute short':
            shorter = 'automation/2_4_6_W-3X_FinalAspirate_test.LHC'
            url = ENV.wash_url + 'execute_protocol/' + shorter
        elif config.disp_and_wash_mode == 'execute':
            url = ENV.wash_url + 'execute_protocol/' + self.protocol_path
        else:
            raise ValueError
        res = curl(url)
        assert res['status'] == 'OK', f'status not OK: {res = }'

    est: float
    def time_estimate(self) -> float:
        return self.est

@dataclass(frozen=True)
class disp_cmd(Command):
    protocol_path: str
    def execute(self, config: Config) -> None:
        if config.disp_and_wash_mode == 'noop':
            # print('dry run', self)
            return
        elif config.disp_and_wash_mode == 'execute' or config.disp_and_wash_mode == 'execute short':
            url = ENV.disp_url + 'execute_protocol/' + self.protocol_path
        else:
            raise ValueError
        res = curl(url)
        assert res['status'] == 'OK', f'status not OK: {res = }'

    est: float = 15
    def time_estimate(self) -> float:
        return self.est

@dataclass(frozen=True)
class incu_cmd(Command):
    action: Literal['put', 'get']
    incu_loc: str
    est: float
    def execute(self, config: Config) -> None:
        assert self.action in 'put get'.split()
        if config.incu_mode == 'noop':
            # print('dry run', self)
            return
        elif config.incu_mode == 'execute':
            if self.action == 'put':
                action_path = 'input_plate'
            elif self.action == 'get':
                action_path = 'output_plate'
            else:
                raise ValueError
            url = ENV.incu_url + action_path + '/' + self.incu_loc
            res = curl(url)
            assert res['status'] == 'OK', f'status not OK: {res = }'
        else:
            raise ValueError

    def time_estimate(self) -> float:
        return self.est

def curl(url: str) -> Any:
    return json.loads(urlopen(url).read())

def is_ready(machine: Literal['disp', 'wash', 'incu'], config: Config) -> Any:
    res = curl(getattr(ENV, machine + '_url') + 'is_ready')
    assert res['status'] == 'OK', f'status not OK: {res = }'
    return res['value'] is True

@dataclass(frozen=True)
class wait_for_ready_cmd(Command):
    machine: Literal['disp', 'wash', 'incu']
    def execute(self, config: Config) -> None:
        if self.machine == 'incu':
            mode = config.incu_mode
        else:
            mode = config.disp_and_wash_mode
        if mode == 'execute' or mode == 'execute short':
            while not is_ready(self.machine, config):
                time.sleep(0.1)
        elif mode == 'noop':
            print('Dry run, pretending', self.machine, 'is ready')
        else:
            raise ValueError(f'bad mode: {mode}')

    def time_estimate(self) -> float:
        return 0

@dataclass(frozen=True)
class par(Command):
    subs: list[wash_cmd | disp_cmd | incu_cmd | robotarm_cmd]

    def __post_init__(self):
        for cmd, next in utils.iterate_with_next(self.subs):
            if isinstance(cmd, robotarm_cmd):
                assert next is None, 'put the nonblocking commands first, then the robotarm last'

    def sub_cmds(self) -> tuple[Command, ...]:
        return tuple(self.subs)

    def time_estimate(self) -> float:
        return max(sub.time_estimate() for sub in self.sub_cmds())

    def execute(self, config: Config) -> None:
        for sub in self.sub_cmds():
            sub.execute(config)
