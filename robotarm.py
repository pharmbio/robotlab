from __future__ import annotations

from dataclasses import dataclass
from typing import *

import re
import socket
import json
from moves import Move

DEFAULT_HOST='10.10.0.98'

@dataclass(frozen=True)
class Robotarm:
    sock: socket.socket
    on_json: Callable[[Any], None] | None = None

    @staticmethod
    def init(host: str=DEFAULT_HOST, port: int=23, password: str='Help', on_json: Callable[[Any], None] | None = None) -> Robotarm:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        arm = Robotarm(sock, on_json)
        arm.send(password)
        arm.wait_for_ready()
        return arm

    def flash(self):
        end_of_text = '\u0003'
        self.send('execute File.CreateDirectory("/flash/projects/imx_helper")')
        files = [
            'Project.gpr',
            'Main.gpl',
        ]
        for name in files:
            content = open(name, 'r').read()
            self.send(f'create /flash/projects/imx_helper/{name}\n{content}{end_of_text}')
        self.send('unload -all')
        self.send('load /flash/projects/imx_helper -compile')
        self.log('flash done')
        self.recv_until('flash done')

    def quit(self):
        self.send('quit')
        self.recv_until('Exiting console task')
        self.close()

    def wait_for_ready(self):
        self.log('ready')
        self.recv_until('log ready')

    def recv_until(self, line_start: str):
        data = ''
        while True:
            b = self.sock.recv(4096)
            data += b.decode(errors='replace')
            if '\n' in data:
                print(data.splitlines())
            if data.startswith(line_start):
                break
            if ('\n' + line_start) in data:
                break
        for line in data.splitlines():
            try:
                v = json.loads(line)
                if self.on_json:
                    self.on_json(v)
                else:
                    print(v)
            except ValueError:
                if re.match(r'\S+:\d', line):
                    print(line)
                elif line.startswith('log'):
                    print(line)
                elif line.startswith('*'):
                    print(line)
        # print(data, end='', flush=True)
        return data

    def send(self, msg: str):
        msg += '\n'
        self.sock.sendall(msg.encode())

    def log(self, msg: str):
        assert '"' not in msg
        self.send(f'execute Console.WriteLine("log {msg}")')

    def close(self):
        self.sock.close()

    def set_speed(self, value: int) -> Robotarm:
        if not (0 < value <= 100):
            raise ValueError
        self.send(f'execute Controller.SystemSpeed = {value}')
        return self

    def execute_moves(self, movelist: list[Move], name: str='script') -> None:
        for move in movelist:
            self.send(f'execute {move.to_script()}')
        name = name.replace('/', '_of_')
        name = name.replace(' ', '_')
        name = name.replace('-', '_')
        self.send(f'execute Move.WaitForEOM()')
        self.log(f'{name} done')
        self.recv_until(f'log {name} done')

