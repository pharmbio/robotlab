from __future__ import annotations
from typing import *
from typing_extensions import TypedDict
from .machine import Machine, Log
from dataclasses import *
import contextlib
import time
import queue
import threading
import json
import re

from queue import Queue
from threading import Lock, RLock

import socket

class PFDesc(TypedDict):
    nick: str
    ip: str
    location: str
    has_rail: bool
    has_kine_sol: bool

PFs = [
    local_pf := PFDesc(
        nick='local',
        ip='127.0.0.1',
        location='bmc-imager',
        has_rail=False,
        has_kine_sol=False,
    ),
    rhumba := PFDesc(
        nick='rhumba',
        ip='10.10.0.91',
        location='bmc-imager',
        has_rail=False,
        has_kine_sol=False,
    ),
    polka := PFDesc(
        nick='polka',
        ip='10.80.90.112',
        location='hq-robotlab',
        has_rail=True,
        has_kine_sol=True,
    ),
]

def get_PF_by_ip(ip: str) -> PFDesc:
    for pf in PFs:
        if pf['ip'] == ip:
            return pf
    raise ValueError(f'No PF with {ip=}')

def get_PF_by_nick(nick: str) -> PFDesc:
    for pf in PFs:
        if pf['nick'] == nick:
            return pf
    raise ValueError(f'No PF with {nick=}')

def log(name: str, msg: str):
    filename = 'pf_log.txt'
    if name == 'status':
        filename = 'pf_log_status.txt'
        return
    with open(filename, 'a') as fp:
        print(msg, file=fp, flush=True)


A = TypeVar('A')

ActionStatus: TypeAlias = Literal['done', 'cancelled']


@dataclass(frozen=True)
class ActionResponse:
    status: ActionStatus
    io: list[tuple[str, str]]


class KineSolution(TypedDict):
    q2: float
    q3: float
    q4: float
    rail: float


@dataclass(frozen=True, order=True)
class PFState:
    x: float
    y: float
    z: float  # q1
    rail: float  # q6
    angle: float
    q2: float  # shoulder
    q3: float  # elbow
    q4: float  # wrist
    q5: float  # gripper
    sys_state: int        = 0
    sys_state_label: str  = ''
    move_state: int       = 0
    move_state_label: str = ''
    hp: int               = 1
    speed: int            = 1
    uptime: float         = 0.0

    @staticmethod
    def fromdict(d: dict[str, Any]) -> PFState:
        fieldnames = {field.name for field in fields(PFState)}
        return PFState(**{k: v for k, v in d.items() if k in fieldnames})

    @property
    def q1(self) -> float:
        return self.z

    @property
    def q6(self) -> float:
        return self.rail

    @property
    def has_high_power(self) -> bool:
        return bool(self.hp)

    @property
    def ok_to_attach(self):
        return self.sys_state == 20

    @property
    def is_attached(self):
        return self.sys_state == 21

    @property
    def gripper(self) -> float:
        return self.q5

    def truncate(self, precision: float = 1.0) -> PFState:
        r = 1.0 / precision
        return replace(
            self,
            x=round(self.x * r) / r,
            y=round(self.y * r) / r,
            z=round(self.z * r) / r,
            rail=round(self.rail * r) / r,
            angle=round(self.angle * r) / r,
            q2=round(self.q2 * r) / r,
            q3=round(self.q3 * r) / r,
            q4=round(self.q4 * r) / r,
            q5=round(self.q5 * r) / r,
            uptime=self.uptime and round(self.uptime),
        )

    def coords(self) -> list[float]:
        return [self.x, self.y, self.z, self.rail, self.angle, self.q2, self.q3, self.q4, self.q5]

