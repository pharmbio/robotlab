#!/usr/bin/env python3
import sys
import os.path
import os
import json
from flask import Flask, jsonify
from subprocess import Popen, PIPE, STDOUT
from queue import Queue
from typing import Callable, Any
import threading
import time

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols\\"
PORT = int(os.environ.get('PORT', 5050))
HOST = os.environ.get('HOST', '10.10.0.56')

def spawn(f: Callable[[], None]) -> None:
    threading.Thread(target=f, daemon=True).start()

def machine(name: str, args: list[str]):

    input_queue: Queue[tuple[str, str, Queue[Any]]] = Queue()
    is_ready: bool = False

    @spawn
    def handler():
        nonlocal is_ready
        with Popen(
            args,
            stdin=PIPE,
            stdout=PIPE,
            # stderr=STDOUT,
            stderr=PIPE,
            # bufsize=1,  # line buffered
            # universal_newlines=True,
            encoding='utf-8',
            # errors='replace',
            # capture_output=True,
        ) as p:
            stdin = p.stdin
            stdout = p.stdout
            assert stdin
            assert stdout

            def read_to_ready(t0: float):
                lines: list[tuple[float, str]] = []
                while True:
                    exc = p.poll()
                    if exc is not None:
                        t = round(time.monotonic() - t0, 3)
                        lines += [(t, f"exit code: {exc}")]
                        return lines
                    line = stdout.readline().strip()
                    t = round(time.monotonic() - t0, 3)
                    print(t, name, line)
                    if line.startswith('ready'):
                        return lines
                    else:
                        lines += [(t, line)]

            lines = read_to_ready(time.monotonic())
            print(f"{lines = }")
            while True:
                is_ready = True
                cmd, arg, reply_queue = input_queue.get()
                is_ready = False
                t0 = time.monotonic()
                stdin.write(cmd + ' ' + arg + '\n')
                stdin.flush()
                lines = read_to_ready(t0)
                success = any(line.startswith('success') for _, line in lines)
                reply_queue.put_nowait(dict(success=success, lines=lines))

    def message(cmd: str, arg: str=""):
        if is_ready:
            reply_queue: Queue[Any] = Queue()
            input_queue.put((cmd, arg, reply_queue))
            return reply_queue.get()
        else:
            return dict(success=False, lines=[(0.0, str("not ready"))])

    return message

def example_main():
    while True:
        print("ready")
        line = input()
        print("message", line)
        if "error" in line:
            print("error")
        else:
            print("success")

def main(test: bool):
    if test:
        machines = {
            'example': machine(
                'example',
                args=['python', __file__, "--example"]
            ),
        }
    else:
        machines = {
            'example': machine(
                'example',
                args=['python', __file__, "--example"],
            ),
            'wash': machine(
                'wash',
                args=[LHC_CALLER_CLI_PATH, "405 TS/LS", "USB 405 TS/LS sn:191107F"],
            ),
            'disp': machine(
                'disp',
                args=[LHC_CALLER_CLI_PATH, "MultiFloFX", "USB MultiFloFX sn:19041612"],
            ),
        }

    app = Flask(__name__)
    @app.route('/<machine>/<cmd>')             # type: ignore
    @app.route('/<machine>/<cmd>/<path:arg>')  # type: ignore
    def execute(machine: str, cmd: str, arg: str=""):
        return jsonify(machines[machine](cmd, arg))

    app.run(host=HOST, port=PORT, threaded=True, processes=1)

if __name__ == '__main__':
    if '--example' in sys.argv:
        example_main()
    else:
        main('--test' in sys.argv)

