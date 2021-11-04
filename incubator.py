from __future__ import annotations
from dataclasses import *
from typing import *

from runtime import Runtime, curl
import timings

def execute(
    runtime: Runtime,
    action: Literal['put', 'get', 'get_climate'],
    incu_loc: str | None,
    metadata: dict[str, Any] = {},
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
    if incu_loc is not None:
        metadata = {**metadata, 'incu_loc': incu_loc}
        arg = action # + ' ' + incu_loc
    else:
        arg = action
    with runtime.timeit('incu', arg, metadata):
        assert action in {'put', 'get', 'get_climate'}
        if runtime.config.incu_mode == 'noop':
            est = timings.estimate('incu', arg)
            runtime.sleep(est, {**metadata, 'silent': True})
            res: Any = {"success":True,"lines":[]}
        else:
            assert runtime.config.incu_mode == 'execute'
            if action == 'put':
                assert incu_loc is not None
                action_path = 'put/' + incu_loc
            elif action == 'get':
                assert incu_loc is not None
                action_path = 'get/' + incu_loc
            elif action == 'get_climate':
                assert incu_loc is None
                action_path = 'get_climate'
            else:
                raise ValueError
            url = runtime.env.incu_url + '/' + action_path
            res = curl(url)
        success: bool = res.get('success', False)
        lines: list[str] = res.get('lines', [])
        if success:
            return
        else:
            for line in lines:
                runtime.log('error', 'incu', line)
            raise ValueError(res)
