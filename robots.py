from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta
from contextlib import *

from utils import show

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
    robotarm_host = 'localhost',
    robotarm_port = 30001,
    disp_url = 'http://dispenser.lab.pharmb.io:5001/',
    wash_url = 'http://washer.lab.pharmb.io:5000/',
    incu_url = 'TODO',
)

@dataclass(frozen=True)
class Config:
    robotarm_mode: Literal['dry run' | 'no gripper' | 'gripper']
    disp_mode: Literal['dry run' | 'simulate' | 'execute']
    wash_mode: Literal['dry run' | 'simulate' | 'execute']
    incu_mode: Literal['dry run' | 'fail if used' | 'execute']
    simulate_time: bool

dry_run = Config(
    robotarm_mode='dry run',
    disp_mode='dry run',
    wash_mode='dry run',
    incu_mode='dry run',
    simulate_time=True,
)

live_robotarm_only_no_gripper = Config(
    robotarm_mode='no gripper',
    disp_mode='dry run',
    wash_mode='dry run',
    incu_mode='dry run',
    simulate_time=True,
)

live_robotarm_only = Config(
    robotarm_mode='gripper',
    disp_mode='dry run',
    wash_mode='dry run',
    incu_mode='fail if used',
    simulate_time=True,
)

live_robotarm_only_sim_disp_wash = Config(
    robotarm_mode='gripper',
    disp_mode='simulate',
    wash_mode='simulate',
    incu_mode='fail if used',
    simulate_time=False,
)

live_robotarm_and_incu_only = Config(
    robotarm_mode='gripper',
    disp_mode='simulate',
    wash_mode='simulate',
    incu_mode='execute',
    simulate_time=False,
)

live_execute_all = Config(
    robotarm_mode='gripper',
    disp_mode='execute',
    wash_mode='execute',
    incu_mode='execute',
    simulate_time=False,
)

class Command(abc.ABC):
    @abc.abstractmethod
    def execute(self, config: Config) -> None:
        pass

@dataclass(frozen=True)
class robotarm_cmd(Command):
    prog_path: str
    def execute(self, config: Config) -> None:
        prog_path = self.prog_path
        if config.robotarm_mode == 'dry run':
            # print('dry run', self)
            return
        if config.robotarm_mode == 'no gripper':
            prog_path = prog_path.replace('generated', 'generated_nogripper')
        prog_str = open(prog_path, 'rb').read()
        prog_name = prog_path.split('/')[-1]
        needle = f'Program {prog_name} completed'.encode()
        assert needle in prog_str
        assert config.robotarm_mode in {'gripper', 'no gripper'}
        print('connecting to robot...', end=' ')
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ENV.robotarm_host, ENV.robotarm_port))
        print('connected!')
        s.sendall(prog_str)
        while True:
            data = s.recv(4096)
            # RuntimeExceptionMessage, looks like:
            # b'syntax_error_on_line:4:    movej([0.5, -1, -2, 0, 0, -0], a=0.25, v=1.0):'
            # b'compile_error_name_not_found:getactual_joint_positions:'
            # b'SECONDARY_PROGRAM_EXCEPTION_XXXType error: str_sub takes exact'
            for m in re.findall(b'([\x20-\x7e]*(?:error|EXCEPTION)[\x20-\x7e]*)', data):
                m = m.decode()
                print(f'{m = }')

            # KeyMessage, looks like:
            # PROGRAM_XXX_STARTEDtestmove2910
            # PROGRAM_XXX_STOPPEDtestmove2910
            for m in re.findall(b'PROGRAM_XXX_(\w*)', data):
                m = m.decode()
                print(f'{m = }')

            if needle in data:
                print(f'program {prog_name} completed!')
                break
        s.close()

@dataclass(frozen=True)
class wash_cmd(Command):
    protocol_path: str
    def execute(self, config: Config) -> None:
        if config.wash_mode == 'dry run':
            # print('dry run', self)
            return
        elif config.wash_mode == 'simulate':
            url = ENV.wash_url + 'simulate_protocol/' + self.protocol_path
        elif config.wash_mode == 'execute':
            url = ENV.wash_url + 'execute_protocol/' + self.protocol_path
        else:
            raise ValueError
        res = curl(url)
        assert res['status'] == 'OK', f'status not OK: {res = }'

@dataclass(frozen=True)
class disp_cmd(Command):
    protocol_path: str
    def execute(self, config: Config) -> None:
        if config.disp_mode == 'dry run':
            # print('dry run', self)
            return
        elif config.disp_mode == 'simulate':
            url = ENV.disp_url + 'simulate_protocol/' + self.protocol_path
        elif config.disp_mode == 'execute':
            url = ENV.disp_url + 'execute_protocol/' + self.protocol_path
        else:
            raise ValueError
        res = curl(url)
        assert res['status'] == 'OK', f'status not OK: {res = }'

@dataclass(frozen=True)
class incu_cmd(Command):
    action: Literal['put' | 'get']
    incu_loc: str
    def execute(self, config: Config) -> None:
        assert self.action in 'put get'.split()
        busywait: bool = self.action == 'get'

        if config.incu_mode == 'dry run':
            # print('dry run', self)
            return
        elif config.incu_mode == 'fail if used':
            raise RuntimeError
        elif config.incu_mode == 'execute':
            url = ENV.incu_url + self.action + '/' + self.incu_loc
            res = curl(url)
            assert res['status'] == 'OK', f'status not OK: {res = }'
            if busywait:
                while not is_ready('incu', config):
                    time.sleep(0.1)
        else:
            raise ValueError

def curl(url: str) -> Any:
    return json.loads(urlopen(url).read())

def is_ready(machine: Literal['disp', 'wash', 'incu'], config: Config) -> Any:
    res = curl(getattr(ENV, machine + '_url'))
    assert res['status'] == 'OK', f'status not OK: {res = }'
    return res['value'] is True

def robotarm_execute(path: str) -> None:
    robotarm_cmd(path).execute(
        config=dry_run
        # config=live_robotarm_only_no_gripper
        # config=live_robotarm_only
    )

if 0:
    from glob import glob
    for path in glob('./generated/*'):
        robotarm_execute(path)

def execute_scripts(s: str) -> None:
    for path in s.strip().split('\n'):
        robotarm_execute(path.strip())

if 0:
    execute_scripts('''
        ./generated/r1_put
        ./generated/r1_get

        ./generated/r11_put
        ./generated/r11_get

        ./generated/r15_put
        ./generated/r15_get
    ''')

if 0:
    execute_scripts('''
        ./generated/lid_h19_put

        ./generated/incu_put
        ./generated/incu_get

        ./generated/disp_put
        ./generated/disp_get

        ./generated/wash_put
        ./generated/wash_get

        ./generated/r19_put
        ./generated/r19_get

        ./generated/h17_put
        ./generated/h17_get

        ./generated/lid_h19_get
    ''')

if 0:
    execute_scripts('''
        ./generated/h19_put
        ./generated/r21_put
        ./generated/r19_put
        ./generated/r21_get
        ./generated/r19_get
        ./generated/out18_put
        ./generated/wash_get
    ''')

