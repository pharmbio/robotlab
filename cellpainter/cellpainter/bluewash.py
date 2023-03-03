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
            case 'Run':
                assert isinstance(protocol_path, str)
                res = bluewash.Run(*protocol_path.split('/'))
            case 'Validate':
                assert isinstance(protocol_path, str)
                res = bluewash.Validate(*protocol_path.split('/'))
            case 'RunValidated':
                assert isinstance(protocol_path, str)
                res = bluewash.RunValidated(*protocol_path.split('/'))
            case 'TestCommunications':
                assert protocol_path is None
                res = bluewash.TestCommunications()
            case 'reset_and_activate':
                res = bluewash.init_all()
            case 'get_working_plate':
                res = bluewash.get_working_plate()
            case _: # type: ignore
                raise ValueError(f'No such bluewash {action=}')

    res # bluewash raises error if error, otherwise everything OK
