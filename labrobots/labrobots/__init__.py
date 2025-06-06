from .machines import Machines
from .liconic import STX, Fridge
from .barcode_reader import BarcodeReader
from .dir_list import DirList
from .biotek import Biotek
from .squid import Squid
from .bluewash import BlueWash
from .nikon_nis import NikonNIS
from .nikon_stage import NikonStage
from .labeler import Labeler
from .dlid import DLid

from dataclasses import *

LHC_CALLER_CLI_PATH = "C:\\Program Files (x86)\\BioTek\\Liquid Handling Control 2.22\\LHC_CallerCLI.exe"
LHC_PROTOCOLS_ROOT = "C:\\ProgramData\\BioTek\\Liquid Handling Control 2.22\\Protocols\\"
HTS_PROTOCOLS_ROOT = "C:\\Users\\MolDev\\Desktop\\Protocols\\Plate protocols\\384-Well_Plate_Protocols\\"

@dataclass
class WindowsNUC(Machines):
    ip = '10.10.0.56'
    node_name = 'WINDOWS-NUC'
    incu: STX = STX()
    wash: Biotek = Biotek(name='wash', args=[LHC_CALLER_CLI_PATH, "405 TS/LS", "COM4", LHC_PROTOCOLS_ROOT])
    disp: Biotek = Biotek(name='disp', args=[LHC_CALLER_CLI_PATH, "MultiFloFX", "COM3", LHC_PROTOCOLS_ROOT])
    dir_list: DirList = DirList(root_dir=LHC_PROTOCOLS_ROOT, ext=['LHC', 'prog'])
    blue: BlueWash = BlueWash(root_dir=LHC_PROTOCOLS_ROOT, com_port='COM6')
    dlid: DLid = DLid(com_port='COM8')

@dataclass
class WindowsGBG(Machines):
    ip = '10.10.0.97'
    node_name = 'WINDOWS-GBG'
    fridge: Fridge = Fridge()
    barcode: BarcodeReader = BarcodeReader(com_port='COM3')
    # imx: IMX = IMX()

@dataclass
class WindowsIMX(Machines):
    ip = '127.0.0.1'
    node_name = 'ImageXpress'
    dir_list: DirList = DirList(root_dir=HTS_PROTOCOLS_ROOT, ext='HTS', enable_hts_mod=True)

@dataclass
class Example(Machines):
    ip = '127.0.0.1'
    node_name = 'example'
    dir_list: DirList = DirList(root_dir='.', ext=['py', 'md'], enable_hts_mod=True)

@dataclass
class MikroAsus(Machines):
    ip = '10.10.0.95'
    node_name = 'mikro-asus'
    skip_up_check = True
    squid: Squid = Squid()

@dataclass
class Nikon(Machines):
    ip = '10.10.0.72'
    node_name = 'NIKON-72'
    nikon: NikonNIS = NikonNIS()

@dataclass
class NikonPi(Machines):
    ip = '10.10.0.76'
    node_name = 'nikonpi'
    nikon_stage: NikonStage = NikonStage()

@dataclass
class LabelerComputer(Machines):
    ip = '10.10.0.74'
    node_name = 'DESKTOP-C3JFE20'
    labeler: Labeler = Labeler(['C:\\Users\\admin\\PlateRepl.exe'])

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
    if args.test:
        node_name = 'example'
    print('node_name:', node_name)

    machines = Machines.lookup_node_name(node_name)
    machines.serve(port=args.port, host=machines.ip if args.host == 'default' else args.host)

if __name__ == '__main__':
    main()
