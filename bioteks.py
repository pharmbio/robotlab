from __future__ import annotations
from dataclasses import *
from typing import *

from runtime import Runtime, RuntimeConfig, curl
import timings

def execute(
    runtime: Runtime,
    machine: Literal['wash', 'disp'],
    protocol_path: str | None,
    sub_cmd: Literal['LHC_RunProtocol', 'LHC_TestCommunications'] = 'LHC_RunProtocol',
    metadata: dict[str, Any] = {},
):
    '''
    Repeatedly try to run the protocol until it succeeds or we get an unknown error.

    Success looks like this:

        {"err":"","out":{"details":"1 - eOK","status":"1","value":""}}

        {"err":"","out":{"details": "1 - eReady - the run completed
        successfully: stop polling for status", "status":"1", "value":""}}

    Acceptable failure looks like this:

        {"err":"","out":{"details":"Message - Exception calling cLHC method:
            LHC_TestCommunications, ErrorCode: 24673, ErrorString:
            Error code: 6061rnPort is no longer available - ...",
        "status":"99","value":"EXCEPTION"}}

    '''
    log_arg = protocol_path or sub_cmd
    with runtime.timeit(machine, log_arg, metadata=metadata):
        while True:
            if runtime.config.disp_and_wash_mode == 'noop':
                est = timings.estimate(machine, log_arg)
                runtime.log('info', machine, f'pretending to run for {round(est, 2)}s', metadata)
                runtime.sleep(est)
                res: Any = {"err":"","out":{"details":"1 - eOK","status":"1","value":""}}
            else:
                url = (
                    runtime.env.biotek_url +
                    '/' + machine +
                    '/' + sub_cmd +
                    '/' + (protocol_path or '')
                )
                url = url.rstrip('/')
                res: Any = curl(url)
            out = res['out']
            status = out['status']
            details = out['details']
            if status == '99' and 'Error code: 6061' in details and 'Port is no longer available' in details:
                runtime.log('warn', machine, 'got error code 6061, retrying...', {**metadata, **res})
                continue
            elif status == '1' and ('eOK' in details or 'eReady' in details):
                break
            else:
                raise ValueError(res)
