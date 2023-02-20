from __future__ import annotations

from dataclasses import *
from typing import *

from .moves import Move

import re
import socket
from . import gripper

prelude = '''
    # Set TCP so that RPY makes sense
    # set_tcp(p[0, 0, 0, -1.2092, 1.2092, 1.2092])
    # set_tcp(p[0, 0, 0, 0, 0, 0])
    set_tcp(p[0, 0, 0, 1.2092, 1.2092, -1.2092])

    set_gravity([0.0, 0.0, 9.82])
    set_payload(0.1)

    global last_xyz = [0.0, 0.0, 0.0]
    global last_rpy = [0.0, 0.0, 0.0]
    global last_lin = False

    def set_last(x, y, z, r, p, yaw, flag):
        last_xyz = [x, y, z]
        last_rpy = [r, p, yaw]
        last_lin = flag
    end

    def MoveLin(x, y, z, r, p, yaw, slow=False):
        rv = rpy2rotvec([d2r(r), d2r(p), d2r(yaw)])
        pose = p[x/1000, y/1000, z/1000, rv[0], rv[1], rv[2]]
        set_last(x, y, z, r, p, yaw, True)
        if slow:
            movel(pose, a=0.3, v=0.10)
        else:
            movel(pose, a=1.2, v=0.25)
        end
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

    def EnsureRelPos():
        while not is_steady():
            sync()
        end
        p = get_actual_tcp_pose()
        rpy = rotvec2rpy([p[3], p[4], p[5]])
        rpy = [r2d(rpy[0]), r2d(rpy[1]), r2d(rpy[2])]
        xyz = [p[0]*1000, p[1]*1000, p[2]*1000]
        set_last(xyz[0], xyz[1], xyz[2], rpy[0], rpy[1], rpy[2], True)
        textmsg("log set reference pos to " + to_str(xyz) + " " + to_str(rpy))
    end

    def MoveJoint(q1, q2, q3, q4, q5, q6, slow=False):
        q = [d2r(q1), d2r(q2), d2r(q3), d2r(q4), d2r(q5), d2r(q6)]
        if slow:
            movej(q, a=0.3, v=0.25)
        else:
            movej(q, a=1.4, v=1.05)
        end
        set_last(0, 0, 0, 0, 0, 0, False)
    end
'''

def gripper_code(with_gripper: bool=False) -> str:
    '''
    Gripper URScript code.

    The public commands are:

        GripperMove(pos)  # pos in range [0, 255]: 255=closed, 0=maximally open
        GripperTest()

    '''

    if with_gripper:
        code = gripper.gripper_code
    else:
        code = '''
            def GripperMove(pos, soft=False):
                if pos > 255:
                    pos = 255
                elif pos < 0:
                    pos = 0
                end
                if soft:
                    softly = "softly "
                else:
                    softly = ""
                end
                textmsg("log gripper simulated, pretending to move " + softly + "to ", pos)
                write_output_integer_register(0, pos)
                sleep(0.1)
            end
            def GripperInit():
                sleep(0.1)
            end
        '''

    return code + '''
        def Shake():
            w = -0.2 MoveRel(w, w, w, w/4, w/4, w/4)
            w =  0.4 MoveRel(w, w, w, w/4, w/4, w/4)
            w = -0.2 MoveRel(w, w, w, w/4, w/4, w/4)
        end

        def GripperTest():
            EnsureRelPos()
            start_pos = read_output_integer_register(0)
            d = 14.0
            GripperMove(255)       MoveRel(0, 0,  d,        0, 0, 0)
            Shake()                MoveRel(0, 0, -d + 0.25, 0, 0, 0)
            GripperMove(start_pos) MoveRel(0, 0,     -0.25, 0, 0, 0)
        end

        def GripperInitAndCheck():
            GripperInit()
            GripperMove(95)
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
    assert re.match(r'(?!\d)\w*$', name)
    assert len(name) <= 30
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
    def init_noop(with_gripper: bool, quiet: bool = False) -> Robotarm:
        return Robotarm(with_gripper, 'noop', quiet)

    with_gripper: bool
    sock: socket.socket | Literal['noop']
    quiet: bool = False

    def send(self, prog_str: str) -> Robotarm:
        prog_bytes = prog_str.encode()
        if self.sock == 'noop':
            return self
        # print(prog_str)
        self.sock.sendall(prog_bytes)
        return self

    def recv(self) -> Iterator[bytes]:
        if self.sock == 'noop':
            raise RuntimeError
        while True:
            data = self.sock.recv(4096)
            for m in re.findall(rb'[\x20-\x7e]*(?:log|fatal|program|assert|\w+exception|error|\w+_\w+:)[\x20-\x7e]*', data, re.IGNORECASE):
                m = m.decode()
                # self.quiet or print(f'{m = }')
                print(f'{m = }')
                if 'fatal' in m:
                    self.sock.sendall('textmsg("log panic stop")\n'.encode())
                    raise RuntimeError(m)
            yield data

    def recv_until(self, needle: str) -> None:
        if self.sock == 'noop':
            return
        for data in self.recv():
            if needle.encode() in data:
                self.quiet or print(f'received {needle}')
                return

    def close(self) -> None:
        if self.sock == 'noop':
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
                textmsg("log speed changed to {value}")
            end
        '''))
        return self

    def stop(self):
        self.send('textmsg("log quit")\n')
        self.recv_until('quit')

    def execute_moves(self, movelist: list[Move], name: str='script', allow_partial_completion: bool=False) -> None:
        name = name.replace('/', '_of_')
        name = name.replace(' ', '_')
        name = name.replace('-', '_')
        name = name[:30]
        self.send(make_script(movelist, self.with_gripper, name=name))
        if allow_partial_completion:
            self.recv_until(f'PROGRAM_XXX_STOPPED{name}')
        else:
            self.recv_until(f'log {name} done')

