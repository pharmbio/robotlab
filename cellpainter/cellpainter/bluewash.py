from __future__ import annotations
from dataclasses import *
from typing import *

from .runtime import Runtime

from .log import CommandWithMetadata, Metadata
from .commands import BlueWashAction

def execute(
    runtime: Runtime,
    entry: CommandWithMetadata,
    action: BlueWashAction,
    protocol_path: str | None,
):
    bluewash = runtime.blue
    if bluewash is None:
        est = entry.metadata.est
        assert isinstance(est, float)
        runtime.sleep(est, entry.merge(Metadata(dry_run_sleep=True)))
        res: list[str] = []
    else:
        match action:
            case 'write_prog':
                assert isinstance(protocol_path, str)
            case _:
                assert not isinstance(protocol_path, str)
        match action:
            case 'write_prog':
                assert isinstance(protocol_path, str)
                res = bluewash.write_prog(*protocol_path.split('/'))
            case 'run_prog':          res = bluewash.run_prog()
            case 'init_all':          res = bluewash.init_all()
            case 'get_balance_plate': res = bluewash.get_balance_plate()
            case 'get_working_plate': res = bluewash.get_working_plate()
            case 'get_info':          res = bluewash.get_info()
    res # bluewash raises error if error, otherwise everything OK
