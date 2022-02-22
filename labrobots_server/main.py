'''
This server is a python flask server which calls the biotek repl executable
(which in turn communicates with the BioTek instruments)
and the liconic repl as a subprocess (which in turn communicates with the incubator)
'''

import ast
import sys
import threading
import time
from argparse import ArgumentParser

from dataclasses import dataclass, field
from queue import Queue
from subprocess import Popen, PIPE, STDOUT
from typing import Any, List, Tuple

from flask import Flask, jsonify

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols\\"

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
                        print(t, self.name, f"exit code: {exc}")
                        lines += [f"exit code: {exc}"]
                        return lines
                    line = stdout.readline().rstrip()
                    t = round(time.monotonic() - t0, 3)
                    short_line = line
                    if len(short_line) > 250:
                        short_line = short_line[:250] + '... (truncated)'
                    print(t, self.name, short_line)
                    if line.startswith('ready'):
                        return lines, value
                    value_line = False
                    if line.startswith('value'):
                        try:
                            value = ast.literal_eval(line[len('value '):])
                            value_line = True
                        except:
                            pass
                    if not value_line:
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

def main():
    parser = ArgumentParser('labrobots_server')
    parser.add_argument('--port', type=int, default=5050)
    parser.add_argument('--host', type=str, default='10.10.0.56')
    parser.add_argument('--test', action='store_true', default=False)
    args = parser.parse_args(sys.argv[1:])
    main_with_args(port=args.port, host=args.host, test=args.test)

def main_with_args(port: int, host: str, test: bool):
    import os
    if os.name == 'posix':
        dir_list = 'labrobots-dir-list-repl'
        example = 'labrobots-example-repl'
        incu = 'incubator-repl'
    else:
        dir_list = 'labrobots-dir-list-repl.exe'
        example = 'labrobots-example-repl.exe'
        incu = 'incubator-repl.exe'
    if test:
        machines = {
            'example': Machine('example', args=[example]),
            'dir_list': Machine('dir_list', args=[dir_list, '--root-dir', '.', '--extension', 'py']),
        }
    else:
        machines = {
            'example': Machine('example', args=[example]),
            'dir_list': Machine('dir_list', args=[dir_list, '--root-dir', PROTOCOLS_ROOT, '--extension', 'LHC']),
            'incu': Machine('incu', args=[incu]),
            'wash': Machine(
                'wash',
                args=[LHC_CALLER_CLI_PATH, "405 TS/LS", "USB 405 TS/LS sn:191107F", PROTOCOLS_ROOT],
            ),
            'disp': Machine(
                'disp',
                args=[LHC_CALLER_CLI_PATH, "MultiFloFX", "USB MultiFloFX sn:19041612", PROTOCOLS_ROOT],
            ),
        }

    app = Flask(__name__)
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
    app.config['JSON_SORT_KEYS'] = False             # type: ignore

    @app.route('/<machine>')                   # type: ignore
    @app.route('/<machine>/<cmd>')             # type: ignore
    @app.route('/<machine>/<cmd>/<path:arg>')  # type: ignore
    def _(machine: str, cmd: str="", arg: str=""):
        arg = arg.replace('/', '\\')
        return jsonify(machines[machine].message(cmd, arg))

    app.run(host=host, port=port, threaded=True, processes=1)

if __name__ == '__main__':
    main()

def example_repl():
    while True:
        print("ready")
        line = input()
        print("message", line)
        if "error" in line:
            print("error")
        else:
            print("success")

