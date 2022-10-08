from typing import *
from dataclasses import dataclass, field

import os
import traceback

from threading import Thread
from datetime import datetime

from serial import Serial # type: ignore

from .machine import Machine


@dataclass
class BarcodeReader(Machine):
    last_seen: Dict[str, Union[str, List[str]]] = field(default_factory=lambda: {
        'barcode': '',
        'date': '',
    })

    def init(self):
        Thread(target=self._scanner_thread, daemon=True).start()

    def _scanner_thread(self):
        COM_PORT: str = os.environ.get('BARCODE_COM_PORT', 'COM3')
        print('barcode_reader: Using BARCODE_COM_PORT', COM_PORT)
        scanner: Any = Serial(COM_PORT, timeout=60)
        while True:
            try:
                b: bytes = scanner.read_until(b'\r')
                line = b.decode('ascii')
            except Exception as e:
                traceback.print_exc()
                self.last_seen = {
                    'error': str(e),
                    'traceback': traceback.format_exc().splitlines(keepends=False)
                }
                continue
            line = line.strip()
            if line:
                self.last_seen = {
                    'barcode': line,
                    'date': datetime.now().replace(microsecond=0).isoformat(sep=' ')
                }
                print('message', line)

    def read(self):
        return self.last_seen

    def clear(self):
        self.last_seen = {
            'barcode': '',
            'date': '',
        }

    def read_and_clear(self):
        val = self.read()
        self.clear()
        return val

