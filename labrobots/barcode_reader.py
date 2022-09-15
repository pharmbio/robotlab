import typing as t
from dataclasses import dataclass, field

import os
import traceback

from threading import Thread
from datetime import datetime

from serial import Serial # type: ignore

from .machine import Machine

COM_PORT = os.environ.get('COM_PORT', 'COM3')

@dataclass
class BarcodeReader(Machine):
    last_seen: t.Dict[str, t.Union[str, t.List[str]]] = field(default_factory=lambda: {
        'barcode': '',
        'date': '',
    })

    def __post_init__(self):
        print('message using COM_PORT', COM_PORT)
        Thread(target=self._scanner_thread, daemon=True).start()

    def _scanner_thread(self):
        global last_seen
        scanner: t.Any = Serial(COM_PORT, timeout=60)
        while True:
            try:
                b: bytes = scanner.read_until(b'\r')
                line = b.decode('ascii')
            except Exception as e:
                traceback.print_exc()
                last_seen = {
                    'error': str(e),
                    'traceback': traceback.format_exc().splitlines(keepends=False)
                }
                continue
            line = line.strip()
            if line:
                last_seen = {
                    'barcode': line,
                    'date': datetime.now().replace(microsecond=0).isoformat(sep=' ')
                }
                print('message', line)

    def read(self):
        return last_seen

    def clear(self):
        self.last_seen = {
            'barcode': '',
            'date': '',
        }

    def read_and_clear(self):
        val = self.read()
        self.clear()
        return val

