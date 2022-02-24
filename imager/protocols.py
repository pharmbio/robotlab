from __future__ import annotations
from typing import Any, cast
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

def load_by_barcode(num_plates: int):
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

def unload_by_barcode(barcodes: list[str]):
    '''
    Unloads plates with the given barcodes to the hotel, locations: H1, H2 to H# to empty locations in the fridge
    '''
    cmds: list[Command] = []
    for hotel_loc, barcode in zip(HotelLocs, barcodes):
        cmds += [
            FridgeCmd('get_by_barcode', barcode=barcode),
            RobotarmCmd('fridge to H12'),
            RobotarmCmd(f'H12 to H{hotel_loc}') if hotel_loc != 'H12' else Noop(),
        ]
    return cmds

def image(barcodes: list[str], hts_file: str, thaw_time: timedelta):
    '''
    Images the plates with the given barcodes. These should already be in the fridge.
    '''
    cmds: list[Command] = []
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

def test_comm():
    cmds: list[Command] = []
    cmds += [
        RobotarmCmd('test-comm'),
        BarcodeClear(),
        WaitForIMX(),
        FridgeCmd('get_status'),
    ]
    return cmds

def home_robot():
    cmds: list[Command] = []
    cmds += [
        RobotarmCmd('home'),
    ]
    return cmds
