from __future__ import annotations

from dataclasses import dataclass
from typing import *

import socket
from utils import Mutable

DEFAULT_HOST='10.10.0.98'

@dataclass(frozen=True)
class Robotarm:
    sock: socket.socket
    data: Mutable[str] = Mutable.factory('')

    @staticmethod
    def init(host: str=DEFAULT_HOST, port: int=10100) -> Robotarm:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        return Robotarm(sock)

    def recv(self):
        while True:
            try:
                b = self.sock.recv(4096)
            except OSError as e:
                print(e)
                break
            self.data.value += b.decode(errors='replace').replace('\r\n', '\n').replace('\r', '\n')
            lines = self.data.value.splitlines(keepends=True)
            next_data = ''
            full_lines: list[str] = []
            for line in lines:
                if '\n' in line:
                    line = line.rstrip()
                    if line:
                        print('<<<', line)
                        full_lines += [line]
                else:
                    if next_data:
                        print('warning: multiple "lines" without newline ending:', lines)
                    next_data += line
            self.data.value = next_data
            yield from full_lines

    def wait_for_ready(self, msg: str='ready'):
        pass

    def send(self, msg: str):
        print('>>>', msg)
        msg += '\n'
        self.sock.sendall(msg.encode())

    def close(self):
        self.sock.close()

