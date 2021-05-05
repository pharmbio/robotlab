from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta
from contextlib import *

from utils import show

from scriptgenerator import *

import time
from urllib.request import urlopen
import json

import abc
import socket
import re

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
    disp_url = os.environ.get('DISP_URL'),
    wash_url = os.environ.get('WASH_URL'),
    incu_url = os.environ.get('INCU_URL'),
)

@dataclass(frozen=True)
class Config:
    robotarm_mode: Literal['dry run' | 'no gripper' | 'gripper']
    disp_mode: Literal['dry run' | 'simulate' | 'execute']
    wash_mode: Literal['dry run' | 'simulate' | 'execute']
    incu_mode: Literal['dry run' | 'fail if used' | 'execute']
    time_mode: Literal['dry run' | 'execute']
    timers: dict[str, datetime] = field(default_factory=dict) # something something
    def name(self) -> str:
        for k, v in configs.items():
            if v is self:
                return k
        return 'unknown_config'

configs: dict[str, Config] = dict(
    dry_run = Config(
        robotarm_mode='dry run',
        disp_mode='dry run',
        wash_mode='dry run',
        incu_mode='dry run',
        time_mode='dry run',
    ),
    live_robotarm_only_no_gripper = Config(
        robotarm_mode='no gripper',
        disp_mode='dry run',
        wash_mode='dry run',
        incu_mode='dry run',
        time_mode='dry run',
    ),
    live_robotarm_only_one_plate = Config(
        robotarm_mode='gripper',
        disp_mode='dry run',
        wash_mode='dry run',
        incu_mode='dry run',
        time_mode='dry run',
    ),
    live_robotarm_only = Config(
        robotarm_mode='gripper',
        disp_mode='dry run',
        wash_mode='dry run',
        incu_mode='fail if used',
        time_mode='dry run',
    ),
    live_robotarm_and_incu_only = Config(
        robotarm_mode='gripper',
        disp_mode='dry run',
        wash_mode='dry run',
        incu_mode='execute',
        time_mode='dry run',
    ),
    live_robotarm_sim_disp_wash = Config(
        robotarm_mode='gripper',
        disp_mode='simulate',
        wash_mode='simulate',
        incu_mode='execute',
        time_mode='execute',
    ),
    live_execute_all = Config(
        robotarm_mode='gripper',
        disp_mode='execute',
        wash_mode='execute',
        incu_mode='execute',
        time_mode='execute',
    )
)

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
        if config.time_mode == 'execute':
            remain = config.timers[self.timer_id] - datetime.now()
            remain_s = remain.total_seconds()
            if remain_s > 0:
                print('Idle for', remain_s, 'seconds...')
                time.sleep(remain_s)
            else:
                print('Behind time:', -remain_s, 'seconds!')
        elif config.time_mode == 'dry run':
            remain = config.timers[self.timer_id] - datetime.now()
            remain_s = remain.total_seconds()
            print('Dry run, pretending to sleep for', remain_s, 'seconds.')


class Robotarm:
    s: socket.socket
    def __init__(self, config: Config):
        assert config.robotarm_mode in {'gripper', 'no gripper'}
        print('connecting to robot...', end=' ')
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((ENV.robotarm_host, ENV.robotarm_port))
        print('connected!')

    def send(self, prog_str: str) -> None:
        self.s.sendall(prog_str.encode())

    def recv(self) -> Iterator[bytes]:
        while True:
            data = self.s.recv(4096)
            for m in re.findall(b'[\x20-\x7e]*(?:log|program|exception|error)[\x20-\x7e]*', data, re.IGNORECASE):
                # RuntimeExceptionMessage, looks like:
                # b'syntax_error_on_line:4:    movej([0.5, -1, -2, 0, 0, -0], a=0.25, v=1.0):'
                # b'compile_error_name_not_found:getactual_joint_positions:'
                # b'SECONDARY_PROGRAM_EXCEPTION_XXXType error: str_sub takes exact'

                # KeyMessage, looks like:
                # PROGRAM_XXX_STARTEDtestmove2910
                # PROGRAM_XXX_STOPPEDtestmove2910
                m = m.decode()
                print(f'{m = }')
            yield data

    def recv_until(self, needle: str) -> None:
        for data in self.recv():
            if needle.encode() in data:
                print(f'received {needle}')
                return

    def close(self) -> None:
        self.s.close()

@dataclass(frozen=True)
class robotarm_cmd(Command):
    program_name: str
    prep: bool = False

    def is_prep(self) -> bool:
        return self.prep

    def time_estimate(self) -> float:
        return 5.0

    def execute(self, config: Config) -> None:
        program_name = self.program_name
        program = generate_robot_send(program_name)
        if config.robotarm_mode == 'dry run':
            # print('dry run', self)
            return
        assert config.robotarm_mode in {'gripper', 'no gripper'}
        robot = Robotarm(config)
        robot.send(program)
        robot.recv_until('log: done ' + program_name)
        robot.close()

@dataclass(frozen=True)
class wash_cmd(Command):
    protocol_path: str

    def execute(self, config: Config) -> None:
        if config.wash_mode == 'dry run':
            # print('dry run', self)
            return
        elif config.wash_mode == 'simulate':
            url = ENV.wash_url + 'simulate_protocol/' + str(int(self.est))
        elif config.wash_mode == 'execute':
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
        if config.disp_mode == 'dry run':
            # print('dry run', self)
            return
        elif config.disp_mode == 'simulate':
            url = ENV.disp_url + 'simulate_protocol/' + str(int(self.est))
        elif config.disp_mode == 'execute':
            url = ENV.disp_url + 'execute_protocol/' + self.protocol_path
        else:
            raise ValueError
        res = curl(url)
        assert res['status'] == 'OK', f'status not OK: {res = }'

    est: float
    def time_estimate(self) -> float:
        return self.est

@dataclass(frozen=True)
class incu_cmd(Command):
    action: Literal['put' | 'get']
    incu_loc: str
    est: float
    busywait: bool = True
    def execute(self, config: Config) -> None:
        assert self.action in 'put get'.split()
        if config.incu_mode == 'dry run':
            # print('dry run', self)
            return
        elif config.incu_mode == 'fail if used':
            raise RuntimeError
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
    res = curl(getattr(ENV, machine + '_url'))
    assert res['status'] == 'OK', f'status not OK: {res = }'
    return res['value'] is True

@dataclass(frozen=True)
class wait_for_ready_cmd(Command):
    machine: Literal['disp', 'wash', 'incu']
    def execute(self, config: Config) -> None:
        mode = getattr(config, self.machine + '_mode')
        if mode == 'execute':
            while not is_ready(self.machine, config):
                time.sleep(0.1)
        elif mode == 'dry run':
            print('Dry run, pretending', self.machine, 'is ready')
        else:
            raise ValueError(f'bad mode: {mode}')

    def time_estimate(self) -> float:
        return 0


