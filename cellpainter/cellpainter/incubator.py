from __future__ import annotations
from dataclasses import *
from typing import *

from .runtime import Runtime
from .log import Metadata, CommandWithMetadata

def execute(
    runtime: Runtime,
    entry: CommandWithMetadata,
    action: Literal['put', 'get', 'get_status', 'reset_and_activate'],
    incu_loc: str | None,
):
    '''
    Run the incubator.
    '''
    if runtime.incu is None:
        est = entry.metadata.est
        assert isinstance(est, float)
        runtime.sleep(est)
    else:
        try:
            if action == 'put':
                assert incu_loc is not None
                runtime.incu.put(incu_loc)
            elif action == 'get':
                assert incu_loc is not None
                runtime.incu.get(incu_loc)
            elif action == 'get_status':
                assert incu_loc is None
                runtime.incu.get_status()
            elif action == 'reset_and_activate':
                assert incu_loc is None
                runtime.incu.reset_and_activate()
            else:
                raise ValueError('Incubator {action=} not supported')
        except BaseException as e:
            machine = 'incu'
            runtime.log(entry.message(f'{machine}: {e}', is_error=True))
            raise
