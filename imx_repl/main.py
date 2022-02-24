from typing import Any

import json
import os
import traceback

from serial import Serial # type: ignore

COM_PORT = os.environ.get('COM_PORT', 'COM4')
imx: Any = Serial(COM_PORT, timeout=5)
def main():
    print('message using COM_PORT', COM_PORT)
    while True:
        try:
            print('ready')
            line = input()
            if line.startswith('{'):
                form = json.loads(line)
                msg_str: str = '1,' + form['msg']
            else:
                cmd, sep, arg = line.partition(' ')
                if sep:
                    msg_str = '1,' + cmd + ',' + arg
                else:
                    msg_str = '1,' + cmd
            msg = msg_str.strip().encode()
            assert b'\n' not in msg
            assert b'\r' not in msg
            msg = msg + b'\r\n'
            n = imx.write(msg)
            print('message sent', n, 'bytes:', repr(msg))
            reply_bytes: bytes = imx.readline()
            print('message reply', repr(reply_bytes))
            reply = reply_bytes.decode().strip()
            if reply and 'ERROR' not in reply:
                print('success')
            else:
                print('error')
            print('value', json.dumps(reply))
        except Exception as e:
            traceback.print_exc()
            print('error', e)

if __name__ == '__main__':
    main()
