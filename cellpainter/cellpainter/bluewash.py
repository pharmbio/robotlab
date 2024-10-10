from __future__ import annotations
from dataclasses import *
from typing import *

from .runtime import Runtime

from .log import CommandWithMetadata
from .commands import BlueWashAction

def execute(
    runtime: Runtime,
    entry: CommandWithMetadata,
    action: BlueWashAction,
    protocol_path: str | None,
):
    for blue in runtime.time_resource_use(entry, runtime.blue):
        match action:
            case 'Run':
                assert isinstance(protocol_path, str)
                res = blue.Run(*protocol_path.split('/'))
            case 'TestCommunications':
                assert protocol_path is None
                res = blue.TestCommunications()
            case 'reset_and_activate':
                res = blue.init_all()
            case 'get_working_plate':
                res = blue.get_working_plate()
            case _: # type: ignore
                raise ValueError(f'No such bluewash {action=}')

        res # bluewash raises error if error, otherwise everything OK
