from __future__ import annotations
from dataclasses import *
from typing import *

import sys

from pbutils.mixins import DBMixin

from .timelike import Timelike, WallTime, SimulatedTime


LockName = Literal['PF and Fridge', 'Squid', 'Nikon']

@dataclass(frozen=True)
class UREnv:
    mode: Literal['noop', 'execute', 'execute no gripper']
    host: str
    port: int

class UREnvs:
    live      = UREnv('execute', '10.10.0.112', 30001)
    forward   = UREnv('execute', '127.0.0.1', 30001)
    simulator = UREnv('execute no gripper', '127.0.0.1', 30001)
    dry       = UREnv('noop', '', 0)

@dataclass(frozen=True)
class PFEnv:
    mode: Literal['noop', 'execute']
    host: str
    _: KW_ONLY
    port_rw: int
    port_ro: int

class PFEnvs:
    live      = PFEnv('execute', '10.10.0.98', port_rw=10100, port_ro=10000)
    forward   = PFEnv('execute', 'localhost',  port_rw=10100, port_ro=10000)
    dry       = PFEnv('noop', '', port_rw=0, port_ro=0)

@dataclass(frozen=True)
class RuntimeConfig(DBMixin):
    name:                   str = 'simulate'
    timelike:               Literal['WallTime', 'SimulatedTime'] = 'SimulatedTime'
    ur_env:                 UREnv = UREnvs.dry
    pf_env:                 PFEnv = PFEnvs.dry
    signal_handlers:               Literal['install', 'noop'] = 'noop'
    _: KW_ONLY
    run_incu_wash_disp:     bool = False
    run_fridge_squid_nikon: bool = False

    # ur_speed: int = 100
    # pf_speed: int = 50
    log_filename: str | None = None
    plate_metadata_dir: str | None = None

    def only_arm(self) -> RuntimeConfig:
        return self.replace(
            run_incu_wash_disp=False,
            run_fridge_squid_nikon=False,
            signal_handlers='noop',
        )

    def make_timelike(self) -> Timelike:
        if self.timelike == 'WallTime':
            return WallTime()
        elif self.timelike == 'SimulatedTime':
            return SimulatedTime()
        else:
            raise ValueError(f'No such {self.timelike=}')

    def __post_init__(self):
        if self.ur_env.mode != 'noop' and self.pf_env.mode != 'noop':
            raise ValueError(f'Not allowed: PF & UR ({self=})')
        if self.run_incu_wash_disp and self.run_fridge_squid_nikon:
            raise ValueError(f'Not allowed: cellpainting room and microscope room ({self=})')

    @staticmethod
    def lookup(name: str) -> RuntimeConfig:
        return {c.name: c for c in configs}[name]

    @staticmethod
    def simulate() -> RuntimeConfig:
        return RuntimeConfig.lookup('simulate')

    @staticmethod
    def from_argv(argv: list[str]=sys.argv) -> RuntimeConfig:
        for c in configs:
            if '--' + c.name in sys.argv:
                return c
        else:
            raise ValueError('Start with one of ' + ', '.join('--' + c.name for c in configs))

configs: list[RuntimeConfig]
configs = [
    # UR:
    RuntimeConfig('live',         'WallTime', UREnvs.live,      PFEnvs.dry, run_incu_wash_disp=True,  run_fridge_squid_nikon=False, signal_handlers='install'),
    RuntimeConfig('ur-simulator', 'WallTime', UREnvs.simulator, PFEnvs.dry, run_incu_wash_disp=False, run_fridge_squid_nikon=False),
    RuntimeConfig('forward',      'WallTime', UREnvs.forward,   PFEnvs.dry, run_incu_wash_disp=False, run_fridge_squid_nikon=False, signal_handlers='install'),

    # PF:
    RuntimeConfig('pf-live',       'WallTime',      UREnvs.dry,       PFEnvs.live,    run_incu_wash_disp=False,  run_fridge_squid_nikon=True,  signal_handlers='install', plate_metadata_dir='./plate-metadata'),
    RuntimeConfig('pf-forward',    'WallTime',      UREnvs.dry,       PFEnvs.forward, run_incu_wash_disp=False,  run_fridge_squid_nikon=False, signal_handlers='install', plate_metadata_dir='./plate-metadata'),

    # Simulate:
    RuntimeConfig('simulate-wall', 'WallTime',      UREnvs.dry,       PFEnvs.dry,     run_incu_wash_disp=False,  run_fridge_squid_nikon=False, plate_metadata_dir='./plate-metadata'),
    RuntimeConfig('simulate',      'SimulatedTime', UREnvs.dry,       PFEnvs.dry,     run_incu_wash_disp=False,  run_fridge_squid_nikon=False, plate_metadata_dir='./plate-metadata'),
]
