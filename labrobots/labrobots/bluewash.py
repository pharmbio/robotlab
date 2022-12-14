from typing import *
from serial import Serial # type: ignore
from .machine import Machine
from dataclasses import *
from pathlib import Path

@dataclass(unsafe_hash=True)
class BlueWash(Machine):
    com_port: str = 'COM6'
    com: Any = None # Serial

    def init(self):
        print('bluewash: Using com_port', self.com_port)
        self.com = Serial(
            self.com_port,
            timeout=5,
            baudrate=115200
        )

    def write(self, line: str):
        self.com.write(line.strip().encode('ascii'))

    def run(self, filename: str):
        path = Path(filename)
        lines = path.read_text().splitlines(keepends=False)
        self.write('$deleteprog 99')
        self.write('$Copyprog 99 _' + path.name)
        for line in lines:
            self.write('$& ' + line)
        self.write('$%')
        # Expect Err=00 ... maybe something more
        self.write('$runprog 99')
        # check for Err=..
        # reply_bytes: bytes = self.com.readline()
        # print('message reply', repr(reply_bytes))
        # reply = reply_bytes.decode().strip()

