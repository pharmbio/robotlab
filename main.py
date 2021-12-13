from __future__ import annotations

from dataclasses import dataclass
from typing import *

import re
import socket
import json

@dataclass(frozen=True)
class Robotarm:
    sock: socket.socket

    @staticmethod
    def init(host: str, port: int=23, password: str='Help') -> Robotarm:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        res = Robotarm(sock)
        res.send(password)
        res.wait_for_ready()
        return res

    def wait_for_ready(self):
        self.send('echo ready')
        self.recv_until('^ready')

    def recv_until(self, regex: str):
        data = ''
        while not re.search(regex, data, flags=re.MULTILINE):
            b = self.sock.recv(4096)
            data += b.decode(errors='replace')
        for line in data.splitlines():
            try:
                v = json.loads(line)
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

    def close(self):
        self.sock.close()

def main():
    arm = Robotarm.init('10.10.0.98')
    end_of_text = '\u0003'
    arm.send('execute File.CreateDirectory("/flash/projects/imx_helper")')
    files = [
        'Project.gpr',
        'Main.gpl',
    ]
    for name in files:
        content = open(name, 'r').read()
        arm.send(f'create /flash/projects/imx_helper/{name}\n{content}{end_of_text}')
    arm.send('unload -all')
    arm.send('load /flash/projects/imx_helper -compile')
    arm.send('execute Run()')
    arm.send('execute Console.WriteLine("log bye bye")')
    arm.send('quit')
    arm.recv_until('^Exiting console task')

if __name__ == '__main__':
    main()

