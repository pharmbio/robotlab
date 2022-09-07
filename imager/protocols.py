from __future__ import annotations
from typing import Any, cast, Callable
from dataclasses import dataclass

from .moves import HotelLocs

from .commands import (
    Command,
    RobotarmCmd,
    Acquire,
    Open,
    Close,
    WaitForIMX,
    FridgeGet,
    FridgePut,
    FridgeGetByBarcode,
    FridgePutByBarcode,
    FridgeAction,
    BarcodeClear,
    CheckpointCmd,
    WaitForCheckpoint,
    Noop,
)

from . import utils

list_of_protocols: list[Callable[..., list[Command]]] = []

@list_of_protocols.append
def image_plate_in_imx(params: list[str], hts_file: str, **_):
    assert isinstance(params, list) and len(params) == 1, 'provide one plate name'
    assert hts_file and isinstance(hts_file, str), 'specify a --hts-file'
    [plate_id] = params
    cmds: list[Command] = [
        CheckpointCmd(f'image-begin {plate_id}'),
        Acquire(hts_file=hts_file, plate_id=plate_id),
        WaitForIMX(),
        CheckpointCmd(f'image-end {plate_id}'),
    ]
    return cmds

@dataclass(frozen=True)
class Todo:
    hotel_loc: str  # 'H1'
    plate_id: str
    hts_path: str   # full path

def image_todos_from_hotel(todos: list[Todo], thaw_secs: float) -> list[Command]:
    cmds: list[Command] = []
    cmds += [
        CheckpointCmd(f'initial delay'),
        WaitForCheckpoint(f'initial delay', plus_secs=thaw_secs),
    ]
    for todo in todos:
        assert todo.hotel_loc != 'H12'
        assert todo.hotel_loc in HotelLocs
        cmds += [
            RobotarmCmd(f'{todo.hotel_loc}-to-H12'),
            Open(),
            RobotarmCmd('H12-to-imx', keep_imx_open=True),
            Close(),
            CheckpointCmd(f'image-begin {todo.plate_id}'),
            Acquire(hts_file=todo.hts_path, plate_id=todo.plate_id),
            WaitForIMX(),
            CheckpointCmd(f'image-end {todo.plate_id}'),
            Open(),
            RobotarmCmd('imx-to-H12', keep_imx_open=True),
            Close(),
            RobotarmCmd(f'H12-to-{todo.hotel_loc}'),
        ]
    return cmds

@list_of_protocols.append
def image_from_hotel(params: list[str], hts_file: str, thaw_secs: float, **_):
    assert params and isinstance(params, list), 'specify some plate names'
    assert hts_file and isinstance(hts_file, str), 'specify a --hts-file'
    return image_todos_from_hotel(
        [
            Todo(hotel_loc, plate_id, hts_file)
            for hotel_loc, plate_id in zip(HotelLocs, params)
        ],
        thaw_secs=thaw_secs,
    )

@list_of_protocols.append
def test_comm(**_):
    cmds: list[Command] = []
    cmds += [
        RobotarmCmd('test-comm'),
        BarcodeClear(),
        WaitForIMX(),
        # FridgeCmd('get_status'),
    ]
    return cmds

@list_of_protocols.append
def home_robot(**_):
    cmds: list[Command] = []
    cmds += [
        RobotarmCmd('home'),
    ]
    return cmds

@list_of_protocols.append
def test_image_one(params: list[str], hts_file: str, **_):
    '''
    Image one plate from H12, specify its barcode
    '''
    assert params and isinstance(params, list), 'specify one barcode'
    assert hts_file and isinstance(hts_file, str), 'specify a --hts-file'
    [barcode] = params
    cmds: list[Command] = []
    cmds += [
        Open(),
        RobotarmCmd('H12-to-imx', keep_imx_open=True),
        Close(),
        CheckpointCmd(f'image-begin {barcode}'),
        Acquire(hts_file=hts_file, plate_id=barcode),
    ]
    cmds += [
        WaitForIMX(),
        CheckpointCmd(f'image-end {barcode}'),
        Open(),
        RobotarmCmd('imx-to-H12', keep_imx_open=True),
        Close(),
    ]
    return cmds


@list_of_protocols.append
def load_by_barcode(num_plates: int, **_):
    '''
    Loads the plates from H1, H2 to H# to empty locations in the fridge
    '''
    assert num_plates and isinstance(num_plates, int), 'specify --num-plates'
    cmds: list[Command] = []
    for hotel_loc in reversed(HotelLocs[:num_plates]):
        cmds += [
            RobotarmCmd(f'{hotel_loc}-to-H12') if hotel_loc != 'H12' else Noop(),
            RobotarmCmd('H12-to-fridge'),
            FridgePutByBarcode(),
        ]
    return cmds

@list_of_protocols.append
def unload_by_barcode(params: list[str], **_):
    '''
    Unloads plates with the given barcodes to the hotel, locations: H1, H2 to H# to empty locations in the fridge
    '''
    assert params and isinstance(params, list), 'specify some barcodes'
    cmds: list[Command] = []
    barcodes = params
    for hotel_loc, barcode in zip(HotelLocs, barcodes):
        cmds += [
            FridgeGetByBarcode(barcode=barcode),
            RobotarmCmd('fridge-to-H12'),
            RobotarmCmd(f'H12-to-{hotel_loc}') if hotel_loc != 'H12' else Noop(),
        ]
    return cmds

@list_of_protocols.append
def image(params: list[str], hts_file: str, thaw_secs: float | int, **_):
    '''
    Images the plates with the given barcodes. These should already be in the fridge.
    '''
    assert params and isinstance(params, list), 'specify some barcodes'
    assert hts_file and isinstance(hts_file, str), 'specify a --hts-file'
    assert thaw_secs and isinstance(thaw_secs, float | int), 'specify a --thaw-secs in seconds'
    cmds: list[Command] = []
    barcodes = params
    for i, barcode in enumerate(barcodes):
        cmds += [
            FridgeGetByBarcode(barcode=barcode),
            RobotarmCmd('fridge-to-H12'),
            CheckpointCmd(f'RT {i}'),
        ]
        cmds += [
            WaitForCheckpoint(f'RT {i}', plus_secs=thaw_secs),
            Open(),
            RobotarmCmd('H12-to-imx', keep_imx_open=True),
            Close(),
            CheckpointCmd(f'image-begin {barcode}'),
            Acquire(hts_file=hts_file, plate_id=barcode),
        ]
        cmds += [
            WaitForIMX(),
            CheckpointCmd(f'image-end {barcode}'),
            Open(),
            RobotarmCmd('imx-to-H12', keep_imx_open=True),
            Close(),
            RobotarmCmd('H12-to-fridge'),
            FridgePutByBarcode(), # could check that it still has the same barcode
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

# @list_of_protocols.append
def reset_and_activate_fridge(**_):
    cmds: list[Command] = []
    cmds += [
        FridgeAction('reset_and_activate'),
    ]
    return cmds


from .moves import movelists

@list_of_protocols.append
def run_robotarm(params: list[str], **_):
    nl = '\n'
    assert params, f'No params, pick from:{nl}{nl.join(movelists.keys())}'
    for p in params:
        assert p in movelists, f'Not available: {p}, pick from:{nl}{nl.join(movelists.keys())}'
    cmds: list[Command] = []
    cmds += [
        c
        for p in params
        for c in (
            [Open(), RobotarmCmd(p, keep_imx_open=True)]
            if 'imx' in p.lower() else
            [RobotarmCmd(p)]
        )
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
