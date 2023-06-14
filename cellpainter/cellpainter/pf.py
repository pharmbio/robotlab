from __future__ import annotations

from dataclasses import *
from typing import *

import socket
import contextlib
import time

from labrobots.log import Log

from .moves import Move, MoveList

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
            if not lines:
                continue
            if lines[-1].endswith('\n'):
                return lines[-1]
            else:
                msg = lines[-1]
                # self.log(f'Last line {msg!r} did not end with newline, continuing...')

    def send(self, msg: str):
        msg = msg.strip() + '\n'
        self.log(f'pf.send({msg!r})')
        return self.sock.send(msg.encode('ascii'))

    def send_and_recv(self, msg: str):
        self.send(msg)
        return self.read_line()

@dataclass(frozen=True)
class PF:
    host: str    # = 'localhost' # '10.10.0.98'
    port_rw: int = 10100
    port_ro: int = 10000

    @contextlib.contextmanager
    def connect(self, quiet: bool=True, write_to_log_db: bool=True, mode: Literal['ro', 'rw'] = 'rw'):
        port = self.port_rw if mode == 'rw' else self.port_ro
        for _retries in range(10):
            try:
                with contextlib.closing(socket.create_connection((self.host, port))) as sock:
                    if write_to_log_db:
                        log = Log.make('ur', stdout=not quiet)
                    else:
                        log = Log.without_db(stdout=not quiet)
                    yield ConnectedPF(sock, log=log)
                    break
            except ConnectionRefusedError:
                import traceback as tb
                import sys
                print(
                    'PF connection error:',
                    tb.format_exc(),
                    'Retrying in 1s',
                    sep='\n',
                    file=sys.stderr,
                )
                time.sleep(1)

    def set_speed(self, value: int):
        if not (0 < value <= 100):
            raise ValueError(f'Speed out of range: {value=}')
        with self.connect(quiet=False) as arm:
            arm.send_and_recv(f'mspeed {value}')

    def execute_moves(self, ms: list[Move]):
        with self.connect(quiet=False) as arm:
            for m in ms:
                for line in m.to_pf_script().split('\n'):
                    res = arm.send_and_recv(line)
                    if res.strip() != '0':
                        raise ValueError(f'PF returned {res!r} (should be {"0"!r}). Is it initialized?')
                arm.send_and_recv('WaitForEOM')

    def init(self):
        with self.connect(quiet=False) as arm:
            arm.send_and_recv('hp 1 60')
            arm.send_and_recv('attach 1')
            arm.send_and_recv('home 1')
