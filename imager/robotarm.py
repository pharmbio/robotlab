from __future__ import annotations

from dataclasses import dataclass, field
from typing import *

import socket
from collections import deque

from .utils import Mutable
from .moves import Move, MoveList, movelists

DEFAULT_HOST='10.10.0.98'
# DEFAULT_HOST='127.0.0.1'

@dataclass(frozen=True)
class Socket:
    sock: socket.socket
    lines: deque[str] = field(default_factory=deque)
    data: Mutable[str] = Mutable.factory('')

    def send(self, msg: str):
        msg = msg.strip() + '\n'
        self.sock.sendall(msg.encode())

    def read_line(self):
        while True:
            if self.lines:
                return self.lines.popleft()
            b = self.sock.recv(4096)
            self.data.value += b.decode(errors='replace').replace('\r\n', '\n').replace('\r', '\n')
            lines = self.data.value.splitlines(keepends=True)
            next_data = ''
            for line in lines:
                if '\n' in line:
                    line = line.rstrip()
                    if line:
                        self.lines.append(line)
                else:
                    if next_data:
                        print('warning: multiple "lines" without newline ending:', lines)
                    next_data += line
            self.data.value = next_data

    def close(self):
        self.sock.close()

@dataclass(frozen=True)
class Robotarm:
    sock: Socket
    quiet: bool

    @staticmethod
    def init(host: str=DEFAULT_HOST, port: int=10100, quiet: bool=False) -> Robotarm:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        return Robotarm(Socket(sock), quiet=quiet)

    def read_line(self):
        line = self.sock.read_line()
        if not self.quiet:
            print('<<<', line.strip())
        return line

    def send(self, msg: str):
        if not self.quiet:
            print('>>>', msg.strip())
        return self.sock.send(msg)

    def execute(self, msg: str):
        self.send(msg)
        return self.read_line()

    def close(self):
        self.sock.close()

    def execute_moves(self, ms: list[Move], before_each: Callable[[], None] | None = None):
        for m in ms:
            if before_each:
                before_each()
            self.execute(m.to_script())
            self.execute('WaitForEOM')

    def execute_movelist(self, name: str, before_each: Callable[[], None] | None = None):
        self.execute_moves(movelists[name], before_each=before_each)

    def set_speed(self, value: int):
        assert 1 <= value <= 100
        return self.execute(f'mspeed {value}')
