from typing import Any, Dict, List, Union

import json
import os
import traceback

from threading import Thread
from datetime import datetime

from serial import Serial # type: ignore

COM_PORT = os.environ.get('COM_PORT', 'COM3')

last_seen: Dict[str, Union[str, List[str]]] = {
    'barcode': '',
    'date': '',
}

def scanner_thread():
    global last_seen
    scanner: Any = Serial(COM_PORT, timeout=60)
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

def main():
    global last_seen
    print('message using COM_PORT', COM_PORT)
    Thread(target=scanner_thread, daemon=True).start()
    while True:
        print('ready')
        cmd = input()
        valid = '''
            read
            clear
            read_and_clear
        '''.split()
        if cmd not in valid:
            print('error', cmd, 'not valid')
            print('error valid commands are', *valid)
            continue
        if 'read' in cmd:
            print('value', json.dumps(last_seen))
        if 'clear' in cmd:
            last_seen = {
                'barcode': '',
                'date': '',
            }
        print('success')

if __name__ == '__main__':
    main()

