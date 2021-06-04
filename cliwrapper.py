#!/usr/bin/env python3
import sys
import os.path
import json
from flask import Flask, jsonify
from subprocess import Popen, PIPE

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols"

def try_json(s):
    try:
        return json.loads(s)
    except:
        return s

def main(machine):
    if machine == 'wash':
        BIOTEK_PRODUCT = "405 TS/LS"
        COM_PORT = "USB 405 TS/LS sn:191107F"
        CMD = [LHC_CALLER_CLI_PATH, BIOTEK_PRODUCT, COM_PORT]
        PORT = 5000
    elif machine == 'disp':
        BIOTEK_PRODUCT = "MultiFloFX"
        COM_PORT = "USB MultiFloFX sn:19041612"
        CMD = [LHC_CALLER_CLI_PATH, BIOTEK_PRODUCT, COM_PORT]
        PORT = 5001
    elif machine == 'echo':
        CMD = ['echo']
        PORT = 5005
    else:
        raise ValueError(machine)

    app = Flask(__name__)
    @app.route('/<subcmd>')
    @app.route('/<subcmd>/<path:arg>')
    def execute(subcmd, arg=None):
        argv = [*CMD, subcmd]
        if isinstance(arg, str):
            arg = os.path.join(PROTOCOLS_ROOT, arg)
            argv += [arg]
        print('subcmd:', subcmd)
        print('arg:', arg)
        print('argv:', argv)
        proc = Popen(argv, stdout=PIPE, stderr=PIPE, stdin=None)
        out, err = proc.communicate()
        out = try_json(out.decode(errors='replace'))
        err = try_json(err.decode(errors='replace'))
        return dict(out=out, err=err)

    app.run(host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    _, machine = sys.argv
    main(machine)

