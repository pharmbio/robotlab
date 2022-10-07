from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Any, cast, ClassVar, TypeAlias, Union, Iterator

import pbutils
from .moves import movelists

@dataclass(frozen=True)
class RobotarmCmd:
    '''
    Run a program on the robotarm.
    '''
    program_name: str
    keep_imx_open: bool = False

    def __post_init__(self):
        assert self.program_name in movelists, self.program_name

@dataclass(frozen=True)
class Noop:
    '''
    Do nothing.
    '''
    pass

@dataclass(frozen=True)
class Pause:
    '''
    Pause execution.
    '''
    pass

@dataclass(frozen=True)
class Acquire:
    '''
    Acquires the plate on the IMX (closing it first if necessary).
    '''
    hts_file: str
    plate_id: str

@dataclass(frozen=True)
class Open:
    '''
    Open the IMX.
    '''
    pass

@dataclass(frozen=True)
class Close:
    '''
    Closes the IMX.
    '''
    pass

@dataclass(frozen=True)
class WaitForIMX:
    '''
    Wait for IMX to finish imaging
    '''
    pass

@dataclass(frozen=True)
class FridgeGet:
    loc: str
    check_barcode: bool = False

@dataclass(frozen=True)
class FridgePut:
    loc: str
    project: str
    barcode: str

@dataclass(frozen=True)
class FridgePutByBarcode:
    '''
    Puts the plate on some empty location using its barcode
    '''
    project: str
    check_barcode: str | None = None

@dataclass(frozen=True)
class FridgeGetByBarcode:
    project: str
    barcode: str

@dataclass(frozen=True)
class FridgeAction:
    action: Literal['get_status', 'reset_and_activate']

@dataclass(frozen=True)
class BarcodeClear:
    '''
    Clears the last seen barcode from the barcode reader memory
    '''
    pass

@dataclass(frozen=True)
class CheckpointCmd:
    name: str

@dataclass(frozen=True)
class WaitForCheckpoint:
    name: str
    plus_secs: timedelta | float | int = 0

    @property
    def plus_timedelta(self) -> timedelta:
        if isinstance(self.plus_secs, timedelta):
            return self.plus_secs
        else:
            return timedelta(seconds=self.plus_secs)

Command: TypeAlias = Union[
    Noop,
    Pause,
    RobotarmCmd,
    Acquire,
    Open,
    Close,
    WaitForIMX,
    FridgeGet,
    FridgePut,
    FridgePutByBarcode,
    FridgeGetByBarcode,
    FridgeAction,
    BarcodeClear,
    CheckpointCmd,
    WaitForCheckpoint,
]

pbutils.serializer.register(globals())
