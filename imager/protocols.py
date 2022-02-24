from __future__ import annotations
from typing import Any, cast, Callable
from dataclasses import dataclass
from datetime import timedelta

from .moves import HotelLocs

from .scheduler import (
    Command,           # type: ignore
    RobotarmCmd,       # type: ignore
    Acquire,           # type: ignore
    Open,              # type: ignore
    Close,             # type: ignore
    WaitForIMX,        # type: ignore
    FridgeCmd,         # type: ignore
    BarcodeClear,      # type: ignore
    Checkpoint,        # type: ignore
    WaitForCheckpoint, # type: ignore
    Noop,              # type: ignore
)

from . import utils

list_of_protocols: list[Callable[..., list[Command]]] = []

@list_of_protocols.append
def load_by_barcode(num_plates: int, **_):
    '''
    Loads the plates from H1, H2 to H# to empty locations in the fridge
    '''
    cmds: list[Command] = []
    for hotel_loc in reversed(HotelLocs[:num_plates]):
        cmds += [
            RobotarmCmd(f'H{hotel_loc} to H12') if hotel_loc != 'H12' else Noop(),
            RobotarmCmd('H12 to fridge'),
            FridgeCmd('put_by_barcode'),
        ]
    return cmds

@list_of_protocols.append
def unload_by_barcode(params: list[str], **_):
    '''
    Unloads plates with the given barcodes to the hotel, locations: H1, H2 to H# to empty locations in the fridge
    '''
    cmds: list[Command] = []
    barcodes = params
    for hotel_loc, barcode in zip(HotelLocs, barcodes):
        cmds += [
            FridgeCmd('get_by_barcode', barcode=barcode),
            RobotarmCmd('fridge to H12'),
            RobotarmCmd(f'H12 to H{hotel_loc}') if hotel_loc != 'H12' else Noop(),
        ]
    return cmds

@list_of_protocols.append
def image(params: list[str], hts_file: str, thaw_time: timedelta, **_):
    '''
    Images the plates with the given barcodes. These should already be in the fridge.
    '''
    cmds: list[Command] = []
    barcodes = params
    for i, barcode in enumerate(barcodes):
        cmds += [
            FridgeCmd('get_by_barcode', barcode=barcode),
            RobotarmCmd('fridge to H12'),
            Checkpoint(f'RT {i}'),
        ]
        cmds += [
            WaitForCheckpoint(f'RT {i}', plus_secs=thaw_time),
            RobotarmCmd('H12 to imx', keep_imx_open=True),
            Close(),
            Checkpoint(f'image-begin {barcode}'),
            Acquire(hts_file=hts_file, plate_id=barcode),
        ]
        cmds += [
            WaitForIMX(),
            Checkpoint(f'image-end {barcode}'),
            RobotarmCmd('imx to H12', keep_imx_open=True),
            Close(),
            RobotarmCmd('H12 to fridge'),
            FridgeCmd('put_by_barcode'), # could check that it still has the same barcode
        ]
    return cmds

'''
This is a possible way to interleave it, but let's do that later:

fridge -> RT
          RT -> imx
fridge -> RT
                imx -> fridge
          RT -> imx
fridge -> RT
                imx -> fridge
          RT -> imx
                imx -> fridge

This assumes time to image is less than thaw time.
If image time is much less than thaw time, several plates need to be in RT simultaneously.
'''

@list_of_protocols.append
def test_comm(**_):
    cmds: list[Command] = []
    cmds += [
        RobotarmCmd('test-comm'),
        BarcodeClear(),
        WaitForIMX(),
        FridgeCmd('get_status'),
    ]
    return cmds

@list_of_protocols.append
def home_robot(**_):
    cmds: list[Command] = []
    cmds += [
        RobotarmCmd('home'),
    ]
    return cmds

@dataclass(frozen=True)
class ProtocolData:
    name: str
    make: Callable[..., list[Command]]
    doc: str

protocols_dict = {
    p.__name__: ProtocolData(p.__name__, p, utils.doc_header(p))
    for p in list_of_protocols
}
