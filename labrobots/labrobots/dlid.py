from typing import *
from dataclasses import *

import traceback

from threading import Thread

import time

from serial import Serial # type: ignore

from .machine import Machine, Cell, Log

descriptions = {
    'L0': 'Delidder has released a lid',
    'L1': 'Delidder has gripped a lid',
    'w1': 'Transfer too fast. Microplate removed before target vacuum level reached.',
    'w2': 'Delid sensor not returned to rest state within timeout period',
    'w3': 'High vacuum level on startup, possible unexpected power loss',
    'w4': 'Pump voltage is not stable',
    'w5': 'Pump voltage level outside set tolerance',
    'w6': 'Button depressed longer than max timeout period',
    'w7': 'User setting data corrupted',
    'w8': 'User setting data backup corrupted',
    'w9': 'Factory setting data corrupted',
    'e1': 'startup process failed to complete within timeout period',
    'e2': 'unknown state on startup',
    'e3': 'Reset fail, vacuum pressure should be zero',
    'e4': 'Plate sensor is triggered',
    'e5': 'Lid grip failure',
    'e6': 'Lid dropped',
    'e7': 'Lid release failure',
    'e8': 'Lid release check failed',
    'e9': 'EEPROM memory corrupted, re-initialized to program defaults',
    'e10': 'Factory setting data backup corrupted',
    'e11': 'Neighbor Lost (Up Neighbor)',
    'e12': 'Network Length Changed',
    'e13': 'ID Changed',
    'e14': 'PC Link Lost',
    'e15': 'Message Buffer Overflow (Lost Messages)',
    'e16': 'Message String Buffer Overflow (Message Truncated)',
    'e17': 'Calibration Failure?',
}

@dataclass(frozen=True)
class DLid(Machine):
    com_port: str
    status: dict[str, str] = field(default_factory=dict)
    serial_cell: Cell[Serial | None] = field(default_factory=lambda: Cell(None))
    serial_log_cell: Cell[Log | None] = field(default_factory=lambda: Cell(None))

    def init(self):
        Thread(target=self._dlid_thread, daemon=True).start()

    @property
    def serial_log(self) -> Log:
        log = self.serial_log_cell.value
        if log is None:
            raise ValueError('No serial log registered!')
        return log

    def _dlid_thread(self):
        self.serial_log_cell.value = Log.make('dlid')
        serial = self.serial_cell.value = Serial(self.com_port, baudrate=57600, timeout=None)
        self.serial_log('using com_port', self.com_port)
        while True:
            try:
                b: bytes = serial.read_until(b'\r\n')
                line = b.decode('ascii')
            except:
                err_lines = traceback.format_exc().splitlines(keepends=False)
                for err_line in err_lines:
                    self.serial_log('error:', err_line, err_line=err_line)
                continue
            line = line.strip()
            if line.startswith('<'):
                id, sep, status = line.removeprefix('<').removesuffix('()').partition(': ')
                self.serial_log(
                    f'dlid.read() = {line!r} ({id=!r}, {status=!r}: {descriptions.get(status, "?")})',
                    line=line,
                    id=id,
                    status=status
                )
                if sep == ': ' and status.isalnum():
                    self.status[id] = status
            else:
                self.serial_log(f'dlid.read() = {line!r}', line=line)

    def send(self, id: str, message: str):
        serial = self.serial_cell.value
        if serial is None:
            raise ValueError('No serial registered!')
        line = f'>{id}: {message.strip()}\r\n'
        self.serial_log(f'dlid.write({line!r})', line=line)
        serial.write(line.encode('ascii'))

    def get_status(self, id: str) -> Literal['free', 'taken', 'error']:
        id = str(id)
        self.send(id, 'L?')
        self.status[id] = status = '?'
        for _ in range(20):
            status = self.status.get(id, '?')
            if status != '?':
                break
            else:
                time.sleep(0.1)
        match status:
            case 'L0':
                return 'free'
            case 'L1':
                return 'taken'
            case _:
                return 'error'
