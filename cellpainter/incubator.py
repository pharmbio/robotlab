from __future__ import annotations
from dataclasses import *
from typing import *

from .runtime import Runtime
from .log import Metadata, LogEntry, Error
from .utils import curl

def execute(
    runtime: Runtime,
    entry: LogEntry,
    action: Literal['put', 'get', 'get_status', 'reset_and_activate'],
    incu_loc: str | None,
):
    '''
    Run the incubator.

    Success looks like this:

        {
          "lines": [
            "success"
          ],
          "success": True
        }

    Failure looks like this:

        {
          "lines": [
            "error not ready"
          ],
          "success": False
        }
    '''
    assert action in {'put', 'get', 'get_status', 'reset_and_activate'}
    if runtime.config.incu_mode == 'noop':
        est = entry.metadata.est
        assert isinstance(est, float)
        runtime.sleep(est, entry.add(Metadata(dry_run_sleep=True)))
        res: Any = {"success":True,"lines":[]}
    else:
        assert runtime.config.incu_mode == 'execute'
        if action == 'put':
            assert incu_loc is not None
            action_path = 'put/' + incu_loc
        elif action == 'get':
            assert incu_loc is not None
            action_path = 'get/' + incu_loc
        elif action == 'get_status':
            assert incu_loc is None
            action_path = 'get_status'
        elif action == 'reset_and_activate':
            assert incu_loc is None
            action_path = 'reset_and_activate'
        else:
            raise ValueError
        url = runtime.env.incu_url + '/' + action_path
        res = curl(url)
    success: bool = res.get('success', False)
    lines: list[str] = res.get('lines', [])
    if success:
        return
    else:
        machine = 'incu'
        for line in lines or ['']:
            runtime.log(entry.add(err=Error(f'{machine}: {line}')))
        raise ValueError(res)
