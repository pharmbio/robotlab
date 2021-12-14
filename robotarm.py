from __future__ import annotations

from dataclasses import dataclass, field
from typing import *

import re
import socket
import json
from moves import Move
from utils import Mutable
from queue import Queue
from threading import Thread, Lock

DEFAULT_HOST='10.10.0.98'

@dataclass(frozen=True)
class Robotarm:
    sock: socket.socket
    on_json: Callable[[Any], None] | None = None
    listeners: list[Queue[str]] = field(default_factory=list)
    lock_listeners: Lock = field(default_factory=Lock)
    nonces: Mutable[int] = Mutable.factory(0)

    @staticmethod
    def init(host: str=DEFAULT_HOST, port: int=23, password: str='Help', on_json: Callable[[Any], None] | None = None) -> Robotarm:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        arm = Robotarm(sock, on_json)
        t = Thread(target=lambda: arm.recv_worker(), daemon=True)
        t.start()
        arm.send(password)
        arm.wait_for_ready()
        return arm

    def recv_worker(self):
        data = ''
        while True:
            b = self.sock.recv(4096)
            data += b.decode(errors='replace')
            lines = data.splitlines(keepends=True)
            next_data = ''
            for line in lines:
                if '\n' in line:
                    self.handle_line(line)
                else:
                    if next_data:
                        print('warning: multiple "lines" without newline ending:', lines)
                    next_data += line
            data = next_data

    def handle_line(self, line: str):
        try:
            v = json.loads(line)
            if self.on_json:
                self.on_json(v)
            else:
                print(v)
        except ValueError:
            with self.lock_listeners:
                for ear in self.listeners:
                    ear.put_nowait(line)
            if re.match(r'\S+:\d', line):
                print(line)
            elif line.startswith('log'):
                print(line)
            elif line.startswith('*'):
                print(line)

    def flash(self):
        end_of_text = '\u0003'
        self.execute('File.CreateDirectory("/flash/projects/imx_helper")')
        files = '''
            Project.gpr
            Main.gpl
        '''
        for name in files.split():
            content = open(name, 'r').read()
            self.send(f'create /flash/projects/imx_helper/{name}\n{content}{end_of_text}')
        self.send('unload -all')
        self.send('load /flash/projects/imx_helper -compile')
        self.send('stop Tcp_cmd_server_pf400')
        self.send('stop TcpCom1')
        self.send('stop TcpCom2')
        self.send('stop TcpCom3')
        self.send('stop TcpCom4')
        self.execute('Init()')
        self.wait_for_ready('flash done')

    def quit(self):
        self.send('quit')
        self.recv_until('Exiting console task')
        self.close()

    def wait_for_ready(self, msg: str='ready'):
        self.nonces.value += 1
        i = self.nonces.value
        self.log(f'{msg} {i}')
        self.recv_until(f'log {msg} {i}')

    def recv_until(self, line_start: str):
        q = Queue[str]()
        with self.lock_listeners:
            self.listeners.append(q)
        while True:
            msg = q.get()
            if msg.startswith(line_start):
                break
        with self.lock_listeners:
            self.listeners.remove(q)

    def send(self, msg: str):
        msg += '\n'
        self.sock.sendall(msg.encode())

    def execute(self, stmt: str):
        self.send(f'execute {stmt}')

    def log(self, msg: str):
        assert '"' not in msg
        self.execute(f'Console.WriteLine("log {msg}")')

    def close(self):
        self.sock.close()

    def set_speed(self, value: int):
        if not (0 < value <= 100):
            raise ValueError
        self.execute(f'Controller.SystemSpeed = {value}')

    def execute_moves(self, movelist: list[Move], name: str='script') -> None:
        for move in movelist:
            self.execute(move.to_script())
        name = name.replace('/', '_of_')
        name = name.replace(' ', '_')
        name = name.replace('-', '_')
        self.wait_for_ready(f'{name} done')

