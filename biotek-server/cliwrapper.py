#!/usr/bin/env python3
import sys
import os.path
import os
import json
from flask import Flask, jsonify
from subprocess import Popen, PIPE

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols"
PORT = int(os.environ.get('PORT', 5050))
HOST = os.environ.get('HOST', '10.10.0.56')

def try_json(s):
    try:
        cleaned = s.strip().replace("\\","\\\\").replace("\r", "\\r").replace("\n","\\n")
        return json.loads(cleaned)
    except:
        return s

def main():
    app = Flask(__name__)
    @app.route('/<machine>/<sub_cmd>')
    @app.route('/<machine>/<sub_cmd>/<path:path_arg>')
    def execute(machine, sub_cmd, path_arg=None):
        if machine == 'wash':
            BIOTEK_PRODUCT = "405 TS/LS"
            COM_PORT = "USB 405 TS/LS sn:191107F"
            ARGS = [LHC_CALLER_CLI_PATH, BIOTEK_PRODUCT, COM_PORT]
        elif machine == 'disp':
            BIOTEK_PRODUCT = "MultiFloFX"
            COM_PORT = "USB MultiFloFX sn:19041612"
            ARGS = [LHC_CALLER_CLI_PATH, BIOTEK_PRODUCT, COM_PORT]
        elif machine == 'echo':
            ARGS = ['echo']
        elif machine == 'help':
            ARGS = ['help.exe']
        else:
            raise ValueError(machine)
        args = [*ARGS, sub_cmd]
        if isinstance(path_arg, str):
            path_arg = os.path.join(PROTOCOLS_ROOT, path_arg)
            args += [path_arg]
        print('sub_cmd:', sub_cmd)
        print('path_arg:', path_arg)
        print('args:', args)
        proc = Popen(args, stdout=PIPE, stderr=PIPE, stdin=None)
        out, err = proc.communicate()
        out = try_json(out.decode(errors='replace'))
        err = try_json(err.decode(errors='replace'))
        return dict(out=out, err=err)

    app.run(host=HOST, port=PORT)

if __name__ == '__main__':
    main()