@dataclass
class ConnectedPF:
    status_sock: Socket
    actions_sock: Socket
    emergency_sock: Socket

    statejson: dict[str, float | str | int] | None = None

    request_num: int = 0
    request_num_write_lock: Lock = field(default_factory=Lock)
    action_queue: Queue[tuple[int, str | queue.Queue[ActionResponse]]] = field(default_factory=lambda: Queue())
    action_state: Literal['ready', 'busy'] = 'ready'

    current_action_for_debugging: str | None = None

    emergency_queue: Queue[tuple[str, queue.Queue[str]]] = field(default_factory=lambda: Queue())

    is_broken: bool = False

    def __post_init__(self):
        threading.Thread(target=self.action_manager, daemon=True).start()
        threading.Thread(target=self.statejson_manager, daemon=True).start()
        threading.Thread(target=self.emergency_manager, daemon=True).start()

    def close(self):
        self.status_sock.close()
        self.actions_sock.close()
        self.emergency_sock.close()

    def statejson_manager(self):
        while True:
            try:
                statejson_raw = self.status_sock.send_and_recv('statejson')
            except OSError as e:
                print(f'Socket error in statejson_manager: {e}')
                self.is_broken = True
                self.close()
                return

            try:
                statejson = json.loads(statejson_raw)
            except json.JSONDecodeError as e:
                print(f'{e!r}: {statejson_raw!r}')
            else:
                if statejson.get('move_state_label') != (self.statejson or {}).get('move_state_label'):
                    print('New move state:', json.dumps(statejson, indent=2).replace('"', ''))
                elif statejson.get('sys_state_label') != (self.statejson or {}).get('sys_state_label'):
                    print('New sys state:', json.dumps(statejson, indent=2).replace('"', ''))
                self.statejson = statejson
            finally:
                time.sleep(0.100)

    def action_manager(self):
        io: list[tuple[str, str]] = []
        while not self.is_broken:
            request_index, msg = self.action_queue.get()

            if request_index < self.request_num:
                # skip outdated msg
                if isinstance(msg, queue.Queue):
                    msg.put_nowait(ActionResponse('cancelled', io))
                    io = []

            elif isinstance(msg, queue.Queue):
                self.action_state = 'ready'
                msg.put_nowait(ActionResponse('done', io))
                io = []

            else:
                self.action_state = 'busy'
                self.current_action_for_debugging = msg

                if msg == '@check_gripper_pos_gt_75':

                    statejson_raw = self.actions_sock.send_and_recv('statejson')
                    resp = 'Ok'

                    try:
                        q5 = float(json.loads(statejson_raw).get('q5'))
                        if q5 < 75.5:
                            resp = f'Gripper closed too far ({q5} is too close to 75)'
                    except json.JSONDecodeError as e:
                        resp = f'{e!r}: {statejson_raw!r}'
                else:
                    resp = self.actions_sock.send_and_recv(msg)
                    io += [(msg, resp)]

                cmd_name, *_ = msg.lower().split()
                expects_ok = '''
                    hp
                    move
                    waitforeom
                    home
                    @check_gripper_pos_gt_75
                '''.split()
                command_expects_ok = any(s in cmd_name for s in expects_ok)
                if command_expects_ok and resp.strip() != 'Ok':
                    with self.request_num_write_lock:
                        # Invalidate current request num
                        self.request_num += 1
                        self.action_state = 'ready'

                self.current_action_for_debugging = None

    def action_enqueue(self, cmdlist: list[str], fire_and_forget: bool = False):
        with self.request_num_write_lock:
            self.request_num += 1
            my_request_num = self.request_num

        reply_queue = queue.Queue[ActionResponse]()
        for msg in cmdlist:
            self.action_queue.put_nowait((my_request_num, msg))
        self.action_queue.put_nowait((my_request_num, reply_queue))
        if fire_and_forget:
            return ActionResponse('done', [])
        else:
            return reply_queue.get()

    def emergency_manager(self):
        while not self.is_broken:
            msg, reply_queue = self.emergency_queue.get()
            resp = self.emergency_sock.send_and_recv(msg)
            reply_queue.put_nowait(resp)

    def send_emergency(self, msg: str):
        reply_queue = queue.Queue[str]()
        self.emergency_queue.put_nowait((msg, reply_queue))
        return reply_queue.get()

    def run_cmds(self, cmdlist: list[str]) -> list[tuple[str, str]]:
        if self.action_state != 'ready':
            raise ValueError(f'Already processing an action ({self.current_action_for_debugging})')

        split_cmdlist: list[str] = []

        for multipart_msg in cmdlist:
            for msg in multipart_msg.split(';'):
                msg = msg.strip()
                split_cmdlist += [msg]

        del cmdlist

        resp = self.action_enqueue(split_cmdlist)

        if resp.status == 'done':
            return resp.io
        elif not resp.io:
            raise ValueError(f'Cancelled (before starting any of the {len(resp.io)} commands)')
        elif len(resp.io) == len(split_cmdlist):
            last_io = resp.io[-1]
            raise ValueError(f'Cancelled at last command {last_io!r}')
        else:
            next_cmd = split_cmdlist[len(resp.io)]
            last_io = resp.io[-1]
            raise ValueError(
                f'Cancelled (after {len(resp.io)} of {len(split_cmdlist)} commands, last successful io: {last_io!r}, current command: {next_cmd!r})'
            )

    def run_cmd(self, cmd: str) -> str:
        (_, reply) = self.run_cmds([cmd])[-1]
        return reply

    def soft_estop(self):
        # invalidate all current queued actions
        self.action_enqueue([], fire_and_forget=True)

        # send soft estop, this will cancel current and upcoming blended moves
        self.send_emergency('SoftEStop')

        # wait until we are fully stopped
        self.action_enqueue(['halt'])

    def set_speed(self, value: int):
        return self.send_emergency(f'mspeed {value}')

    def stop_and_reattach(self):
        self.soft_estop()
        for _ in range(10):
            # reattach
            self.run_cmd('attach 1')
            time.sleep(0.05)
            # check for successfull attach
            resp = self.run_cmd('attach')
            if resp.endswith('= 1'):
                return
            else:
                time.sleep(0.05)
        raise ValueError('Failed to reattach')


