from __future__ import annotations
from dataclasses import *
from typing import *

from .runtime import Runtime
from .log import CommandWithMetadata

def execute(
    runtime: Runtime,
    entry: CommandWithMetadata,
    action: Literal['put', 'get', 'get_status', 'reset_and_activate'],
    incu_loc: str | None,
):
    '''
    Run the incubator.
    '''
    for incu in runtime.time_resource_use(entry, runtime.incu):
        try:
            if action == 'put':
                assert incu_loc is not None
                incu.put(incu_loc)
            elif action == 'get':
                assert incu_loc is not None
                incu.get(incu_loc)
            elif action == 'get_status':
                assert incu_loc is None
                incu.get_status()
            elif action == 'reset_and_activate':
                assert incu_loc is None
                incu.reset_and_activate()
            else:
                raise ValueError(f'Incubator {action=} not supported')
        except BaseException as e:
            machine = 'incu'
            runtime.log(entry.message(f'{machine}: {e}', is_error=True))
            raise
