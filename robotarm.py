from __future__ import annotations

from dataclasses import *
from typing import *

from moves import Move, MoveList

import re
import socket


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
        GripperSocketCleanup.

    They initialize the gripper socket and variables when called the first time.
    Exception: cleanup does not force initialization.
    '''

    return f'''
        def gripper_fail(msg1, msg2=""):
            msg = str_cat(msg1, msg2)
            textmsg("log gripper fail ", msg)
            popup(str_cat("Gripper fail ", msg), error=True)
            halt
        end

        gripper_initialized = False

        def get_gripper(varname):
            if not gripper_initialized:
                gripper_init()
            end
            socket_send_line(str_cat("GET ", varname), socket_name="gripper") # send "GET PRE\\n"
            s = socket_read_string(socket_name="gripper")  # recv "PRE 077\\n"
            s = str_sub(s, 4)                              # drop "PRE "
            s = str_sub(s, 0, str_len(s) - 1)              # drop "\\n"
            value = to_num(s)
            return value
        end

        def set_gripper(varname, value):
            if not gripper_initialized:
                gripper_init()
            end
            socket_set_var(varname, value, socket_name="gripper") # send "SET POS 77\\n"
            ack_bytes = socket_read_byte_list(3, socket_name="gripper", timeout=0.1)
            ack = ack_bytes == [3, 97, 99, 107] # 3 bytes received, then ascii for "ack"
            if not ack:
                gripper_fail("gripper request did not ack for var ", varname)
            end
        end

        def gripper_init():
            gripper_initialized = True
            ok = socket_open("127.0.0.1", 63352, socket_name="gripper")
            if not ok:
                gripper_fail("could not open socket")
            end
            if get_gripper("STA") != 3:
                gripper_fail("gripper needs to be activated, STA=", get_gripper("STA"))
            end
            if get_gripper("FLT") != 0:
                gripper_fail("gripper fault, FLT=", get_gripper("FLT"))
            end

            set_gripper("GTO", 1)
            set_gripper("SPE", 0)
            set_gripper("FOR", 0)
            set_gripper("MSC", 0)
        end

        def GripperSocketCleanup():
            # I don't think we actually need this: the robotiq gripper script
            # never explicitly closes the socket so we shouldn't need to either
            if gripper_initialized:
                socket_close(socket_name="gripper")
            end
        end

        def GripperMove(pos):
            if {not with_gripper}:
                textmsg("log gripper simulated, pretending to move to ", pos)
                sleep(0.1)
                return None
            end
            set_gripper("POS", pos)
            while (get_gripper("PRE") != pos):
                sleep(0.02)
            end
            while (get_gripper("OBJ") == 0):
                sleep(0.02)
            end
            if get_gripper("OBJ") != 3:
                gripper_fail("gripper move complete but OBJ != 3, OBJ=", get_gripper("OBJ"))
            end
            if get_gripper("FLT") != 0:
                gripper_fail("gripper fault FLT=", get_gripper("FLT"))
            end
        end

        def GripperClose():
            GripperMove(255)
        end

        def GripperOpen():
            GripperMove(77)
        end
    '''


def reindent(s: str) -> str:
    out: list[str] = []
    i = 0
    for line in s.strip().split('\n'):
        line = line.strip()
        if '"' not in line:
            line = re.sub('#.*$', '', line).strip()
        if line == 'end' or line.startswith('elif') or line.startswith('else'):
            i -= 2
        if line:
            out += [' ' * i + line]
        if line.endswith(':') and not line.startswith('#'):
            i += 2
    return '\n'.join(out) + '\n'  # final newline required when sending on socket

def make_script(movelist: list[Move], with_gripper: bool) -> str:
    body = '\n'.join(m.to_script() for m in movelist)
    return reindent(f'''
        def script():
            {prelude}
            {gripper_code(with_gripper)}
            {body}
            GripperSocketCleanup()
            textmsg("log script done")
        end
    ''')

@dataclass
class Robotarm:
    host: str
    port: int
    with_gripper: bool
    s: socket.socket = cast(Any, None)
    def __post_init__(self) -> None:
        print('connecting to robot...', end=' ')
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((self.host, self.port))
        print('connected!')

    def send(self, prog_str: str) -> Robotarm:
        print(prog_str)
        self.s.sendall(prog_str.encode())
        return self

    def recv(self) -> Iterator[bytes]:
        while True:
            data = self.s.recv(4096)
            for m in re.findall(b'[\x20-\x7e]*(?:log|program|assert|\w+exception|error|\w+_\w+:)[\x20-\x7e]*', data, re.IGNORECASE):
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

    def execute_moves(self, movelist: list[Move]) -> None:
        self.send(make_script(movelist, self.with_gripper))
        self.recv_until("log script done")
        self.close()