@dataclass(frozen=True)
class PF(Machine):
    ip: str
    status_port: int = 10000
    actions_port: int = 10100
    emergency_port: int = 10001
    command_line_port: int = 23
    ftp_port: int = 21

    connected_pf_box: Box[ConnectedPF] = field(default_factory=lambda: Box())
    reconnect_lock: RLock = field(default_factory=RLock)

    def init(self):
        with self.reconnect_lock:
            if old_pf := self.connected_pf_box.try_value():
                self.connected_pf_box.set_empty()
                time.sleep(1.0)
                old_pf.close()
            try:
                pf = ConnectedPF(
                    status_sock=Socket.create('status', self.ip, self.status_port),
                    actions_sock=Socket.create('actions', self.ip, self.actions_port),
                    emergency_sock=Socket.create('emergency', self.ip, self.emergency_port),
                )
                self.connected_pf_box.set_value(pf)
            except Exception as e:
                import traceback as tb
                log = Log.make('pf')
                for line in tb.format_exc().splitlines():
                    log(line)
                log('PF initialization error.\nPossible solution: start the TCS program.\nFrom this web service you can start it with /pf/recompile.', type='error', error=repr(e))

    def is_broken(self):
        with self.reconnect_lock:
            if pf := self.connected_pf_box.try_value():
                return pf.is_broken
            else:
                return True

    @property
    def connected_pf(self) -> ConnectedPF:
        with self.reconnect_lock:
            if self.is_broken():
                self.init()
            return self.connected_pf_box.value

    @Machine.no_log
    def statejson(self) -> dict[str, str | float | int] | None:
        return self.connected_pf.statejson

    @Machine.no_log
    def state(self) -> PFState | None:
        if st := self.statejson():
            return PFState.fromdict(st)
        else:
            return None

    def _try_state(self) -> PFState:
        if st := self.state():
            return st
        else:
            raise ValueError('No Status available')

    def recompile(self, project: str = 'Tcp_cmd_server_pa'):
        """
        Recompiles and restarts a project on the PF controller.

        The first Help that is sent is the password. The whole conversation looks like this:

        ```bash
        $ {
            echo 'Help';
            echo 'stop -all';
            echo 'unload -all';
            echo 'load /flash/projects/Tcp_cmd_server_pa -compile';
            echo 'start Tcp_cmd_server_pa';
            echo 'quit';
        } | nc 10.80.90.112 23

        Welcome to the GPL Console

        Password:

        GPL: stop -all
        GPL: unload -all
        GPL: load /flash/projects/Tcp_cmd_server_pa -compile
        06-03-2025 23:39:49: project Tcp_cmd_server_pa, begin compiler pass 1
        06-03-2025 23:39:49: project Tcp_cmd_server_pa, begin compiler pass 2
        06-03-2025 23:39:50: project Tcp_cmd_server_pa, begin compiler pass 3
        .Compile successful
        GPL: start Tcp_cmd_server_pa
        GPL: quit

        Exiting console task...
        ```
        """
        commands = [
            'Help',
            'stop -all',
            'unload -all',
            f'load /flash/projects/{project} -compile',
            f'start {project}',
            'quit',
        ]

        print(self, commands)

        with Socket.create_temp('console', self.ip, self.command_line_port) as console_sock:
            for cmd in commands:
                console_sock.send(cmd)

            out: list[str] = []
            for line in console_sock.iter_lines():
                out += [line]
                if 'quit' in line.lower():
                    break
                if 'exit' in line.lower():
                    break
                if 'fail' in line.lower():
                    break
                if 'error' in line.lower():
                    break
            return out

    def pf_desc(self) -> PFDesc:
        return get_PF_by_ip(self.ip)

    def remove_kinesol_from_gpl_code(self, contents: bytes) -> bytes:
        if not self.pf_desc()['has_kine_sol']:
            lines: list[bytes] = []
            hits: list[int] = []
            for lineno, line in enumerate(contents.splitlines(keepends=True), start=1):
                if b'.KineSol(' in line:
                    hits += [lineno]
                    lines += [b'']
                else:
                    lines += [line]
            contents = b''.join(lines)
            if hits:
                print(f'Removed {len(hits)} KineSol on lines {hits}')
        return contents


    def reupload(self, project: str = 'Tcp_cmd_server_pa'):
        from pathlib import Path

        import ftplib
        import os
        import re
        import io

        paths = list(Path(f'./pf_projects/{project}').glob('*'))

        print(f"ip: {self.ip}")
        print(f'paths: {paths}')

        with ftplib.FTP() as ftp:
            print('FTP connecting:', ftp)
            ftp.connect(self.ip, self.ftp_port)
            ftp.login()
            print('FTP connected:', ftp)

            # Get remote file sizes
            filesizes: dict[str, list[int]] = {}
            ftp.cwd("/flash/projects/Tcp_cmd_server_pa")
            lines: list[str] = []
            ftp.dir(lines.append)
            for line in lines:
                details, _space, filename = line.strip().rpartition(" ")
                if details.startswith("d"):
                    continue
                sizes = re.findall(r"\d{3,}", details)
                if sizes:
                    filesizes[filename] = [int(size) for size in sizes]
                    print(details, *sizes, filename, sep="\t")

            for file_path in paths:
                filename = file_path.name # os.path.basename(file_path)
                remote_path = f"/flash/projects/Tcp_cmd_server_pa/{filename}"
                contents = file_path.read_bytes()
                if filename.endswith('.gpl'):
                    contents = self.remove_kinesol_from_gpl_code(contents)
                local_size = len(contents)

                print(remote_path, f"{local_size=}", *filesizes.get(filename, []))
                if local_size in filesizes.get(filename, []):
                    print(f"Skipping {filename}\t(unchanged {local_size=})")
                    continue

                print(f"Uploading {filename}")
                ftp.storbinary(f"STOR {remote_path}", io.BytesIO(contents))

        return self.recompile(project)

    def soft_estop(self):
        return self.connected_pf.soft_estop()

    def set_speed(self, value: int):
        return self.connected_pf.set_speed(value)

    def hp(self, on_off: Literal['1', '0']='1'):
        return self.run_cmds([f'hp {on_off} 15'], wait_for_eom=False)

    def attach(self):
        return self.run_cmd('attach 1')

    def home(self):
        return self.run_cmd('home')

    def freedrive(self):
        return self.stop_and_run_cmd('freedrive')

    def stop_and_reattach(self):
        """
        Runs a soft estop, then reattaches
        """
        move_state_label = (self.connected_pf.statejson or {}).get('move_state_label', '')
        if self.connected_pf.action_state == 'busy' or move_state_label == 'Jog control mode':
            self.connected_pf.stop_and_reattach()
        else:
            pass

    def stop_and_run_cmds(self, cmdlist: list[str]):
        """
        Stop what we are doing, then run this
        """
        self.stop_and_reattach()
        return self.run_cmds(cmdlist)

    def stop_and_run_cmd(self, *parts: str) -> str:
        """
        Stop what we are doing, then run this
        """
        self.stop_and_reattach()
        return self.run_cmd(*parts)

    def run_cmds(self, cmdlist: list[str], wait_for_eom: bool = True):
        """
        Errors if already running. Uses WaitForEOM to run to completion.
        """
        if wait_for_eom:
            return self.connected_pf.run_cmds(cmdlist + ['WaitForEOM'])[:-1]
        else:
            return self.connected_pf.run_cmds(cmdlist)

    def run_cmd(self, *parts: str) -> str:
        """
        Returns command reply or errors if cancelled
        """
        cmd = ' '.join(map(str, parts))
        return self.run_cmds([cmd])[-1][1]

    def move_rail(self, d_rail: float, profile: int = 1):
        return self.movec_rel(d_x=-d_rail, d_rail=d_rail, profile=profile)

    def movec_rel(
        self,
        d_x: float = 0,
        d_y: float = 0,
        d_z: float = 0,
        d_rail: float = 0,
        d_angle: float = 0,
        profile: int = 1,
    ):
        if self.pf_desc()['has_rail']:
            return self.run_cmd(f'MoveC_Rel_WithRail {profile} {d_x} {d_y} {d_z} {d_rail} {d_angle}')
        else:
            return self.run_cmd(f'MoveC_Rel_WithoutRail {profile} {d_x} {d_y} {d_z} {d_rail} {d_angle}')

    def movej_rel(
        self,
        d_q1: float = 0,
        d_q2: float = 0,
        d_q3: float = 0,
        d_q4: float = 0,
        d_q5: float = 0,
        d_q6: float = 0,
        profile: int = 2,
    ):
        return self.run_cmd(f'MoveJ_Rel {profile} {d_q1} {d_q2} {d_q3} {d_q4} {d_q5} {d_q6}')

    def move_gripper(self, q5: float):
        return self.run_cmd(f'MoveGripper 1 {q5}')

    def movej_no_gripper(self, q1: float, q2: float, q3: float, q4: float, q6: float, profile: int = 2):
        return self.run_cmd(f'MoveJ_NoGripper {profile} {q1} {q2} {q3} {q4} {q6}')

    def show_temperature(self):
        d: dict[str, float] = {}
        for line in self.console_show('Temperature'):
            line = line.strip()
            line = re.sub(' +', ' ', line)
            if m := re.match(r'(.*):.*?([\d\.]+) C', line):
                k, v = m.groups()
                d[k] = float(v)
        return d

    def console_show(self, what: str):
        return self.run_cmd(f'ConsoleShow {what}').replace(';; ', '\n').splitlines()

    def show_info(self):
        lines: dict[str, list[str]] = {}
        for what in 'StartupLog Version Flash FPGA GSB'.split():
            lines[what] = self.console_show(what)
        return lines

    def serial_number(self):
        for line in self.console_show('StartupLog'):
            if m := re.match('Serial Number: (.*)', line):
                return m.group(1)

    def local_ip(self):
        for line in self.console_show('StartupLog'):
            if m := re.match('Local IP address: (.*)', line):
                return m.group(1)

    def kinesol(self, x: float, y: float, rail: float, angle: float, q2: float=0.0, q3: float=0.0, q4: float=0.0) -> KineSolution:
        [res] = self.kinesol_batch([[x, y, angle, rail, q2, q3, q4]])
        return res

    def kinesol_batch(self, inputs: list[list[float]]) -> list[KineSolution]:
        outputs = self.run_cmds([
            ' '.join(['kinesol'] + [str(x) for x in input])
            for input in inputs
        ], wait_for_eom=False)
        if len(outputs) != len(inputs):
            raise ValueError(f'Length mismatch! Expected {len(inputs)} outputs, got {len(outputs)}')
        out: list[Any] = []
        for _i, o in outputs:
            p = json.loads(o)
            del p['input']
            out += [p]
        return out

    def kinesol_search(self, x: float, y: float, angle: float, rail: float):
        inputs = [
            [x, y, angle, rail, q2, q3, q4]
            for q2 in list(range(-90, 90, 30))
            for q3 in list(range(-180, 180, 45))
            for q4 in list(range(0, 360, 45))
        ]
        return list({
            tuple(res.values())
            for res in self.kinesol_batch(inputs)
        })

    def test_round_z(self):
        """Test movement in z by snapping z to the closest rounded mm.

        Can be used to counteract backlash from repeated movements back and forth."""
        self.hp()
        self.attach()
        initial_z = self._try_state().z
        target_z = round(initial_z)
        self.movec_rel(d_z=target_z - initial_z)
        final_z = self._try_state().z
        return dict(
            initial_z=round(initial_z, 4),
            target_z=round(target_z, 4),
            final_z=round(final_z, 4),
        )

    def test_wiggle(self, dz: float = 2.0):
        """Test communication by wiggling robot up/down in z"""
        print(f'Testing PF with {dz}mm z wiggle...')

        initial_z = self._try_state().z
        print(f'Initial z: {initial_z:.2f}mm')

        self.hp()
        self.attach()
        self.movec_rel(d_z=dz)
        up_z = self._try_state().z
        print(f'Up z: {up_z:.2f}mm')

        self.movec_rel(d_z=-dz)
        final_z = self._try_state().z
        print(f'Final z: {final_z:.2f}mm')

        up_diff = up_z - initial_z
        return_diff = final_z - initial_z
        print(f'Up diff: {up_diff:.2f}mm, Final diff: {return_diff:.2f}mm')
        return dict(
            up_diff=round(up_diff, 3),
            return_diff=round(return_diff, 3),
            initial_z=round(initial_z, 3),
            up_z=round(up_z, 3),
            final_z=round(final_z, 3),
            rounding=self.test_round_z(),
        )

    def test_estop(self, dz: float = 5.0):
        """Test E-stop by interrupting a long z movement"""
        print(f'Testing E-stop with {dz}mm z movement...')

        initial_z = self._try_state().z
        print(f'Initial z: {initial_z:.2f}mm')

        self.hp()
        self.attach()

        # Queue to communicate between threads
        result_queue = queue.Queue[str]()

        def move_thread():
            try:
                self.movec_rel(d_z=dz)
                result_queue.put('erroneously completed')
            except Exception as e:
                result_queue.put(f'correctly interrupted: {e}')

        # Start movement in separate thread
        other_thread = threading.Thread(target=move_thread)
        other_thread.start()

        # Wait short time then send E-stop
        time.sleep(0.1)
        print('Sending E-stop...')
        self.stop_and_reattach()

        # Wait for thread to finish
        other_thread.join()
        interrupt_result = result_queue.get()
        print(f'Move result: {interrupt_result}')

        # Check where we ended up
        interrupt_z = self._try_state().z
        travelled_z = interrupt_z - initial_z
        print(f'Interrupted at z: {interrupt_z:.2f}mm (travelled_z: {travelled_z:.2f}mm)')

        # Return to initial position
        print('Returning to initial position...')
        self.stop_and_reattach()
        return_dz = initial_z - interrupt_z
        self.movec_rel(d_z=return_dz)

        final_z = self._try_state().z
        return_diff = final_z - initial_z
        print(f'Final z: {final_z:.2f}mm (diff from start: {return_diff:.2f}mm)')

        res = dict(
            travelled_z=round(travelled_z, 3),
            return_diff=round(return_diff, 3),
            initial_z=round(initial_z, 3),
            interrupt_z=round(interrupt_z, 3),
            final_z=round(final_z, 3),
            interrupt_result=interrupt_result,
            rounding=self.test_round_z(),
        )

        if 'correctly interrupted' not in interrupt_result:
            raise ValueError(f'E-stop did not fire correctly: {res}')
        else:
            return res

    def test_repeatedly(self, N: int = 10, dz: float = 2.0):
        """
        Run test_wiggle and test_estop repeatedly.

        Put dz to zero to verify that the estop firing is not fast enough.
        """
        res: list[Any] = []
        zs: list[Any] = []
        for _ in range(N):
            res += [self.test_wiggle(dz)]
            zs += [self._try_state().z]
            res += [self.test_estop(dz)]
            zs += [self._try_state().z]
            dz = -dz
        return res, zs


