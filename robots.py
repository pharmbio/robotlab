from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta
from contextlib import *

from utils import show
import snoop # type: ignore
snoop.install(pformat=show)
pp: Any

import time
from urllib.request import urlopen
import json

import abc
import socket
import re

# test-protocols/dispenser_prime_all_buffers.LHC
# test-protocols/washer_prime_buffers_A_B_C_D_25ml.LHC

@dataclass(frozen=True)
class Env:
    robotarm_host: str
    robotarm_port: int

    disp_url: str
    wash_url: str
    incu_url: str

env = Env(
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

dry_run = Config(
    robotarm_mode='dry run',
    disp_mode='dry run',
    wash_mode='dry run',
    incu_mode='dry run',
)

live_robotarm_only_no_gripper = Config(
    robotarm_mode='no gripper',
    disp_mode='dry run',
    wash_mode='dry run',
    incu_mode='dry run',
)

live_robotarm_only = Config(
    robotarm_mode='gripper',
    disp_mode='simulate',
    wash_mode='simulate',
    incu_mode='fail if used',
)

live_robotarm_and_incu_only = Config(
    robotarm_mode='gripper',
    disp_mode='simulate',
    wash_mode='simulate',
    incu_mode='execute',
)

live_execute_all = Config(
    robotarm_mode='gripper',
    disp_mode='execute',
    wash_mode='execute',
    incu_mode='execute',
)

def config_factory() -> Tuple[Callable[[Config], ContextManager[None]], Callable[[], Config]]:

    config_stack: list[Config]
    config_stack = []

    @contextmanager
    def use_config(c: Config) -> Iterator[None]:
        config_stack.append(c)
        yield
        config_stack.pop()

    def config() -> Config:
        return config_stack[-1]

    return use_config, config

use_config, config = config_factory()

class Command(abc.ABC):
    @abc.abstractmethod
    def execute(self, conf: Config, env: Env) -> None:
        pass

@dataclass(frozen=True)
class robotarm_cmd(Command):
    prog_path: str
    def execute(self, conf: Config, env: Env) -> None:
        prog_path = self.prog_path
        if conf.robotarm_mode == 'dry run':
            print('dry run', prog_path)
            return
        if conf.robotarm_mode == 'no gripper':
            prog_path = prog_path.replace('generated', 'generated_nogripper')
        prog_str = open(pp(prog_path), 'rb').read()
        prog_name = prog_path.split('/')[-1]
        needle = f'Program {prog_name} completed'.encode()
        # pp(needle)
        assert needle in prog_str
        assert conf.robotarm_mode in {'gripper', 'no gripper'}
        print('connecting to robot...', end=' ')
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((env.robotarm_host, env.robotarm_port))
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
                pp(m)

            # KeyMessage, looks like:
            # PROGRAM_XXX_STARTEDtestmove2910
            # PROGRAM_XXX_STOPPEDtestmove2910
            for m in re.findall(b'PROGRAM_XXX_(\w*)', data):
                m = m.decode()
                pp(m)

            if needle in data:
                print(f'program {prog_name} completed!')
                break
        s.close()

@dataclass(frozen=True)
class wash_cmd(Command):
    protocol_path: str
    def execute(self, conf: Config, env: Env) -> None:
        if conf.wash_mode == 'dry run':
            print('dry run', self.protocol_path)
            return
        elif conf.wash_mode == 'simulate':
            url = env.wash_url + 'simulate_protocol/' + self.protocol_path
        elif conf.wash_mode == 'execute':
            url = env.wash_url + 'execute_protocol/' + self.protocol_path
        else:
            raise ValueError
        res = curl(url)
        assert res['status'] == 'OK', pp(res)

@dataclass(frozen=True)
class disp_cmd(Command):
    protocol_path: str
    def execute(self, conf: Config, env: Env) -> None:
        if conf.disp_mode == 'dry run':
            print('dry run', self.protocol_path)
            return
        elif conf.disp_mode == 'simulate':
            url = env.disp_url + 'simulate_protocol/' + self.protocol_path
        elif conf.disp_mode == 'execute':
            url = env.disp_url + 'execute_protocol/' + self.protocol_path
        else:
            raise ValueError
        res = curl(url)
        assert res['status'] == 'OK', pp(res)

@dataclass(frozen=True)
class incu_cmd(Command):
    action: Literal['put' | 'get']
    incu_loc: str
    def execute(self, conf: Config, env: Env) -> None:
        if conf.incu_mode == 'dry run':
            print('dry run', self.incu_loc)
        elif conf.incu_mode == 'fail if used':
            raise RuntimeError
        elif conf.incu_mode == 'execute':
            url = env.incu_url + self.action + '/' + self.incu_loc
        else:
            raise ValueError
        res = curl(url)
        assert res['status'] == 'OK', pp(res)
        busy_wait(env.incu_url + 'is_ready')

def curl(url: str) -> Any:
    return json.loads(urlopen(url).read())

def busy_wait(url: str) -> None:
    while 1:
        res = curl(url)
        assert res['status'] == 'OK', pp(res)
        if res['value'] is True:
            return
        else:
            time.sleep(0.1)

def robotarm(path: str):
    robotarm_cmd(path).execute(config(), env)

with use_config(dry_run):
    if 0:
        from glob import glob
        for path in glob('./generated/*'):
            robotarm(path)

    def script(s: str):
        for path in s.strip().split('\n'):
            robotarm(path.strip())

    if 0:
        script('''
            ./generated/r1_put
            ./generated/r1_get

            ./generated/r11_put
            ./generated/r11_get

            ./generated/r15_put
            ./generated/r15_get
        ''')

    if 0:
        script('''
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
        script('''
            ./generated/h19_put
            ./generated/r21_put
            ./generated/r19_put
            ./generated/r21_get
            ./generated/r19_get
            ./generated/out18_put
            ./generated/wash_get
        ''')

