from __future__ import annotations

from dataclasses import *
from typing import *

from .moves import Move, MoveList
from .ur_script import URScript

from labrobots.log import Log
import contextlib

import sys
import re
import socket

@contextlib.contextmanager
def ur_handler(log: Log):
    try:
        yield
    except OSError as e:
        try:
            extra_info = dict(
                repr=repr(e),
                as_dict=repr(e.__dict__),
            )
        except:
            extra_info = {}
        log(str(e), **extra_info)
        raise ValueError(f'UR robotarm communication error: {e}')

@dataclass(frozen=True)
class ConnectedUR:
    sock: socket.socket
    log: Log

    def send(self, prog_str: str) -> None:
        with ur_handler(self.log):
            if not prog_str.endswith('\n'):
                prog_str = prog_str + '\n'
            self.log(f'arm.send({prog_str[:100]!r})  // length: {len(prog_str)}')
            prog_bytes = prog_str.encode()
            self.sock.sendall(prog_bytes)

    def recv(self) -> Iterator[bytes]:
        with ur_handler(self.log):
            while True:
                data = self.sock.recv(4096)
                pattern = r'[\x20-\x7e]*(?:log|fatal|program|assert|\w+exception|error|\w+_\w+:)[\x20-\x7e]*'
                for m in re.findall(pattern.encode('ascii'), data, re.IGNORECASE):
                    msg: str = m.decode(errors='replace')
                    self.log(f'arm.read() = {msg!r}')
                    if 'error' in msg:
                        print('ur:', msg, file=sys.stderr)
                    if 'fatal' in msg:
                        self.send('textmsg("log panic stop")\n')
                        raise RuntimeError(msg)
                yield data

    def recv_until(self, needle: str) -> None:
        with ur_handler(self.log):
            for data in self.recv():
                if needle.encode() in data:
                    self.log(f'received {needle}')
                    return

    def close(self) -> None:
        with ur_handler(self.log):
            self.sock.close()

@dataclass(frozen=True)
class UR:
    host: str
    port: int

    @contextlib.contextmanager
    def connect(self, quiet: bool=True, write_to_log_db: bool=True):
        if write_to_log_db:
            log = Log.make('ur', stdout=not quiet)
        else:
            log = Log.without_db(stdout=not quiet)
        with ur_handler(log):
            with contextlib.closing(socket.create_connection((self.host, self.port), timeout=60)) as sock:
                yield ConnectedUR(sock, log=log)

    def set_speed(self, value: int):
        if not (0 < value <= 100):
            raise ValueError(f'Speed out of range: {value=}')
        with self.connect() as arm:
            # The speed is set on the RTDE interface on port 30003:
            arm.send(URScript.reindent(f'''
                sec set_speed():
                    socket_open("127.0.0.1", 30003)
                    socket_send_line("set speed {value/100}")
                    socket_close()
                    textmsg("log speed changed to {value}")
                end
            '''))

    def stop(self):
        with self.connect() as arm:
            arm.send('textmsg("log quit")\n')
            arm.recv_until('quit')

    def execute_moves(self, movelist: list[Move], name: str='script', allow_partial_completion: bool=False, with_gripper: bool=True) -> None:
        script = MoveList(movelist).make_ur_script(with_gripper=with_gripper, name=name)
        return self.execute_script(script, allow_partial_completion=allow_partial_completion)

    def execute_script(self, script: URScript, allow_partial_completion: bool=False) -> None:
        with self.connect() as arm:
            arm.send(script.code)
            if allow_partial_completion:
                arm.recv_until(f'PROGRAM_XXX_STOPPED{script.name}')
            else:
                arm.recv_until(f'log {script.name} done')