@dataclass(frozen=True)
class Socket:
    name: str
    sock: socket.socket
    file: BinaryIO = field(compare=False, repr=False)

    @staticmethod
    def create(name: str, host: str, port: int):
        sock = socket.create_connection((host, port))
        this = Socket(name, sock, sock.makefile('rb'))
        return this

    @staticmethod
    @contextlib.contextmanager
    def create_temp(name: str, host: str, port: int):
        sock = socket.create_connection((host, port))
        this = Socket(name, sock, sock.makefile('rb'))
        try:
            yield this
        finally:
            try:
                this.file.close()
                sock.close()
                log(name, f'{name} socket closed')
            except Exception as e:
                log(name, f'Error closing {name} socket: {e}')

    def __post_init__(self):
        log(self.name, f'{self.name} {self.sock}')

    def close(self):
        try:
            self.sock.close()
        except Exception as e:
            log(self.name, f'Error closing {self.name} socket: {e}')
        try:
            self.file.close()
        except Exception as e:
            log(self.name, f'Error closing {self.name} file: {e}')

    def send(self, msg: str):
        msg = msg.strip() + '\n'
        msg_bytes = msg.encode('ascii')
        log(self.name, f'{self.name}.send({msg_bytes!r})')
        bytes_sent = self.sock.send(msg_bytes)
        if bytes_sent != len(msg_bytes):
            log(
                self.name,
                f'{self.name} sent {bytes_sent} bytes != {len(msg_bytes)} bytes!',
            )

    def read_line(self):
        raw_line = self.file.readline()
        try:
            line = raw_line.decode('ascii')
        except UnicodeDecodeError as e:
            log(
                self.name,
                f'{self.name}.read_line() decode error: {e}, raw bytes: {raw_line!r}',
            )
            raise ValueError(f'Failed to decode ASCII: {raw_line!r}') from e

        line = line.rstrip('\r\n')
        log(self.name, f'{self.name}.read_line() = {line!r}')
        return line

    def iter_lines(self):
        # Iterate over lines from the socket using file interface
        for line in self.file:
            log(self.name, f'{self.name}.read() = {line!r}')
            # Filter telnet sequences
            line = re.sub(b'\xff[\xfb-\xfe].', b'', line)
            line = re.sub(b'\xff[\xf0-\xfa]', b'', line)
            yield line.decode('ascii').rstrip('\r\n')

    def send_and_recv(self, msg: str):
        self.send(msg)
        return self.read_line()


_EmptySentinel = object()


@dataclass(frozen=False)
class Box(Generic[A]):
    """
    A mutable box, starts out empty
    """

    _raw_value: A = cast(Any, _EmptySentinel)

    @property
    def is_empty(self) -> bool:
        return self._raw_value is _EmptySentinel

    @property
    def value(self) -> A:
        if self.is_empty:
            raise ValueError('Box empty!')
        else:
            return self._raw_value

    def try_value(self) -> A | None:
        if self.is_empty:
            return None
        else:
            return self._raw_value

    def set_value(self, new_value: A):
        self._raw_value = new_value

    def set_empty(self):
        self._raw_value = cast(Any, _EmptySentinel)

