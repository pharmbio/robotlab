

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

API_CODE = {
    -12: 'run blockly app exception',
    -11: 'convert blockly app to pythen exception',
    -9: 'emergency stop',
    -8: 'out of range',
    -7: 'joint angle limit',
    -6: 'cartesian pos limit',
    -5: 'revesed, no use',
    -4: 'command is not exist',
    -3: 'revesed, no use',
    -2: 'xArm is not ready, may be the motion is not enable or not set state',
    -1: 'xArm is disconnect or not connect',
    0: 'success',
    1: 'there are errors that have not been cleared',
    2: 'there are warnings that have not been cleared',
    3: 'get response timeout',
    4: 'tcp reply length error',
    5: 'tcp reply number error',
    6: 'tcp protocol flag error',
    7: 'tcp reply command and send command do not match',
    8: 'send command error, may be network exception',
    9: 'state is not ready to move',
    10: 'the result is invalid',
    11: 'other error',
    12: 'parameter error',
    20: 'host id error',
    21: 'modbus baudrate not supported',
    22: 'modbus baudrate not correct',
    23: 'modbus reply length error',
    31: 'trajectory read/write failed',
    32: 'trajectory read/write timeout',
    33: 'playback trajectory timeout',
    34: 'playback trajectory failed',
    41: 'wait to set suction cup timeout',
    80: 'linear track has error',
    81: 'linear track sci is low',
    82: 'linear track is not init',
    100: 'wait finish timeout',
    101: 'too many consecutive failed tests',
    102: 'end effector has error',
    103: 'end effector is not enabled',
    129: '(standard modbus tcp)illegal/unsupported function code',
    120: '(standard modbus tcp)illegal target address',
    131: '(standard modbus tcp)exection of requested data',
}


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
        X = 1.0
        code: None | int = None
        match m:
            case moves.MoveLin([x, y, z], [r, p, a]):
                code = self.arm.set_position(
                    x=x,
                    y=y,
                    z=z,
                    roll=180,
                    pitch=0,
                    yaw=a,
                    relative=False,
                    speed=250.0 / X / (10.0 if m.slow else 1.0),
                    wait=True, # sync
                    radius=0,  # linear
                    is_radian=False,
                )
            case moves.MoveRel([x, y, z], [r, p, a]):
                code = self.arm.set_position(
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
                code = self.arm.set_servo_angle(
                    angle=joints[:5],
                    relative=False,
                    speed=60.0 / X,
                    wait=True, # sync
                    is_radian=False,
                )
            case moves.GripperMove():
                # with open('gripper_log.jsonl') as log:
                #     _, status = self.arm.get_bio_gripper_status()
                #     print('Gripper', m.is_close(),
                if m.is_close():
                    code = self.arm.close_bio_gripper(speed=1, wait=True)
                else:
                    if 1:
                        code = self.arm.open_bio_gripper(speed=1, wait=True)
                    else:
                        code = self.arm.open_bio_gripper(speed=1, wait=False)
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
        if code is not None and isinstance(code, int):
            if code != 0:
                raise ValueError(f'XArm reports error {code=}: {API_CODE.get(code)}')


@dataclass(frozen=True)
class XArm:
    host: str

    @contextlib.contextmanager
    def connect(self, verbose: bool=True):
        from xarm.wrapper import XArmAPI
        arm: None | XArmAPI = None
        for num_retry in range(10):
            try:
                arm = XArmAPI(self.host)
                break
            except Exception as e:
                # xarm/x3/base.py
                if str(e) == 'connect serial failed':
                    import traceback as tb
                    import sys
                    print(
                        'XArm connection error:',
                        tb.format_exc(),
                        'Retrying in 1s',
                        sep='\n',
                        file=sys.stderr,
                    )
                    time.sleep(0.5)
                else:
                    raise
        if arm is None:
            raise ValueError('Failed to connect to the XArm')
        xarm = ConnectedXArm(arm, verbose=verbose)
        xarm.init()
        yield xarm
        arm.disconnect()

    def execute_moves(self, ms: list[Move]):
        with self.connect() as arm:
            for m in ms:
                arm.execute_move(m)
