from .machine import Machine, Echo, Machines
from .liconic import STX
from .barcode_reader import BarcodeReader
from .imx import IMX
from .dir_list import DirList
from .repl_wrap import ReplWrap

from dataclasses import dataclass

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
LHC_PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols\\"
HTS_PROTOCOLS_ROOT = "C:\\Users\\MolDev\\Desktop\\Protocols\\Plate protocols\\384-Well_Plate_Protocols\\"

@dataclass(frozen=True)
class WindowsNUC(Machines):
    incu: STX = STX()
    wash: ReplWrap = ReplWrap('wash', [LHC_CALLER_CLI_PATH, "405 TS/LS", "USB 405 TS/LS sn:191107F", LHC_PROTOCOLS_ROOT])
    disp: ReplWrap = ReplWrap('disp', [LHC_CALLER_CLI_PATH, "MultiFloFX", "USB MultiFloFX sn:19041612", LHC_PROTOCOLS_ROOT])
    dir_list: DirList = DirList(root_dir=LHC_PROTOCOLS_ROOT, ext='LHC')

@dataclass(frozen=True)
class WindowsGBG(Machines):
    fridge: STX = STX()
    barcode: BarcodeReader = BarcodeReader()
    imx: IMX = IMX()

@dataclass(frozen=True)
class WindowsIMX(Machines):
    dir_list = DirList(root_dir=HTS_PROTOCOLS_ROOT, ext='HTS', enable_hts_mod=True)

@dataclass(frozen=True)
class Example(Machines):
    dir_list: DirList = DirList(root_dir='.', ext='py', enable_hts_mod=True)

def main():
    import sys
    import platform
    from argparse import ArgumentParser

    parser = ArgumentParser('labrobots_server')
    parser.add_argument('--port', type=int, default=5050)
    parser.add_argument('--host', type=str, default='default')
    parser.add_argument('--test', action='store_true', default=False)
    parser.add_argument('--node-name', type=str, default=platform.node())
    args = parser.parse_args(sys.argv[1:])
    node_name = args.node_name
    print('node_name:', node_name)
    host = args.host
    if args.test:
        node_name = 'test'

    machines: Machines
    if node_name == 'test':
        machines = Example()
    elif node_name == 'WINDOWS-NUC':
        machines = WindowsNUC()
    elif node_name == 'WINDOWS-GBG':
        machines = WindowsGBG()
    elif node_name == 'ImageXpress':
        machines = WindowsIMX()
    else:
        raise ValueError(f'{node_name} not configured (did you want to run with --test?)')

    LOCAL_IP = {
        'WINDOWS-NUC': '10.10.0.56', # connected to the bioteks and 37C incubator
        'WINDOWS-GBG': '10.10.0.97', # connected to the fridge incubator in imx room
        'ImageXpress': '10.10.0.99', # connected to the imx
    }

    if host == 'default':
        host = LOCAL_IP.get(node_name, 'localhost')

    machines.serve(port=args.port, host=host)

if __name__ == '__main__':
    main()
