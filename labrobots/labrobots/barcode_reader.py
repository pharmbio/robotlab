from typing import *
from dataclasses import *

import traceback

from threading import Thread
from datetime import datetime

from serial import Serial # type: ignore

from .machine import Machine, Cell, make_log_handle

@dataclass(frozen=True)
class BarcodeReader(Machine):
    com_port: str
    current_barcode: Cell[str] = field(default_factory=lambda: Cell(''))

    def init(self):
        Thread(target=self._scanner_thread, daemon=True).start()

    def _scanner_thread(self):
        log = make_log_handle('barcode')
        scanner: Any = Serial(self.com_port, timeout=60)
        log('using com_port', self.com_port)
        while True:
            try:
                b: bytes = scanner.read_until(b'\r')
                line = b.decode('ascii')
            except Exception as e:
                self.current_barcode.value = str(e)
                lines = traceback.format_exc().splitlines(keepends=False)
                for line in lines:
                    log(line)
                continue
            line = line.strip()
            if line:
                self.current_barcode.value = line
                log(f'recv({line!r})', line=line)

    def read(self):
        return self.current_barcode.value

    def clear(self):
        self.current_barcode.value = ''

    def read_and_clear(self):
        val = self.read()
        self.clear()
        return val

