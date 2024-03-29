from typing import *
from dataclasses import *

import traceback

from threading import Thread

from serial import Serial # type: ignore

from .machine import Machine, Cell, Log

@dataclass(frozen=True)
class BarcodeReader(Machine):
    com_port: str
    current_barcode: Cell[str] = field(default_factory=lambda: Cell(''))

    def init(self):
        Thread(target=self._scanner_thread, daemon=True).start()

    def _scanner_thread(self):
        self_log = Log.make('barcode')
        scanner: Any = Serial(self.com_port, timeout=60)
        self_log('using com_port', self.com_port)
        while True:
            try:
                b: bytes = scanner.read_until(b'\r')
                line = b.decode('ascii')
            except Exception as e:
                self.current_barcode.value = str(e)
                err_lines = traceback.format_exc().splitlines(keepends=False)
                for err_line in err_lines:
                    self_log('error:', err_line, err_line=err_line)
                continue
            line = line.strip()
            if line:
                self.current_barcode.value = line
                self_log(f'barcode.read() = {line!r}', line=line)

    def read(self):
        return self.current_barcode.value

    def clear(self):
        self.current_barcode.value = ''

    def read_and_clear(self):
        val = self.read()
        self.clear()
        return val

