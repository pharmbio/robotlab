from __future__ import annotations
from dataclasses import *
from typing import *

from runtime import Runtime, curl
import timings
import time

def is_endpoint_ready(runtime: Runtime):
    res = curl(runtime.env.incu_url + '/is_ready')
    assert res['status'] == 'OK', res
    return res['value'] is True

def execute(
    runtime: Runtime,
    action: Literal['put', 'get', 'get_climate'],
    incu_loc: str | None,
    metadata: dict[str, Any] = {},
):
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
        elif runtime.config.incu_mode == 'execute':
            if action == 'put':
                assert incu_loc is not None
                action_path = 'input_plate/' + incu_loc
            elif action == 'get':
                assert incu_loc is not None
                action_path = 'output_plate/' + incu_loc
            elif action == 'get_climate':
                assert incu_loc is None
                action_path = 'getClimate'
            else:
                raise ValueError
            url = runtime.env.incu_url + '/' + action_path
            res = curl(url)
            assert res['status'] == 'OK', res
            while not is_endpoint_ready(runtime):
                time.sleep(0.05)
        else:
            raise ValueError

