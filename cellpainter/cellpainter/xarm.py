

from __future__ import annotations

from dataclasses import *
from typing import *

import socket
import contextlib
import time

from labrobots.log import Log

from .moves import Move
from . import moves

if TYPE_CHECKING:
    from xarm.wrapper import XArmAPI

DEFAULT_HOST='10.10.0.84'

@dataclass(frozen=True)
class Intercept:
    base: Any
    text: str = ''

    def __getattr__(self, attr: str):
        return Intercept(getattr(self.base, attr), f'{self.text}.{attr}')

    def __call__(self, *args: Any, **kwargs: Any):
        params = ','.join(map(str, (*args, *[f'{k}={v}' for k, v in kwargs.items()])))
        print(f'{self.text}({params})')
        res = self.base(*args, **kwargs)
        print(f'{self.text}({params}) = {res}')
        return res

@dataclass(frozen=True)
class ConnectedXArm:
    _arm: XArmAPI
    verbose: bool

    @property
    def arm(self) -> XArmAPI:
        if self.verbose:
            return cast('XArmAPI', Intercept(self._arm, 'xarm'))
        else:
            return self._arm

    def init(self):
        self.arm.set_tcp_offset([0, 0, 0, 0, 0, 0], is_radian=False)
        self.arm.motion_enable(True)
        self.arm.clean_error()
        self.arm.set_mode(0)   # 2: freedrive, 0: normal
        self.arm.set_state(0)
        self.arm.set_bio_gripper_enable(True)

    def poll_info(self) -> dict[str, list[float]]:
        code, xyzrpa = self.arm.get_position(is_radian=False)
        if code != 0:
            raise ValueError(f'arm.get_position failed with {code=}')
        code, joints = self.arm.get_servo_angle(is_radian=False)
        if code != 0:
            raise ValueError(f'arm.get_servo_angle failed with {code=}')
        x, y, z, r, p, a = xyzrpa
        return {
            'xyz': [x, y, z],
            'rpy': [r, p, a],
            'joints': joints,
            'pos': [0] # gripper pos (unknown)
        }

    def execute_move(self, m: Move):
        X = 3.0
        match m:
            case moves.MoveLin([x, y, z], [r, p, a]):
                self.arm.set_position(
                    x=x,
                    y=y,
                    z=z,
                    roll=180,
                    pitch=0,
                    yaw=a,
                    relative=False,
                    speed=250.0 / X,
                    wait=True, # sync
                    radius=0,  # linear
                    is_radian=False,
                )
            case moves.MoveRel([x, y, z], [r, p, a]):
                self.arm.set_position(
                    x=x,
                    y=y,
                    z=z,
                    roll=r,
                    pitch=p,
                    yaw=a,
                    relative=True,
                    speed=100.0,
                    wait=True, # sync
                    radius=0,  # linear
                    is_radian=False,
                )
            case moves.MoveJoint(joints):
                self.arm.set_servo_angle(
                    angle=joints[:5],
                    relative=False,
                    speed=60.0 / X,
                    wait=True, # sync
                    is_radian=False,
                )
            case moves.GripperMove():
                if m.is_close():
                    self.arm.close_bio_gripper(speed=1, wait=True)
                else:
                    if 0:
                        self.arm.open_bio_gripper(speed=1, wait=True)
                    else:
                        self.arm.open_bio_gripper(speed=1, wait=False)
                        time.sleep(0.8)
                        self.arm.set_bio_gripper_enable(False)
                        self.arm.set_bio_gripper_enable(True)
            case moves.Section():
                pass
            case moves.XArmBuiltin(cmd):
                match cmd:
                    case 'freedrive':
                        self.arm.set_mode(2)
                        self.arm.set_state(0)
                    case 'stop':
                        print('stopping robot!')
                        self.arm.emergency_stop()
                        time.sleep(1)
                        self.init()
                        print('stopping robot!')
            case _:
                raise ValueError(f'Unsupported XArm move: {m}')


@dataclass(frozen=True)
class XArm:
    host: str

    @contextlib.contextmanager
    def connect(self, verbose: bool=True):
        from xarm.wrapper import XArmAPI
        arm = XArmAPI(self.host)
        xarm = ConnectedXArm(arm, verbose=verbose)
        xarm.init()
        yield xarm
        arm.disconnect()

    def execute_moves(self, ms: list[Move]):
        with self.connect() as arm:
            for m in ms:
                arm.execute_move(m)
