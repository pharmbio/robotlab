from __future__ import annotations

from dataclasses import dataclass
from typing import *

import re
import socket
import json

import guidance_code

@dataclass(frozen=True)
class Robotarm:
    sock: socket.socket

    @staticmethod
    def init(host: str, port: int=23, password: str='Help') -> Robotarm:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        res = Robotarm(sock)
        res.send('Help')
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
            if re.match(r'\S+:\d', line):
                print(line)
            elif line.startswith('log'):
                print(line)
            else:
                try:
                    v = json.loads(line)
                    print(v)
                except ValueError:
                    pass
        # print(data, end='')
        return data

    def send(self, msg: str):
        msg += '\n'
        self.sock.sendall(msg.encode())

    def close(self):
        self.sock.close()

project = '''
ProjectBegin
ProjectName="imx_helper"
ProjectStart="Main"
ProjectSource="Main.gpl"
ProjectEnd
'''

def main():
    arm = Robotarm.init('10.10.0.98')
    end_of_text = '\u0003'
    arm.send('execute File.CreateDirectory("/flash/projects/imx_helper")')
    arm.send('create /flash/projects/imx_helper/Project.gpr' + '\n' + project + '\n' + end_of_text)
    arm.send('create /flash/projects/imx_helper/Main.gpl' + '\n' + guidance_code.module + '\n' + end_of_text)
    arm.send('unload -all')
    arm.send('load /flash/projects/imx_helper -compile')
    arm.send('execute Run()')
    arm.send('execute Console.WriteLine("log bye bye")')
    arm.send('quit')
    arm.recv_until('^Exiting console task')

if __name__ == '__main__':
    main()

