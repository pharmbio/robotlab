from __future__ import annotations

from dataclasses import dataclass, field
from typing import *

import socket
from utils import Mutable
from queue import Queue
from pathlib import Path
from ftplib import FTP
import io

DEFAULT_HOST='10.10.0.98'

def ftp_store(ftp: FTP, filename: str, data: bytes):
    ftp.storbinary(f'STOR {filename}', io.BytesIO(data))

@dataclass(frozen=True)
class Robotarm:
    sock: socket.socket
    data: Mutable[str] = Mutable.factory('')

    @staticmethod
    def init(host: str=DEFAULT_HOST, port: int=23, password: str='Help') -> Robotarm:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        arm = Robotarm(sock)
        arm.send(password)
        arm.wait_for_ready()
        return arm

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

    def flash(self):
        project = Path('Tcp_cmd_server')
        dir = f'/flash/projects/{project}'
        self.execute(f'File.CreateDirectory("{dir}")')
        self.wait_for_ready('mkdir')
        with FTP('10.10.0.98') as ftp:
            ftp.login()
            for path in project.glob('*.gp*'):
                ftp_store(ftp, f'{dir}/{path.name}', path.read_bytes())
        for cmd in [
            'stop -all',
            'unload -all',
            f'load {dir} -compile',
            'execute StartMain()',
        ]:
            self.send(cmd)
            self.wait_for_ready(cmd.split(' ')[0])

    def quit(self):
        self.send('quit')
        for line in self.recv():
            if line.startswith('Exiting console task'):
                break
        self.close()

    def wait_for_ready(self, msg: str='ready'):
        self.log(msg)
        for line in self.recv():
            if line.startswith(f'log {msg}') :
                return

    def send(self, msg: str):
        print('>>>', msg)
        msg += '\n'
        self.sock.sendall(msg.encode())

    def execute(self, stmt: str):
        self.send(f'execute {stmt}')

    def log(self, msg: str):
        assert '"' not in msg
        self.execute(f'Console.WriteLine("log {msg}")')

    def close(self):
        self.sock.close()

