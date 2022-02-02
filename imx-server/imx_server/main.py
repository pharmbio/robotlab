from typing import Any

import os

from threading import Lock
from flask import Flask, request
from serial import Serial # type: ignore

PORT = int(os.environ.get('PORT', 5050))
HOST = os.environ.get('HOST', '10.10.0.99')

COM_PORT=os.environ.get('COM_PORT', 'COM8')

imx: Any = Serial(COM_PORT, timeout=5)

imx_lock = Lock()

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
app.config['JSON_SORT_KEYS'] = False             # type: ignore

@app.post('/')  # type: ignore
def send():
    msg = request.form['msg']
    msg = msg.strip().encode()
    assert b'\n' not in msg
    assert b'\r' not in msg
    msg = msg + b'\r\n'
    with imx_lock:
        n = imx.write(msg)
        print('sent', n, 'bytes:', repr(msg))
        reply: bytes = imx.readline()
        print('reply', repr(reply))
    return {
        'sent': msg.decode().strip(),
        'reply': reply.decode().strip(),
    }

def main():
    app.run(host=HOST, port=PORT, threaded=True, processes=1)

if __name__ == '__main__':
    main()
