import ast
import os
import os.path
import sys
import threading
import time

from dataclasses import dataclass, field
from queue import Queue
from subprocess import Popen, PIPE, STDOUT
from typing import Any, List, Tuple

from flask import Flask, jsonify

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols\\"
PORT = int(os.environ.get('PORT', 5050))
HOST = os.environ.get('HOST', '10.10.0.56')

@dataclass
class Machine:
    name: str
    args: List[str]

    input_queue: 'Queue[Tuple[str, str, Queue[Any]]]' = field(default_factory=Queue)
    is_ready: bool = False

    def __post_init__(self):
        threading.Thread(target=self.handler, daemon=True).start()

    def message(self, cmd: str, arg: str=""):
        if self.is_ready:
            reply_queue: Queue[Any] = Queue()
            self.input_queue.put((cmd, arg, reply_queue))
            return reply_queue.get()
        else:
            return dict(success=False, lines=["not ready"])

    def handler(self):
        with Popen(
            self.args,
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
            bufsize=1,  # line buffered
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
        ) as p:
            stdin = p.stdin
            stdout = p.stdout
            assert stdin
            assert stdout

            def read_to_ready(t0: float):
                lines: List[str] = []
                value: None = None
                while True:
                    exc = p.poll()
                    if exc is not None:
                        t = round(time.monotonic() - t0, 3)
                        lines += [(t, f"exit code: {exc}")]
                        return lines
                    line = stdout.readline().rstrip()
                    t = round(time.monotonic() - t0, 3)
                    print(t, self.name, line)
                    if line.startswith('ready'):
                        return lines, value
                    if line.startswith('value'):
                        try:
                            value = ast.literal_eval(line[len('value '):])
                        except:
                            pass
                    lines += [line]

            lines = read_to_ready(time.monotonic())
            while True:
                self.is_ready = True
                cmd, arg, reply_queue = self.input_queue.get()
                self.is_ready = False
                t0 = time.monotonic()
                stdin.write(cmd + ' ' + arg + '\n')
                stdin.flush()
                lines, value = read_to_ready(t0)
                success = any(line.startswith('success') for line in lines)
                response = dict(lines=lines, success=success)
                if value is not None:
                    response['value'] = value
                reply_queue.put_nowait(response)

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
            'example': Machine(
                'example',
                args=['python', __file__, "--example"]
            ),
        }
    else:
        machines = {
            'example': Machine(
                'example',
                args=['python', __file__, "--example"],
            ),
            'wash': Machine(
                'wash',
                args=[LHC_CALLER_CLI_PATH, "405 TS/LS", "USB 405 TS/LS sn:191107F", PROTOCOLS_ROOT],
            ),
            'disp': Machine(
                'disp',
                args=[LHC_CALLER_CLI_PATH, "MultiFloFX", "USB MultiFloFX sn:19041612", PROTOCOLS_ROOT],
            ),
            'incu': Machine(
                'incu',
                args=["python", "-u", "../incubator-repl/incubator.py"],
            ),
        }

    app = Flask(__name__)
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
    app.config['JSON_SORT_KEYS'] = False             # type: ignore

    @app.route('/<machine>/<cmd>')             # type: ignore
    @app.route('/<machine>/<cmd>/<path:arg>')  # type: ignore
    def execute(machine: str, cmd: str, arg: str=""):
        arg = arg.replace('/', '\\')
        return jsonify(machines[machine].message(cmd, arg))

    app.run(host=HOST, port=PORT, threaded=True, processes=1)

if __name__ == '__main__':
    if '--example' in sys.argv:
        example_main()
    else:
        main('--test' in sys.argv)

