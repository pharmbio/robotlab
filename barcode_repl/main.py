
from datetime import datetime
from typing import Any, Dict, List, Union

import json
import os
from threading import Lock, Thread
from serial import Serial # type: ignore
import traceback

COM_PORT = os.environ.get('COM_PORT', 'COM1')

scanner: Any = Serial(COM_PORT, timeout=5)
scanner_lock = Lock()

last_seen: Dict[str, Union[str, List[str]]] = {
    'barcode': '',
    'date': '',
}

def scanner_thread():
    global last_seen
    while True:
        try:
            b: bytes = scanner.readline()
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

def main():
    Thread(target=scanner_thread, daemon=True).start()
    while True:
        print("ready")
        _ = input()
        print("value", json.dumps(last_seen))
        print("success")

if __name__ == '__main__':
    main()

