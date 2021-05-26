from __future__ import annotations

from dataclasses import *
from typing import *

from moves import Move, MoveList

import re
import socket
import gripper

        # printf '%s\n' 'def u():' ' socket_open("127.0.0.1", 63352, socket_name="gripper")' ' socket_send_line("SET " + "POS" + " " + to_str(77), socket_name="gripper")' 'end' | nc localhost 30001

prelude = '''
    set_gravity([0.0, 0.0, 9.82])
    set_tcp(p[0, 0, 0, -1.2092, 1.2092, 1.2092])

    set_payload(0.1)
    set_standard_analog_input_domain(0, 1)
    set_standard_analog_input_domain(1, 1)
    set_tool_analog_input_domain(0, 1)
    set_tool_analog_input_domain(1, 1)
    set_analog_outputdomain(0, 0)
    set_analog_outputdomain(1, 0)
    set_input_actions_to_default()
    set_tool_communication(False, 115200, 0, 1, 1.5, 3.5)
    set_tool_output_mode(0)
    set_tool_digital_output_mode(0, 1)
    set_tool_digital_output_mode(1, 1)
    set_tool_voltage(0)
    set_safety_mode_transition_hardness(1)

    set_tool_voltage(24) # urk

    global last_xyz = [0, 0, 0]
    global last_rpy = [0, 0, 0]
    global last_lin = False

    def MoveLin(x, y, z, r, p, yaw, slow=False):
        rv = rpy2rotvec([d2r(r), d2r(p), d2r(yaw)])
        pose = p[x/1000, y/1000, z/1000, rv[0], rv[1], rv[2]]
        if slow:
            movel(pose, a=0.3, v=0.10)
        else:
            movel(pose, a=1.2, v=0.25)
        end
        last_xyz = [x, y, z]
        last_rpy = [r, p, yaw]
        last_lin = True
    end

    def MoveRel(x, y, z, r, p, yaw, slow=False):
        if not last_lin:
            textmsg("log fail MoveRel without preceding linear move")
            popup("MoveRel without preceding linear move", error=True)
            halt
        end
        MoveLin(
            last_xyz[0] + x, last_xyz[1] + y, last_xyz[2] + z,
            last_rpy[0] + r, last_rpy[1] + p, last_rpy[2] + yaw,
            slow=slow
        )
    end

    def MoveJoint(q1, q2, q3, q4, q5, q6, slow=False):
        q = [d2r(q1), d2r(q2), d2r(q3), d2r(q4), d2r(q5), d2r(q6)]
        if slow:
            movej(q, a=0.3, v=0.25)
        else:
            movej(q, a=1.4, v=1.05)
        end
        last_xyz = [0, 0, 0]
        last_rpy = [0, 0, 0]
        last_lin = False
    end
'''

def gripper_code(with_gripper: bool=False) -> str:
    '''
    Gripper URScript code.

    The public commands are:

        GripperMove,
        GripperClose,
        GripperOpen,

    '''

    if with_gripper:
        code = gripper.gripper_code
    else:
        code = '''
            def GripperMove(pos):
                textmsg("log gripper simulated, pretending to move to ", pos)
                sleep(0.1)
            end
        '''

    return code + '''
        def GripperClose():
            GripperMove(255)
        end

        def GripperOpen():
            GripperMove(77)
        end

        def Shake():
            w = 0.25
            MoveRel(-0.5,    0, w, w, w, w) w = -w
            MoveRel(   0, -0.5, w, w, w, w) w = -w
            MoveRel(   1,    0, w, w, w, w) w = -w
            MoveRel(   0,    1, w, w, w, w) w = -w
            MoveRel(-0.5,    0, w, w, w, w) w = -w
            MoveRel(   0, -0.5, w, w, w, w) w = -w
        end

        def GripperTest():
            GripperClose() MoveRel(0, 0,  21, 0, 0, 0)
            Shake()        MoveRel(0, 0, -20, 0, 0, 0)
            GripperOpen()  MoveRel(0, 0,  -1, 0, 0, 0)
        end
    '''


def reindent(s: str) -> str:
    out: list[str] = []
    i = 0
    for line in s.strip().split('\n'):
        line = line.strip()
        # if '"' not in line:
        #     line = re.sub('#.*$', '', line).strip()
        if line == 'end' or line.startswith('elif') or line.startswith('else'):
            i -= 2
        if line:
            out += [' ' * i + line]
        if line.endswith(':') and not line.startswith('#'):
            i += 2
    return '\n'.join(out) + '\n'  # final newline required when sending on socket

def make_script(movelist: list[Move], with_gripper: bool, name: str='script') -> str:
    body = '\n'.join(
        ("# " + getattr(m, 'name') + '\n' if hasattr(m, 'name') else '')
        + m.to_script()
        for m in movelist
    )
    print(body)
    assert re.match(r'(?!\d)\w*$', name)
    return reindent(f'''
        def {name}():
            {prelude}
            {gripper_code(with_gripper)}
            {body}
            textmsg("log {name} done")
        end
    ''')

@dataclass(frozen=True)
class Robotarm:

    @staticmethod
    def init(host: str, port: int, with_gripper: bool, quiet: bool = False) -> Robotarm:
        quiet or print('connecting to robotarm...', end=' ')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        quiet or print('connected!')
        return Robotarm(with_gripper, sock, quiet)

    @staticmethod
    def init_simulate(with_gripper: bool, quiet: bool = False) -> Robotarm:
        return Robotarm(with_gripper, 'simulate', quiet)

    with_gripper: bool
    sock: socket.socket | Literal['simulate']
    quiet: bool = False

    def send(self, prog_str: str) -> Robotarm:
        prog_bytes = prog_str.encode()
        if self.sock == 'simulate':
            return self
        # print(prog_str)
        self.sock.sendall(prog_bytes)
        return self

    def recv(self) -> Iterator[bytes]:
        if self.sock == 'simulate':
            raise RuntimeError
        while True:
            data = self.sock.recv(4096)
            for m in re.findall(rb'[\x20-\x7e]*(?:log|program|assert|\w+exception|error|\w+_\w+:)[\x20-\x7e]*', data, re.IGNORECASE):
                m = m.decode()
                self.quiet or print(f'{m = }')
            yield data

    def recv_until(self, needle: str) -> None:
        if self.sock == 'simulate':
            return
        for data in self.recv():
            if needle.encode() in data:
                self.quiet or print(f'received {needle}')
                return

    def close(self) -> None:
        if self.sock == 'simulate':
            return
        self.sock.close()

    def set_speed(self, value: int) -> Robotarm:
        if not (0 < value <= 100):
            raise ValueError
        # The speed is set on the RTDE interface on port 30003:
        self.send(reindent(f'''
            sec set_speed():
                socket_open("127.0.0.1", 30003)
                socket_send_line("set speed {value/100}")
                socket_close()
            end
        '''))
        return self

    def execute_moves(self, movelist: list[Move], name: str='script') -> None:
        self.send(make_script(movelist, self.with_gripper, name=name))
        self.recv_until(f'log {name} done')
        # self.close()
