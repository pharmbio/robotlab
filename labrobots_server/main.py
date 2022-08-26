'''
This server is a python flask server which calls the biotek repl executable
(which in turn communicates with the BioTek instruments)
and the liconic repl as a subprocess (which in turn communicates with the incubator)
'''

import ast
import sys
import threading
import time
import platform
import os
import json
from argparse import ArgumentParser

from dataclasses import dataclass, field
from queue import Queue
from subprocess import Popen, PIPE, STDOUT
from typing import Any, List, Tuple

from flask import Flask, jsonify, request

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
LHC_PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols\\"
HTS_PROTOCOLS_ROOT = "C:\\Users\\MolDev\\Desktop\\Protocols\\Plate protocols\\"

LOCAL_IP = {
    'WINDOWS-NUC': '10.10.0.56', # connected to the bioteks and 37C incubator
    'WINDOWS-GBG': '10.10.0.97', # connected to the fridge incubator in imx room
    'ImageXpress': '10.10.0.99', # connected to the imx
}

@dataclass
class Machine:
    name: str
    args: List[str]

    input_queue: 'Queue[Tuple[str, Queue[Any]]]' = field(default_factory=Queue)
    is_ready: bool = False

    def __post_init__(self):
        threading.Thread(target=self.handler, daemon=True).start()

    def message(self, cmd: str, arg: str=""):
        if self.is_ready:
            reply_queue: Queue[Any] = Queue()
            if arg:
                msg = cmd + ' ' + arg
            else:
                msg = cmd
            self.input_queue.put((msg, reply_queue))
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

            def read_until_ready(t0: float):
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

            lines = read_until_ready(time.monotonic())
            while True:
                self.is_ready = True
                msg, reply_queue = self.input_queue.get()
                self.is_ready = False
                t0 = time.monotonic()
                stdin.write(msg + '\n')
                stdin.flush()
                lines, value = read_until_ready(t0)
                success = any(line.startswith('success') for line in lines)
                response = dict(lines=lines, success=success)
                if value is not None:
                    response['value'] = value
                reply_queue.put_nowait(response)

def exe(path: str) -> str:
    if os.name == 'posix':
        return path
    else:
        return path + '.exe'

def main():
    parser = ArgumentParser('labrobots_server')
    parser.add_argument('--port', type=int, default=5050)
    parser.add_argument('--host', type=str, default='default')
    parser.add_argument('--test', action='store_true', default=False)
    parser.add_argument('--node-name', type=str, default=platform.node())
    args = parser.parse_args(sys.argv[1:])
    node_name = args.node_name
    host = args.host
    if host == 'default':
        host = LOCAL_IP.get(node_name, 'localhost')
    main_with_args(port=args.port, host=host, test=args.test, node_name=node_name)

def main_with_args(port: int, host: str, test: bool, node_name: str):
    if test:
        node_name = 'test'

    print('node_name:', node_name)

    if node_name == 'WINDOWS-GBG':
        machines = [
            Machine('example',  args=[exe('labrobots-example-repl')]),
            Machine('fridge',   args=[exe('incubator-repl')]),
            Machine('barcode',  args=[exe('barcode-repl')]),
            Machine('imx',      args=[exe('imx-repl')]),
        ]
    elif node_name == 'WINDOWS-NUC':
        machines = [
            Machine('example',  args=[exe('labrobots-example-repl')]),
            Machine('incu',     args=[exe('incubator-repl')]),
            Machine('wash',     args=[LHC_CALLER_CLI_PATH, "405 TS/LS", "USB 405 TS/LS sn:191107F", LHC_PROTOCOLS_ROOT]),
            Machine('disp',     args=[LHC_CALLER_CLI_PATH, "MultiFloFX", "USB MultiFloFX sn:19041612", LHC_PROTOCOLS_ROOT]),
            Machine('dir_list', args=[exe('labrobots-dir-list-repl'), '--root-dir', LHC_PROTOCOLS_ROOT, '--extension', 'LHC']),
        ]
    elif node_name == 'ImageXpress':
        machines = [
            Machine('example',  args=[exe('labrobots-example-repl')]),
            Machine('dir_list', args=[exe('labrobots-dir-list-repl'), '--root-dir', HTS_PROTOCOLS_ROOT, '--extension', 'HTS']),
        ]
    else:
        machines = [
            Machine('example',  args=[exe('labrobots-example-repl')]),
            Machine('dir_list', args=[exe('labrobots-dir-list-repl'), '--root-dir', '.', '--extension', 'py']),
        ]

    machine_by_name = {m.name: m for m in machines}
    print('machines:', list(machine_by_name.keys()))

    app = Flask(__name__)
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
    app.config['JSON_SORT_KEYS'] = False             # type: ignore

    @app.get('/<machine>')                   # type: ignore
    @app.get('/<machine>/<cmd>')             # type: ignore
    @app.get('/<machine>/<cmd>/<path:arg>')  # type: ignore
    def get(machine: str, cmd: str="", arg: str=""):
        arg = arg.replace('/', '\\')
        return jsonify(machine_by_name[machine].message(cmd, arg))

    @app.post('/<machine>') # type: ignore
    def post(machine: str):
        cmd = json.dumps(request.form)
        return jsonify(machine_by_name[machine].message(cmd))

    _ = get, post # mark them as used for typechecker

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
