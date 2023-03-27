from __future__ import annotations

from dataclasses import *
from typing import *

import socket
import contextlib

from labrobots.machine import Log

# from .moves import Move, MoveList, movelists

DEFAULT_HOST='10.10.0.98'
DEFAULT_HOST='127.0.0.1'

@dataclass(frozen=True)
class ConnectedPF:
    sock: socket.socket
    log: Log

    def read_line(self) -> str:
        msg = ''
        while True:
            msg_bytes = self.sock.recv(4096)
            msg = msg + msg_bytes.decode('ascii')
            msg = msg.replace('\r\n', '\n').replace('\r', '\n')
            lines = msg.splitlines(keepends=True)
            for line in lines:
                self.log(f'pf.read() = {line.strip()!r}')
            if lines[-1].endswith('\n'):
                return lines[-1]
            else:
                msg = lines[-1]
                self.log(f'Last line {msg!r} did not end with newline, continuing...')

    def send(self, msg: str):
        self.log(f'pf.send({msg!r})')
        return self.sock.send(msg.encode('ascii'))

    def send_and_recv(self, msg: str):
        self.send(msg)
        return self.read_line()

@dataclass(frozen=True)
class PF:
    host: str = '10.10.0.98'
    port: int = 10100

    @contextlib.contextmanager
    def connect(self, quiet: bool=True):
        with socket.create_connection((self.host, self.port), timeout=60) as sock:
            yield ConnectedPF(sock, log=Log.make('pf', stdout=not quiet))

    def set_speed(self, value: int):
        if not (0 < value <= 100):
            raise ValueError('Speed out of range: {value=}')
        with self.connect() as arm:
            arm.send_and_recv(f'mspeed {value}')

    def execute_moves(self, ms: list[Move]):
        with self.connect() as arm:
            for m in ms:
                arm.send_and_recv(m.to_script())
                arm.send_and_recv('WaitForEOM')

    def execute_movelist(self, name: str):
        self.execute_moves(movelists[name])

