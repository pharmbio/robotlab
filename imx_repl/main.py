from typing import Any
import os
import json
from serial import Serial # type: ignore
import traceback

COM_PORT = os.environ.get('COM_PORT', 'COM5')
imx: Any = Serial(COM_PORT, timeout=5)
def main():
    print('message using COM_PORT', COM_PORT)
    while True:
        try:
            print('ready')
            line = input()
            form = json.loads(line)
            msg_str: str = form['msg']
            msg = msg_str.strip().encode()
            assert b'\n' not in msg
            assert b'\r' not in msg
            msg = msg + b'\r\n'
            n = imx.write(msg)
            print('message sent', n, 'bytes:', repr(msg))
            reply: bytes = imx.readline()
            print('message reply', repr(reply))
            value = {
                'sent': msg.decode().strip(),
                'reply': reply.decode().strip(),
            }
            print('value', json.dumps(value))
        except Exception as e:
            traceback.print_exc()
            print('error', e)

if __name__ == '__main__':
    main()
