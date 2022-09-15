'''
This server is a python flask server which calls the biotek repl executable
(which in turn communicates with the BioTek instruments)
and the liconic repl as a subprocess (which in turn communicates with the incubator)
'''

import sys
import platform
from argparse import ArgumentParser

from flask import Flask, jsonify, request

from .machine import Machine, Example
from .liconic import STX
from .barcode_reader import BarcodeReader
from .imx import IMX
from .dir_list import DirList
from .repl_wrap import ReplWrap

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
LHC_PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols\\"
HTS_PROTOCOLS_ROOT = "C:\\Users\\MolDev\\Desktop\\Protocols\\Plate protocols\\384-Well_Plate_Protocols\\"

LOCAL_IP = {
    'WINDOWS-NUC': '10.10.0.56', # connected to the bioteks and 37C incubator
    'WINDOWS-GBG': '10.10.0.97', # connected to the fridge incubator in imx room
    'ImageXpress': '10.10.0.99', # connected to the imx
}

def get_machines(node_name: str) -> dict[str, Machine]:
    if node_name == 'WINDOWS-GBG':
        return {
            'fridge':  STX(),
            'barcode': BarcodeReader(),
            'imx':     IMX(),
        }
    elif node_name == 'WINDOWS-NUC':
        return {
            'wash':     ReplWrap('wash', [LHC_CALLER_CLI_PATH, "405 TS/LS", "USB 405 TS/LS sn:191107F", LHC_PROTOCOLS_ROOT]),
            'disp':     ReplWrap('disp', [LHC_CALLER_CLI_PATH, "MultiFloFX", "USB MultiFloFX sn:19041612", LHC_PROTOCOLS_ROOT]),
            'dir_list': DirList(root_dir=LHC_PROTOCOLS_ROOT, ext='LHC'),
        }
    elif node_name == 'ImageXpress':
        return {
            'dir_list': DirList(root_dir=HTS_PROTOCOLS_ROOT, ext='HTS', enable_hts_mod=True),
        }
    elif node_name == 'test':
        return {
            'dir_list': DirList(root_dir='.', ext='py', enable_hts_mod=True),
        }
    else:
        raise ValueError('{node_name} not configured')

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

    machines = get_machines(node_name)
    machines['example'] = Example()

    print('machines:', list(machines.keys()))

    app = Flask(__name__)
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
    app.config['JSON_SORT_KEYS'] = False             # type: ignore

    for name, m in machines.items():
        m.serve(name, app)

    app.run(host=host, port=port, threaded=True, processes=1)

if __name__ == '__main__':
    main()

