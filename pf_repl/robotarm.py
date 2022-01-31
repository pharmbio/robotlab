from __future__ import annotations

from dataclasses import dataclass
from typing import *

import socket
from utils import Mutable
from pathlib import Path
from ftplib import FTP
import io
import time

DEFAULT_HOST='10.10.0.98'

def ftp_store(ftp: FTP, filename: str, data: bytes):
    ftp.storbinary(f'STOR {filename}', io.BytesIO(data))

@dataclass(frozen=True)
class Robotarm:
    # sock: socket.socket
    host: str
    data: Mutable[str] = Mutable.factory('')

    @staticmethod
    def init(host: str=DEFAULT_HOST, port: int=23, password: str='Help') -> Robotarm:
        # sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # sock.connect((host, port))
        arm = Robotarm(host)
        print(next(arm.recv()))
        arm.send(password)
        print(next(arm.recv()))
        arm.wait_for_ready()
        return arm

    def recv(self):
        yield ''

    def flash(self):
        self.send('stop -all')
        # time.sleep(0.5)
        self.wait_for_ready('stop')
        self.send('unload -all')
        # time.sleep(0.5)
        self.wait_for_ready('unload')
        project = Path('Tcp_cmd_server')
        dir = f'/flash/projects/{project}'
        self.execute(f'File.CreateDirectory("{dir}")')
        self.wait_for_ready('mkdir')
        with FTP(self.host) as ftp:
            ftp.login()
            for path in project.glob('*.gp*'):
                print('ftp store', path.name)
                ftp_store(ftp, f'{dir}/{path.name}', path.read_bytes())
        for cmd in [
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
        # time.sleep(0.1)
        # self.log(msg)
        # for line in self.recv():
        #     if line.startswith(f'log {msg}') :
        #         time.sleep(0.1)
        #         return
        pass

    def send(self, msg: str):
        print('>>>', msg)
        msg += '\n'
        # self.sock.sendall(msg.encode())
        # time.sleep(0.1)

    def execute(self, stmt: str):
        self.send(f'execute {stmt}')

    def log(self, msg: str):
        assert '"' not in msg
        self.execute(f'Console.WriteLine("log {msg}")')

    def close(self):
        pass
        # self.sock.close()

